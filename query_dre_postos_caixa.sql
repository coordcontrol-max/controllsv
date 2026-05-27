-- =============================================================================
-- DRE Postos · REGIME DE CAIXA · com detalhamento título-a-título
--
-- Espelha query_dre_postos_competencia.sql mas trocando:
--   • Despesas/Receitas: data_liquidacao + valor_liquidado (regime de caixa)
--     fonte: vwfw_titulo_financeiro + parcela_despesa_receita + despesa_receita
--     + tipo_despesa_receita + categoria_despesa_receita (mantém o mesmo
--     'grupo'/'conta' do plano DRE pra bater 1:1 com a tela de competência).
--   • Vendas: data_movimento (idêntico — venda usa a mesma data nos 2 regimes)
--   • Taxa adm/Tarifa transação cartão: data_liquidacao do título a receber
--
-- Cobre 2025 + 2026 num único export. ETL particiona por ano (filter_ano)
-- e gera 1 JSON por ano: {ano}_caixa.json + despesas_{ano}_caixa.json.
--
-- Roda na "Consulta SQL" do Adaptive (PG 17.4) → exporta como .xls com nome
-- contendo "caixa" (ex: DRE_Postos_Caixa.xls). Salva em /Automate/.
-- ETL: etl_dre_postos_caixa_sql.py
--
-- COLUNAS (14): tipo, posto, posto_nome, ano, mes, grupo, conta,
--   dt, doc, fornecedor, obs, litros, valor, custo
-- =============================================================================

SELECT * FROM (

-- ── 1) DESPESAS / INVESTIMENTOS / RETIRADAS (saídas) — título-a-título ────────
-- Regime de caixa: data = data_liquidacao do título, valor = valor_liquidado.
-- Só títulos efetivamente pagos no período entram.
SELECT
    CASE
        WHEN tdr.codigo LIKE '4.%'                              THEN 'INVESTIMENTO'
        WHEN tdr.codigo LIKE 'RETIRADA%'                        THEN 'RETIRADA'
        WHEN cat.denominacao ILIKE 'RETIRADA%'                  THEN 'RETIRADA'
        ELSE 'DESPESA'
    END                                            AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM tf.data_liquidacao)::int    AS ano,
    EXTRACT(MONTH FROM tf.data_liquidacao)::int    AS mes,
    COALESCE(cat.denominacao, tdr.codigo)          AS grupo,
    tdr.denominacao                                AS conta,
    to_char(tf.data_liquidacao, 'DD/MM/YYYY')      AS dt,
    tf.numero_titulo                               AS doc,
    tf.nome_credor_devedor                         AS fornecedor,
    tf.observacao                                  AS obs,
    NULL::numeric                                  AS litros,
    -- Usa tf.valor_liquidado direto (mesmo padrão do SQL DRE.sql legado em
    -- produção). Títulos com rateio 1:N em parcela_despesa_receita podem
    -- duplicar (efeito conhecido do legado — afeta < 1% dos títulos).
    tf.valor_liquidado                             AS valor,
    NULL::numeric                                  AS custo
FROM vwfw_titulo_financeiro tf
    JOIN parcela_despesa_receita p
                                   ON p.id_titulo_financeiro = tf.id_titulo_financeiro
    JOIN despesa_receita dr        ON dr.id_despesa_receita = p.id_despesa_receita
    JOIN tipo_despesa_receita tdr  ON tdr.id_tipo_despesa_receita = dr.id_tipo_despesa_receita
    LEFT JOIN categoria_despesa_receita cat
                                   ON cat.id_categoria_despesa_receita = tdr.id_categoria_despesa_receita
    JOIN sis_empresa emp           ON emp.id_empresa = tf.id_empresa
WHERE tf.pagar_receber = 1
  AND emp.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND emp.registro_ativo = 'S'
  AND tf.data_liquidacao >= DATE '2025-01-01' AND tf.data_liquidacao < DATE '2027-01-01'
  AND tf.valor_liquidado IS NOT NULL
  AND COALESCE(tf.titulo_situacao, '') <> 'Cancelado'

UNION ALL

-- ── 2) RECEITAS (título-a-título) ─────────────────────────────────────────────
SELECT
    'RECEITA'                                      AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM tf.data_liquidacao)::int    AS ano,
    EXTRACT(MONTH FROM tf.data_liquidacao)::int    AS mes,
    COALESCE(cat.denominacao, tdr.codigo)          AS grupo,
    tdr.denominacao                                AS conta,
    to_char(tf.data_liquidacao, 'DD/MM/YYYY')      AS dt,
    tf.numero_titulo                               AS doc,
    tf.nome_credor_devedor                         AS fornecedor,
    tf.observacao                                  AS obs,
    NULL::numeric                                  AS litros,
    tf.valor_liquidado                             AS valor,
    NULL::numeric                                  AS custo
FROM vwfw_titulo_financeiro tf
    JOIN parcela_despesa_receita p
                                   ON p.id_titulo_financeiro = tf.id_titulo_financeiro
    JOIN despesa_receita dr        ON dr.id_despesa_receita = p.id_despesa_receita
    JOIN tipo_despesa_receita tdr  ON tdr.id_tipo_despesa_receita = dr.id_tipo_despesa_receita
    LEFT JOIN categoria_despesa_receita cat
                                   ON cat.id_categoria_despesa_receita = tdr.id_categoria_despesa_receita
    JOIN sis_empresa emp           ON emp.id_empresa = tf.id_empresa
WHERE tf.pagar_receber = 2
  AND emp.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND emp.registro_ativo = 'S'
  AND tf.data_liquidacao >= DATE '2025-01-01' AND tf.data_liquidacao < DATE '2027-01-01'
  AND tf.valor_liquidado IS NOT NULL
  AND COALESCE(tf.titulo_situacao, '') <> 'Cancelado'

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
WHERE v.data_movimento >= DATE '2025-01-01' AND v.data_movimento < DATE '2027-01-01'
GROUP BY 1, 2, 3, 4, 5, 6, 7

UNION ALL

-- ── 4) TAXA DE ADMINISTRAÇÃO PAGA (cartão, somada) ────────────────────────────
-- Em caixa usa data_liquidacao do título a receber (data do depósito do cartão).
SELECT
    'DESPESA'                                      AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM tf.data_liquidacao)::int    AS ano,
    EXTRACT(MONTH FROM tf.data_liquidacao)::int    AS mes,
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
  AND tf.data_liquidacao >= DATE '2025-01-01' AND tf.data_liquidacao < DATE '2027-01-01'
  AND COALESCE(tf.valor_taxa_administracao, 0) <> 0
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11

UNION ALL

-- ── 5) TARIFA DE TRANSAÇÃO PAGA (cartão, somada) ──────────────────────────────
SELECT
    'DESPESA'                                      AS tipo,
    emp.codigo                                     AS posto,
    emp.nome                                       AS posto_nome,
    EXTRACT(YEAR  FROM tf.data_liquidacao)::int    AS ano,
    EXTRACT(MONTH FROM tf.data_liquidacao)::int    AS mes,
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
  AND tf.data_liquidacao >= DATE '2025-01-01' AND tf.data_liquidacao < DATE '2027-01-01'
  AND COALESCE(tf.tarifa_transacao, 0) <> 0
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11

) q
WHERE q.ano IN (2025, 2026)
ORDER BY 1, 2, 4, 5, 6, 7, 8
