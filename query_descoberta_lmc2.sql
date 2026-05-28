-- =============================================================================
-- DESCOBERTA 2 · ligar a medição LMC a POSTO (empresa) e DATA
-- A view vwfw_medicao_tanque_lmc tem perda/sobra por tanque, mas não tem empresa
-- nem data. Preciso achar essas ligações. Rode as 3 e me mande.
-- =============================================================================

-- ── 1) Colunas da TABELA-BASE medicao_tanque_lmc (deve ter data + id_empresa)
SELECT ordinal_position, column_name, data_type
FROM   information_schema.columns
WHERE  table_name = 'medicao_tanque_lmc'
ORDER  BY ordinal_position;

-- ── 2) Colunas da view de tanque (liga id_tanque → empresa + produto/combustível)
SELECT ordinal_position, column_name, data_type
FROM   information_schema.columns
WHERE  table_name = 'vwfw_tanque_combustivel'
ORDER  BY ordinal_position;

-- ── 3) Amostra do tanque (ver codigo/nome do posto e o produto)
SELECT * FROM vwfw_tanque_combustivel LIMIT 5;
