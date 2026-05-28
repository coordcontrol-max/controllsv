-- =============================================================================
-- DESCOBERTA · vwfw_medicao_tanque_lmc (Perdas e Sobras / Variação de Estoque)
-- Rode as 2 e me mande o resultado.
-- =============================================================================

-- ── 1) TODAS as colunas da view (procurar empresa/posto, data, item/produto, perda, sobra)
SELECT ordinal_position, column_name, data_type
FROM   information_schema.columns
WHERE  table_name = 'vwfw_medicao_tanque_lmc'
ORDER  BY ordinal_position;


-- ── 2) AMOSTRA: 5 linhas (pra ver os valores de perda/sobra e como identifica posto/data/item)
SELECT *
FROM   vwfw_medicao_tanque_lmc
LIMIT  5;
