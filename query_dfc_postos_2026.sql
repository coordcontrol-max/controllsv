-- =============================================================================
-- DFC Postos · regime de caixa · ANO 2026
--
-- Cópia da SQL DFC.sql (Automate) — datas: 2026-01-01..2027-01-01.
-- Roda na "Consulta SQL" do Adaptive → exporta como DFC_Postos.xlsx
-- (precisa conter "DFC" no nome pra o ETL achar). Salva em /Automate/.
-- ETL: etl_dfc_postos_sql.py "/mnt/controller/03 - POSTOS/Automate/DFC_Postos.xlsx"
-- =============================================================================

-- ===== SAÍDAS (títulos a pagar liquidados) — título a título =====
SELECT 'SAIDA' AS fluxo, e.codigo AS posto, e.nome AS posto_nome,
  EXTRACT(YEAR  FROM tf.data_liquidacao)::int AS ano,
  EXTRACT(MONTH FROM tf.data_liquidacao)::int AS mes,
  CASE
    WHEN td.denominacao ILIKE '%TRANSFER%'
      OR tf.denominacao_natureza_titulo ILIKE '%Transfer%' THEN 'Transferências'
    WHEN td.titulo_classificacao IS NOT NULL              THEN td.titulo_classificacao
    WHEN tf.denominacao_natureza_titulo ILIKE '%Compra%'  THEN 'Fornecedores'
    ELSE COALESCE(tf.denominacao_natureza_titulo, 'Outros')
  END AS grupo,
  COALESCE(td.denominacao, tf.denominacao_natureza_titulo) AS conta,
  tf.data_liquidacao AS dt, tf.numero_titulo AS doc,
  tf.nome_credor_devedor AS pessoa, tf.observacao AS obs,
  tf.valor_liquidado AS valor
FROM vwfw_titulo_financeiro tf
LEFT JOIN parcela_despesa_receita p  ON p.id_titulo_financeiro    = tf.id_titulo_financeiro
LEFT JOIN despesa_receita        dr ON dr.id_despesa_receita      = p.id_despesa_receita
LEFT JOIN vwfw_tipo_despesa      td ON td.id_tipo_despesa_receita = dr.id_tipo_despesa_receita
JOIN vw_empresa e ON e.id_empresa = tf.id_empresa
WHERE tf.pagar_receber = 1
  AND tf.data_liquidacao >= DATE '2026-01-01' AND tf.data_liquidacao < DATE '2027-01-01'
  AND tf.valor_liquidado IS NOT NULL

UNION ALL
-- ===== ENTRADAS — cartões/PIX/prazo/receitas (títulos a receber, líquido) — título a título =====
SELECT 'ENTRADA', e.codigo, e.nome,
  EXTRACT(YEAR  FROM tf.data_liquidacao)::int,
  EXTRACT(MONTH FROM tf.data_liquidacao)::int,
  COALESCE(tf.denominacao_natureza_titulo, 'Outros') AS grupo,
  COALESCE(tf.denominacao_natureza_titulo, 'Outros') AS conta,
  tf.data_liquidacao, tf.numero_titulo, tf.nome_credor_devedor, tf.observacao,
  tf.valor_liquidado
FROM vwfw_titulo_financeiro tf
JOIN vw_empresa e ON e.id_empresa = tf.id_empresa
WHERE tf.pagar_receber = 2
  AND tf.id_titulo_filho IS NULL
  AND tf.data_liquidacao >= DATE '2026-01-01' AND tf.data_liquidacao < DATE '2027-01-01'
  AND tf.valor_liquidado IS NOT NULL

UNION ALL
-- ===== ENTRADAS — dinheiro: DEPÓSITO (PROTEGE), POR DIA, positivo =====
SELECT 'ENTRADA', e.codigo, e.nome,
  EXTRACT(YEAR  FROM mf.data_movimento)::int,
  EXTRACT(MONTH FROM mf.data_movimento)::int,
  'Dinheiro' AS grupo, 'Depósito (dinheiro)' AS conta,
  mf.data_movimento, NULL::text, NULL::text, 'Depósito de dinheiro (extrato)'::text,
  SUM(mf.valor_movimento_saida)
FROM vwfw_movimento_financeiro mf
JOIN vw_empresa e ON e.id_empresa = mf.id_empresa
WHERE mf.denominacao_tipo_movto_financ ILIKE '%Dep_sito%'
  AND COALESCE(mf.valor_movimento_saida, 0) > 0
  AND mf.data_movimento >= DATE '2026-01-01' AND mf.data_movimento < DATE '2027-01-01'
GROUP BY e.codigo, e.nome, mf.data_movimento
ORDER BY posto, ano, mes, fluxo, grupo, conta, dt;
