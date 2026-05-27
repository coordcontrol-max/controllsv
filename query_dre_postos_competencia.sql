-- =============================================================================
-- DRE Postos · REGIME DE COMPETÊNCIA · com detalhamento título-a-título
--
-- Espelha "SQL DRE.sql" do Automate (regime de caixa), mas trocando a data:
--   • Despesas/Receitas: data_emissao  (via vwfw_despesa / vwfw_receita)
--   • Vendas:            data_movimento (igual ao caixa — venda = mesma data
--                        de emissão da NF nos dois regimes)
--   • Taxa adm/Tarifa transação cartão: data_emissao do título a receber
--     (em caixa é data_liquidacao)
--
-- Cobre 2025 + 2026 num único export — o ETL particiona por ano e gera 1 JSON
-- por ano (2025_competencia.json + 2026_competencia.json).
--
-- Roda na "Consulta SQL" do Adaptive (PG 17.4) → exporta como .xls com nome
-- contendo "competencia" (ex: DRE_Postos_Competencia.xls).
-- ETL: etl_dre_postos_competencia_sql.py
--
-- COLUNAS (14, mantenha estes nomes):
--   tipo, posto, posto_nome, ano, mes, grupo, conta,
--   dt, doc, fornecedor, obs, litros, valor, custo
-- =============================================================================

SELECT * FROM (

-- ── 1) DESPESAS / INVESTIMENTOS / RETIRADAS (saídas) — uma linha por título ──
SELECT
    CASE
        WHEN tdr.codigo LIKE '4.%'                              THEN 'INVESTIMENTO'
        WHEN tdr.codigo LIKE 'RETIRADA%'                        THEN 'RETIRADA'
        WHEN cat.denominacao ILIKE 'RETIRADA%'                  THEN 'RETIRADA'
        ELSE 'DESPESA'
    END                                            AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM d.data_despesa_receita)::int  AS ano,
    EXTRACT(MONTH FROM d.data_despesa_receita)::int  AS mes,
    COALESCE(cat.denominacao, tdr.codigo)          AS grupo,
    tdr.denominacao                                AS conta,
    to_char(d.data_despesa_receita, 'DD/MM/YYYY')  AS dt,
    d.numero_documento                             AS doc,
    d.nome_pessoa                                  AS fornecedor,
    d.observacao                                   AS obs,
    NULL::numeric                                  AS litros,
    d.valor_despesa_receita                        AS valor,
    NULL::numeric                                  AS custo
FROM vwfw_despesa              d
    JOIN sis_empresa           emp ON emp.id_empresa = d.id_empresa
    JOIN tipo_despesa_receita  tdr ON tdr.id_tipo_despesa_receita = d.id_tipo_despesa_receita
    LEFT JOIN categoria_despesa_receita cat
                                   ON cat.id_categoria_despesa_receita = tdr.id_categoria_despesa_receita
WHERE emp.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND emp.registro_ativo = 'S'
  AND d.data_despesa_receita BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
  AND COALESCE(d.titulo_situacao, '') <> 'Cancelado'

UNION ALL

-- ── 2) RECEITAS (rendimentos, ajustes, devoluções de taxa) — título a título ──
SELECT
    'RECEITA'                                      AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM r.data_despesa_receita)::int  AS ano,
    EXTRACT(MONTH FROM r.data_despesa_receita)::int  AS mes,
    COALESCE(cat.denominacao, tdr.codigo)          AS grupo,
    tdr.denominacao                                AS conta,
    to_char(r.data_despesa_receita, 'DD/MM/YYYY')  AS dt,
    r.numero_documento                             AS doc,
    r.nome_pessoa                                  AS fornecedor,
    r.observacao                                   AS obs,
    NULL::numeric                                  AS litros,
    r.valor_despesa_receita                        AS valor,
    NULL::numeric                                  AS custo
FROM vwfw_receita              r
    JOIN sis_empresa           emp ON emp.id_empresa = r.id_empresa
    JOIN tipo_despesa_receita  tdr ON tdr.id_tipo_despesa_receita = r.id_tipo_despesa_receita
    LEFT JOIN categoria_despesa_receita cat
                                   ON cat.id_categoria_despesa_receita = tdr.id_categoria_despesa_receita
