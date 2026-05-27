"""Engine do Fluxo de Caixa: pega rawOracle/{ano-mes}__fluxo_*, classifica,
junta com lançamentosManuaisFluxo + saldosBancarios e produz:
    fluxoCaixa/{ano-mes} no formato compacto consumido pela UI.

Sem rateio (usuário decisão: DFC não usa rateio).

Formato do doc gerado (semelhante ao meses/{ano-mes} do DRE):
{
  ano: 2026, mes: 5, v: 1,
  dim: { dias: ["01","02",...], grupos:[...], agrupamentos:[...], linhas:[...] },
  porGrupo:       [{d, g, v}],
  porAgrupamento: [{d, a, v}],
  porLinha:       [{d, g, a, n, v}],
  saldoInicial: 12345.67,
  saldoFinalDiario: [{d, v}],   # acumulado dia a dia
}
"""
from __future__ import annotations
import datetime as dt
import re
from collections import defaultdict
from firebase_admin import firestore

import classifier_fluxo


def _carregar_raw_fluxo(db, ano: int, mes: int) -> dict[str, list]:
    """Lê rawOracle/{ano-mes}__fluxo_pago, ..._juros, ..._opfin, ..._transitorias.
    Quando chunked, lê chunk a chunk por índice (totalChunks) — evita o
    .stream() do gRPC que tem incompatibilidade com Python 3.14
    (_UnaryStreamMultiCallable._retry).
    """
    chave = f"{ano:04d}-{mes:02d}"
    out = {}
    for slug in ["fluxo_pago", "fluxo_juros", "fluxo_opfin", "fluxo_transitorias"]:
        doc_id = f"{chave}__{slug}"
        snap = db.collection("rawOracle").document(doc_id).get()
        if not snap.exists:
            out[slug] = []
            continue
        data = snap.to_dict() or {}
        rows = data.get("rows", [])
        if data.get("chunked"):
            rows = []
            n_total = int(data.get("totalChunks") or 0)
            chunks_ref = db.collection("rawOracle").document(doc_id).collection("chunks")
            for n in range(n_total):
                cs = chunks_ref.document(str(n)).get()
                if cs.exists:
                    rows.extend((cs.to_dict() or {}).get("rows", []))
            print(f"   {slug}: lidos {n_total} chunk(s) → {len(rows)} linhas")
        out[slug] = rows
    return out


def _carregar_lancamentos_fluxo(db, ano: int, mes: int) -> list[dict]:
    """Lê lancamentosManuaisFluxo/ filtrando por mes (YYYY-MM)."""
    chave = f"{ano:04d}-{mes:02d}"
    out = []
    for d in db.collection("lancamentosManuaisFluxo").stream():
        data = d.to_dict() or {}
        if data.get("mes") != chave:
            continue
        # Manuais podem ter data específica do dia OU só o mês — assume dia 1 se só mês
        data_dia = data.get("data") or f"{chave}-01"
        out.append({
            "data": data_dia,
            "nroempresa": data.get("nroempresa"),
            "banco": data.get("banco"),
            "linha": data.get("linha", ""),
            "valor": float(data.get("valor", 0) or 0),
            "_fonte": "manualFluxo",
        })
    return out


def _saldo_final_mes_anterior(db, ano: int, mes: int, sufixo: str = "") -> float | None:
    """Saldo Final acumulado do último dia do mês anterior, lido de
    fluxoCaixa/{ano-mes-1}{sufixo}. Retorna None se o doc não existir."""
    if mes == 1:
        ant_ano, ant_mes = ano - 1, 12
    else:
        ant_ano, ant_mes = ano, mes - 1
    chave = f"{ant_ano:04d}-{ant_mes:02d}{sufixo}"
    snap = db.collection("fluxoCaixa").document(chave).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    sfd = d.get("saldoFinalDiario") or []
    if sfd:
        return float(sfd[-1].get("v", 0) or 0)
    # Sem dias gravados → saldo do mês anterior == saldoInicial dele
    return float(d.get("saldoInicial", 0) or 0)


