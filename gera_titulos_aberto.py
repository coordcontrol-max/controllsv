"""Gera snapshot JSON dos titulos em aberto (Direito/Obrigacao).

Datasets gerados em /root/projeto_dre/titulos_aberto_data.json:
  - agg:         agregado especie x ano-venc x mes-venc x empresa x OD
  - especies:    {codespecie: descricao}
  - empresas:    [{nro, nome}]
  - aging:       {D:{venc, 0_30, 31_60, 61_90, mais_90, total}, O:{...}}
  - proximos7d:  top titulos com vencimento nos proximos 7 dias (separados D/O)
  - top5Atraso:  top 5 fornecedores com obrigacoes vencidas
  - porDia:      {YYYY-MM-DD: {D: saldo, O: saldo}}  (para projecao no DFC diario)
  - porDiaLinha: {YYYY-MM-DD: {linha-nome: saldo}}   (per-linha do DFC, sinal D=+/O=-)
"""
import os, sys, json, datetime as dt
import oracledb
from dotenv import load_dotenv

# Reusa o mapa CODESPECIE -> LINHA do classifier oficial do agente
sys.path.insert(0, "/root/projeto_dre/agente")
from classifier_fluxo import (
    CODESPECIE_TO_LINHA_FLUXO,
    CARTAO_PROPRIO_RAZOES,
    CODESPECIE_IGNORAR_FLUXO,
    MUTUO_ENTRE_GRUPOS_RAZOES,
)