WHERE emp.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND emp.registro_ativo = 'S'
  AND r.data_despesa_receita BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
  AND COALESCE(r.titulo_situacao, '') <> 'Cancelado'

UNION ALL

-- ── 3) VENDAS (somadas por produto) — mesma data nos dois regimes ─────────────
SELECT
    'VENDA'                                        AS tipo,
    v.codigo_empresa                               AS posto,
    v.nome_empresa                                 AS posto_nome,
    EXTRACT(YEAR  FROM v.data_movimento)::int      AS ano,
    EXTRACT(MONTH FROM v.data_movimento)::int      AS mes,
    'Total das Vendas'                             AS grupo,
    CASE WHEN v.combustivel THEN UPPER(v.denominacao_item)
         ELSE 'Outros Produtos' END                AS conta,
    NULL::text                                     AS dt,
    NULL::text                                     AS doc,
    NULL::text                                     AS fornecedor,
    NULL::text                                     AS obs,
    SUM(v.quantidade_item_venda)                   AS litros,
    SUM(v.total_item)                              AS valor,
    SUM(v.custo)                                   AS custo
FROM vw_venda v
WHERE v.data_movimento BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
GROUP BY 1, 2, 3, 4, 5, 6, 7

UNION ALL

-- ── 4) TAXA DE ADMINISTRAÇÃO PAGA (cartão, somada) ────────────────────────────
-- Em competência usa data_emissao do título a receber (data da venda no cartão)
SELECT
    'DESPESA'                                      AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM tf.data_emissao)::int       AS ano,
    EXTRACT(MONTH FROM tf.data_emissao)::int       AS mes,
    'OUTRAS DESPESAS'                              AS grupo,
    'TAXA DE ADMINISTRAÇÃO PAGA'                   AS conta,
    NULL::text                                     AS dt,
    NULL::text                                     AS doc,
    '(cartão)'                                     AS fornecedor,
    NULL::text                                     AS obs,
    NULL::numeric                                  AS litros,
    SUM(tf.valor_taxa_administracao)               AS valor,
    NULL::numeric                                  AS custo
FROM vwfw_titulo_financeiro tf
    JOIN sis_empresa emp ON emp.id_empresa = tf.id_empresa
WHERE tf.pagar_receber = 2
  AND tf.id_titulo_filho IS NULL
  AND emp.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND emp.registro_ativo = 'S'
  AND tf.data_emissao BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
  AND COALESCE(tf.valor_taxa_administracao, 0) <> 0
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11

UNION ALL

-- ── 5) TARIFA DE TRANSAÇÃO PAGA (cartão, somada) ──────────────────────────────
SELECT
    'DESPESA'                                      AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM tf.data_emissao)::int       AS ano,
    EXTRACT(MONTH FROM tf.data_emissao)::int       AS mes,
    'OUTRAS DESPESAS'                              AS grupo,
    'TARIFA DE TRANSAÇÃO PAGA'                     AS conta,
    NULL::text                                     AS dt,
    NULL::text                                     AS doc,
    '(cartão)'                                     AS fornecedor,
    NULL::text                                     AS obs,
    NULL::numeric                                  AS litros,
    SUM(tf.tarifa_transacao)                       AS valor,
    NULL::numeric                                  AS custo
FROM vwfw_titulo_financeiro tf
    JOIN sis_empresa emp ON emp.id_empresa = tf.id_empresa
WHERE tf.pagar_receber = 2
  AND tf.id_titulo_filho IS NULL
  AND emp.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND emp.registro_ativo = 'S'
  AND tf.data_emissao BETWEEN DATE '2025-01-01' AND DATE '2026-12-31'
  AND COALESCE(tf.tarifa_transacao, 0) <> 0
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11

) q
-- Filtro final de segurança: vwfw_titulo_financeiro às vezes expõe data_emissao
-- derivada de parcelas históricas, escapando do BETWEEN nos blocos de cartão.
WHERE q.ano IN (2025, 2026)
ORDER BY 1, 2, 4, 5, 6, 7, 8;
