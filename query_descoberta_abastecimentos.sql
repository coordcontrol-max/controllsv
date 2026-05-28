-- =============================================================================
-- DESCOBERTA · Nº de Abastecimentos a partir da vw_venda
-- Rode UMA POR VEZ na "Consulta SQL" do Adaptive e me mande o resultado.
-- Objetivo: descobrir o grão da vw_venda pra montar a query de Nº Abastecimentos.
-- =============================================================================

-- ── 1) COLUNAS da vw_venda (procurar algo tipo "cupom", "abastec", "nota", "documento")
SELECT column_name, data_type
FROM   information_schema.columns
WHERE  table_name = 'vw_venda'
ORDER  BY ordinal_position;


-- ── 2) GRÃO: quantas LINHAS a vw_venda tem por posto/mês de combustível,
--     e o COUNT distinto de documento/cupom (se existir o campo).
--     Compare o "num_linhas" com o "Número Total de Abastecimentos" do Mapa
--     Anual (ex.: P03 mai/2026). Se bater → COUNT(*) é o nº de abastecimentos.
SELECT v.codigo_empresa                          AS posto,
       EXTRACT(YEAR  FROM v.data_movimento)::int AS ano,
       EXTRACT(MONTH FROM v.data_movimento)::int AS mes,
       COUNT(*)                                  AS num_linhas,
       SUM(v.quantidade_item_venda)              AS litros
FROM   vw_venda v
WHERE  v.combustivel = true
  AND  v.data_movimento >= DATE '2026-05-01' AND v.data_movimento < DATE '2026-06-01'
GROUP  BY 1, 2, 3
ORDER  BY 1;
