-- =============================================================================
-- DESCOBERTA 3 · achar a DATA da medição LMC
-- medicao_tanque_lmc liga ao tanque (→ posto via vwfw_tanque_combustivel), mas a
-- DATA vem de id_movimento_lmc ou id_movimento_estoque. Rode as 3 e me mande.
-- =============================================================================

-- ── 1) Tabelas com "movimento_lmc" / "lmc" / "movimento_estoque" no nome
SELECT table_schema, table_name, table_type
FROM   information_schema.tables
WHERE  table_name ILIKE '%movimento_lmc%' OR table_name ILIKE '%lmc%'
   OR  table_name = 'movimento_estoque' OR table_name ILIKE '%movimento_estoque%'
ORDER  BY table_name;

-- ── 2) Colunas de movimento_estoque (procurar data + id_empresa)
SELECT ordinal_position, column_name, data_type
FROM   information_schema.columns
WHERE  table_name = 'movimento_estoque'
ORDER  BY ordinal_position;

-- ── 3) Colunas com "data" nas tabelas de movimento_lmc (se a #1 achar o nome,
--      troque 'movimento_lmc' pelo nome exato que apareceu)
SELECT table_name, column_name, data_type
FROM   information_schema.columns
WHERE  (table_name ILIKE '%lmc%')
  AND  (column_name ILIKE '%data%' OR column_name ILIKE '%empresa%' OR column_name ILIKE '%competencia%' OR column_name ILIKE '%referencia%')
ORDER  BY table_name, ordinal_position;
