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

SQL_INCLUIDO = """
  select t.codespecie, t.obrigdireito,
         extract(month from t.dtainclusao) mes,
         sum(t.vlrnominal) vlr
    from fi_titulo t
   where t.dtainclusao >= :ini and t.dtainclusao < :fim
     and t.situacao <> 'C'
   group by t.codespecie, t.obrigdireito, extract(month from t.dtainclusao)
"""
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
    ini, fim = date(ano, 1, 1), date(ano + 1, 1, 1)

    con = agente.conectar_oracle()
    cur = con.cursor()

    # mov[mes][(grupo,agrup,linha)] = {"incluido": x, "liquidado": y}
    mov = defaultdict(lambda: defaultdict(lambda: {"incluido": 0.0, "liquidado": 0.0}))
    nao_map = defaultdict(float)

    def processa(sql, campo):
        cur.execute(sql, ini=ini, fim=fim)
        for codespecie, obrig, mes, vlr in cur.fetchall():
            if not mes or vlr is None:
                continue
            if codespecie in CODESPECIE_IGNORAR_FLUXO:
                continue
            linha = CODESPECIE_TO_LINHA_FLUXO.get(codespecie)
            if not linha:
                nao_map[codespecie or "—"] += abs(float(vlr))
                continue
            grupo, agrup = l2g.get(linha, ("", ""))
            sign = -1 if obrig == "O" else 1
            mm = f"{int(mes):02d}"
            mov[mm][(grupo, agrup, linha)][campo] += float(vlr) * sign

    print(f">> Movimento de títulos {ano} (FI_TITULO)…")
    processa(SQL_INCLUIDO, "incluido")
    processa(SQL_LIQUIDADO, "liquidado")
    cur.close()
    con.close()

    meses = {}
    for mm in sorted(mov.keys()):
        linhas = []
        for (g, a, l), v in mov[mm].items():
            linhas.append({"grupo": g, "agrupamento": a, "linha": l,
                           "incluido": round(v["incluido"], 2),
                           "liquidado": round(v["liquidado"], 2)})
        meses[mm] = linhas
        ti = sum(x["incluido"] for x in linhas)
        tl = sum(x["liquidado"] for x in linhas)
        print(f"   mês {mm}: {len(linhas)} linhas · incluído {ti:,.0f} · liquidado {tl:,.0f}")

    if nao_map:
        top = sorted(nao_map.items(), key=lambda x: -x[1])[:8]
        print("   (CODESPECIE sem mapa, ignorados):", ", ".join(f"{c}={v:,.0f}" for c, v in top))

    doc = {
        "ano": ano,
        "grupos_ordenados": dim["grupos_ordenados"],
        "agrupamentos_ordenados": dim["agrupamentos_ordenados"],
        "meses": meses,
        "geradoEm": firestore.SERVER_TIMESTAMP,
    }
    db.collection("titulosMovimento").document(str(ano)).set(doc, merge=False)
    print(f"✓ titulosMovimento/{ano}: {len(meses)} meses gravados")


if __name__ == "__main__":
    gerar(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)