load_dotenv("/root/projeto_dre/agente/.env")
oracledb.init_oracle_client(lib_dir=os.environ["ORACLE_CLIENT_DIR"])
dsn = f"{os.environ['ORACLE_HOST']}:{os.environ['ORACLE_PORT']}/{os.environ['ORACLE_SERVICE']}"
conn = oracledb.connect(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"], dsn=dsn)
cur = conn.cursor()

# 1) AGREGADO POR especie x ano x mes x empresa
print("[1/6] Agregado por especie x ano x mes x empresa...")
cur.execute("""
SELECT t.OBRIGDIREITO, t.CODESPECIE,
       EXTRACT(YEAR  FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)) AS ANO,
       EXTRACT(MONTH FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)) AS MES,
       t.NROEMPRESA,
       COUNT(*) AS QTD,
       SUM(t.VLRNOMINAL) AS VN,
       SUM(t.VLRPAGO) AS VP,
       SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD,
       SUM(CASE WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) < TRUNC(SYSDATE)
                THEN t.VLRNOMINAL - t.VLRPAGO ELSE 0 END) AS SLD_VENC
FROM   FI_TITULO t
WHERE  t.ABERTOQUITADO = 'A' AND t.SITUACAO <> 'C'
  AND  t.OBRIGDIREITO IN ('D','O')

GROUP BY t.OBRIGDIREITO, t.CODESPECIE,
         EXTRACT(YEAR FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)),
         EXTRACT(MONTH FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)),
         t.NROEMPRESA
""")
agg = [{
    "od": r[0], "cod": r[1],
    "ano": int(r[2]) if r[2] is not None else None,
    "mes": int(r[3]) if r[3] is not None else None,
    "emp": int(r[4]) if r[4] is not None else None,
    "qtd": int(r[5]),
    "vn":  round(float(r[6] or 0), 2),
    "vp":  round(float(r[7] or 0), 2),
    "sld": round(float(r[8] or 0), 2),
    "vnc": round(float(r[9] or 0), 2),
} for r in cur.fetchall()]
print(f"  {len(agg):,} linhas")

# 2) Descricoes de especies
print("[2/6] Descricoes de especies...")
cur.execute("""
SELECT CODESPECIE, MAX(DESCRICAO) FROM FI_ESPECIE
WHERE  CODESPECIE IN (SELECT DISTINCT CODESPECIE FROM FI_TITULO
                     WHERE ABERTOQUITADO='A' AND SITUACAO<>'C'
                       )
GROUP BY CODESPECIE
""")
desc_especie = {r[0]: (r[1] or r[0]) for r in cur.fetchall()}
print(f"  {len(desc_especie)} especies")

# 3) Empresas
print("[3/6] Empresas...")
cur.execute("""
SELECT NROEMPRESA, NOMEREDUZIDO FROM MAX_EMPRESA
WHERE NROEMPRESA IN (SELECT DISTINCT NROEMPRESA FROM FI_TITULO
                    WHERE ABERTOQUITADO='A' AND SITUACAO<>'C'
                      )
ORDER BY NROEMPRESA
""")
empresas = [{"nro": int(r[0]), "nome": (r[1] or f"Empresa {r[0]}").strip()} for r in cur.fetchall()]
print(f"  {len(empresas)} empresas")

# 4) AGING por faixa
print("[4/6] Aging por faixa...")
cur.execute("""
SELECT t.OBRIGDIREITO,
       CASE
         WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <  TRUNC(SYSDATE)                                       THEN 'V'
         WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <= TRUNC(SYSDATE) + 30                                  THEN 'A30'
         WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <= TRUNC(SYSDATE) + 60                                  THEN 'A60'
         WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <= TRUNC(SYSDATE) + 90                                  THEN 'A90'
         ELSE 'A90P'
       END AS FAIXA,
       SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD,
       COUNT(*) AS QTD
FROM   FI_TITULO t
WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C' AND t.OBRIGDIREITO IN ('D','O')
GROUP BY t.OBRIGDIREITO,
         CASE
           WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <  TRUNC(SYSDATE)                                       THEN 'V'
           WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <= TRUNC(SYSDATE) + 30                                  THEN 'A30'
           WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <= TRUNC(SYSDATE) + 60                                  THEN 'A60'
           WHEN NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) <= TRUNC(SYSDATE) + 90                                  THEN 'A90'
           ELSE 'A90P'
         END
""")
aging = {"D": {}, "O": {}}
for r in cur.fetchall():
    aging[r[0]][r[1]] = {"sld": round(float(r[2] or 0), 2), "qtd": int(r[3])}
print(f"  ok ({len(aging['D'])} faixas D, {len(aging['O'])} faixas O)")

# 5) PROXIMOS 7 DIAS — top titulos por valor (com nome da pessoa)
# Top 10 de cada lado (D/O) via ROW_NUMBER particionado pra garantir que
# nenhum lado fique zerado quando o outro tem muitos títulos.
print("[5/6] Proximos 7 dias com nome...")
cur.execute("""
SELECT OBRIGDIREITO, CODESPECIE, DTAPROGRAMADA, NROTITULO, NOMERAZAO, SLD
FROM (
  SELECT t.OBRIGDIREITO, t.CODESPECIE,
         NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) AS DTAPROGRAMADA,
         t.NROTITULO,
         p.NOMERAZAO,
         (t.VLRNOMINAL - t.VLRPAGO) AS SLD,
         ROW_NUMBER() OVER (
           PARTITION BY t.OBRIGDIREITO
           ORDER BY (t.VLRNOMINAL - t.VLRPAGO) DESC
         ) AS RN
  FROM   FI_TITULO t
  JOIN   GE_PESSOA p ON p.SEQPESSOA = t.SEQPESSOA
  WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C'
    AND  t.OBRIGDIREITO IN ('D','O')
    AND  t.CODESPECIE NOT IN ('RECNFC','PAGNFC','DESP9','DESP91',
                              'JURFOR','PDDFOR','CREJUD','BONIAC')
    AND  NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE) + 7
    AND  (t.VLRNOMINAL - t.VLRPAGO) > 0
) WHERE RN <= 30
ORDER BY OBRIGDIREITO, SLD DESC
""")
proximos7d = []
for r in cur.fetchall():
    proximos7d.append({
        "od":   r[0],
        "cod":  r[1],
        "dta":  r[2].strftime("%Y-%m-%d") if r[2] else None,
        "nro":  int(r[3]) if r[3] is not None else None,
        "nome": (r[4] or "").strip(),
        "sld":  round(float(r[5] or 0), 2),
    })
print(f"  {len(proximos7d)} titulos")

# 6) TOP 5 fornecedores em atraso — Direitos vencidos de Recbto de Contratos.
# User pediu: filtrar somente fornecedores nas CODESPECIEs de "Recbto de Contratos"
# (acordos comerciais, bonificações etc.) — ou seja, fornecedores que estão
# devendo recebimentos contratuais para nós.
CODESPECIES_RECBTO_CONTRATOS = [
    "ACRA22","ACRA23","ACRA24","ACRA25","ACRA26",
    "ACRCOM","ACREX2","ACRFOR","ACRINA","ACRINT","ACRLOG","ACRMGM","ACRMKT",
    "ACRPEN","ACRPON","ACRPRE","ACRQUE","ACRTRO","ACRXTR",
    "CONTRT","DEVREC","DUPR",
    # user pediu pra desconsiderar: "JURFOR","PDDFOR","CREJUD","BONIAC"
]
print("[6/6] Top 5 fornecedores em atraso (Recbto de Contratos)...")
codes_in = ",".join(f"'{c}'" for c in CODESPECIES_RECBTO_CONTRATOS)
cur.execute(f"""
SELECT * FROM (
  SELECT t.SEQPESSOA,
         p.NOMERAZAO,
         SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD,
         MAX(TRUNC(SYSDATE) - NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)) AS DIAS_MAX,
         COUNT(*) AS QTD
  FROM   FI_TITULO t
  JOIN   GE_PESSOA p ON p.SEQPESSOA = t.SEQPESSOA
  WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C' AND t.OBRIGDIREITO='D'
    AND  t.CODESPECIE IN ({codes_in})
    AND  NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) < TRUNC(SYSDATE)
    AND  (t.VLRNOMINAL - t.VLRPAGO) > 0
  GROUP BY t.SEQPESSOA, p.NOMERAZAO
  ORDER BY SLD DESC
) WHERE ROWNUM <= 30
""")
top5_atraso = []
for r in cur.fetchall():
    top5_atraso.append({
        "seqpessoa": int(r[0]) if r[0] is not None else None,
        "nome":      (r[1] or "").strip(),
        "sld":       round(float(r[2] or 0), 2),
        "dias_max":  int(r[3]) if r[3] is not None else 0,
        "qtd":       int(r[4]),
    })

# 6b) Detalhe título-a-título dos top 30 fornecedores (drill-down do modal).
# Sem janela de data — pega TODOS os títulos vencidos por seqpessoa, pois
# alguns fornecedores estão com 700+ dias de atraso e o detalhe.json normal
# só cobre 30 dias passados.
top30_detalhe = {}
if top5_atraso:
    seqs = [a["seqpessoa"] for a in top5_atraso if a["seqpessoa"] is not None]
    if seqs:
        seqs_in = ",".join(str(s) for s in seqs)
        print(f"[6b/6] Detalhe título-a-título dos {len(seqs)} top fornecedores...")
        cur.execute(f"""
        SELECT t.SEQPESSOA,
               t.CODESPECIE,
               TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD') AS DTA,
               t.NROEMPRESA,
               t.NROTITULO,
               t.SERIETITULO,
               t.NROPARCELA,
               (t.VLRNOMINAL - t.VLRPAGO) AS SLD,
               (TRUNC(SYSDATE) - NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)) AS DIAS,
               t.OBSERVACAO
        FROM   FI_TITULO t
        WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C' AND t.OBRIGDIREITO='D'
          AND  t.CODESPECIE IN ({codes_in})
          AND  NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) < TRUNC(SYSDATE)
          AND  (t.VLRNOMINAL - t.VLRPAGO) > 0
          AND  t.SEQPESSOA IN ({seqs_in})
        ORDER BY t.SEQPESSOA, NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)
        """)
        for r in cur.fetchall():
            seqp, cod, dta, nro_emp, nrotit, serie, parc, sld_raw, dias, obs = r
            obs_str = None
            if obs is not None:
                try: obs_str = obs.read() if hasattr(obs, "read") else str(obs)
                except Exception: obs_str = None
            key = str(int(seqp))
            top30_detalhe.setdefault(key, []).append({
                "cod":   cod,
                "dta":   dta,
                "emp":   int(nro_emp) if nro_emp is not None else None,
                "nro":   int(nrotit) if nrotit is not None else None,
                "serie": (serie or "").strip() or None,
                "parc":  (parc or "").strip() or None,
                "sld":   round(float(sld_raw or 0), 2),
                "dias":  int(dias) if dias is not None else 0,
                "obs":   (obs_str or "").strip() or None,
            })
        print(f"  {sum(len(v) for v in top30_detalhe.values())} títulos para {len(top30_detalhe)} fornecedores")
print(f"  {len(top5_atraso)} fornecedores")

# 7) SALDO POR DIA (agregado D/O) — para Recebimentos/Pagamentos no diario
# 8) SALDO POR DIA x LINHA do DFC — para distribuir titulos nas linhas reais
# Janela: 90 dias atras / 365 futuro (cobre todo o resto do ano)
print("[7/8] Saldo por dia (D/O)...")
cur.execute("""
SELECT t.OBRIGDIREITO,
       TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD') AS DTA,
       SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD,
       COUNT(*) AS QTD
FROM   FI_TITULO t
WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C'
  AND  t.OBRIGDIREITO IN ('D','O')

  AND  NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) BETWEEN TRUNC(SYSDATE) - 90 AND TRUNC(SYSDATE) + 365
GROUP BY t.OBRIGDIREITO, TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD')
""")
por_dia = {}
for r in cur.fetchall():
    dta = r[1]
    od  = r[0]
    if dta not in por_dia: por_dia[dta] = {}
    por_dia[dta][od] = {"sld": round(float(r[2] or 0), 2), "qtd": int(r[3])}
print(f"  {len(por_dia)} dias")

print("[8a/8] Detalhe titulo-a-titulo (TODOS os titulos em aberto)...")
# Alimenta o modal de Detalhamento (DFC Diario + cards de Titulos em Aberto do
# BP). SEM janela de vencimento — precisa cobrir TODO o universo em aberto
# (inclusive vencidos antigos) pra bater com o agregado por especie/aging.
cur.execute("""
SELECT t.OBRIGDIREITO, t.CODESPECIE,
       TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD') AS DTA,
       t.NROEMPRESA, t.NROTITULO, t.SERIETITULO, t.NROPARCELA,
       UPPER(NVL(p.NOMERAZAO, '')) AS NOMERAZAO,
       p.SEQPESSOA,
       (t.VLRNOMINAL - t.VLRPAGO) AS SLD,
       t.OBSERVACAO
FROM   FI_TITULO t
JOIN   GE_PESSOA p ON p.SEQPESSOA = t.SEQPESSOA
WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C'
  AND  t.OBRIGDIREITO IN ('D','O')
  AND  (t.VLRNOMINAL - t.VLRPAGO) <> 0
""")
det = []
for r in cur.fetchall():
    od, cod, dta, nro_emp, nrotit, serie, parc, razao, seqp, sld_raw, obs = r
    if cod in CODESPECIE_IGNORAR_FLUXO:
        continue
    linha = CODESPECIE_TO_LINHA_FLUXO.get(cod)  # pode ser None (espécie sem linha DFC) — mantém p/ drilldown por espécie
    if cod == "CARTAO":
        if any(p in (razao or "") for p in CARTAO_PROPRIO_RAZOES):
            linha = "Recbto de Venda em Cartão Próprio"
    if cod in ("MUTPAG", "MUTREC"):
        if any(p in (razao or "") for p in MUTUO_ENTRE_GRUPOS_RAZOES):
            linha = "Mutuo A Pagar (entre grupos)" if cod == "MUTPAG" else "Mutuo A Receber (entre grupos)"
    val = -float(sld_raw or 0) if od == "O" else float(sld_raw or 0)
    obs_str = None
    if obs is not None:
        try: obs_str = obs.read() if hasattr(obs, "read") else str(obs)
        except Exception: obs_str = None
    det.append({
        "dta":   dta,
        "linha": linha,
        "emp":   int(nro_emp) if nro_emp is not None else None,
        "nro":   int(nrotit) if nrotit is not None else None,
        "serie": (serie or "").strip() or None,
        "parc":  (parc or "").strip() or None,
        "seqp":  int(seqp) if seqp is not None else None,
        "nome":  (razao or "").strip(),
        "cod":   cod,
        "sld":   round(val, 2),
        "obs":   (obs_str or "").strip() or None,
    })
det_path = "/root/projeto_dre/titulos_aberto_detalhe.json"
with open(det_path, "w", encoding="utf-8") as f:
    json.dump({"geradoEm": dt.datetime.now().isoformat(timespec="seconds"), "items": det},
              f, ensure_ascii=False, separators=(",", ":"))
print(f"  {len(det):,} titulos | gravado em {det_path} ({os.path.getsize(det_path):,} bytes)")

print("[8/8] Saldo por dia x linha do DFC...")
# Pra CARTAO precisamos do nomerazao pra detectar cartao proprio (DM/FortBrasil).
cur.execute("""
SELECT t.OBRIGDIREITO,
       t.CODESPECIE,
       TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD') AS DTA,
       UPPER(NVL(p.NOMERAZAO, '')) AS NOMERAZAO,
       SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD,
       COUNT(*) AS QTD
FROM   FI_TITULO t
JOIN   GE_PESSOA p ON p.SEQPESSOA = t.SEQPESSOA
WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C'
  AND  t.OBRIGDIREITO IN ('D','O')

  AND  NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO) BETWEEN TRUNC(SYSDATE) - 90 AND TRUNC(SYSDATE) + 365
GROUP BY t.OBRIGDIREITO, t.CODESPECIE,
         TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD'),
         UPPER(NVL(p.NOMERAZAO, ''))
""")
por_dia_linha = {}
nao_mapeados = {}
for r in cur.fetchall():
    od, cod, dta, razao, sld_raw, qtd = r[0], r[1], r[2], r[3], float(r[4] or 0), int(r[5])
    if cod in CODESPECIE_IGNORAR_FLUXO:
        continue
    linha = CODESPECIE_TO_LINHA_FLUXO.get(cod)
    if not linha:
        nao_mapeados[cod] = nao_mapeados.get(cod, 0) + 1
        continue
    # Cartao proprio: CARTAO + adquirente DM/FortBrasil
    if cod == "CARTAO":
        if any(p in (razao or "") for p in CARTAO_PROPRIO_RAZOES):
            linha = "Recbto de Venda em Cartão Próprio"
    if cod in ("MUTPAG", "MUTREC"):
        if any(p in (razao or "") for p in MUTUO_ENTRE_GRUPOS_RAZOES):
            linha = "Mutuo A Pagar (entre grupos)" if cod == "MUTPAG" else "Mutuo A Receber (entre grupos)"
    # Sinal: 'O' (obrigacao) = saida, valor negativo. 'D' = entrada, positivo.
    val = -sld_raw if od == "O" else sld_raw
    bucket = por_dia_linha.setdefault(dta, {})
    bucket[linha] = round(bucket.get(linha, 0.0) + val, 2)
print(f"  {len(por_dia_linha)} dias, {sum(len(v) for v in por_dia_linha.values())} entradas linha/dia")
if nao_mapeados:
    top = sorted(nao_mapeados.items(), key=lambda x: -x[1])[:10]
    print(f"  ⚠ codespecies sem mapeamento (top 10): {top}")

print("[9/9] Por fornecedor (todos os títulos em aberto, D + O)...")
cur.execute("""
SELECT t.OBRIGDIREITO,
       t.SEQPESSOA,
       MAX(p.NOMERAZAO) AS NOMERAZAO,
       t.CODESPECIE,
       EXTRACT(YEAR  FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)) AS ANO,
       EXTRACT(MONTH FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)) AS MES,
       COUNT(*) AS QTD,
       SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD
FROM   FI_TITULO t
JOIN   GE_PESSOA p ON p.SEQPESSOA = t.SEQPESSOA
WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C'
  AND  t.OBRIGDIREITO IN ('D','O')

GROUP BY t.OBRIGDIREITO, t.SEQPESSOA, t.CODESPECIE,
         EXTRACT(YEAR FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO)),
         EXTRACT(MONTH FROM NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO))
""")
abertoPorFornecedor = []
for r in cur.fetchall():
    od, seqp, nome, cod, ano_v, mes_v, qtd, sld = r
    abertoPorFornecedor.append({
        "od":   od,
        "seqp": int(seqp) if seqp is not None else None,
        "nome": (nome or "").strip(),
        "cod":  cod,
        "ano":  int(ano_v) if ano_v is not None else None,
        "mes":  int(mes_v) if mes_v is not None else None,
        "qtd":  int(qtd),
        "sld":  round(float(sld or 0), 2),
    })
print(f"  {len(abertoPorFornecedor):,} linhas (fornecedor × CODESPECIE × ano/mês × OD)")

print("[10/10] Agregado espécie × dia de vencimento × OD (todo o período)...")
# Alimenta o filtro de CODESPECIE + período (data EXATA de vencimento) dos cards
# de Títulos em Aberto no Balanço Patrimonial. Cobre TODOS os títulos em aberto
# (sem janela de data), agregado por dia de vencimento -> ~3,5k linhas / ~0,3 MB,
# leve o bastante pra ir pro cliente e filtrar lá em tempo real.
cur.execute("""
SELECT t.OBRIGDIREITO, t.CODESPECIE,
       TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD') AS DTA,
       SUM(t.VLRNOMINAL - t.VLRPAGO) AS SLD,
       COUNT(*) AS QTD
FROM   FI_TITULO t
WHERE  t.ABERTOQUITADO='A' AND t.SITUACAO<>'C'
  AND  t.OBRIGDIREITO IN ('D','O')
GROUP BY t.OBRIGDIREITO, t.CODESPECIE,
         TO_CHAR(NVL(t.DTAPROGRAMADA, t.DTAVENCIMENTO), 'YYYY-MM-DD')
""")
agg_dia = [{
    "od":  r[0],
    "cod": r[1],
    "dta": r[2],
    "sld": round(float(r[3] or 0), 2),
    "qtd": int(r[4]),
} for r in cur.fetchall()]
print(f"  {len(agg_dia):,} linhas (espécie × dia × OD)")

cur.close(); conn.close()

agora_iso = dt.datetime.now().isoformat(timespec="seconds")
hoje_iso = dt.date.today().isoformat()

payload = {
    "geradoEm":   agora_iso,
    "hoje":       hoje_iso,
    "agg":        agg,
    "aggDia":     agg_dia,
    "especies":   desc_especie,
    "empresas":   empresas,
    "aging":      aging,
    "proximos7d": proximos7d,
    "abertoPorFornecedor": abertoPorFornecedor,
    "top5Atraso": top5_atraso,
    "top30AtrasoDetalhe": top30_detalhe,
    "porDia":     por_dia,
    "porDiaLinha": por_dia_linha,
}

out_path = "/root/projeto_dre/titulos_aberto_data.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
print(f"\nOK gerado: {out_path}  ({os.path.getsize(out_path):,} bytes)")
