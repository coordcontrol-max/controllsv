#!/usr/bin/env python3
r"""Movimento de Títulos por mês — INCLUÍDO × PAGO/RECEBIDO, agrupado igual ao DFC.

Fonte: Oracle Consinco, tabela FI_TITULO (todos os títulos, abertos + quitados).
  - INCLUÍDO no mês   = SUM(VLRNOMINAL) por mês de DTAINCLUSAO  (título lançado)
  - PAGO/RECEBIDO     = SUM(VLRPAGO)    por mês de DTAQUITACAO  (título liquidado)
Classifica por CODESPECIE → LINHA (mesmo mapa do DFC) → grupo/agrupamento
(meta/linhasFluxo). Sinal: obrigação (O) negativo, direito (D) positivo.

Grava em titulosMovimento/{ano} no Firestore (projeto-686e2), consumido pela
aba "Movimento de Títulos" da página Títulos em Aberto (Supervendas).

Uso (na WSL, Oracle acessível):
  LD_LIBRARY_PATH=/opt/oracle/instantclient_23_5 python3 gera_titulos_movimento.py [ano]
"""
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, "agente")
import agente                                   # conexão Oracle + Firebase (db)
from firebase_admin import firestore
import engine_fluxo
from classifier_fluxo import CODESPECIE_TO_LINHA_FLUXO, CODESPECIE_IGNORAR_FLUXO

db = agente.db

# Coorte de INCLUSÃO: dos títulos lançados (DTAINCLUSAO) no mês, quanto é o
# nominal (incluido), quanto já foi pago (quitado) e quanto está em aberto (saldo).
# incluido = quitado + aberto.
SQL_INCLUIDO = """
  select t.codespecie, t.obrigdireito,
         extract(month from t.dtainclusao) mes,
         sum(t.vlrnominal) incluido,
         sum(t.vlrpago) quitado,
         sum(t.vlrnominal - t.vlrpago) aberto
    from fi_titulo t
   where t.dtainclusao >= :ini and t.dtainclusao < :fim
     and t.situacao <> 'C'
   group by t.codespecie, t.obrigdireito, extract(month from t.dtainclusao)
"""
# PAGO/RECEBIDO por mês de LIQUIDAÇÃO (DTAQUITACAO) — independe da inclusão.
SQL_LIQUIDADO = """
  select t.codespecie, t.obrigdireito,
         extract(month from t.dtaquitacao) mes,
         sum(t.vlrpago) vlr
    from fi_titulo t
   where t.dtaquitacao >= :ini and t.dtaquitacao < :fim
     and t.situacao <> 'C' and t.vlrpago > 0
   group by t.codespecie, t.obrigdireito, extract(month from t.dtaquitacao)
"""


def gerar(ano: int):
    dim = engine_fluxo._carregar_dimensoes_fluxo(db)
    l2g = dim["linha_para_grupo"]
    # subAgrupamento por linha (ex.: "Recbto de Contratos") — pra tabela hierárquica DFC
    linha_sub = {}
    snap = db.collection("meta").document("linhasFluxo").get()
    if snap.exists:
        for it in (snap.to_dict() or {}).get("items", []):
            n = it.get("nome", "")
            s = (it.get("subAgrupamento") or "").strip()
            if n and s:
                linha_sub[n] = s
    ini, fim = date(ano, 1, 1), date(ano + 1, 1, 1)

    con = agente.conectar_oracle()
    cur = con.cursor()

    # mov[mes][(grupo,agrup,linha)] = {incluido, quitado, aberto, liquidado}
    def _z():
        return {"incluido": 0.0, "quitado": 0.0, "aberto": 0.0, "liquidado": 0.0}
    mov = defaultdict(lambda: defaultdict(_z))
    nao_map = defaultdict(float)

    def _classifica(codespecie, obrig):
        if codespecie in CODESPECIE_IGNORAR_FLUXO:
            return None
        linha = CODESPECIE_TO_LINHA_FLUXO.get(codespecie)
        if not linha:
            return None
        grupo, agrup = l2g.get(linha, ("", ""))
        sign = -1 if obrig == "O" else 1
        return (grupo, agrup, linha), sign

    print(f">> Movimento de títulos {ano} (FI_TITULO)…")
    # INCLUÍDO (coorte de inclusão: incluido = quitado + aberto)
    cur.execute(SQL_INCLUIDO, ini=ini, fim=fim)
    for codespecie, obrig, mes, inc, quit_, abe in cur.fetchall():
        if not mes:
            continue
        cl = _classifica(codespecie, obrig)
        if cl is None:
            nao_map[codespecie or "—"] += abs(float(inc or 0))
            continue
        key, sign = cl
        mm = f"{int(mes):02d}"
        d = mov[mm][key]
        d["incluido"] += float(inc or 0) * sign
        d["quitado"] += float(quit_ or 0) * sign
        d["aberto"] += float(abe or 0) * sign
    # LIQUIDADO (por mês de quitação)
    cur.execute(SQL_LIQUIDADO, ini=ini, fim=fim)
    for codespecie, obrig, mes, vlr in cur.fetchall():
        if not mes or vlr is None:
            continue
        cl = _classifica(codespecie, obrig)
        if cl is None:
            continue
        key, sign = cl
        mm = f"{int(mes):02d}"
        mov[mm][key]["liquidado"] += float(vlr) * sign
    cur.close()
    con.close()

    meses = {}
    for mm in sorted(mov.keys()):
        linhas = []
        for (g, a, l), v in mov[mm].items():
            linhas.append({"grupo": g, "agrupamento": a, "linha": l,
                           "incluido": round(v["incluido"], 2),
                           "quitado": round(v["quitado"], 2),
                           "aberto": round(v["aberto"], 2),
                           "liquidado": round(v["liquidado"], 2)})
        meses[mm] = linhas
        ti = sum(x["incluido"] for x in linhas)
        tq = sum(x["quitado"] for x in linhas)
        ta = sum(x["aberto"] for x in linhas)
        print(f"   mês {mm}: {len(linhas)} linhas · incluído {ti:,.0f} (quitado {tq:,.0f} + aberto {ta:,.0f})")

    if nao_map:
        top = sorted(nao_map.items(), key=lambda x: -x[1])[:8]
        print("   (CODESPECIE sem mapa, ignorados):", ", ".join(f"{c}={v:,.0f}" for c, v in top))

    doc = {
        "ano": ano,
        "grupos_ordenados": dim["grupos_ordenados"],
        "agrupamentos_ordenados": dim["agrupamentos_ordenados"],
        "linhas_ordenadas": dim["linhas_ordenadas"],
        "agrupamento_para_grupo": dim["agrupamento_para_grupo"],
        "linha_sub": linha_sub,
        "meses": meses,
        "geradoEm": firestore.SERVER_TIMESTAMP,
    }
    db.collection("titulosMovimento").document(str(ano)).set(doc, merge=False)
    print(f"✓ titulosMovimento/{ano}: {len(meses)} meses gravados")


if __name__ == "__main__":
    gerar(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)