def _carregar_saldo_inicial(db, ano: int, mes: int) -> tuple[float, list[dict]]:
    """Lê saldosBancarios/{ano-mes} → (total, [{banco, valor}]).

    Fallback: se o cadastro não existir (ou estiver vazio), deriva o saldo
    inicial do Saldo Final do mês anterior (fluxoCaixa/{prev}). Isso permite
    que o user cadastre saldosBancarios em UM mês âncora (ex: Abr/2026) e
    todos os meses seguintes herdem automaticamente sem novo cadastro."""
    chave = f"{ano:04d}-{mes:02d}"
    snap = db.collection("saldosBancarios").document(chave).get()
    if snap.exists:
        saldos = (snap.to_dict() or {}).get("saldos", [])
        if saldos:
            total = sum(float(s.get("valor", 0) or 0) for s in saldos)
            return total, saldos
    # Fallback: saldo final do mês anterior
    prev = _saldo_final_mes_anterior(db, ano, mes, sufixo="")
    if prev is not None:
        print(f"   ↪ saldosBancarios/{chave} sem cadastro → herda saldo final de {ano:04d}-{mes-1 if mes>1 else 12:02d}: R$ {prev:,.2f}")
        return prev, []
    return 0.0, []


# Bancos do saldosBancarios vêm com prefixo "LJ##" no nome (ex: "LJ01 SANTANDER
# - APLICAÇÃO - 302", "LJ101 ..."). O número é o NROEMPRESA → converte pra
# loja descrição via meta/lojas.
_LJ_PREFIX_RE = re.compile(r"^LJ\s*(\d+)\b", re.IGNORECASE)


def _quebrar_saldo_por_loja(saldos: list[dict],
                             nro_para_loja: dict[int, str]) -> tuple[dict[str, float], float]:
    """Soma os valores de `saldos` por loja descricao (ex: 'L01').
    Retorna ({loja_desc: total}, sem_loja_total). Bancos cujo prefixo LJ##
    não casa com nenhum NROEMPRESA cadastrado caem em sem_loja_total
    (ainda contam no consolidado, só não aparecem no doc da loja)."""
    por_loja: dict[str, float] = {}
    sem_loja = 0.0
    for s in saldos:
        valor = float(s.get("valor", 0) or 0)
        nome = str(s.get("banco", "") or "")
        m = _LJ_PREFIX_RE.match(nome.strip())
        if not m:
            sem_loja += valor
            continue
        try:
            nro = int(m.group(1))
        except ValueError:
            sem_loja += valor
            continue
        desc = nro_para_loja.get(nro)
        if not desc:
            sem_loja += valor
            continue
        por_loja[desc] = por_loja.get(desc, 0.0) + valor
    return por_loja, sem_loja


def _carregar_dimensoes_fluxo(db) -> dict:
    """Lê meta/gruposFluxo + meta/agrupamentosFluxo + meta/linhasFluxo."""
    out = {
        "linha_para_grupo": {},      # linha → (grupo, agrupamento)
        "agrupamento_para_grupo": {},
        "grupos_ordenados": [],
        "agrupamentos_ordenados": [],
        "linhas_ordenadas": [],
    }
    snap = db.collection("meta").document("gruposFluxo").get()
    if snap.exists:
        items = sorted((snap.to_dict() or {}).get("items", []),
                       key=lambda x: x.get("ordem", 9999))
        out["grupos_ordenados"] = [it["nome"] for it in items if it.get("nome")]
    snap = db.collection("meta").document("agrupamentosFluxo").get()
    if snap.exists:
        for it in (snap.to_dict() or {}).get("items", []):
            n, g = it.get("nome", ""), it.get("grupo", "")
            if n:
                out["agrupamento_para_grupo"][n] = g
                if n not in out["agrupamentos_ordenados"]:
                    out["agrupamentos_ordenados"].append(n)
    snap = db.collection("meta").document("linhasFluxo").get()
    if snap.exists:
        for it in (snap.to_dict() or {}).get("items", []):
            n, a = it.get("nome", ""), it.get("agrupamento", "")
            if not n: continue
            g = out["agrupamento_para_grupo"].get(a, "")
            out["linha_para_grupo"][n] = (g, a)
            if n not in out["linhas_ordenadas"]:
                out["linhas_ordenadas"].append(n)
    return out


# ─── Linhas calculadas (tipo Margem Operacional do DRE) ───────────────────
# (Caixa Operacional removido a pedido do user — vinha duplicando a soma
#  de "ATIVIDADES OPERACIONAIS" como linha extra no DFC.)
LINHAS_CALCULADAS_FLUXO = []

# Grupos que NÃO entram no líquido do dia (liq_dia) usado pra projetar o saldo
# de caixa acumulado. O grupo "SALDO" é resumo/balanço (Saldo Inicial, (+)
# Recebimentos, (-) Pagamentos, Saldo Final e as linhas "Saldo Conta
# Transitória") — são saldos, não movimento de caixa; somá-los no liq_dia
# corromperia o saldoFinalDiario (a "Saldo Conta Transitória", inclusive, já é
# LUMI + Exceto LUMI, então contaria o saldo transitório em dobro).
GRUPOS_FORA_DO_LIQUIDO = {"SALDO"}


