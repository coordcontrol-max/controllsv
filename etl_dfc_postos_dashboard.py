#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adapter: Adaptive DFC (dfc_postos_{ano}.json) → docs mensais no FORMATO DO
DASHBOARD (dados_fluxo_postos/{ano-mes}.json + {ano-mes}__P0X.json).

Assim o "Dashboard DFC" (renderDFCResumo, tela legada que lê via loadFluxoMes)
passa a mostrar os números da Adaptive, sem reescrever os 5 gráficos.

Formato de saída (igual etl_fluxo_segmentos.py):
  {ano, mes, v, segmento:"postos", loja, dim:{dias,grupos,agrupamentos,linhas},
   porLinha:[{d,g,a,n,v}], porAgrupamento:[{d,g,a,v}], porGrupo:[{d,g,v}],
   saldoFinalDiario:[{d,v}]}
Roda DEPOIS do etl_dfc_postos_sql.py (que gera o dfc_postos_{ano}.json) e
SOBRESCREVE os docs de postos do etl_fluxo_segmentos.
"""
import os, json, glob, datetime as dt

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(BASE, "dados_dre_postos_adaptive")
OUT_DIR = os.path.join(BASE, "dados_fluxo_postos")

GRUPO_OP, GRUPO_FIN, GRUPO_INV = (
    "ATIVIDADES OPERACIONAIS", "ATIVIDADES DE FINANCIAMENTO", "ATIVIDADES DE INVESTIMENTO")
GRUPOS = [GRUPO_OP, GRUPO_FIN, GRUPO_INV]
# ordem dos agrupamentos no dashboard
AGRUPS = ["Recebimentos Operacionais", "Fornecedores", "Despesas",
          "Atividades de Financiamento", "Atividades de Investimento"]


# Linhas de despesa que, na verdade, são ATIVIDADES DE FINANCIAMENTO (espelha o
# _DFCP_DESP_FIN do dashboard.html: agrupamentos Vendas, Financeiras e
# "Transferências entre Grupos"). Mantém Dashboard DFC e DFC Consolidado coerentes
# com a DFC Diário/Mensal (que reclassificam essas linhas no front).
FIN_LINES = {
    # Vendas (sobrou só comissão/bônus de venda)
    "TAXAS ALUGUEL DE POS", "APLICATIVO CIBUS-RESGATE", "PREMIAÇÃO/BONUS",
    # Financeiras — custos bancários, cartão, IOF/IR, multas/descontos financeiros
    "DESPESAS BANCARIA", "DESPESAS BANCARIAS COM COBRANÇAS",
    "TARIFA ANTECIPAÇÃO", "TAXA DE ADESÃO",
    "IOF", "IR", "JURO DE COBRANÇA PAGO",
    "ACRÉSCIMO FINANCEIRO PAGO", "MULTA DE COBRANÇA PAGA",
    "DESCONTO FINANCEIRO CONCEDIDO", "DESCONTO DE COBRANÇA CONCEDIDO",
    "TARIFAS BANCARIAS", "TAXA ADMINISTRATIVA DE CARTOES",
    "TAXA PIX", "DESPESA FAZENDA",
    "TAXAS EXTRAS CARTOES", "MULTAS FISCAIS",
    "TARIFA DE TRANSAÇÃO PAGA",
    "TAXA DE ADMINISTRAÇÃO PAGA POR LITRO",
    "TAXA DE ADMINISTRAÇÃO PAGA",
    "(-) ARREDONDAMENTO CARTÃO",
    # Transferência entre grupos (linha "Despesas" = transferência do posto SM p/ LP)
    "Despesas",
}


def classifica(fluxo, grupo, conta=None):
    """(fluxo, grupo Adaptive, conta) → (grupoDashboard, agrupamento)."""
    if fluxo == "ENTRADA":
        if grupo in ("Receitas", "Mútuos a Receber (entre grupos)"):
            return GRUPO_FIN, "Atividades de Financiamento"
        return GRUPO_OP, "Recebimentos Operacionais"
    # SAIDA
    if grupo in ("Fornecedores", "Conhecimento de Frete"):
        return GRUPO_OP, "Fornecedores"
    if grupo == "Investimentos":
        return GRUPO_INV, "Atividades de Investimento"
    if grupo in ("Mútuos a Pagar (entre grupos)", "Transferências"):
        return GRUPO_FIN, "Atividades de Financiamento"
    if conta in FIN_LINES:   # Vendas/Financeiras/Transf entre grupos → Financiamento
        return GRUPO_FIN, "Atividades de Financiamento"
    return GRUPO_OP, "Despesas"


def build_doc(ano, mes, agg_postos):
    """agg_postos: lista de agg (um por posto incluído) no formato Adaptive
    agg[fluxo][grupo][conta][dia]. Soma todos e monta o doc do dashboard."""
    pre = f"{ano}-{mes:02d}-"
    ndias = (dt.date(ano + (mes == 12), (mes % 12) + 1, 1) - dt.timedelta(days=1)).day
    dias = [f"{d:02d}" for d in range(1, ndias + 1)]
    # cubo: (dia, grupoDash, agrup, linha) -> valor (com sinal)
    cubo = {}
    for agg in agg_postos:
        for fluxo in ("ENTRADA", "SAIDA"):
            sign = 1 if fluxo == "ENTRADA" else -1
            for grupo, contas in (agg.get(fluxo) or {}).items():
                for conta, perdia in contas.items():
                    gd, ag = classifica(fluxo, grupo, conta)
                    for dk, v in perdia.items():
                        if not dk.startswith(pre):
                            continue
                        d = dk[8:10]
                        key = (d, gd, ag, conta)
                        cubo[key] = cubo.get(key, 0.0) + sign * (v or 0.0)
    if not cubo:
        return None
    # dim
    linhas = []
    seen = set()
    for (_, _, _, ln) in cubo:
        if ln not in seen:
            seen.add(ln); linhas.append(ln)
    dim = {"dias": dias, "grupos": GRUPOS, "agrupamentos": AGRUPS, "linhas": linhas}
    di = {d: i for i, d in enumerate(dias)}
    gi = {g: i for i, g in enumerate(GRUPOS)}
    ai = {a: i for i, a in enumerate(AGRUPS)}
    ni = {n: i for i, n in enumerate(linhas)}
    porLinha, porAgr, porGr = [], {}, {}
    saldoDia = {}
    for (d, gd, ag, ln), v in cubo.items():
        vr = round(v, 2)
        if abs(vr) < 0.005:
            continue
        porLinha.append({"d": di[d], "g": gi[gd], "a": ai[ag], "n": ni[ln], "v": vr})
        porAgr[(di[d], gi[gd], ai[ag])] = round(porAgr.get((di[d], gi[gd], ai[ag]), 0.0) + vr, 2)
        porGr[(di[d], gi[gd])] = round(porGr.get((di[d], gi[gd]), 0.0) + vr, 2)
        saldoDia[d] = round(saldoDia.get(d, 0.0) + vr, 2)
    porAgrumento = [{"d": k[0], "g": k[1], "a": k[2], "v": v} for k, v in porAgr.items()]
    porGrupo = [{"d": k[0], "g": k[1], "v": v} for k, v in porGr.items()]
    # saldoFinalDiario: acumulado do líquido diário (offset do saldo inicial real
    # é injetado no front via saldos_oficiais; aqui só o acumulado relativo)
    acc = 0.0; sfd = []
    for d in dias:
        acc = round(acc + saldoDia.get(d, 0.0), 2)
        sfd.append({"d": di[d], "v": acc})
    return {
        "ano": ano, "mes": mes, "v": 2, "segmento": "postos", "loja": "",
        "dim": dim, "porLinha": porLinha, "porAgrupamento": porAgrumento,
        "porGrupo": porGrupo, "saldoFinalDiario": sfd,
        "fonte": "Adaptive (etl_dfc_postos_dashboard.py)",
    }


def build_detalhe(ano, mes, src_data, despesas_data):
    """Items pro modal Detalhamento. Combina:
       • ENTRADAS — dados[posto].det[dia_iso][conta] (do dfc_postos_*.json).
       • SAÍDAS   — titulos[posto_nome][conta][mes_2d] (do despesas_*.json).
       O modal espera {items:[{ano,mes,data,linha,loja,nroempresa,valor,
       nomerazao,observacao,nrotitulo,descricao}]}."""
    pre_iso = f"{ano}-{mes:02d}-"
    mes_2 = f"{mes:02d}"
    items = []
    cod_nome = {p["codigo"]: p["nome"] for p in src_data.get("postos", [])}
    nome_loja = {n: "P" + c[-2:] for c, n in cod_nome.items()}

    def _push(loja, d_iso, conta, valor, fornec, obs, doc_n):
        items.append({
            "ano": str(ano), "mes": mes_2, "data": d_iso,
            "linha": conta, "loja": loja, "nroempresa": loja,
            "valor": round(float(valor or 0), 2),
            "nomerazao": fornec or "", "observacao": obs or "",
            "nrotitulo": str(doc_n or ""), "descricao": conta,
        })

    # ENTRADAS (det)
    for nome, info in (src_data.get("dados") or {}).items():
        loja = nome_loja.get(nome)
        if not loja:
            continue
        for dia_iso, contas in (info.get("det") or {}).items():
            if not dia_iso.startswith(pre_iso):
                continue
            for conta, titulos in contas.items():
                for t in titulos:
                    sign = 1 if t.get("f") == "ENTRADA" else -1
                    _push(loja, dia_iso, conta, sign * float(t.get("v") or 0),
                          t.get("pessoa"), t.get("obs"), t.get("doc"))

    # SAÍDAS (despesas)
    titulos = (despesas_data or {}).get("titulos") or {}
    for nome, contas in titulos.items():
        loja = nome_loja.get(nome)
        if not loja:
            continue
        for conta, meses in contas.items():
            ts = meses.get(mes_2) or []
            for t in ts:
                d_str = str(t.get("d") or "")
                if len(d_str) == 10 and d_str[2] == "/":
                    d_iso = f"{d_str[6:10]}-{d_str[3:5]}-{d_str[0:2]}"
                elif len(d_str) >= 10 and d_str[4] == "-":
                    d_iso = d_str[:10]
                else:
                    continue
                _push(loja, d_iso, conta, -float(t.get("v") or 0),
                      t.get("f"), t.get("o"), t.get("doc"))
    return items


def main():
    fontes = sorted(glob.glob(os.path.join(SRC_DIR, "dfc_postos_*.json")))
    if not fontes:
        print("  · (sem dfc_postos_*.json — rode etl_dfc_postos_sql.py antes)")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    for src in fontes:
        data = json.load(open(src, encoding="utf-8"))
        ano = int(data.get("ano") or 0)
        if not ano:
            continue
        # carrega despesas_{ano}.json (títulos das saídas — Honorários, Água, Aluguel…)
        desp_path = os.path.join(SRC_DIR, f"despesas_{ano}.json")
        despesas_data = json.load(open(desp_path, encoding="utf-8")) if os.path.exists(desp_path) else {}
        # codigo → nome ; agg por nome
        cod_nome = {p["codigo"]: p["nome"] for p in data.get("postos", [])}
        aggs = {c: (data["dados"].get(n) or {}).get("agg", {}) for c, n in cod_nome.items()}
        meses = set()
        for agg in aggs.values():
            for fl in agg.values():
                for g in fl.values():
                    for c in g.values():
                        for dk in c:
                            meses.add(int(dk[5:7]))
        nfiles = 0
        for mes in sorted(meses):
            # agregado (todos os postos) → loja ""
            doc = build_doc(ano, mes, list(aggs.values()))
            if doc:
                json.dump(doc, open(os.path.join(OUT_DIR, f"{ano}-{mes:02d}.json"), "w", encoding="utf-8"),
                          ensure_ascii=False, separators=(",", ":"))
                nfiles += 1
            # por posto → loja P0X
            for cod, agg in aggs.items():
                p = "P" + cod[-2:]
                docp = build_doc(ano, mes, [agg])
                if docp:
                    docp["loja"] = p
                    json.dump(docp, open(os.path.join(OUT_DIR, f"{ano}-{mes:02d}__{p}.json"), "w", encoding="utf-8"),
                              ensure_ascii=False, separators=(",", ":"))
                    nfiles += 1
            # detalhe título-a-título (sobrescreve a versão antiga do Excel, que
            # tinha só recebimentos — agora inclui também as despesas do Adaptive).
            items = build_detalhe(ano, mes, data, despesas_data)
            if items:
                json.dump({"items": items},
                          open(os.path.join(OUT_DIR, f"detalhe_{ano}-{mes:02d}.json"), "w", encoding="utf-8"),
                          ensure_ascii=False, separators=(",", ":"))
                nfiles += 1
        print(f"  ✓ {os.path.basename(src)} → {nfiles} docs do dashboard (ano {ano}, {len(meses)} meses)")


if __name__ == "__main__":
    main()
