-- =============================================================================
-- QUERIES DE DESCOBERTA DO SCHEMA ADAPTIVE
-- Rode UMA POR VEZ na "Consulta SQL" do Adaptive e me mande o resultado de cada.
-- Com isso eu termino a query de competência sem precisar adivinhar nomes.
-- =============================================================================

-- ── 1) TABELAS CANDIDATAS (mostra todas que parecem ter o que precisamos)
SELECT table_schema, table_name
FROM   information_schema.tables
WHERE  table_type = 'BASE TABLE'
  AND  (
    table_name ILIKE '%titulo%'      OR table_name ILIKE '%duplicata%'
    OR table_name ILIKE '%pagar%'    OR table_name ILIKE '%receber%'
    OR table_name ILIKE '%nf%saida%' OR table_name ILIKE '%nota%fiscal%'
    OR table_name ILIKE '%movim%'    OR table_name ILIKE '%lancamento%'
    OR table_name ILIKE '%plano%'    OR table_name ILIKE '%conta%contabil%'
    OR table_name ILIKE '%empresa%'  OR table_name ILIKE '%filial%'
    OR table_name ILIKE '%posto%'    OR table_name ILIKE '%fornecedor%'
    OR table_name ILIKE '%cliente%'  OR table_name ILIKE '%produto%'
    OR table_name ILIKE '%item%'     OR table_name ILIKE '%vendas%'
    OR table_name ILIKE '%dre%'
  )
ORDER  BY table_schema, table_name;


-- ── 2) COLUNAS DA TABELA DE TÍTULOS A PAGAR (mais provavelmente o que precisamos)
-- Depois de rodar a #1, identifique qual nome bate (ex: 'titulo_pagar',
-- 'duplicata_pagar', 'fin_titulo_pagar', etc.) e mude o WHERE abaixo:
SELECT column_name, data_type, is_nullable
FROM   information_schema.columns
WHERE  table_name IN ('titulo_pagar','titulopagar','duplicata_pagar','fin_titulo_pagar')
ORDER  BY table_name, ordinal_position;


-- ── 3) AMOSTRA DE LINHAS — confirma quais colunas têm dt_emissao, status, valor
-- (troque o FROM pelo nome que apareceu na #1)
SELECT *
FROM   titulo_pagar     -- troque se for outro nome
LIMIT  3;


-- ── 4) PLANO DE CONTAS / CLASSIFICAÇÃO 3.3.x
-- Vai mostrar a tabela e como o grupo da DRE (3.3.X DESPESAS...) é armazenado.
SELECT table_name, column_name
FROM   information_schema.columns
WHERE  column_name ILIKE '%grupo%'  OR column_name ILIKE '%plano%'
   OR  column_name ILIKE '%nivel%'  OR column_name ILIKE '%cod%conta%'
   OR  column_name ILIKE '%dre%'    OR column_name ILIKE '%natureza%'
ORDER  BY table_name, column_name;


-- ── 5) COMO IDENTIFICAR OS 11 POSTOS
-- (Adaptive típico: tabela "empresa" / "filial" com campo de código tipo 001..011)
SELECT *
FROM   empresa          -- troque se for outro nome
WHERE  codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
   OR  ativa = TRUE
LIMIT  20;