def executar_fluxo(db, ano: int, mes: int) -> dict:
    """Pipeline completo: lê raw + manuais + saldo, classifica, agrega,
    grava em fluxoCaixa/{ano-mes}."""
    print(f"\n>> Executando fluxo de caixa {ano}-{mes:02d}...")

    raws = _carregar_raw_fluxo(db, ano, mes)
    print(f"   rawOracle: pago={len(raws['fluxo_pago'])}  juros={len(raws['fluxo_juros'])}  "
          f"opfin={len(raws['fluxo_opfin'])}  transitorias={len(raws['fluxo_transitorias'])}")

    fatos = []
    warnings = {}
    for slug, rows in raws.items():
        f, w = classifier_fluxo.classificar_fluxo(slug, rows)
        fatos.extend(f)
        if w:
            for k, v in w.items():
                warnings.setdefault(k, {}).update(v if isinstance(v, dict) else {})

    manuais = _carregar_lancamentos_fluxo(db, ano, mes)
    fatos.extend(manuais)
    print(f"   fatos classificados: {len(fatos) - len(manuais)}  +  manuais: {len(manuais)}")

    saldo_inicial, saldos_por_banco = _carregar_saldo_inicial(db, ano, mes)
    print(f"   saldo inicial: R$ {saldo_inicial:,.2f}  ({len(saldos_por_banco)} bancos)")

    dim = _carregar_dimensoes_fluxo(db)
    print(f"   dimensões: {len(dim['grupos_ordenados'])} grupos · {len(dim['agrupamentos_ordenados'])} agrups · {len(dim['linhas_ordenadas'])} linhas")

    # Agrega + grava docs. Roda 1x com todos os fatos (doc agregado) e
    # 1x por NROEMPRESA distinta (docs por loja com sufixo __{nroempresa}).
    linhas_fora_total = {}
    saldo_acum_total = saldo_inicial

    def _agregar_e_gravar(fatos_subset, sufixo, saldo_ini):
        """Agrega `fatos_subset` e grava em fluxoCaixa/{ano-mes}{sufixo}.
        Retorna (saldo_final, n_pontos, linhas_fora_local).
        """
        porLinha = defaultdict(float)
        porAgrupamento = defaultdict(float)
        porGrupo = defaultdict(float)
        dias_set = set()
        grupos_set, agrups_set, linhas_set = set(), set(), set()
        linhas_fora = {}

        for f in fatos_subset:
            data = f.get("data")
            if not data: continue
            dia = data[8:10]
            linha = f.get("linha") or ""
            valor = float(f.get("valor") or 0)
            if not linha or valor == 0: continue
            if linha not in dim["linha_para_grupo"]:
                linhas_fora[linha] = linhas_fora.get(linha, 0.0) + abs(valor)
            grupo, agrup = dim["linha_para_grupo"].get(linha, ("", ""))
            porLinha[(dia, grupo, agrup, linha)] += valor
            if agrup: porAgrupamento[(dia, agrup)] += valor
            if grupo: porGrupo[(dia, grupo)] += valor
            dias_set.add(dia)
            linhas_set.add(linha)
            if grupo: grupos_set.add(grupo)
            if agrup: agrups_set.add(agrup)

        # LINHAS_CALCULADAS_FLUXO
        linha_por_dia = defaultdict(lambda: defaultdict(float))
        agrup_por_dia = defaultdict(lambda: defaultdict(float))
        grupo_por_dia = defaultdict(lambda: defaultdict(float))
        for (dia, _g, _a, ln), v in porLinha.items():    linha_por_dia[dia][ln] += v
        for (dia, ag), v in porAgrupamento.items():       agrup_por_dia[dia][ag] += v
        for (dia, gr), v in porGrupo.items():             grupo_por_dia[dia][gr] += v
        for fc in LINHAS_CALCULADAS_FLUXO:
            nome  = fc["nome"]
            agrup = fc.get("agrupamento", "")
            grupo = fc.get("grupo") or dim["agrupamento_para_grupo"].get(agrup, "")
            for dia in list(dias_set):
                valor = fc["calc"](
                    lambda n, _d=dia: linha_por_dia[_d].get(n, 0.0),
                    lambda n, _d=dia: agrup_por_dia[_d].get(n, 0.0),
                    lambda n, _d=dia: grupo_por_dia[_d].get(n, 0.0),
                )
                if valor == 0: continue
                porLinha[(dia, grupo, agrup, nome)] = valor
                if agrup:
                    porAgrupamento[(dia, agrup)] = valor
                    agrup_por_dia[dia][agrup] = valor
                if grupo:
                    porGrupo[(dia, grupo)] = valor
                    grupo_por_dia[dia][grupo] = valor
                linhas_set.add(nome)
                if grupo: grupos_set.add(grupo)
                if agrup: agrups_set.add(agrup)

        # Saldo acumulado por dia
        dias_ordenados = sorted(dias_set)
        saldo_final_por_dia = []
        saldo_acum = saldo_ini
        for dia in dias_ordenados:
            liq_dia = sum(v for g, v in grupo_por_dia[dia].items()
                          if g not in GRUPOS_FORA_DO_LIQUIDO)
            saldo_acum += liq_dia
            saldo_final_por_dia.append({"d": dia, "v": round(saldo_acum, 2)})

        # Empacota
        def _ordena(presentes, ordenadas):
            out = [x for x in ordenadas if x in presentes]
            for x in sorted(presentes):
                if x not in out: out.append(x)
            return out

        dias = dias_ordenados
        grupos = _ordena(grupos_set, dim["grupos_ordenados"])
        agrups = _ordena(agrups_set, dim["agrupamentos_ordenados"])
        linhas = _ordena(linhas_set, dim["linhas_ordenadas"])
        idia = {x: i for i, x in enumerate(dias)}
        igrupo = {x: i for i, x in enumerate(grupos)}
        iagrup = {x: i for i, x in enumerate(agrups)}
        ilinha = {x: i for i, x in enumerate(linhas)}
        chave_doc = f"{ano:04d}-{mes:02d}{sufixo}"
        doc = {
            "ano": ano, "mes": mes, "v": 1,
            "dim": { "dias": dias, "grupos": grupos,
                     "agrupamentos": agrups, "linhas": linhas },
            "porGrupo": [
                {"d": idia[d], "g": igrupo[g], "v": round(v, 2)}
                for (d, g), v in porGrupo.items()
            ],
            "porAgrupamento": [
                {"d": idia[d], "a": iagrup[a], "v": round(v, 2)}
                for (d, a), v in porAgrupamento.items()
            ],
            "porLinha": [
                {"d": idia[d], "g": igrupo.get(g, 0), "a": iagrup.get(a, 0),
                 "n": ilinha[ln], "v": round(v, 2)}
                for (d, g, a, ln), v in porLinha.items()
            ],
            "saldoInicial": round(saldo_ini, 2),
            "saldoFinalDiario": saldo_final_por_dia,
            "geradoEm": firestore.SERVER_TIMESTAMP,
        }
        db.collection("fluxoCaixa").document(chave_doc).set(doc, merge=False)
        return saldo_acum, len(doc["porLinha"]), linhas_fora

    # 1) Agregado total (mesmo doc de sempre)
    saldo_acum, pontos_total, linhas_fora_total = _agregar_e_gravar(fatos, "", saldo_inicial)
    print(f"   ✓ fluxoCaixa/{ano:04d}-{mes:02d}: {pontos_total} pontos. "
          f"Saldo final: R$ {saldo_acum:,.2f}")

    # 2) Um doc por LOJA DESCRIÇÃO (meta/lojas). Respeita o cadastro:
    #    L01 pode ter NROEMPRESAs [1, 101] → agrega os dois nesse doc.
    #    Sufixo: __{descricao} (ex: __L01).
    #    saldo_ini por loja: derivado do prefixo "LJ##" no nome de cada banco
    #    do saldosBancarios (LJ## == NROEMPRESA → loja descricao via meta/lojas).
    #    O total do consolidado bate com a soma das partes (mesma planilha).
    nro_para_loja = {}
    try:
        ls = db.collection("meta").document("lojas").get()
        for it in (ls.to_dict() or {}).get("items", []):
            desc = (it.get("descricao") or "").strip()
            if not desc or it.get("ativo") is False: continue
            for nro in (it.get("nroempresa") or []):
                try: nro_para_loja[int(nro)] = desc
                except (TypeError, ValueError): pass
    except Exception as e:
        print(f"   ⚠ meta/lojas indisponível ({e}) — fallback: 1 doc por NROEMPRESA")

    if nro_para_loja:
        saldo_ini_por_loja, saldo_sem_loja = _quebrar_saldo_por_loja(saldos_por_banco, nro_para_loja)
        if saldo_sem_loja:
            print(f"   ⚠ R$ {saldo_sem_loja:,.2f} de saldo bancário sem prefixo LJ## "
                  f"reconhecido (entra só no consolidado, não em docs por loja)")
        # Fallback per-loja: se o cadastro do mês não tem (ou não bateu por LJ##),
        # herda o saldo final por loja do mês anterior. Mantém a cadeia
        # mês-a-mês sem precisar re-cadastrar.
        if not saldo_ini_por_loja:
            herdou = 0
            for desc in set(nro_para_loja.values()):
                prev_loja = _saldo_final_mes_anterior(db, ano, mes, sufixo=f"__{desc}")
                if prev_loja is not None and prev_loja != 0:
                    saldo_ini_por_loja[desc] = prev_loja
                    herdou += 1
            if herdou:
                print(f"   ↪ saldo inicial por loja herdado de {ano:04d}-{mes-1 if mes>1 else 12:02d} "
                      f"({herdou} lojas, total R$ {sum(saldo_ini_por_loja.values()):,.2f})")
        if saldo_ini_por_loja:
            top = sorted(saldo_ini_por_loja.items(), key=lambda kv: -kv[1])[:5]
            print(f"   saldo inicial por loja (top 5): "
                  + " · ".join(f"{k}={v:,.2f}" for k, v in top))
        # Agrupa fatos por loja-descrição
        fatos_por_loja = {}
        sem_loja = []
        for f in fatos:
            nro = f.get("nroempresa")
            if nro is None:
                continue
            try: nro = int(nro)
            except (TypeError, ValueError): continue
            desc = nro_para_loja.get(nro)
            if not desc:
                sem_loja.append(nro)
                continue
            fatos_por_loja.setdefault(desc, []).append(f)
        # Garante que toda loja com saldo inicial vire um doc, mesmo sem fato
        # no mês (Saldo Inicial precisa aparecer na tela mesmo sem movimento).
        for desc in saldo_ini_por_loja.keys():
            fatos_por_loja.setdefault(desc, [])
        n_lojas_gravadas = 0
        for desc in sorted(fatos_por_loja.keys()):
            saldo_ini_desc = saldo_ini_por_loja.get(desc, 0.0)
            _, pts, _ = _agregar_e_gravar(fatos_por_loja[desc], f"__{desc}", saldo_ini_desc)
            if pts or saldo_ini_desc: n_lojas_gravadas += 1
        if sem_loja:
            sem_loja_unicas = sorted(set(sem_loja))
            print(f"   ⚠ NROEMPRESAs sem cadastro em meta/lojas (ignoradas no filtro): {sem_loja_unicas[:10]}{'...' if len(sem_loja_unicas) > 10 else ''}")
        print(f"   ✓ {n_lojas_gravadas} docs por loja gravados em fluxoCaixa/{ano:04d}-{mes:02d}__{{LOJA}}")
    else:
        # Fallback: 1 doc por NROEMPRESA (comportamento anterior)
        nros_distintos = sorted({int(f["nroempresa"]) for f in fatos
                                  if f.get("nroempresa") is not None})
        n_lojas_gravadas = 0
        for nro in nros_distintos:
            fatos_loja = [f for f in fatos if f.get("nroempresa") == nro]
            if not fatos_loja: continue
            _, pts, _ = _agregar_e_gravar(fatos_loja, f"__{nro}", 0.0)
            if pts: n_lojas_gravadas += 1
        print(f"   ✓ {n_lojas_gravadas} docs por NROEMPRESA gravados (fallback)")
    linhas_fora = linhas_fora_total
    saldo_acum_total = saldo_acum  # pra retorno coerente
    if linhas_fora:
        print(f"   ⚠ {len(linhas_fora)} LINHAs fora do plano DFC (TOP 10):")
        for ln, total in sorted(linhas_fora.items(), key=lambda kv: -kv[1])[:10]:
            print(f"      {total:>15,.2f}  {ln}")
    if warnings:
        print(f"   ⚠ Warnings de classificação: {warnings}")

    # Firestore exige chaves de map como string. CODOPERACAO pode aparecer como
    # int (ex.: codops_nao_mapeados={15: 2951}). Converte recursivamente antes
    # de devolver o dict ao agente, que vai gravar em tasks/{id}.resultado.
    def _stringify_keys(obj):
        if isinstance(obj, dict):
            return {str(k): _stringify_keys(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_stringify_keys(x) for x in obj]
        return obj

    return {
        "ano": ano, "mes": mes,
        "fatos":           len(fatos) - len(manuais),
        "manuais":         len(manuais),
        "saldoInicial":    round(saldo_inicial, 2),
        "saldoFinal":      round(saldo_acum_total, 2),
        "lojasGravadas":   n_lojas_gravadas,
        "pontosTotal":     pontos_total,
        "linhasForaPlano": list(linhas_fora.keys()),
        "warnings":        _stringify_keys(warnings),
    }
