"""Gera JSONs auxiliares pros relatórios de Supermercados:
  • taxas_cartoes.json — bandeiras de cartão, com Tarifa cobrada por mês/empresa
  • comparativo_protege.json — depósitos PROREC (Protege) por mês/empresa

Sem taxa contratual (Supermercados não tem cadastro de taxa negociada como Postos),
então o relatório mostra apenas a Tarifa Cobrada (Bruto − Pago em títulos quitados).
"""
import os, json, datetime as dt
import oracledb
from dotenv import load_dotenv

OUT = "/root/projeto_dre/dados_fluxo_supermercados"
os.makedirs(OUT, exist_ok=True)

load_dotenv("/root/projeto_dre/agente/.env")
oracledb.init_oracle_client(lib_dir=os.environ["ORACLE_CLIENT_DIR"])
dsn = f"{os.environ['ORACLE_HOST']}:{os.environ['ORACLE_PORT']}/{os.environ['ORACLE_SERVICE']}"
conn = oracledb.connect(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"], dsn=dsn)
cur = conn.cursor()
_schema = os.environ.get("ORACLE_SCHEMA", "CONSINCO")
if _schema:
    cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA = {_schema}")

# Mapa NROEMPRESA → descrição da loja (lojas Lxx)
print("[1/3] Carregando mapa NROEMPRESA → loja…")
cur.execute("SELECT NROEMPRESA, NOMEREDUZIDO FROM MAX_EMPRESA")
mapa_emp = {r[0]: r[1] for r in cur.fetchall()}

# Espécies de cartão (CARTAO/CARDEB/CARDIG/TICKET) — bandeiras na descrição
# CODESPECIE_TO_LINHA via FI_ESPECIE
print("[2/3] Descrições de espécies de cartão…")
cur.execute("""
SELECT CODESPECIE, MAX(DESCRICAO)
FROM FI_ESPECIE
WHERE CODESPECIE IN ('CARTAO','CARDEB','CARDIG','TICKET','PROREC','PRORECCB')
GROUP BY CODESPECIE
""")
desc_especie = {r[0]: r[1] for r in cur.fetchall()}

# ── Taxas Cartões: agrega FI_TITULO por (ano, mes, empresa, CODESPECIE)
print("[3/3] Agregando títulos quitados de cartão por mês/empresa…")
cur.execute("""
SELECT
  EXTRACT(YEAR  FROM DTAQUITACAO) AS ANO,
  EXTRACT(MONTH FROM DTAQUITACAO) AS MES,
  NROEMPRESA,
  CODESPECIE,
  COUNT(*) AS QTD,
  SUM(VLRNOMINAL) AS BRUTO,
  SUM(VLRPAGO)    AS PAGO
FROM FI_TITULO
WHERE ABERTOQUITADO = 'Q'
  AND SITUACAO <> 'C'
  AND CODESPECIE IN ('CARTAO','CARDEB','CARDIG','TICKET')
  AND DTAQUITACAO > ADD_MONTHS(SYSDATE, -18)
  AND DTAQUITACAO <= SYSDATE
  AND EXISTS (SELECT 1 FROM FI_TITOPERACAO o
              WHERE o.SEQTITULO = FI_TITULO.SEQTITULO
                AND o.CODOPERACAO IN (5, 6, 16))
GROUP BY EXTRACT(YEAR FROM DTAQUITACAO),
         EXTRACT(MONTH FROM DTAQUITACAO),
         NROEMPRESA,
         CODESPECIE
""")
items_cart = []
for r in cur.fetchall():
    ano, mes, nro, codespecie, qtd, bruto, pago = r
    if ano is None or mes is None: continue
    bruto = float(bruto or 0); pago = float(pago or 0)
    tarifa = bruto - pago
    tx_paga = tarifa / bruto if bruto else 0
    items_cart.append({
        "ano": int(ano), "mes": int(mes),
        "posto": str(int(nro)),
        "loja": mapa_emp.get(int(nro), str(int(nro))),
        "bandeira": desc_especie.get(codespecie, codespecie),
        "codespecie": codespecie,
        "qtd": int(qtd),
        "valor_bruto": round(bruto, 2),
        "valor_liquido": round(pago, 2),
        "tarifa_paga_rs": round(tarifa, 2),
        "tx_paga_pct": round(tx_paga, 6),
        "tx_contr_pct": 0,
        "tarifa_contr_rs": 0,
        "diff_rs": 0,
    })
print(f"  {len(items_cart)} items cartões")
with open(f"{OUT}/taxas_cartoes.json", "w", encoding="utf-8") as f:
    json.dump({"items": items_cart,
               "taxa_contratual": {},
               "geradoEm": dt.datetime.now().isoformat(),
               "obs": "Supermercados não tem cadastro de taxa contratual — só Tarifa Cobrada (Bruto − Pago)."},
              f, ensure_ascii=False)

# ── Comparativo Protege: vendas em dinheiro (CODOPERACAO 920 em FI_CTACORLANCA)
# vs depósito Protege (CODESPECIE PROREC em FI_TITULO quitados).
print("\n[bonus] Comparativo Protege Supermercados…")

# 1) Vendas em dinheiro — FI_CTACORLANCA CODOPERACAO=920
print("  • Vendas em dinheiro (CODOPERACAO 920)…")
# Estas NROEMPRESAs não geram vendas em dinheiro próprias (são holdings/
# entidades agregadoras cujas vendas já são contabilizadas em outras NROEMPRESAs).
# Empresas 1,2,3,4,6,8,12,15,19,25 foram REMOVIDAS dessa exclusão a pedido
# do usuário — elas têm vendas em dinheiro próprias e devem aparecer no relatório.
EMPRESAS_SEM_VENDA_DINHEIRO = (22,)
# Exclusões parciais (nroempresa → ano-mes a partir do qual a venda em dinheiro
# deixa de ser considerada). Empresa 9 (ABWA): a partir de mar/2026 a loja
# parou de operar caixa próprio, então o lançamento OP 920 não bate mais com
# a realidade — usuário pediu pra ignorar.
EXCLUSOES_PARCIAIS_VENDA_DINHEIRO = {
    9: (2026, 5),   # 09-ABWA — a partir de Mai/2026 inclusive (mantém Mar e Abr)
}
# Monta lista SQL ("(22)" ou "(22, 23)") — tuple Python com 1 elemento
# vira "(22,)" e Oracle rejeita por causa da vírgula final.
_sql_not_in = "(" + ", ".join(str(n) for n in EMPRESAS_SEM_VENDA_DINHEIRO) + ")"
cur.execute(f"""
SELECT EXTRACT(YEAR FROM DTALANCTO), EXTRACT(MONTH FROM DTALANCTO),
       NROEMPRESA, COUNT(*), SUM(VLRLANCAMENTO)
FROM FI_CTACORLANCA
WHERE CODOPERACAO = 920
  AND DTALANCTO > ADD_MONTHS(SYSDATE, -18)
  AND DTALANCTO <= SYSDATE
  AND NROEMPRESA NOT IN {_sql_not_in}
GROUP BY EXTRACT(YEAR FROM DTALANCTO),
         EXTRACT(MONTH FROM DTALANCTO),
         NROEMPRESA
""")
vendas = {}
n_excluidos = 0
for r in cur.fetchall():
    ano, mes, nro = int(r[0]), int(r[1]), int(r[2])
    cutoff = EXCLUSOES_PARCIAIS_VENDA_DINHEIRO.get(nro)
    if cutoff and (ano, mes) >= cutoff:
        n_excluidos += 1
        continue
    vendas[(ano, mes, nro)] = {"qtd": int(r[3]), "valor": float(r[4] or 0)}
if n_excluidos:
    print(f"  {n_excluidos} registros excluídos por regra parcial: {EXCLUSOES_PARCIAIS_VENDA_DINHEIRO}")

# 2a) Depósito Protege "regular" — CODESPECIE=PROREC em FI_TITULO quitado
print("  • Depósitos Protege (PROREC quitado)…")
cur.execute("""
SELECT EXTRACT(YEAR FROM DTAQUITACAO), EXTRACT(MONTH FROM DTAQUITACAO),
       NROEMPRESA, COUNT(*), SUM(VLRPAGO)
FROM FI_TITULO
WHERE ABERTOQUITADO = 'Q' AND SITUACAO <> 'C'
  AND CODESPECIE = 'PROREC'
  AND DTAQUITACAO > ADD_MONTHS(SYSDATE, -18)
  AND DTAQUITACAO <= SYSDATE
  AND EXISTS (SELECT 1 FROM FI_TITOPERACAO o
              WHERE o.SEQTITULO = FI_TITULO.SEQTITULO
                AND o.CODOPERACAO IN (5, 6, 16))
GROUP BY EXTRACT(YEAR FROM DTAQUITACAO),
         EXTRACT(MONTH FROM DTAQUITACAO),
         NROEMPRESA
""")
protege = {}
for r in cur.fetchall():
    ano, mes, nro = int(r[0]), int(r[1]), int(r[2])
    protege[(ano, mes, nro)] = {"qtd": int(r[3]), "valor": float(r[4] or 0)}

# 2b) "Recbto de Protege Cash" — FI_CTACORLANCA CODOPERACAO=15
# (Transferência Entre C/C) com HISTORICO contendo PROTEGE/PROTCASH/PROT.CASH/
# PROT CASH e TIPOLANCTO='C' (só o crédito, não dobra o valor da transf).
print("  • Protege Cash (OP 15 + HISTÓRICO PROTEGE/PROTCASH)…")
cur.execute("""
SELECT EXTRACT(YEAR FROM DTALANCTO), EXTRACT(MONTH FROM DTALANCTO),
       NROEMPRESA, COUNT(*), SUM(VLRLANCAMENTO)
FROM FI_CTACORLANCA
WHERE CODOPERACAO = 15
  AND TIPOLANCTO = 'C'
  AND DTALANCTO > ADD_MONTHS(SYSDATE, -18)
  AND DTALANCTO <= SYSDATE
  AND (UPPER(HISTORICO) LIKE '%PROTEGE%'
    OR UPPER(HISTORICO) LIKE '%PROTCASH%'
    OR UPPER(HISTORICO) LIKE '%PROT.CASH%'
    OR UPPER(HISTORICO) LIKE '%PROT CASH%')
GROUP BY EXTRACT(YEAR FROM DTALANCTO),
         EXTRACT(MONTH FROM DTALANCTO),
         NROEMPRESA
""")
protege_cash = {}
for r in cur.fetchall():
    ano, mes, nro = int(r[0]), int(r[1]), int(r[2])
    protege_cash[(ano, mes, nro)] = {"qtd": int(r[3]), "valor": float(r[4] or 0)}
# Soma Protege Cash ao depósito total Protege
for k, v in protege_cash.items():
    if k in protege:
        protege[k]["qtd"] += v["qtd"]
        protege[k]["valor"] += v["valor"]
    else:
        protege[k] = dict(v)
print(f"    {len(protege_cash)} entries Protege Cash adicionadas")

# 3) Combina pelo union das chaves
todas_keys = set(vendas.keys()) | set(protege.keys())
items_prot = []
n_skip_sem_vendas = 0
for k in sorted(todas_keys):
    ano, mes, nro = k
    v = vendas.get(k, {"qtd": 0, "valor": 0})["valor"]
    p = protege.get(k, {"qtd": 0, "valor": 0})["valor"]
    # Em Jan/Fev/2026 as empresas que acabaram de ser incluídas (vendas próprias)
    # podem aparecer só com depósito Protege e vendas=0 — é dado vestigial de
    # quando a venda em dinheiro era contabilizada noutra NROEMPRESA. Pula.
    if ano == 2026 and mes in (1, 2) and v == 0:
        n_skip_sem_vendas += 1
        continue
    diff = v - p
    items_prot.append({
        "ano": ano, "mes": mes,
        "posto": mapa_emp.get(nro, str(nro)),
        "nroempresa": nro,
        "vendas_dinheiro": round(v, 2),
        "depositado_protege": round(p, 2),
        "diferenca": round(diff, 2),
        "diferenca_pct": round((diff / v) if v else 0, 6),
        "qtd_vendas": vendas.get(k, {"qtd": 0})["qtd"],
        "qtd_protege": protege.get(k, {"qtd": 0})["qtd"],
    })
if n_skip_sem_vendas:
    print(f"  {n_skip_sem_vendas} entries Jan/Fev/2026 sem vendas em dinheiro descartados")
print(f"  {len(items_prot)} items totais ({len(vendas)} vendas + {len(protege)} protege)")
with open(f"{OUT}/comparativo_protege.json", "w", encoding="utf-8") as f:
    json.dump({"items": items_prot,
               "geradoEm": dt.datetime.now().isoformat(),
               "obs": "Vendas em dinheiro = FI_CTACORLANCA WHERE CODOPERACAO=920 (Crédito Ref Dinheiro Loja). Depositado Protege = FI_TITULO CODESPECIE=PROREC ABERTOQUITADO=Q. Diferença positiva = vendas > depósitos (dinheiro ainda no cofre/em trânsito)."},
              f, ensure_ascii=False)

print(f"\nOK · arquivos em {OUT}")
