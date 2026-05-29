"""Apuração de Contratos de Retorno (Supermercados).

Compara, por fornecedor e mês:
  • VLRTOTALNF   — total das entradas de NF (divisões 1-4) no período
  • PERCDESCONTO — % do contrato de retorno ativo do fornecedor
  • VLRESPERADO  — VLRTOTALNF × PERCDESCONTO/100 (retorno esperado)
  • VLRAPURADO   — títulos CONTRT (Contrato de Retorno) emitidos no período
  • DIFERENCA    — VLRESPERADO − VLRAPURADO (positivo = retorno a apurar)

Gera /root/projeto_dre/apuracao_contratos.json:
  { geradoEm, meses: { "2026-05": {items:[...], totais:{...}}, ... } }
"""
import os, json, datetime as dt
import oracledb
from dotenv import load_dotenv

OUT = "/root/projeto_dre/apuracao_contratos.json"

load_dotenv("/root/projeto_dre/agente/.env")
oracledb.init_oracle_client(lib_dir=os.environ["ORACLE_CLIENT_DIR"])
dsn = f"{os.environ['ORACLE_HOST']}:{os.environ['ORACLE_PORT']}/{os.environ['ORACLE_SERVICE']}"
conn = oracledb.connect(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"], dsn=dsn)
cur = conn.cursor()
_schema = os.environ.get("ORACLE_SCHEMA", "CONSINCO")
if _schema:
    cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {_schema}")

SQL = """
WITH CONTRATOS_ATIVOS AS (
  SELECT X.SEQPESSOA, X.SEQCONTRATO, X.SEQREDE, X.DESCRICAO, X.PERCDESCONTO
  FROM (
    SELECT GR.SEQPESSOA, MC.SEQCONTRATO, MC.SEQREDE, MC.DESCRICAO, MC2.PERCDESCONTO,
           ROW_NUMBER() OVER (PARTITION BY GR.SEQPESSOA ORDER BY MC.SEQCONTRATO DESC) AS RN
    FROM CONSINCO.MGC_CONTRATO MC
    JOIN CONSINCO.GE_REDEPESSOA GR ON GR.SEQREDE = MC.SEQREDE
    JOIN CONSINCO.MGC_CONTRATORETORNO MC2 ON MC2.SEQCONTRATO = MC.SEQCONTRATO
    WHERE MC.STATUS = 'A'
  ) X WHERE X.RN = 1
),
BASE_NF AS (
  SELECT E2.SEQPESSOA, F2.NOMERAZAO,
    ROUND(SUM(
      (NVL(E2.VLRITEM,0)-NVL(E2.VLRDESCITEM,0)+NVL(E2.VLRICMSSTNF,0)+NVL(E2.VLRIPI,0)+NVL(E2.VLRICMSDI,0)
       +NVL(E2.VLRDESPTRIBUTITEM,0)+NVL(E2.VLRDESPNTRIBUTITEM,0)+NVL(E2.VLRFCPSTNF,0)+NVL(E2.VLRCREDIBSUF,0)
       +NVL(E2.VLRCREDIBSMUN,0)+NVL(E2.VLRCREDCBS,0)+NVL(E2.VLRCREDIS,0))
      -(NVL(E2.DVLRITEM,0)-NVL(E2.DVLRDESCITEM,0)+NVL(E2.DVLRICMSST,0)+NVL(E2.DVLRIPI,0)
        +NVL(E2.DVLRDESPTRIBUTITEM,0)+NVL(E2.DVLRDESPNTRIBUTITEM,0)+NVL(E2.DVLRFCPST,0))
    ),2) AS VLRTOTALNF
  FROM MAXV_ABCENTRADABASE E2
  JOIN MAP_PRODUTO A ON A.SEQPRODUTO=E2.SEQPRODUTO
  JOIN MAP_FAMDIVISAO D ON D.SEQFAMILIA=A.SEQFAMILIA AND D.NRODIVISAO=E2.NRODIVISAO
  JOIN MAD_FAMSEGMENTO H ON H.SEQFAMILIA=D.SEQFAMILIA AND H.NROSEGMENTO=E2.NROSEGMENTOPRINC
  JOIN MAP_FAMEMBALAGEM K ON K.SEQFAMILIA=A.SEQFAMILIA AND K.QTDEMBALAGEM=D.PADRAOEMBCOMPRA
  JOIN MRL_PRODUTOEMPRESA C ON C.SEQPRODUTO=E2.SEQPRODUTO AND C.NROEMPRESA=E2.NROEMPRESA
  JOIN GE_PESSOA F2 ON F2.SEQPESSOA=E2.SEQPESSOA
  WHERE D.NRODIVISAO IN (1,2,3,4)
    AND E2.DTAENTRADA >= TO_DATE(:d1,'DD/MM/YYYY')
    AND E2.DTAENTRADA < TO_DATE(:d2,'DD/MM/YYYY')+1
    AND E2.CODGERALOPER NOT IN (100,101,202,222,802)
    AND EXISTS (SELECT 1 FROM MAX_EMPRESA P WHERE P.SEQPESSOAEMP=E2.NROEMPRESA)
    AND NOT EXISTS (SELECT 1 FROM GE_EMPRESA N WHERE N.SEQPESSOA=E2.SEQPESSOA)
  GROUP BY E2.SEQPESSOA, F2.NOMERAZAO
),
TITULOS_CONTRATO AS (
  SELECT FT.SEQPESSOA, ROUND(SUM(NVL(FT.VLRORIGINAL,0)),2) AS VLRAPURADO
  FROM CONSINCO.FI_TITULO FT
  WHERE FT.ABERTOQUITADO='A' AND FT.CODESPECIE='CONTRT'
    AND FT.DTAEMISSAO >= TO_DATE(:d3,'DD/MM/YYYY')
    AND FT.DTAEMISSAO < TO_DATE(:d4,'DD/MM/YYYY')+1
  GROUP BY FT.SEQPESSOA
),
-- Recebido: baixas de títulos CONTRT pelas operações de recebimento
--   5  = Recebimento em Conta Corrente
--   8  = Juros Recebidos
--   28 = Compensado com Tít. a Pagar  (é como o fornecedor "paga" o retorno)
-- Atribuído pelo mês corrente (DTAOPERACAO em M, janela d1→d2), batendo com o
-- relatório "Contas a Receber - Recebido" do Consinco por período de operação.
RECEBIDO_CONTRATO AS (
  SELECT FT.SEQPESSOA, ROUND(SUM(NVL(O.VLROPERACAO,0)),2) AS VLRRECEBIDO
  FROM CONSINCO.FI_TITOPERACAO O
  JOIN CONSINCO.FI_TITULO FT ON FT.SEQTITULO = O.SEQTITULO
  WHERE FT.CODESPECIE='CONTRT'
    AND O.CODOPERACAO IN (5,8,28)
    AND NVL(O.OPCANCELADA,'N') <> 'S'
    AND O.DTAOPERACAO >= TO_DATE(:d1,'DD/MM/YYYY')
    AND O.DTAOPERACAO < TO_DATE(:d2,'DD/MM/YYYY')+1
  GROUP BY FT.SEQPESSOA
)
SELECT C.SEQPESSOA, NVL(B.NOMERAZAO, P.NOMERAZAO) AS NOMERAZAO,
  C.SEQCONTRATO, C.SEQREDE, C.DESCRICAO, C.PERCDESCONTO,
  NVL(B.VLRTOTALNF,0) AS VLRTOTALNF,
  ROUND(NVL(B.VLRTOTALNF,0)*(NVL(C.PERCDESCONTO,0)/100),2) AS VLRESPERADO,
  NVL(T.VLRAPURADO,0) AS VLRAPURADO,
  ROUND((NVL(B.VLRTOTALNF,0)*(NVL(C.PERCDESCONTO,0)/100))-NVL(T.VLRAPURADO,0),2) AS DIFERENCA,
  NVL(R.VLRRECEBIDO,0) AS VLRRECEBIDO
FROM CONTRATOS_ATIVOS C
JOIN GE_PESSOA P ON P.SEQPESSOA = C.SEQPESSOA
LEFT JOIN BASE_NF B ON B.SEQPESSOA = C.SEQPESSOA
LEFT JOIN TITULOS_CONTRATO T ON T.SEQPESSOA = C.SEQPESSOA
LEFT JOIN RECEBIDO_CONTRATO R ON R.SEQPESSOA = C.SEQPESSOA
ORDER BY ABS(ROUND((NVL(B.VLRTOTALNF,0)*(NVL(C.PERCDESCONTO,0)/100))-NVL(T.VLRAPURADO,0),2)) DESC
"""

def ult_dia(ano, mes):
    if mes == 12:
        return dt.date(ano, 12, 31)
    return dt.date(ano, mes + 1, 1) - dt.timedelta(days=1)

def prox_mes(ano, mes):
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)

