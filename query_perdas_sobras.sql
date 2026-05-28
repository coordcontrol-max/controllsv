-- =============================================================================
-- Perdas e Sobras das Medições dos Tanques (Variação de Estoque) por posto/mês
-- Fonte: medicao_tanque_lmc (perda/sobra por tanque/dia) + movimento_lmc (data)
--        + vwfw_tanque_combustivel (tanque → posto + produto).
-- Variação = Sobra − Perda (em litros). Negativo = perda líquida.
-- Roda na "Consulta SQL" do Adaptive → exporta como PerdasSobras_Postos.xls.
-- =============================================================================

SELECT
    e.codigo                                       AS posto,
    e.nome                                         AS posto_nome,
    EXTRACT(YEAR  FROM ml.data_movimento)::int     AS ano,
    EXTRACT(MONTH FROM ml.data_movimento)::int     AS mes,
    t.denominacao_item                             AS produto,
    SUM(COALESCE(med.perda, 0))                    AS perda,
    SUM(COALESCE(med.sobra, 0))                    AS sobra,
    SUM(COALESCE(med.sobra, 0) - COALESCE(med.perda, 0)) AS variacao,
    SUM(COALESCE(med.venda_dia, 0))                AS venda_litros
FROM medicao_tanque_lmc med
    JOIN movimento_lmc ml            ON ml.id_movimento_lmc = med.id_movimento_lmc
    JOIN vwfw_tanque_combustivel t   ON t.id_local_estoque = med.id_tanque
    JOIN sis_empresa e               ON e.id_empresa = t.id_empresa
WHERE ml.data_movimento >= DATE '2025-01-01' AND ml.data_movimento < DATE '2027-01-01'
  AND e.codigo IN ('001','002','003','004','005','006','007','008','009','010','011')
  AND e.registro_ativo = 'S'
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 3, 4, 5
