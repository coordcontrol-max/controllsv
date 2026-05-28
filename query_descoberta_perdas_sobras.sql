-- =============================================================================
-- DESCOBERTA · Perdas e Sobras das Medições dos Tanques (Variação de Estoque)
-- Rode UMA POR VEZ na "Consulta SQL" do Adaptive e me mande o resultado.
-- Objetivo: achar a tabela/view por trás do relatório "Relação Perdas e Sobras
-- das Medições dos Tanques nas Vendas de Combustíveis".
-- =============================================================================

-- ── 1) TABELAS/VIEWS candidatas (perda, sobra, medição, tanque, encerrante, afericão)
SELECT table_schema, table_name, table_type
FROM   information_schema.tables
WHERE  table_name ILIKE '%perda%'    OR table_name ILIKE '%sobra%'
   OR  table_name ILIKE '%medic%'    OR table_name ILIKE '%medi__o%'
   OR  table_name ILIKE '%tanque%'   OR table_name ILIKE '%encerrante%'
   OR  table_name ILIKE '%aferic%'   OR table_name ILIKE '%afericao%'
   OR  table_name ILIKE '%estoque%combust%' OR table_name ILIKE '%combust%estoque%'
ORDER  BY table_type DESC, table_name;


-- ── 2) COLUNAS com "perda"/"sobra"/"medicao" em qualquer tabela
SELECT table_name, column_name, data_type
FROM   information_schema.columns
WHERE  column_name ILIKE '%perda%' OR column_name ILIKE '%sobra%'
   OR  column_name ILIKE '%medic%' OR column_name ILIKE '%afericao%'
   OR  column_name ILIKE '%encerrante%'
ORDER  BY table_name, column_name;