hoje = dt.date.today()
ano = hoje.year
meses_alvo = list(range(1, hoje.month + 1))   # Jan..mês corrente

resultado = {"geradoEm": dt.datetime.now().isoformat(timespec="seconds"), "meses": {}}
for mes in meses_alvo:
    # Entradas (NF): mês M corrente
    d1 = f"01/{mes:02d}/{ano}"
    d2 = ult_dia(ano, mes).strftime("%d/%m/%Y")
    # Apuração (títulos CONTRT): mês SEGUINTE (M+1) — apuração sai sempre no
    # dia 10 do mês seguinte (ex: entradas de 03/2026 apuradas em 10/04/2026).
    a2, m2 = prox_mes(ano, mes)
    d3 = f"01/{m2:02d}/{a2}"
    d4 = ult_dia(a2, m2).strftime("%d/%m/%Y")
    print(f"[{ano}-{mes:02d}] NF {d1}→{d2} · apuração {d3}→{d4} …", end=" ", flush=True)
    cur.execute(SQL, d1=d1, d2=d2, d3=d3, d4=d4)
    items = []
    tot_nf = tot_esp = tot_apur = tot_dif = tot_receb = 0.0
    for r in cur.fetchall():
        seqp, nome, seqcontr, seqrede, desc, perc, vlrnf, vlresp, vlrapur, dif, vlrreceb = r
        vlrnf = float(vlrnf or 0); vlresp = float(vlresp or 0)
        vlrapur = float(vlrapur or 0); dif = float(dif or 0); vlrreceb = float(vlrreceb or 0)
        items.append({
            "seqpessoa": int(seqp) if seqp is not None else None,
            "nome": (nome or "").strip(),
            "seqcontrato": int(seqcontr) if seqcontr is not None else None,
            "seqrede": int(seqrede) if seqrede is not None else None,
            "descricao": (desc or "").strip(),
            "perc": float(perc or 0),
            "vlrnf": round(vlrnf, 2),
            "vlresperado": round(vlresp, 2),
            "vlrapurado": round(vlrapur, 2),
            "diferenca": round(dif, 2),
            "vlrrecebido": round(vlrreceb, 2),
        })
        tot_nf += vlrnf; tot_esp += vlresp; tot_apur += vlrapur; tot_dif += dif; tot_receb += vlrreceb
    resultado["meses"][f"{ano}-{mes:02d}"] = {
        "items": items,
        "totais": {
            "vlrnf": round(tot_nf, 2),
            "vlresperado": round(tot_esp, 2),
            "vlrapurado": round(tot_apur, 2),
            "diferenca": round(tot_dif, 2),
            "vlrrecebido": round(tot_receb, 2),
            "qtd": len(items),
        },
    }
    print(f"{len(items)} fornecedores")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(resultado, f, ensure_ascii=False, separators=(",", ":"))
cur.close(); conn.close()
print(f"\nOK gerado: {OUT}  ({os.path.getsize(OUT):,} bytes)")
