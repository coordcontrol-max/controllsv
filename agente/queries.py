"""Queries Oracle do Consinco — extraídas do Excel "00 - Base.xlsx".

Cada query é parametrizada por :dta_ini e :dta_fim (objetos datetime.date).
Use:
    from queries import QUERIES
    for slug, info in QUERIES.items():
        cur.execute(info["sql"], dta_ini=date(2026, 5, 1), dta_fim=date(2026, 5, 31))

Estrutura:
    QUERIES = {
        "venda_atual": {
            "nome": "Venda Atual",
            "descricao": "...",
            "sql": "SELECT ..."
        },
        ...
    }
"""

QUERIES = {
    "venda_atual": {
        "nome": "Venda Atual",
        "sql": """
SELECT
    TO_CHAR(V.DTAVDA, 'YYYY')                              AS ANO,
    TO_CHAR(V.DTAVDA, 'MM')                                AS MES,
    E.NROEMPRESA,

    COUNT(DISTINCT V.ROWIDDOCTO)                            AS TICKETS,

    ROUND(SUM(
        (ROUND(V.VLRITEM, 2)) - (ROUND(V.VLRDEVOLITEM, 2))
    ), 2)                                                   AS VENDA,

    ROUND(SUM(
        FC5_AbcDistribLucratividade(
            'L', 'L', 'N',
            V.VLRITEM, 'N',
            V.VLRICMSST, V.VLRFCPST, V.VLRICMSSTEMPORIG,
            E.UF, V.UFPESSOA, 'N', 0, 'N',
            V.VLRIPIITEM, V.VLRIPIDEVOLITEM, 'N',
            V.VLRDESCFORANF,
            Y.CMDIAVLRNF - 0,
            Y.CMDIAIPI,
            NVL(Y.CMDIACREDPIS, 0),
            NVL(Y.CMDIACREDCOFINS, 0),
            Y.CMDIAICMSST, Y.CMDIADESPNF, Y.CMDIADESPFORANF, Y.CMDIADCTOFORANF,
            'S', A.PROPQTDPRODUTOBASE,
            V.QTDITEM, V.VLREMBDESCRESSARCST, V.ACMCOMPRAVENDA,
            V.PISITEM, V.COFINSITEM,
            DECODE(V.TIPCGO, 'S', Y.QTDVDA, NVL(Y.QTDDEVOL, Y.QTDVDA)),
            DECODE(V.TIPCGO, 'S',
                Y.VLRIMPOSTOVDA - NVL(Y.VLRIPIVDA, 0),
                NVL(Y.VLRIMPOSTODEVOL - NVL(V.VLRIPIDEVOLITEM, 0),
                    Y.VLRIMPOSTOVDA - NVL(Y.VLRIPIVDA, 0))),
            'N', V.VLRDESPOPERACIONALITEM, Y.VLRDESPESAVDA,
            'N', NVL(Y.VLRVERBAVDAACR, 0),
            DECODE(V.TIPDOCFISCALCGO, 'T', 0, Y.QTDVERBAVDA),
            Y.VLRVERBAVDA - NVL(Y.VLRVERBAVDAINDEVIDA, 0),
            'N', NVL(V.VLRTOTCOMISSAOITEM, 0),
            V.VLRDEVOLITEM, V.VLRDEVOLICMSST, V.DVLRFCPST,
            V.QTDDEVOLITEM, V.PISDEVOLITEM, V.COFINSDEVOLITEM,
            V.VLRDESPOPERACIONALITEMDEVOL, V.VLRTOTCOMISSAOITEMDEVOL,
            E.PERIRLUCRAT, E.PERCSLLLUCRAT,
            Y.CMDIACREDICMS,
            DECODE(V.ICMSEFETIVOITEM, 0, V.ICMSITEM, V.ICMSEFETIVOITEM) + 0,
            V.VLRFCPICMS, V.PERCPMF, V.PEROUTROIMPOSTO,
            DECODE(V.ICMSEFETIVODEVOLITEM, 0, V.ICMSDEVOLITEM, V.ICMSEFETIVODEVOLITEM) + 0,
            V.DVLRFCPICMS,
            0,
            CASE WHEN DV.UTILACRESCCUSTPRODRELAC = 'S'
                  AND NVL(A.SEQPRODUTOBASE, A.SEQPRODUTOBASEANTIGO) IS NOT NULL
                 THEN COALESCE(PR.PERCACRESCCUSTORELACVIG,
                               NVL(F_RETACRESCCUSTORELACABC(V.SEQPRODUTO, V.DTAVDA), 1))
                 ELSE 1
            END,
            'N', 0, 0, 'S',
            V.VLRDESCMEDALHA, 'S',
            V.VLRDESCFORNEC, V.VLRDESCFORNECDEVOL,
            'N', V.VLRFRETEITEMRATEIO, V.VLRFRETEITEMRATEIODEV,
            'S', V.VLRICMSSTEMBUTPROD, V.VLRICMSSTEMBUTPRODDEV,
            V.VLREMBDESCRESSARCSTDEVOL,
            0,
            NVL(Y.CMDIACREDIPI, 0),
            NVL(V.VLRITEMRATEIOCTE, 0),
            'N', 'C',
            V.VLRIPIPRECOVDA, V.VLRIPIPRECODEVOL,
            V.VLRDESCMEDALHADEVOL, 'N'
        )
    ), 2)                                                   AS MARGEM,

    ROUND(SUM(
        DECODE(DECODE(V.TIPDOCFISCALCGO, 'T', 0, Y.QTDVERBAVDA), 0, 0,
            (Y.VLRVERBAVDA - NVL(Y.VLRVERBAVDAINDEVIDA, 0))
            * NVL(A.PROPQTDPRODUTOBASE, 1)
            / Y.QTDVDA
        ) * (V.QTDITEM - 0)
        + NVL(V.VLRVERBACOMPRA, 0)       - NVL(V.VLRVERBACOMPRADEV, 0)
        + NVL(V.VLRVERBABONIFINCID, 0)   - NVL(V.VLRVERBABONIFINCIDDEV, 0)
        + NVL(V.VLRVERBABONIFSEMINCID, 0)- NVL(V.VLRVERBABONIFSEMINCIDDEV, 0)
    ), 2)                                                   AS VERBA

FROM
    MRL_CUSTODIA            Y,
    MAXV_ABCDISTRIBBASE     V,
    MAP_PRODUTO             A,
    MAP_PRODUTO             PB,
    MAP_FAMDIVISAO          D,
    MAP_FAMEMBALAGEM        K,
    MAX_EMPRESA             E,
    MAX_DIVISAO             DV,
    MAP_PRODACRESCCUSTORELAC PR

WHERE
    D.SEQFAMILIA              = A.SEQFAMILIA
    AND D.NRODIVISAO          = V.NRODIVISAO
    AND V.SEQPRODUTO          = A.SEQPRODUTO
    AND V.SEQPRODUTOCUSTO     = PB.SEQPRODUTO
    AND V.NROSEGMENTO         IN (2, 4, 5, 6, 1, 3)
    AND V.NRODIVISAO          = D.NRODIVISAO
    AND E.NROEMPRESA          = V.NROEMPRESA
    AND E.NRODIVISAO          = DV.NRODIVISAO
    AND V.SEQPRODUTO          = PR.SEQPRODUTO(+)
    AND V.DTAVDA              = PR.DTAMOVIMENTACAO(+)
    AND Y.NROEMPRESA          = NVL(E.NROEMPCUSTOABC, E.NROEMPRESA)
    AND Y.DTAENTRADASAIDA     = V.DTAVDA
    AND K.SEQFAMILIA          = A.SEQFAMILIA
    AND K.QTDEMBALAGEM        = 1
    AND Y.SEQPRODUTO          = PB.SEQPRODUTO
    AND DECODE(V.TIPTABELA, 'S', V.CGOACMCOMPRAVENDA, V.ACMCOMPRAVENDA) IN ('S', 'I')
    -- Lista padrão de exclusão (estrutura 2026). Janelas de exceção em 2026
    -- quando as empresas voltaram a ter venda (eram excluídas indevidamente):
    --   NROEMPRESA  9 → jan e fev/2026
    --   NROEMPRESA 17 → jan, fev e mar/2026
    -- ATÉ 2025: NÃO exclui nenhuma nroempresa (em 2025 as vendas estavam nos
    -- nros primários 1,2,3,4,9,... que a lista de 2026 cortaria).
    AND (
        V.DTAVDA < DATE '2026-01-01'
        OR E.NROEMPRESA NOT IN (1,2,3,4,6,8,9,12,15,19,22,25,17)
        OR (E.NROEMPRESA = 9
            AND V.DTAVDA >= DATE '2026-01-01'
            AND V.DTAVDA <  DATE '2026-03-01')
        OR (E.NROEMPRESA = 17
            AND V.DTAVDA >= DATE '2026-01-01'
            AND V.DTAVDA <  DATE '2026-04-01')
    )
AND V.DTAVDA BETWEEN
    :dta_ini
    AND :dta_fim
GROUP BY
    TO_CHAR(V.DTAVDA, 'YYYY'),
    TO_CHAR(V.DTAVDA, 'MM'),
    E.NROEMPRESA,
    E.NOMEREDUZIDO

ORDER BY
    ANO,
    MES,
    E.NROEMPRESA
""",
    },
    "consumo_interno": {
        "nome": "Consumo Interno",
        "sql": """
-- Versão simplificada (sem joins MAP_FAMDIVISAO/MAP_FAMEMBALAGEM/MRL_PRODUTOEMPRESA
-- que filtravam silenciosamente). Alias agora 'NROEMPRESA' (era 'SEQDETALHE1',
-- que o classificador não reconhecia — agregava tudo em nroempresa=None).
SELECT
    L3.NROEMPRESA                      AS NROEMPRESA,
    TRUNC(L3.DTAENTRADASAIDA, 'MM')    AS MES,
    SUM(L3.VLRENTRADACOMPRA)
    + SUM(L3.VLRENTRADAOUTRAS)
    - SUM(L3.VLRSAIDAVENDA)
    - SUM(L3.VLRSAIDAOUTRAS)           AS VLRCTOLIQUIDO
FROM MAXV_ABCMOVTOBASE_PROD L3
WHERE L3.DTAENTRADASAIDA BETWEEN :dta_ini AND :dta_fim
  AND L3.CODGERALOPER IN (808)
  AND L3.SEQPRODUTO   != 14642   -- exclui Cesta Básica (linha separada)
GROUP BY L3.NROEMPRESA, TRUNC(L3.DTAENTRADASAIDA, 'MM')
""",
    },
    "cesta_basica": {
        "nome": "Cesta Básica",
        "sql": """
-- Versão simplificada (mesma família do Consumo Interno, filtrando SEQPRODUTO=14642).
SELECT
    L3.NROEMPRESA                      AS NROEMPRESA,
    TRUNC(L3.DTAENTRADASAIDA, 'MM')    AS MES,
    SUM(L3.VLRENTRADACOMPRA)
    + SUM(L3.VLRENTRADAOUTRAS)
    - SUM(L3.VLRSAIDAVENDA)
    - SUM(L3.VLRSAIDAOUTRAS)           AS VLRCTOLIQUIDO
FROM MAXV_ABCMOVTOBASE_PROD L3
WHERE L3.DTAENTRADASAIDA BETWEEN :dta_ini AND :dta_fim
  AND L3.CODGERALOPER IN (808)
  AND L3.SEQPRODUTO   = 14642
GROUP BY L3.NROEMPRESA, TRUNC(L3.DTAENTRADASAIDA, 'MM')
""",
    },

    "material_expediente_debug": {
        "nome": "Material Expediente DEBUG (SEQFAMILIA, NRODIVISAO, CODGERALOPER)",
        "sql": """
SELECT
    E2.NROEMPRESA,
    E2.SEQPRODUTO,
    A.DESCCOMPLETA,
    A.SEQFAMILIA,
    E2.NRODIVISAO,
    E2.CODGERALOPER,
    SUM(E2.VLRITEM) AS VLRITEM
FROM MAXV_ABCENTRADABASE E2, MAP_PRODUTO A
WHERE E2.SEQPRODUTO = A.SEQPRODUTO
  AND E2.DTAENTRADA BETWEEN :dta_ini AND :dta_fim
  AND E2.SEQPRODUTO IN (6559, 6562, 6563, 6564, 6573, 31695, 34553, 7579, 21073, 25500)
GROUP BY E2.NROEMPRESA, E2.SEQPRODUTO, A.DESCCOMPLETA, A.SEQFAMILIA, E2.NRODIVISAO, E2.CODGERALOPER
""",
    },

    "material_expediente": {
        "nome": "Material de Expediente",
        "sql": """
-- Versão simplificada (removidos joins com MAP_FAMDIVISAO, MAP_FAMEMBALAGEM,
-- MAD_FAMSEGMENTO, MAX_DIVISAO, MRL_PRODUTOEMPRESA que silenciosamente
-- filtravam SEQPRODUTOs (cadastro de família/embalagem mudou no Consinco).
-- O classificador.py faz lookup por SEQPRODUTO → LINHA, então não precisa
-- dos joins por divisão/segmento. CODGERALOPER=2 mantido (entrada).
SELECT
    E2.NROEMPRESA,
    E2.DTAENTRADA,
    E2.SEQPRODUTO,
    A.DESCCOMPLETA,
    SUM(E2.VLRITEM + E2.VLRIPI + E2.VLRICMSDI + E2.VLRDESPTRIBUTITEM +
        E2.VLRDESPNTRIBUTITEM + E2.VLRDESPFORANF + E2.VLRICMSST +
        E2.VLRFCPST - E2.VLRDESCITEM) -
    SUM(E2.DVLRITEM + E2.DVLRIPI + E2.DVLRICMSDI + E2.DVLRDESPTRIBUTITEM +
        E2.DVLRDESPNTRIBUTITEM + E2.DVLRDESPFORANF + E2.DVLRICMSST +
        E2.DVLRFCPST - E2.DVLRDESCITEM)             AS COMPRA
FROM MAXV_ABCENTRADABASE E2
JOIN MAP_PRODUTO         A   ON E2.SEQPRODUTO = A.SEQPRODUTO
WHERE E2.DTAENTRADA BETWEEN :dta_ini AND :dta_fim
  AND E2.CODGERALOPER IN (2)
GROUP BY E2.NROEMPRESA, E2.DTAENTRADA, E2.SEQPRODUTO, A.DESCCOMPLETA
""",
    },
    "inventario": {
        "nome": "Inventario",
        "sql": """
SELECT
    E.NROEMPRESA                                          AS NROEMPRESA,
    SUM(L3.VLRENTRADACOMPRA)
    + SUM(L3.VLRENTRADAOUTRAS)
    - SUM(L3.VLRSAIDAVENDA)
    - SUM(L3.VLRSAIDAOUTRAS)                              AS VLRCTOLIQUIDO,
    TRUNC(L3.DTAENTRADASAIDA, 'MM')                       AS DTAENTRADASAIDA
FROM MAXV_ABCMOVTOBASE_PROD L3,
     MAP_FAMDIVISAO        D,
     MAP_FAMEMBALAGEM      K,
     MAX_EMPRESA           E,
     MRL_PRODUTOEMPRESA    C
WHERE D.SEQFAMILIA      = L3.SEQFAMILIA
  AND D.NRODIVISAO      IN (1, 2, 3, 4)
  AND K.SEQFAMILIA      = D.SEQFAMILIA
  AND K.QTDEMBALAGEM    = 1
  AND L3.DTAENTRADASAIDA BETWEEN :dta_ini AND :dta_fim
  AND L3.NRODIVISAO     = D.NRODIVISAO
  AND E.NROEMPRESA      = L3.NROEMPRESA
  AND C.SEQPRODUTO      = L3.SEQPRODUTO
  AND C.NROEMPRESA      = E.NROEMPRESA
  AND L3.CODGERALOPER   IN (401, 501)
  AND D.SEQCOMPRADOR    != 14
GROUP BY E.NROEMPRESA,
         TRUNC(L3.DTAENTRADASAIDA, 'MM')
""",
    },

    "perdas_quebras": {
        "nome": "Perdas e Quebras",
        "sql": """
-- Versão simplificada (sem JOINs com MAP_TRIBUTACAOUF, MRL_PRODEMPSEG,
-- MAD_FAMSEGMENTO, MAP_CLASSIFABC, etc) que estavam silenciosamente
-- filtrando 17 empresas dos dados de Perdas e Quebras (resultado caía
-- de R$ -366k pra R$ -157k em Jan/2026). A query DEBUG (sem JOINs)
-- bateu exatamente com o snapshot Excel do BI. Os JOINs eram herança
-- de um SELECT bem mais complexo que era usado em outro contexto.
SELECT
    VW.NROEMPRESA               AS LOJA,
    VW.DTAENTRADASAIDA          AS DATA,
    SUM(VW.VALORLANCTO)         AS VLRLIQUIDO
FROM MAXV_ABCPERDABASE VW
WHERE VW.DTAENTRADASAIDA BETWEEN :dta_ini AND :dta_fim
  AND VW.TIPCLASSINTERNO IN ('P','R','C','A')
  AND VW.CODGERALOPER   = 549
  AND VW.TIPLANCTO      IN ('S')
GROUP BY VW.NROEMPRESA, VW.DTAENTRADASAIDA
""",
    },

    "_perdas_quebras_OBSOLETO": {
        "nome": "Perdas e Quebras (versão antiga, NÃO USAR)",
        "sql": """
select
E.NROEMPRESA as LOJA,
VW.DTAENTRADASAIDA AS DATA,
sum( VW.VALORLANCTO )
as VLRLIQUIDO

from MAP_FAMDIVISAO D, MAX_EMPRESA E, MAX_DIVISAO I2, MAP_CLASSIFABC Z2, MAXV_ABCPERDABASE VW,
MAP_TRIBUTACAOUF T3,
MAP_FAMILIA B, MAD_FAMSEGMENTO H, MAP_FAMEMBALAGEM K,
MRL_PRODUTOEMPRESA C, MRL_PRODEMPSEG C3,

(select A.SEQPRODUTO,
 A.NROEMPRESA,
 SUM( A.ESTQLOJA ) ESTQLOJA, 
 SUM( A.ESTQDEPOSITO ) ESTQDEPOSITO,
 SUM( A.ESTQTROCA ) as ESTQTROCA,
 SUM( A.ESTQALMOXARIFADO ) as ESTQALMOXARIFADO,
 SUM( A.ESTQOUTRO ) as ESTQOUTRO,
 0 
 VLRDESCTRANSFCB

 from MRL_PRODUTOEMPRESA A
 group by A.SEQPRODUTO, A.NROEMPRESA ) SX

 , 

MAD_SEGMENTO SE, MAP_PRODUTO PR,

(SELECT MAX(DX.UTILACRESCCUSTPRODRELAC) UTILACRESCCUSTPRODRELAC
 FROM MAX_DIVISAO DX, MAX_EMPRESA EX
 WHERE DX.NRODIVISAO = EX.NRODIVISAO
 ) I3



where E.NROEMPRESA = VW.NROEMPRESA
and E.NRODIVISAO = D.NRODIVISAO

and H.SEQFAMILIA = VW.SEQFAMILIA
and H.NROSEGMENTO = E.NROSEGMENTOPRINC
and H.NROSEGMENTO = SE.NROSEGMENTO

and D.SEQFAMILIA = VW.SEQFAMILIA
and D.NRODIVISAO in (1,2,3,4)

and B.SEQFAMILIA = VW.SEQFAMILIA

and I2.NRODIVISAO = D.NRODIVISAO

and Z2.NROSEGMENTO = H.NROSEGMENTO
and Z2.CLASSIFCOMERCABC = H.CLASSIFCOMERCABC

and K.SEQFAMILIA = H.SEQFAMILIA
and K.QTDEMBALAGEM = (case when instr('1', ',') > 0 then
 fPadraoEmbVenda2(D.SEQFAMILIA,'1')
 else
 H.PADRAOEMBVENDA
 end)

and C.SEQPRODUTO = VW.SEQPRODUTO
and C.NROEMPRESA = nvl( E.NROEMPCUSTOABC, E.NROEMPRESA )

and C3.NROEMPRESA = VW.NROEMPRESA
and C3.SEQPRODUTO = VW.SEQPRODUTO
and C3.NROSEGMENTO = E.NROSEGMENTOPRINC
and C3.QTDEMBALAGEM = H.PADRAOEMBVENDA

and T3.NROTRIBUTACAO = D.NROTRIBUTACAO
and T3.UFEMPRESA = E.UF
and T3.UFCLIENTEFORNEC = E.UF
and T3.TIPTRIBUTACAO = decode( I2.TIPDIVISAO, 'V', 'SN', 'SC' )
and T3.NROREGTRIBUTACAO = nvl( E.NROREGTRIBUTACAO, 0 ) 

and PR.SEQPRODUTO = VW.SEQPRODUTO

and SX.SEQPRODUTO = VW.SEQPRODUTO 

and SX.NROEMPRESA = VW.NROEMPRESA

and VW.DTAENTRADASAIDA between :dta_ini and :dta_fim

and VW.TIPCLASSINTERNO in ( 'P', 'R', 'C', 'A' )
and VW.CODGERALOPER = 549


and VW.TIPLANCTO IN ('S') 




group by E.NROEMPRESA, VW.DTAENTRADASAIDA
""",
    },
    "receitas_comerciais": {
        "nome": "Receitas Comerciais",
        "sql": """
select a.dtaoperacao,
       a.dtacontabiliza,
       a.vlroperacao,
       a.nroprocesso,
       b.codespecie,
       b.nroempresa,
       b.seqpessoa,
       c.nomerazao,
       b.obrigdireito,
       b.nrotitulo,
       b.serietitulo,
       b.nroparcela,
       b.qtdparcela,
       b.dtavencimento,
       b.abertoquitado,
       b.observacao
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
and a.codoperacao in (5,17,28)
and a.seqtitulo = b.seqtitulo
and b.seqpessoa = c.seqpessoa
and b.situacao not in 'C'
and b.codespecie IN ('ACRA22','ACRA23','ACRA24','ACRA25','ACRCOM','ACREX2','ACRFOR','ACRINA','ACRINT','ACRLOG','ACRMGM','ACRMKT','ACRPEN','ACRPON','ACRPRE','ACRQUE','ACRTRO','ACRXTR','CONTRT','DEVREC','CONTEV')
and a.seqtitoperacao not in (SELECT B.SEQTITOPERACAO FROM FI_TITULO A, FI_TITOPERACAO B WHERE B.OPCANCELADA = ('C'))
""",
    },
    "descontos_obtidos": {
        "nome": "Descontos Obtidos",
        "sql": """
select 
b.codespecie,
a.dtacontabiliza,
a.vlroperacao,
b.nroempresa
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
and a.codoperacao = 29
and a.seqtitulo = b.seqtitulo
and b.seqpessoa = c.seqpessoa
and b.situacao != 'C'
and a.seqtitoperacao not in (SELECT B.SEQTITOPERACAO FROM FI_TITULO A, FI_TITOPERACAO B WHERE B.OPCANCELADA = ('C'))
""",
    },
    "despesas_c_vendas": {
        "nome": "Despesas C/ Vendas",
        "sql": """
select 
       b.nroempresa,
       b.codespecie,
       a.dtaoperacao AS DTAEMISSAO,
       a.vlroperacao AS VLRADMINISTRACAO
  from fi_titoperacao a, fi_titulo b
 where a.dtacontabiliza between :dta_ini and :dta_fim
   and a.codoperacao in (77,156)
   and b.codespecie in ('TICKET','CARTAO','CARDEB','CARDIG')
   and a.seqtitulo = b.seqtitulo
""",
    },
    "operacao_financeira": {
        "nome": "Operação Financeira",
        "sql": """
select a.*, op.descricao as DESCOPERACAO
from FI_CTACORLANCA a
left join FI_OPERACAO op on op.codoperacao = a.codoperacao
where a.dtalancto between :dta_ini and :dta_fim
and a.codoperacao in (223, 205, 142, 139, 129, 112, 108, 34, 69, 132, 136, 130, 140, 73, 191, 217, 225, 214, 218, 220, 216, 167, 219, 157)
and a.seqlancto not in (select b.seqlancto from fi_ctacorlanca b where b.opcancelada = 'C')
AND A.SEQCTACORRENTE != 50
""",
    },
    "transf_consumo": {
        "nome": "Transf Consumo",
        "sql": """
SELECT
    TO_CHAR(V.DTAVDA, 'YYYY')                              AS ANO,
    TO_CHAR(V.DTAVDA, 'MM')                                AS MES,
    E.NROEMPRESA,
    A.SEQPRODUTO as PLU,
    A.DESCCOMPLETA as PRODUTO,
    sum( ( round( V.VLRITEM, 2 ) ) - ( round( V.VLRDEVOLITEM, 2 ) - ( 0 ) ) )
as VLRVENDA
    
from MRL_CUSTODIA Y, MAXV_ABCDISTRIBBASE V, MAP_PRODUTO A, MAP_PRODUTO PB, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E, MAX_DIVISAO DV, MAP_PRODACRESCCUSTORELAC PR where D.SEQFAMILIA = A.SEQFAMILIA
and D.NRODIVISAO = V.NRODIVISAO
and V.SEQPRODUTO = A.SEQPRODUTO
and V.SEQPRODUTOCUSTO = PB.SEQPRODUTO
and V.NROSEGMENTO in ( 2,4,5,6,1,3 )
and V.NRODIVISAO = D.NRODIVISAO
and E.NROEMPRESA = V.NROEMPRESA
and E.NRODIVISAO = DV.NRODIVISAO
AND V.SEQPRODUTO = PR.SEQPRODUTO(+)
AND V.DTAVDA = PR.DTAMOVIMENTACAO(+)
AND V.DTAVDA BETWEEN 
    :dta_ini 
    AND :dta_fim
and Y.NROEMPRESA = nvl( E.NROEMPCUSTOABC, E.NROEMPRESA ) 
and Y.DTAENTRADASAIDA = V.DTAVDA
 and K.SEQFAMILIA = A.SEQFAMILIA and K.QTDEMBALAGEM = 1 
and Y.SEQPRODUTO = PB.SEQPRODUTO 


and V.CODGERALOPER in ( 850, 851 )
and D.SEQCOMPRADOR = 14

 group by E.NROEMPRESA,
A.SEQPRODUTO,
A.DESCCOMPLETA,
TO_CHAR(V.DTAVDA, 'YYYY'),
TO_CHAR(V.DTAVDA, 'MM')
""",
    },
    "despesas": {
        "nome": "Despesas (2)",
        "sql": """
select TO_CHAR(a.dtacontabiliza, 'YYYY') as Ano,
       TO_CHAR(a.dtacontabiliza, 'MM') as MÊS,
       TO_CHAR(a.dtacontabiliza, 'DD/MM/YYYY') as Dta_Contabil,
       b.nroempresa,
TO_CHAR(b.dtavencimento, 'DD/MM/YYYY') as Dta_Vencimento,
       c.nomerazao,
       g.DESCRICAO,
       B.NROTITULO,
       b.codespecie,
       A.USUALTERACAO AS USUARIO,
       B.VLRNOMINAL,
       a.vlroperacao AS VALOR_LIQUIDO,
       b.observacao
  from fi_titoperacao a, fi_titulo b, ge_pessoa c, RF_PARAMNATNFDESP         e,
       ABA_HISTORICOCONTA        f,
       ABA_PLANOCONTA            g,
       RF_PARAMNATNFDESP_ESPECIE h
 where a.dtacontabiliza between :dta_ini and :dta_fim
   -- Operação 16 (Inclusão de Títulos) para TODAS as despesas, EXCETO as contas
   -- de Salários (Operação/ADM/Comercial), que usam a operação 6 (decisão do
   -- usuário 2026-05). Antes era codoperacao in (6) para tudo.
   and (
     (a.codoperacao = 6 and g.DESCRICAO in (
        'Salarios e Ordenados Operaçao',
        'Salarios e Ordenados ADM',
        'Salarios e Ordenados Comercial'
     ))
     or
     (a.codoperacao = 16 and g.DESCRICAO not in (
        'Salarios e Ordenados Operaçao',
        'Salarios e Ordenados ADM',
        'Salarios e Ordenados Comercial'
     ))
   )
   and b.codespecie not in ('PAGNFC','DESP91')
   and b.codespecie = h.codespecie
   and a.seqtitulo = b.seqtitulo
   and b.seqpessoa = c.seqpessoa
   and b.situacao not in 'C'
   and e.CODHISTORICOCONTABIL = f.SEQHISTORICO
   AND f.SEQPLANOCONTA = g.SEQPLANOCONTA
   AND e.CODHISTORICO = h.CODHISTORICO
   AND e.NROEMPRESA = h.MATRIZ
   AND e.NROEMPRESA = '1'
   AND f.TIPO = 'D'
   AND g.CLASSIFICACAO ='D'
   and a.seqtitoperacao not in
       (SELECT B.SEQTITOPERACAO
          FROM FI_TITULO A, FI_TITOPERACAO B
         WHERE B.OPCANCELADA = ('C'))
""",
    },
    "quebra_sobra": {
        "nome": "Quebra/Sobra",
        "sql": """
select 
    extract(year from b.dtamovimento)  as ANO,
    extract(month from b.dtamovimento) as MES,
    b.nroempresa                        as NROEMPRESA,
    case 
        when b.tipo = 'QUE' then '(-) Quebra Caixa'
        when b.tipo = 'SOB' then 'Sobra de Caixa PDV'
    end                                 as ATRIBUTO,
    case 
        when b.tipo = 'QUE' then b.valor * -1
        when b.tipo = 'SOB' then b.valor
    end                                 as VALOR

from fi_tsmovtoopedetalhe b,
     ge_usuario c

where b.codoperador = c.sequsuario
and   b.tipo in ('QUE', 'SOB')
and   b.dtamovimento between :dta_ini and :dta_fim

order by ANO, MES, b.nroempresa, ATRIBUTO
""",
    },
    "compra_transf": {
        "nome": "Compra Transf",
        "sql": """
select  
    extract(year from E2.DTAENTRADA)    as ANO,
    extract(month from E2.DTAENTRADA)   as MES,
    E2.NROEMPRESA                        as NROEMPRESA,
    A.SEQPRODUTO                         as COD,
    A.DESCCOMPLETA                       as PRODUTO,

    sum( E2.VLRITEM + E2.VLRIPI + E2.VLRICMSDI
       + E2.VLRDESPTRIBUTITEM + E2.VLRDESPNTRIBUTITEM + E2.VLRDESPFORANF 
       + E2.VLRICMSST + E2.VLRFCPST - E2.VLRDESCITEM )
    - 
    sum( E2.DVLRITEM + E2.DVLRIPI + E2.DVLRICMSDI
       + E2.DVLRDESPTRIBUTITEM + E2.DVLRDESPNTRIBUTITEM + E2.DVLRDESPFORANF 
       + E2.DVLRICMSST + E2.DVLRFCPST - E2.DVLRDESCITEM )
    as VLRENTRADA

from MAXV_ABCENTRADABASE E2
join MAP_PRODUTO A         on E2.SEQPRODUTO = A.SEQPRODUTO
join MAP_FAMDIVISAO D      on D.SEQFAMILIA = A.SEQFAMILIA and D.NRODIVISAO = 1

where E2.DTAENTRADA between :dta_ini and :dta_fim
  and E2.CODGERALOPER in ( 51, 50 )
  and D.SEQCOMPRADOR = 14

group by
    extract(year from E2.DTAENTRADA),
    extract(month from E2.DTAENTRADA),
    E2.NROEMPRESA,
    A.SEQPRODUTO,
    A.DESCCOMPLETA

order by ANO, MES, NROEMPRESA, COD
""",
    },
    "juros_recebidos": {
        "nome": "Juros Recebidos",
        "sql": """
select a.dtaoperacao,
       a.dtacontabiliza,
       a.vlroperacao,
       a.nroprocesso,
       b.codespecie,
       b.nroempresa,
       b.seqpessoa,
       c.nomerazao,
       b.obrigdireito,
       b.nrotitulo,
       b.serietitulo,
       b.nroparcela,
       b.qtdparcela,
       b.dtavencimento,
       b.abertoquitado,
       b.observacao
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
and a.codoperacao in (8,10)
and a.seqtitulo = b.seqtitulo
and b.seqpessoa = c.seqpessoa
and b.situacao not in 'C'
and a.seqtitoperacao not in (SELECT B.SEQTITOPERACAO FROM FI_TITULO A, FI_TITOPERACAO B WHERE B.OPCANCELADA = ('C'))
""",
    },
    "juros_emprestimo": {
        "nome": "Juros Emprestimo",
        "sql": """
select a.dtaoperacao,
       a.dtacontabiliza,
       a.vlroperacao,
       a.nroprocesso,
       b.codespecie,
       b.nroempresa,
       b.seqpessoa,
       c.nomerazao,
       b.obrigdireito,
       b.nrotitulo,
       b.serietitulo,
       b.nroparcela,
       b.qtdparcela,
       b.dtavencimento,
       b.abertoquitado,
       b.observacao
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
and a.codoperacao in (7)
and a.seqtitulo = b.seqtitulo
and b.seqpessoa = c.seqpessoa
and b.situacao not in 'C'
and b.codespecie IN ('EMPRE2')
and a.seqtitoperacao not in (SELECT B.SEQTITOPERACAO FROM FI_TITULO A, FI_TITOPERACAO B WHERE B.OPCANCELADA = ('C'))
""",
    },
    "juros_pago": {
        "nome": "Juros pAGO",
        "sql": """
select a.dtaoperacao,
       a.dtacontabiliza,
       a.vlroperacao,
       a.nroprocesso,
       b.codespecie,
       b.nroempresa,
       b.seqpessoa,
       c.nomerazao,
       b.obrigdireito,
       b.nrotitulo,
       b.serietitulo,
       b.nroparcela,
       b.qtdparcela,
       b.dtavencimento,
       b.abertoquitado,
       b.observacao
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
and a.codoperacao in (7)
and a.seqtitulo = b.seqtitulo
and b.seqpessoa = c.seqpessoa
and b.situacao not in 'C'
and b.codespecie NOT IN ('EMPRE2')
and a.seqtitoperacao not in (SELECT B.SEQTITOPERACAO FROM FI_TITULO A, FI_TITOPERACAO B WHERE B.OPCANCELADA = ('C'))
""",
    },
    "compra_func": {
        "nome": "Compra Func Atual",
        "sql": """
SELECT
    TO_CHAR(V.DTAVDA, 'YYYY')                                      AS ANO,
    TO_CHAR(V.DTAVDA, 'MM')                                        AS MES,
    E.NROEMPRESA                                                AS EMPRESA,

    ROUND(SUM(
        (V.VLRITEM) - (V.VLRDEVOLITEM - 0)
    ), 2)                                                           AS VENDA

FROM
    MRL_CUSTODIA             Y,
    MAXV_ABCFORMAPAGTO       V,
    MAP_PRODUTO              A,
    MAP_PRODUTO              PB,
    MAP_FAMDIVISAO           D,
    MAP_FAMEMBALAGEM         K,
    MAX_EMPRESA              E,
    MAX_DIVISAO              DV,
    MAP_PRODACRESCCUSTORELAC PR

WHERE
    D.SEQFAMILIA          = A.SEQFAMILIA
    AND D.NRODIVISAO      = V.NRODIVISAO
    AND V.SEQPRODUTO      = A.SEQPRODUTO
    AND V.SEQPRODUTOCUSTO = PB.SEQPRODUTO
    AND V.NROSEGMENTO     IN (2, 4, 5, 6, 1, 3)
    AND V.NRODIVISAO      = D.NRODIVISAO
    AND E.NROEMPRESA      = V.NROEMPRESA
    AND E.NRODIVISAO      = DV.NRODIVISAO
    AND V.SEQPRODUTO      = PR.SEQPRODUTO(+)
    AND V.DTAVDA          = PR.DTAMOVIMENTACAO(+)
    AND Y.NROEMPRESA      = NVL(E.NROEMPCUSTOABC, E.NROEMPRESA)
    AND Y.DTAENTRADASAIDA = V.DTAVDA
    AND K.SEQFAMILIA      = A.SEQFAMILIA
    AND K.QTDEMBALAGEM    = 1
    AND Y.SEQPRODUTO      = PB.SEQPRODUTO
    AND DECODE(V.TIPTABELA, 'S', V.CGOACMCOMPRAVENDA, V.ACMCOMPRAVENDA) IN ('S', 'I')
    AND D.SEQCOMPRADOR    != 14
    AND NVL(V.NROFORMAPAGTO, -1) = 20
AND V.DTAVDA BETWEEN :dta_ini AND :dta_fim

GROUP BY
    TO_CHAR(V.DTAVDA, 'YYYY'),
    TO_CHAR(V.DTAVDA, 'MM'),
    E.NROEMPRESA
""",
    },
    "material_expediente_op": {
        "nome": "Material de Expediente da Operação",
        "sql": """
SELECT
    A.NROEMPRESA                          AS EMPRESA,
    C.NOMERAZAO                           AS RAZAO_SOCIAL,
    A.DTAENTRADA                          AS DATA_LANCAMENTO,
    B.VALORLIQ                            AS VALOR_LIQUIDO
FROM OR_NFDESPESA A
INNER JOIN GE_PESSOA C ON A.SEQPESSOA = C.SEQPESSOA
INNER JOIN OR_NFVENCIMENTO B ON A.SEQNOTA = B.SEQNOTA
WHERE A.CODHISTORICO = 2119
AND A.DTAENTRADA BETWEEN :dta_ini
                     AND :dta_fim
""",
    },

    # ─── FLUXO DE CAIXA ─────────────────────────────────────────────────────
    # Queries extraídas de "00 - Base Fluxo de Caixa.xlsb" (abas BASE_PAGO,
    # JUROS, OPFIN). Originais no Excel filtravam por ano inteiro; aqui
    # parametrizadas com :dta_ini / :dta_fim pra rodar mês a mês.

    "fluxo_pago": {
        "nome": "Fluxo - Base Pagos (Recebimentos + Pagamentos)",
        "sql": """
select a.dtaoperacao,
       a.dtacontabiliza,
       a.vlroperacao,
       a.nroprocesso,
       b.codespecie,
       b.nroempresa,
       b.seqpessoa,
       c.nomerazao,
       b.obrigdireito,
       b.nrotitulo,
       b.serietitulo,
       b.nroparcela,
       b.qtdparcela,
       b.dtavencimento,
       b.abertoquitado,
       b.observacao,
       b.dtaquitacao
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
  and a.codoperacao in (5, 6)
  and a.seqtitulo = b.seqtitulo
  and b.seqpessoa = c.seqpessoa
  and b.situacao <> 'C'
  and a.seqtitoperacao not in (
      SELECT B.SEQTITOPERACAO
      FROM FI_TITOPERACAO B
      WHERE B.OPCANCELADA = 'C'
  )
""",
    },

    "fluxo_juros": {
        "nome": "Fluxo - Juros e Multas",
        "sql": """
select a.dtaoperacao,
       a.dtacontabiliza,
       a.vlroperacao,
       a.nroprocesso,
       b.codespecie,
       b.nroempresa,
       b.seqpessoa,
       c.nomerazao,
       b.obrigdireito,
       b.nrotitulo,
       b.serietitulo,
       b.nroparcela,
       b.qtdparcela,
       b.dtavencimento,
       b.abertoquitado,
       b.observacao,
       b.dtaquitacao
from fi_titoperacao a, fi_titulo b, ge_pessoa c
where a.dtacontabiliza between :dta_ini and :dta_fim
  and a.codoperacao in (7)
  and a.seqtitulo = b.seqtitulo
  and b.seqpessoa = c.seqpessoa
  and b.situacao <> 'C'
  and a.seqtitoperacao not in (
      SELECT B.SEQTITOPERACAO
      FROM FI_TITOPERACAO B
      WHERE B.OPCANCELADA = 'C'
  )
""",
    },

    "fluxo_opfin": {
        "nome": "Fluxo - Operação Financeira",
        "sql": """
select a.*, op.descricao as DESCOPERACAO
from FI_CTACORLANCA a
left join FI_OPERACAO op on op.codoperacao = a.codoperacao
where a.dtalancto between :dta_ini and :dta_fim
  and a.codoperacao in (223, 205, 142, 139, 129, 112, 108, 34, 69, 132, 136, 130, 140, 73, 191, 920, 15, 54, 13, 101)
  and a.seqlancto not in (
      select b.seqlancto
      from fi_ctacorlanca b
      where b.opcancelada = 'C'
        and b.seqlancto is not null
  )
  and A.SEQCTACORRENTE != 50
""",
    },

    # ─── CONTAS TRANSITÓRIAS (DFC CONSOLIDADO) ──────────────────────────────
    # Mesma estrutura da fluxo_opfin (linhas cruas da FI_CTACORLANCA + descrição
    # da operação), mas o escopo é por CONTA — os SEQCTACORRENTE transitórios —
    # em vez de por CODOPERACAO. Alimenta o DFC Consolidado: o classificador de
    # fluxo acumula esses lançamentos e gera as linhas "Saldo Conta Transitória",
    # "Saldo Conta Transitória (LUMI)" e "... (Exceto LUMI)".
    #
    # Data inicial é SEMPRE 01/01/1990 (não :dta_ini): a linha é um SALDO
    # acumulado, então precisa de todo o histórico da conta. O :dta_ini é
    # ignorado de propósito (via LEAST) — só continua referenciado porque o
    # /atualizar sempre faz o bind. :dta_fim define a data-base do saldo.
    # Mesma regra vale para a futura query de Inadimplência (Fornecedores).
    #
    # Escopo fixo: contas "CONCILIADOR LJxx", "CONTA TRANSITORIA TITULOS LUMI"
    # (LUMI = SEQCTACORRENTE 361) e "LJ215 TRANSPORTE DE VALORES PROTEGE"
    # (relatório transt.pdf). Ao abrir/fechar conta transitória, atualizar a
    # lista do IN abaixo.

    "fluxo_transitorias": {
        "nome": "Fluxo - Contas Transitórias (DFC Consolidado)",
        "sql": """
select a.*, op.descricao as DESCOPERACAO
from FI_CTACORLANCA a
left join FI_OPERACAO op on op.codoperacao = a.codoperacao
where a.dtalancto between least(:dta_ini, to_date('01/01/1990','dd/mm/yyyy'))
                     and :dta_fim
  and a.seqctacorrente in (
      361, 264, 266, 268, 5706, 6005, 5707, 6006, 5866, 5489,
      6225, 269, 6007, 5869, 270, 6087, 6105, 272, 273, 642,
      1644, 1684, 3342, 6146, 6147, 6149, 3501, 6151, 4181,
      5285, 5286, 5448, 5470
  )
  and a.seqlancto not in (
      select b.seqlancto
      from fi_ctacorlanca b
      where b.opcancelada = 'C'
        and b.seqlancto is not null
  )
""",
    },

    # ─── PREVENÇÃO ──────────────────────────────────────────────────────────
    # Inventário Rotativo + Quebras detalhadas + Vendas por produto/loja.
    # Drilldown na UI: produto (N1) → loja (N2), com % inventário/venda.

    "prev_inventario": {
        "nome": "Prevenção - Inventário Rotativo",
        "sql": """
SELECT
    TO_CHAR(L3.DTAENTRADASAIDA, 'YYYY')           AS ANO,
    TO_CHAR(L3.DTAENTRADASAIDA, 'MM')             AS MES,
    E.NROEMPRESA,
    O.APELIDO                                     AS COMPRADOR,
    G.CAMINHOCOMPLETO,
    L3.SEQPRODUTO,
    A.DESCCOMPLETA                                AS PRODUTO,
    SUM(L3.QTDENTRADACOMPRA / K.QTDEMBALAGEM)
    + SUM(L3.QTDENTRADAOUTRAS / K.QTDEMBALAGEM)
    - SUM(L3.QTDSAIDAVENDA / K.QTDEMBALAGEM)
    - SUM(L3.QTDSAIDAOUTRAS / K.QTDEMBALAGEM)     AS QTD_DIFERENCA,
    SUM(L3.VLRENTRADACOMPRA)
    + SUM(L3.VLRENTRADAOUTRAS)
    - SUM(L3.VLRSAIDAVENDA)
    - SUM(L3.VLRSAIDAOUTRAS)                      AS VLR_DIFERENCA
FROM  MAXV_ABCMOVTOBASE_PROD  L3
JOIN  MAP_PRODUTO              A   ON  A.SEQPRODUTO      = L3.SEQPRODUTO
JOIN  MAX_EMPRESA              E   ON  E.NROEMPRESA      = L3.NROEMPRESA
JOIN  MAP_FAMDIVISAO           D   ON  D.SEQFAMILIA      = L3.SEQFAMILIA
                                   AND D.NRODIVISAO      = L3.NRODIVISAO
JOIN  MAX_COMPRADOR            O   ON  O.SEQCOMPRADOR    = D.SEQCOMPRADOR
JOIN  MAP_FAMEMBALAGEM         K   ON  K.SEQFAMILIA      = D.SEQFAMILIA
                                   AND K.QTDEMBALAGEM    = 1
JOIN  MRL_PRODUTOEMPRESA       C   ON  C.SEQPRODUTO      = L3.SEQPRODUTO
                                   AND C.NROEMPRESA      = E.NROEMPRESA
JOIN  MAP_FAMDIVCATEG          W   ON  W.SEQFAMILIA      = D.SEQFAMILIA
                                   AND W.NRODIVISAO      = D.NRODIVISAO
                                   AND W.STATUS          = 'A'
JOIN  MAXV_CATEGORIA           G   ON  G.SEQCATEGORIA    = W.SEQCATEGORIA
                                   AND G.NRODIVISAO      = W.NRODIVISAO
                                   AND G.NIVELHIERARQUIA = 3
                                   AND G.TIPCATEGORIA    = 'M'
                                   AND G.STATUSCATEGOR  != 'I'
WHERE L3.DTAENTRADASAIDA BETWEEN :dta_ini AND :dta_fim
  AND L3.CODGERALOPER    IN (401, 501)
  AND D.SEQCOMPRADOR     != 14
  AND L3.SEQPRODUTO NOT IN (18559, 18560)
GROUP BY
    TO_CHAR(L3.DTAENTRADASAIDA, 'YYYY'),
    TO_CHAR(L3.DTAENTRADASAIDA, 'MM'),
    E.NROEMPRESA,
    O.APELIDO,
    G.CAMINHOCOMPLETO,
    L3.SEQPRODUTO,
    A.DESCCOMPLETA
ORDER BY
    TO_CHAR(L3.DTAENTRADASAIDA, 'YYYY'),
    TO_CHAR(L3.DTAENTRADASAIDA, 'MM'),
    E.NROEMPRESA,
    O.APELIDO,
    G.CAMINHOCOMPLETO,
    L3.SEQPRODUTO
""",
    },

    "prev_vendas_produto": {
        "nome": "Prevenção - Vendas por Produto",
        "sql": """
SELECT
    TO_CHAR(V.DTAVDA, 'YYYY')                              AS ANO,
    TO_CHAR(V.DTAVDA, 'MM')                                AS MES,
    E.NROEMPRESA,
    O.APELIDO                                              AS COMPRADOR,
    G.CAMINHOCOMPLETO,
    A.SEQPRODUTO,
    A.DESCCOMPLETA                                         AS PRODUTO,
    SUM(ROUND(V.VLRITEM, 2) - ROUND(V.VLRDEVOLITEM, 2))    AS VENDA,
    ROUND(SUM(
        fC5_AbcDistribLucratividade(
            'L', 'L', 'N',
            V.VLRITEM, 'N',
            V.VLRICMSST, V.VLRFCPST, V.VLRICMSSTEMPORIG,
            E.UF, V.UFPESSOA, 'N', 0, 'N',
            V.VLRIPIITEM, V.VLRIPIDEVOLITEM, 'N',
            V.VLRDESCFORANF,
            Y.CMDIAVLRNF - 0,
            Y.CMDIAIPI,
            NVL(Y.CMDIACREDPIS, 0),
            NVL(Y.CMDIACREDCOFINS, 0),
            Y.CMDIAICMSST, Y.CMDIADESPNF, Y.CMDIADESPFORANF, Y.CMDIADCTOFORANF,
            'S', A.PROPQTDPRODUTOBASE,
            V.QTDITEM, V.VLREMBDESCRESSARCST, V.ACMCOMPRAVENDA,
            V.PISITEM, V.COFINSITEM,
            DECODE(V.TIPCGO, 'S', Y.QTDVDA, NVL(Y.QTDDEVOL, Y.QTDVDA)),
            DECODE(V.TIPCGO, 'S',
                Y.VLRIMPOSTOVDA - NVL(Y.VLRIPIVDA, 0),
                NVL(Y.VLRIMPOSTODEVOL - NVL(V.VLRIPIDEVOLITEM, 0),
                    Y.VLRIMPOSTOVDA - NVL(Y.VLRIPIVDA, 0))),
            'N', V.VLRDESPOPERACIONALITEM, Y.VLRDESPESAVDA, 'N',
            NVL(Y.VLRVERBAVDAACR, 0),
            DECODE(V.TIPDOCFISCALCGO, 'T', 0, Y.QTDVERBAVDA),
            Y.VLRVERBAVDA - NVL(Y.VLRVERBAVDAINDEVIDA, 0),
            'N', NVL(V.VLRTOTCOMISSAOITEM, 0),
            V.VLRDEVOLITEM, V.VLRDEVOLICMSST, V.DVLRFCPST,
            V.QTDDEVOLITEM, V.PISDEVOLITEM, V.COFINSDEVOLITEM,
            V.VLRDESPOPERACIONALITEMDEVOL, V.VLRTOTCOMISSAOITEMDEVOL,
            E.PERIRLUCRAT, E.PERCSLLLUCRAT,
            Y.CMDIACREDICMS,
            DECODE(V.ICMSEFETIVOITEM, 0, V.ICMSITEM, V.ICMSEFETIVOITEM) + 0,
            V.VLRFCPICMS, V.PERCPMF, V.PEROUTROIMPOSTO,
            DECODE(V.ICMSEFETIVODEVOLITEM, 0, V.ICMSDEVOLITEM, V.ICMSEFETIVODEVOLITEM) + 0,
            V.DVLRFCPICMS,
            0,
            CASE WHEN DV.UTILACRESCCUSTPRODRELAC = 'S'
                  AND NVL(A.SEQPRODUTOBASE, A.SEQPRODUTOBASEANTIGO) IS NOT NULL
                 THEN COALESCE(PR.PERCACRESCCUSTORELACVIG,
                               NVL(F_RETACRESCCUSTORELACABC(V.SEQPRODUTO, V.DTAVDA), 1))
                 ELSE 1
            END,
            'N', 0, 0,
            'S', V.VLRDESCMEDALHA,
            'S', V.VLRDESCFORNEC, V.VLRDESCFORNECDEVOL,
            'N', V.VLRFRETEITEMRATEIO, V.VLRFRETEITEMRATEIODEV,
            'S', V.VLRICMSSTEMBUTPROD, V.VLRICMSSTEMBUTPRODDEV,
            V.VLREMBDESCRESSARCSTDEVOL,
            0,
            NVL(Y.CMDIACREDIPI, 0),
            NVL(V.VLRITEMRATEIOCTE, 0),
            'N', 'C',
            V.VLRIPIPRECOVDA, V.VLRIPIPRECODEVOL,
            V.VLRDESCMEDALHADEVOL, 'N'
        )
    ), 2)                                                  AS MARGEM,
    SUM((V.VLRVERBACOMPRA        - V.VLRVERBACOMPRADEV)
      + (V.VLRVERBABONIFINCID    - V.VLRVERBABONIFINCIDDEV)
      + (V.VLRVERBABONIFSEMINCID - V.VLRVERBABONIFSEMINCIDDEV)) AS VERBA
FROM  MAXV_ABCDISTRIBBASE      V
JOIN  MAX_EMPRESA               E   ON  E.NROEMPRESA       = V.NROEMPRESA
JOIN  MAX_DIVISAO               DV  ON  DV.NRODIVISAO      = E.NRODIVISAO
JOIN  MAP_PRODUTO               A   ON  A.SEQPRODUTO       = V.SEQPRODUTO
JOIN  MAP_PRODUTO               PB  ON  PB.SEQPRODUTO      = V.SEQPRODUTOCUSTO
JOIN  MAP_FAMDIVISAO            D   ON  D.SEQFAMILIA       = A.SEQFAMILIA
                                    AND D.NRODIVISAO       = V.NRODIVISAO
JOIN  MAX_COMPRADOR             O   ON  O.SEQCOMPRADOR     = D.SEQCOMPRADOR
JOIN  MRL_CUSTODIA              Y   ON  Y.NROEMPRESA       = NVL(E.NROEMPCUSTOABC, E.NROEMPRESA)
                                    AND Y.DTAENTRADASAIDA  = V.DTAVDA
                                    AND Y.SEQPRODUTO       = PB.SEQPRODUTO
JOIN  MAP_FAMDIVCATEG           U   ON  U.SEQFAMILIA       = D.SEQFAMILIA
                                    AND U.NRODIVISAO       = D.NRODIVISAO
                                    AND U.STATUS           = 'A'
JOIN  MAXV_CATEGORIA            G   ON  G.SEQCATEGORIA     = U.SEQCATEGORIA
                                    AND G.NRODIVISAO       = U.NRODIVISAO
                                    AND G.NIVELHIERARQUIA  = 3
                                    AND G.TIPCATEGORIA     = 'M'
                                    AND G.STATUSCATEGOR   != 'I'
LEFT JOIN MAP_PRODACRESCCUSTORELAC PR ON  PR.SEQPRODUTO       = V.SEQPRODUTO
                                      AND PR.DTAMOVIMENTACAO  = V.DTAVDA
WHERE V.DTAVDA BETWEEN :dta_ini AND :dta_fim
  AND DECODE(V.TIPTABELA, 'S', V.CGOACMCOMPRAVENDA, V.ACMCOMPRAVENDA) IN ('S','I')
  AND D.SEQCOMPRADOR != 14
  -- Mesma janela de exceção pra empresas 9 e 17 que aplicamos em venda_atual.
  -- Até 2025 não exclui nenhuma nroempresa (vendas nos nros primários).
  AND (
      V.DTAVDA < DATE '2026-01-01'
      OR E.NROEMPRESA NOT IN (1,2,3,4,6,8,9,12,15,17,19,22,25)
      OR (E.NROEMPRESA = 9
          AND V.DTAVDA >= DATE '2026-01-01'
          AND V.DTAVDA <  DATE '2026-03-01')
      OR (E.NROEMPRESA = 17
          AND V.DTAVDA >= DATE '2026-01-01'
          AND V.DTAVDA <  DATE '2026-04-01')
  )
GROUP BY
    TO_CHAR(V.DTAVDA, 'YYYY'),
    TO_CHAR(V.DTAVDA, 'MM'),
    E.NROEMPRESA,
    O.APELIDO,
    G.CAMINHOCOMPLETO,
    A.SEQPRODUTO,
    A.DESCCOMPLETA
ORDER BY
    TO_CHAR(V.DTAVDA, 'YYYY'),
    TO_CHAR(V.DTAVDA, 'MM'),
    E.NROEMPRESA,
    O.APELIDO,
    G.CAMINHOCOMPLETO,
    A.SEQPRODUTO
""",
    },

    "prev_quebras": {
        "nome": "Prevenção - Quebras Detalhadas",
        "sql": """
select
    E.NROEMPRESA,
    O.APELIDO,
    A.SEQPRODUTO,
    A.DESCCOMPLETA,
    VW.DTAENTRADASAIDA,
    VW.VALORLANCTOBRT,
    VW.QTDLANCTO
from MAP_PRODUTO A, MAP_FAMDIVISAO D, MAX_EMPRESA E, MAX_DIVISAO I2, MAP_CLASSIFABC Z2, MAXV_ABCPERDABASE VW,
     MAP_TRIBUTACAOUF T3, MAX_COMPRADOR O, MAP_FAMILIA B, MAD_FAMSEGMENTO H, MAP_FAMEMBALAGEM K,
     MRL_PRODUTOEMPRESA C, MRL_PRODEMPSEG C3,
     (select A.SEQPRODUTO, A.NROEMPRESA,
             SUM(A.ESTQLOJA)         ESTQLOJA,
             SUM(A.ESTQDEPOSITO)     ESTQDEPOSITO,
             SUM(A.ESTQTROCA)        AS ESTQTROCA,
             SUM(A.ESTQALMOXARIFADO) AS ESTQALMOXARIFADO,
             SUM(A.ESTQOUTRO)        AS ESTQOUTRO,
             0 VLRDESCTRANSFCB
      from MRL_PRODUTOEMPRESA A
      group by A.SEQPRODUTO, A.NROEMPRESA) SX,
     MAD_SEGMENTO SE, MAP_PRODUTO PR,
     (SELECT MAX(DX.UTILACRESCCUSTPRODRELAC) UTILACRESCCUSTPRODRELAC
      FROM MAX_DIVISAO DX, MAX_EMPRESA EX
      WHERE DX.NRODIVISAO = EX.NRODIVISAO) I3
where E.NROEMPRESA = VW.NROEMPRESA
  and E.NRODIVISAO = D.NRODIVISAO
  and H.SEQFAMILIA = VW.SEQFAMILIA
  and H.NROSEGMENTO = E.NROSEGMENTOPRINC
  and H.NROSEGMENTO = SE.NROSEGMENTO
  and D.SEQFAMILIA = VW.SEQFAMILIA
  and B.SEQFAMILIA = VW.SEQFAMILIA
  and I2.NRODIVISAO = D.NRODIVISAO
  and Z2.NROSEGMENTO = H.NROSEGMENTO
  and Z2.CLASSIFCOMERCABC = H.CLASSIFCOMERCABC
  and K.SEQFAMILIA = H.SEQFAMILIA
  and K.QTDEMBALAGEM = (case when instr('1', ',') > 0
                              then fPadraoEmbVenda2(D.SEQFAMILIA, '1')
                              else H.PADRAOEMBVENDA
                         end)
  and C.SEQPRODUTO = VW.SEQPRODUTO
  and C.NROEMPRESA = nvl(E.NROEMPCUSTOABC, E.NROEMPRESA)
  and C3.NROEMPRESA = VW.NROEMPRESA
  and C3.SEQPRODUTO = VW.SEQPRODUTO
  and C3.NROSEGMENTO = E.NROSEGMENTOPRINC
  and C3.QTDEMBALAGEM = H.PADRAOEMBVENDA
  and O.SEQCOMPRADOR = D.SEQCOMPRADOR
  and T3.NROTRIBUTACAO = D.NROTRIBUTACAO
  and T3.UFEMPRESA = E.UF
  and T3.UFCLIENTEFORNEC = E.UF
  and T3.TIPTRIBUTACAO = decode(I2.TIPDIVISAO, 'V', 'SN', 'SC')
  and T3.NROREGTRIBUTACAO = nvl(E.NROREGTRIBUTACAO, 0)
  and PR.SEQPRODUTO = VW.SEQPRODUTO
  and SX.SEQPRODUTO = VW.SEQPRODUTO
  and SX.NROEMPRESA = VW.NROEMPRESA
  and VW.DTAENTRADASAIDA between :dta_ini and :dta_fim
  and VW.TIPCLASSINTERNO in ('P', 'R', 'C', 'A')
  and VW.CODGERALOPER = 549
  and VW.TIPLANCTO IN ('S')
  and A.SEQPRODUTO = VW.SEQPRODUTO
  and D.SEQFAMILIA not in (select SEQFAMILIA from MAP_FAMDIVISAO where SEQCOMPRADOR = 14)
group by E.NROEMPRESA, E.NOMEREDUZIDO, A.SEQPRODUTO, A.DESCCOMPLETA,
         VW.DTAENTRADASAIDA, O.APELIDO, VW.VALORLANCTOBRT, VW.QTDLANCTO
""",
    },
    # ─── PREVENÇÃO · INDICADORES (scorecard mensal) ─────────────────────────
    "prev_ind_vda": {
        "nome": "Prevenção - Vendas Totais Loja",
        "sql": """
select 
  v.nroempresa, 
sum( ( round( V.VLRITEM, 2 ) ) - ( round( V.VLRDEVOLITEM, 2 ) - ( 0 ) ) ) 
from MRL_CUSTODIA Y, MAXV_ABCDISTRIBBASE V, MAP_PRODUTO A, MAP_PRODUTO PB, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E, MAX_DIVISAO DV, MAP_PRODACRESCCUSTORELAC PR where D.SEQFAMILIA = A.SEQFAMILIA
and D.NRODIVISAO = V.NRODIVISAO
and V.SEQPRODUTO = A.SEQPRODUTO
and V.SEQPRODUTOCUSTO = PB.SEQPRODUTO
and V.NRODIVISAO = D.NRODIVISAO
and E.NROEMPRESA = V.NROEMPRESA
and E.NRODIVISAO = DV.NRODIVISAO
AND  V.SEQPRODUTO = PR.SEQPRODUTO(+)
AND  V.DTAVDA = PR.DTAMOVIMENTACAO(+)
and V.DTAVDA between :dta_ini and :dta_fim
and Y.NROEMPRESA =   nvl( E.NROEMPCUSTOABC, E.NROEMPRESA ) 
and Y.DTAENTRADASAIDA = V.DTAVDA
 and K.SEQFAMILIA = A.SEQFAMILIA   and K.QTDEMBALAGEM = 1 
and Y.SEQPRODUTO = PB.SEQPRODUTO
and DECODE(V.TIPTABELA, 'S', V.CGOACMCOMPRAVENDA, V.ACMCOMPRAVENDA) in ( 'S', 'I' )
and D.SEQCOMPRADOR != 14
group by v.nroempresa
""",
    },

    "prev_ind_cancel": {
        "nome": "Prevenção - Cancelamentos PDV",
        "sql": """
Select FI_TSMOVTOOPERADOR.Nroempresa,
       to_char(fi_tsmovtoopedetalhe.dtamovimento, 'dd/mm/yyyy') ,
       FI_TSMOVTOOPEDETALHE.TIPO,
       FI_TSMOVTOOPEDETALHE.VALOR,
       FIV_TSNOPERADORCAIXA.NOME,
       FIV_TSNOPERADORCAIXA.CODOPERADOR,
       fi_tsmovtoopedetalhe.nropdv
  From FI_TSMOVTOOPERADOR,
       FI_TSMOVTOOPEDETALHE,
       FI_TSCODMOVIMENTO,
       FIV_TSNOPERADORCAIXA,
       GE_EMPRESA
 Where 1 = 1
   AND FI_TSMOVTOOPERADOR.NROPDV = FI_TSMOVTOOPEDETALHE.NROPDV
   AND FI_TSMOVTOOPERADOR.NROEMPRESA = GE_EMPRESA.NROEMPRESA
   AND GE_EMPRESA.STATUS = 'A'
   AND FI_TSMOVTOOPERADOR.NROEMPRESA = FI_TSMOVTOOPEDETALHE.NROEMPRESA
   AND FI_TSMOVTOOPERADOR.DTAMOVIMENTO = FI_TSMOVTOOPEDETALHE.DTAMOVIMENTO
   AND FI_TSMOVTOOPERADOR.CODOPERADOR = FI_TSMOVTOOPEDETALHE.CODOPERADOR
   AND FI_TSMOVTOOPERADOR.NROTURNO = FI_TSMOVTOOPEDETALHE.NROTURNO
   AND FI_TSCODMOVIMENTO.TIPO = FI_TSMOVTOOPEDETALHE.TIPO
   AND FI_TSCODMOVIMENTO.NROEMPRESAMAE = FI_TSMOVTOOPEDETALHE.NROEMPRESAMAE
   AND FI_TSCODMOVIMENTO.CODMOVIMENTO = FI_TSMOVTOOPEDETALHE.CODMOVIMENTO
   AND FIV_TSNOPERADORCAIXA.CODOPERADOR = FI_TSMOVTOOPERADOR.CODOPERADOR
   AND FIV_TSNOPERADORCAIXA.NROEMPRESA = FI_TSMOVTOOPERADOR.NROEMPRESA
   AND NVL(FI_TSMOVTOOPERADOR.VERSAO, 'A') = 'N'
   AND NVL(FI_TSMOVTOOPEDETALHE.VERSAO, 'A') = 'N'
   AND FI_TSMOVTOOPEDETALHE.VALOR > 0.00
   AND FI_TSMOVTOOPERADOR.DTAMOVIMENTO BETWEEN :dta_ini AND :dta_fim
   AND FI_TSMOVTOOPEDETALHE.TIPO IN ('CAN')
   
 GROUP BY FI_TSMOVTOOPERADOR.NROEMPRESA,
          fi_tsmovtoopedetalhe.dtamovimento,
          FI_TSMOVTOOPEDETALHE.VALOR,
          FI_TSMOVTOOPEDETALHE.CODMOVIMENTO,
          FI_TSMOVTOOPEDETALHE.TIPO,
          FI_TSCODMOVIMENTO.DESCRICAO,
          FIV_TSNOPERADORCAIXA.NOME,
          FIV_TSNOPERADORCAIXA.CODOPERADOR,
          FIV_TSNOPERADORCAIXA.CODOPERADOR,
          fi_tsmovtoopedetalhe.nropdv
          
 Order By FI_TSMOVTOOPERADOR.NROEMPRESA,
          FIV_TSNOPERADORCAIXA.NOME,
          FIV_TSNOPERADORCAIXA.CODOPERADOr
""",
    },

    "prev_ind_carrinhos": {
        "nome": "Prevenção - Inventário Carrinhos",
        "sql": """
select 
E.NROEMPRESA as SEQDETALHE1,
sum( L3.QTDENTRADACOMPRA / K.QTDEMBALAGEM )
+ sum( L3.QTDENTRADAOUTRAS / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAVENDA / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAOUTRAS / K.QTDEMBALAGEM )
as QTDDIFERENCA,

sum( L3.VLRENTRADACOMPRA )
+ sum( L3.VLRENTRADAOUTRAS )
- sum( L3.VLRSAIDAVENDA )
- sum( L3.VLRSAIDAOUTRAS )
as VLRDIFERENCA

from MAXV_ABCMOVTOBASE_PROD L3, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E , MRL_PRODUTOEMPRESA C 

where D.SEQFAMILIA = L3.SEQFAMILIA
and K.SEQFAMILIA = D.SEQFAMILIA
and K.QTDEMBALAGEM = 1
and L3.DTAENTRADASAIDA between :dta_ini and :dta_fim
and L3.NRODIVISAO = D.NRODIVISAO
and L3.NROEMPRESA in ( 101,102,103,104,5,106,7,108,29,10,11,112,13,14,215,16,109,18,219,20,21,222,23,125,26,27,28,131,117 )
and E.NROEMPRESA = L3.NROEMPRESA and C.SEQPRODUTO = L3.SEQPRODUTO
 and C.NROEMPRESA = E.NROEMPRESA 


and L3.CODGERALOPER in ( 401,501 )
and D.SEQCOMPRADOR != 14
and L3.SEQPRODUTO in ( 15522,15533,15532,15517,15523,20753,29299,27161,15296,15292,15527 )

group by E.NROEMPRESA
""",
    },

    "prev_ind_inv_sacolas": {
        "nome": "Prevenção - Inventário Sacolas",
        "sql": """
select 
E.NROEMPRESA as SEQDETALHE1,
sum( L3.QTDENTRADACOMPRA / K.QTDEMBALAGEM )
+ sum( L3.QTDENTRADAOUTRAS / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAVENDA / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAOUTRAS / K.QTDEMBALAGEM )
as QTDDIFERENCA,

sum( L3.VLRENTRADACOMPRA )
+ sum( L3.VLRENTRADAOUTRAS )
- sum( L3.VLRSAIDAVENDA )
- sum( L3.VLRSAIDAOUTRAS )
as VLRDIFERENCA

from MAXV_ABCMOVTOBASE_PROD L3, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E  , MRL_PRODUTOEMPRESA C 

where D.SEQFAMILIA = L3.SEQFAMILIA
and K.SEQFAMILIA = D.SEQFAMILIA
and K.QTDEMBALAGEM = 1
and L3.DTAENTRADASAIDA between :dta_ini and :dta_fim
and L3.NRODIVISAO = D.NRODIVISAO
and L3.NROEMPRESA in ( 1, 12, 14, 15, 17, 19, 2, 22, 25, 26, 27, 3, 4, 5, 6, 8, 9, 28, 101, 103, 108, 102, 104, 106, 112,125,131,215,219,222,29,109,117 )
and E.NROEMPRESA = L3.NROEMPRESA and  C.SEQPRODUTO = L3.SEQPRODUTO
    and  C.NROEMPRESA = E.NROEMPRESA 


and L3.CODGERALOPER in ( 401,501 )
and L3.SEQPRODUTO in (25500,32009)

group by E.NROEMPRESA
""",
    },

    "prev_ind_vda_sacolas": {
        "nome": "Prevenção - Vendas Sacolas",
        "sql": """
SELECT
E.NROEMPRESA as SEQDETALHE1,
sum(  (  round( V.VLRITEM, 2 )  )  - (  round( V.VLRDEVOLITEM, 2 )  - ( 0  ) )  )
as VLRVENDA

from MRL_CUSTODIA Y, MAXV_ABCDISTRIBBASE V, MAP_PRODUTO A, MAP_PRODUTO PB, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E, MAX_DIVISAO DV, MAP_PRODACRESCCUSTORELAC PR where D.SEQFAMILIA = A.SEQFAMILIA
and D.NRODIVISAO = V.NRODIVISAO
and V.SEQPRODUTO = A.SEQPRODUTO
and V.SEQPRODUTOCUSTO = PB.SEQPRODUTO
and V.NROEMPRESA in ( 1, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 20, 21, 22, 23, 25, 26, 27, 28, 3, 4, 5, 6, 7, 8, 9, 900, 10, 101, 103, 108, 102, 104, 106, 112,125,131,215,219,222,29,109,117 )
and V.NRODIVISAO = D.NRODIVISAO
and E.NROEMPRESA = V.NROEMPRESA
and E.NRODIVISAO = DV.NRODIVISAO
AND  V.SEQPRODUTO = PR.SEQPRODUTO(+)
AND  V.DTAVDA = PR.DTAMOVIMENTACAO(+)
and V.DTAVDA between :dta_ini and :dta_fim
and Y.NROEMPRESA =   nvl( E.NROEMPCUSTOABC, E.NROEMPRESA ) 
and Y.DTAENTRADASAIDA = V.DTAVDA
 and K.SEQFAMILIA = A.SEQFAMILIA   and K.QTDEMBALAGEM = 1 
and Y.SEQPRODUTO = PB.SEQPRODUTO


and DECODE(V.TIPTABELA, 'S', V.CGOACMCOMPRAVENDA, V.ACMCOMPRAVENDA) in ( 'S', 'I' )
and V.SEQPRODUTO in (25500,32009)

 group by E.NROEMPRESA
""",
    },

    "prev_ind_par_ntranc": {
        "nome": "Prevenção - Inventário Paradas Não Trancadas",
        "sql": """
select 
E.NROEMPRESA as SEQDETALHE1,

sum( L3.QTDENTRADACOMPRA / K.QTDEMBALAGEM )
+ sum( L3.QTDENTRADAOUTRAS / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAVENDA / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAOUTRAS / K.QTDEMBALAGEM )
as QTDDIFERENCA,

sum( L3.VLRENTRADACOMPRA )
+ sum( L3.VLRENTRADAOUTRAS )
- sum( L3.VLRSAIDAVENDA )
- sum( L3.VLRSAIDAOUTRAS )
as VLRDIFERENCA

from MAXV_ABCMOVTOBASE_PROD L3, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E , MRL_PRODUTOEMPRESA C 

where D.SEQFAMILIA = L3.SEQFAMILIA
and K.SEQFAMILIA = D.SEQFAMILIA
and K.QTDEMBALAGEM = 1
and L3.DTAENTRADASAIDA between :dta_ini and :dta_fim
and L3.NRODIVISAO = D.NRODIVISAO
and L3.NROEMPRESA in ( 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 20, 21, 22, 23, 25, 26, 27, 28, 3, 4, 5, 6, 7, 8, 9, 900, 999, 101, 103, 108, 102, 104, 106, 112,125,131,215,219,222,29,109,117 )
and E.NROEMPRESA = L3.NROEMPRESA and C.SEQPRODUTO = L3.SEQPRODUTO
 and C.NROEMPRESA = E.NROEMPRESA 


and L3.CODGERALOPER in ( 401,501 )
and D.SEQCOMPRADOR != 14
and L3.SEQPRODUTO in ( 2731,9338,9340,18624,18661,18657,9339,9358,2735,2745,2749,2751,14139,29148,15208,18830,2755,9360,11949,9361,13838,9363,18655,9362,22284,22279,18831,10953,5994,29147,18656,16301,15989,15976,15974,10972,21733,624,20104,17902,17901,16168,16167,16169,11696,17904,17900,17903,30181,30182,11681,11683,11684,11676,12689,12649,11668,12651,6545,6548,12281,5663,5662,5660,5664,9074,20645,27428,21257,22227,6209,6591,6595,12601,11706,13806,11703,12740,6551,6549,6553,6560,30218,6554,6555,6557,27688,19790,11708,17112,11644,11645,18118,11642,12279,20649,6214,6215,20068,18481,18480,18479,18478,12964,14911,1264,1256,1252,1269,1271,1266,1263,12280,12278,12606,12605,28020,28022,28021,13253,3831,28031,28025,14282,3826,3399,13107,3405,2010,13254,13255,3400,13108,2015,21259,20642,14565,14566,20646,20648,20647,20641,20643,14568,14567,13607,13807,6598,20644,6558,25921,6601,6616,6606,6617,6604,6610,6600,31080,11707,11705,22124,22125,21254,16165,11698,11686,21258,21256,12294,11702,11710,16727,16728,12291,12562,12570,31734,31709,16712,16711,12301,11883,11892,12026,11889,13366,2758,10309,26692,27920,16848,10310,10308,2481,17605,14333,10312,10311,2756,600,605,608,11258,620,621,27634,16497,22324,22323,11270,622,623,11262,619,625,631,12659,27635,13773,9675,9676,9677,9678,13437,15145,9761,9763,12250 )

group by E.NROEMPRESA
""",
    },

    "prev_ind_par_tranc": {
        "nome": "Prevenção - Inventário Paradas Trancadas",
        "sql": """
select 
E.NROEMPRESA as SEQDETALHE1,

sum( L3.QTDENTRADACOMPRA / K.QTDEMBALAGEM )
+ sum( L3.QTDENTRADAOUTRAS / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAVENDA / K.QTDEMBALAGEM )
- sum( L3.QTDSAIDAOUTRAS / K.QTDEMBALAGEM )
as QTDDIFERENCA,

sum( L3.VLRENTRADACOMPRA )
+ sum( L3.VLRENTRADAOUTRAS )
- sum( L3.VLRSAIDAVENDA )
- sum( L3.VLRSAIDAOUTRAS )
as VLRDIFERENCA

from MAXV_ABCMOVTOBASE_PROD L3, MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E , MRL_PRODUTOEMPRESA C 

where D.SEQFAMILIA = L3.SEQFAMILIA
and K.SEQFAMILIA = D.SEQFAMILIA
and K.QTDEMBALAGEM = 1
and L3.DTAENTRADASAIDA between :dta_ini and :dta_fim
and L3.NRODIVISAO = D.NRODIVISAO
and L3.NROEMPRESA in ( 1, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 2, 20, 21, 22, 23, 25, 26, 27, 28, 3, 4, 5, 6, 7, 8, 9, 900, 999, 101, 103, 108, 102, 104, 106, 112,125,131,215,219,222,29,109,117 )
and E.NROEMPRESA = L3.NROEMPRESA and C.SEQPRODUTO = L3.SEQPRODUTO
 and C.NROEMPRESA = E.NROEMPRESA 


and L3.CODGERALOPER in ( 401,501 )
and D.SEQCOMPRADOR != 14
and L3.SEQPRODUTO in ( 27181,27182,27183,27184,27185,27180,27186,27187,27188,27173,27172,27177,27176,27174,27175,27179,27178,15668,16862,13559,17317,1884,1889,13315,13317,14552,9280,9281,9786,21917,13487,20129,19074,14335,9787,21918,14162,9788,9795,9796,16071,9767,9777,9769,9291,9773,9774,13430,9775,9782,9783,9292,9776,9778,9779,9784,9785 )

group by E.NROEMPRESA
""",
    },


}


# ─── QUERIES SEM PARÂMETRO DE DATA (dimensões / cache) ──────────────────────
# Não entram no QUERIES regular porque o /atualizar passa :dta_ini/:dta_fim.
# Rodadas via endpoint separado (/atualizar_dimensoes) que grava em meta/*.
QUERIES_DIMENSOES = {
    "prev_classif_produtos": {
        "nome": "Prevenção - Classificação Produtos × Comprador × Categoria",
        "destino": "meta/produtosClassif",
        "sql": """
SELECT DISTINCT
    O.APELIDO       AS COMPRADOR,
    G.CAMINHOCOMPLETO,
    A.SEQPRODUTO,
    A.DESCCOMPLETA  AS PRODUTO
FROM  MAP_PRODUTO       A
JOIN  MAP_FAMDIVISAO    D   ON  D.SEQFAMILIA    = A.SEQFAMILIA
JOIN  MAX_COMPRADOR     O   ON  O.SEQCOMPRADOR  = D.SEQCOMPRADOR
JOIN  MAP_FAMDIVCATEG   U   ON  U.SEQFAMILIA    = D.SEQFAMILIA
                            AND U.NRODIVISAO    = D.NRODIVISAO
                            AND U.STATUS        = 'A'
JOIN  MAXV_CATEGORIA    G   ON  G.SEQCATEGORIA  = U.SEQCATEGORIA
                            AND G.NRODIVISAO    = U.NRODIVISAO
                            AND G.NIVELHIERARQUIA = 3
                            AND G.TIPCATEGORIA  = 'M'
                            AND G.STATUSCATEGOR != 'I'
ORDER BY
    O.APELIDO,
    G.CAMINHOCOMPLETO,
    A.SEQPRODUTO
""",
    },
    "prev_ind_trocas": {
        "nome": "Prevenção - Estoque de Trocas (snapshot)",
        "destino": "meta/prevIndTrocas",
        "sql": """
select 
E.NROEMPRESA as NOMEDETALHE2,
round( sum( ( ESTQTROCA ) / K.QTDEMBALAGEM ), 6 ) 
as QTDTOTAL,

sum( ( ( C.CMULTVLRNF + C.CMULTIPI + C.CMULTDESPNF + C.CMULTICMSST + C.CMULTDESPFORANF 
- ( C.CMULTDCTOFORANF - C.CMULTIMPOSTOPRESUM ) + C.VLRDESCTRANSFCB 
- 0 )
* ( case when I2.UTILACRESCCUSTPRODRELAC = 'S' and nvl( A.SEQPRODUTOBASE, A.SEQPRODUTOBASEANTIGO ) is not null 
 then coalesce( PR.PERCACRESCCUSTORELACVIG, F_RetAcrescCustoRelac( C.SEQPRODUTO, C.DTAENTRADASAIDA, I2.UTILACRESCCUSTPRODRELAC, PR.PERCACRESCCUSTORELACVIG ) )
 else 1
 end ) ) * ( ESTQTROCA ) )
as VLRCTOBRUTO

from MAP_PRODUTO A, MAP_FAMILIA B,
( select Y.SEQPRODUTO, Y.NROEMPRESA, Y.SEQCLUSTER ,
decode( ( ESTQTROCA ), 0, null, Y.SEQPRODUTO ) SEQPRODUTOCOMESTQ,
 decode( X.PRECO, 0, X.MENORPRECO, X.PRECO ) PRECO, X.MENORPRECO, X.MAIORPRECO, Y.NROGONDOLA, Y.ESTQLOJA, Y.ESTQDEPOSITO, Y.ESTQTROCA, Y.ESTQALMOXARIFADO, Y.ESTQOUTRO, nvl( Y.ESTQTERCEIRO, 0 ) ESTQTERCEIRO,
Y.QTDPENDPEDCOMPRA, Y.QTDPENDPEDEXPED, 
Y.QTDRESERVADAVDA, Y.QTDRESERVADARECEB, Y.QTDRESERVADAFIXA, 
Y.MEDVDIAPROMOC, Y.MEDVDIAGERAL, Y.MEDVDIAFORAPROMOC, 
Y.CMULTVLRNF, 
Y.CMULTIPI, 
Y.CMULTCREDICMS, 
Y.CMULTICMSST, 
Y.CMULTDESPNF, 
Y.CMULTDESPFORANF, 
Y.CMULTDCTOFORANF, 
nvl( Y.CMULTIMPOSTOPRESUM, 0 ) CMULTIMPOSTOPRESUM,
nvl( Y.CMULTCREDICMSPRESUM, 0 ) CMULTCREDICMSPRESUM,
nvl( Y.CMULTCREDICMSANTECIP, 0 ) CMULTCREDICMSANTECIP,
nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) CMULTCUSLIQUIDOEMP,
nvl( Y.CMULTCREDICMSEMP, 0 ) CMULTCREDICMSEMP,
nvl( Y.CMULTCREDPISEMP, 0 ) CMULTCREDPISEMP,
nvl( Y.CMULTCREDCOFINSEMP, 0 ) CMULTCREDCOFINSEMP,
nvl( Y.CMULTCREDPIS, 0 ) CMULTCREDPIS,
nvl( Y.CMULTCREDCOFINS, 0 ) CMULTCREDCOFINS,
Y.STATUSCOMPRA, X.STATUSVENDA,
trunc( sysdate ) - Y.DTAULTENTRADA DIASULTENTRADA, 
nvl( Y.NROSEGPRODUTO, E.NROSEGMENTOPRINC ) NROSEGPRODUTO, 
Y.LOCENTRADA, Y.LOCSAIDA,
nvl( Y.CLASSEABASTQTD, '**Sem Classificação**' ) CLASSEABASTQTD, 
nvl( Y.CLASSEABASTVLR, '**Sem Classificação**' ) CLASSEABASTVLR,
nvl( Y.CMULTVLRCOMPROR, 0 ) CMULTVLRCOMPROR,
nvl( Y.CMULTVLRDESCPISTRANSF, 0 ) CMULTVLRDESCPISTRANSF,
nvl( Y.CMULTVLRDESCCOFINSTRANSF, 0 ) CMULTVLRDESCCOFINSTRANSF,
nvl( Y.CMULTVLRDESCICMSTRANSF, 0 ) CMULTVLRDESCICMSTRANSF, 
nvl( Y.CMULTVLRDESCLUCROTRANSF, 0 ) CMULTVLRDESCLUCROTRANSF,
nvl( Y.CMULTVLRDESCIPITRANSF, 0 ) CMULTVLRDESCIPITRANSF,
nvl( Y.CMULTVLRDESCVERBATRANSF, 0 ) CMULTVLRDESCVERBATRANSF,
nvl( Y.CMULTVLRDESCDIFERENCATRANSF, 0 ) CMULTVLRDESCDIFERENCATRANSF,
nvl( Y.CMULTCREDIPI, 0 ) CMULTCREDIPI, 
trunc( sysdate ) - Y.DTAULTENTRCUSTO DIASULTENTRCUSTO,
( nvl( Y.CMULTVLRDESCPISTRANSF, 0 ) + nvl( Y.CMULTVLRDESCCOFINSTRANSF, 0 ) + nvl( Y.CMULTVLRDESCICMSTRANSF, 0 ) + nvl( Y.CMULTVLRDESCIPITRANSF, 0 )
 + nvl( Y.CMULTVLRDESCLUCROTRANSF, 0 ) + nvl( Y.CMULTVLRDESCVERBATRANSF, 0 ) + nvl( Y.CMULTVLRDESCDIFERENCATRANSF, 0 ) ) VLRDESCTRANSFCB,
Y.SEQSENSIBILIDADE, 
Y.FORMAABASTECIMENTO, case when nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 ) < 0 
 then 0 
 else nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 )
end CUSTOFISCALUNIT, 

case when nvl( ( nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 ) ) * Y.ESTQEMPRESA, 0 ) < 0 
 then 0
 else nvl( ( nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 ) ) * Y.ESTQEMPRESA, 0 ) 
end CUSTOFISCALTOTAL, 


coalesce(
 
 (select ( CUSTOA.QTDESTQINICIALEMP + CUSTOA.QTDENTRADAEMP - CUSTOA.QTDSAIDAEMP)
 from MRL_CUSTODIAEMP CUSTOA
 where CUSTOA.SEQPRODUTO = Y.SEQPRODUTO
 and CUSTOA.NROEMPRESA = Y.NROEMPRESA
 and CUSTOA.DTAENTRADASAIDA = nvl( '', sysdate ) ),

 ( select ( CUSTOA.QTDESTQINICIALEMP + CUSTOA.QTDENTRADAEMP - CUSTOA.QTDSAIDAEMP)
 from MRL_CUSTODIAEMP CUSTOA
 where CUSTOA.SEQPRODUTO = Y.SEQPRODUTO
 and CUSTOA.NROEMPRESA = Y.NROEMPRESA
 and CUSTOA.DTAENTRADASAIDA = ( select max( CUSTOB.DTAENTRADASAIDA )
 from MRL_CUSTODIAEMP CUSTOB
 where CUSTOB.SEQPRODUTO = CUSTOA.SEQPRODUTO
 and CUSTOB.NROEMPRESA = CUSTOA.NROEMPRESA
 and CUSTOB.DTAENTRADASAIDA <= nvl( '', sysdate ) ) ),

0

 ) ESTQFISCALEMPRESA,

nvl( Y.ESTQEMPRESA, 0 ) ESTQEMPRESA,
 sysdate DTAENTRADASAIDA, 
nvl( Y.CMULTVLRDESPFIXA, 0 ) CMULTVLRDESPFIXA,
nvl( Y.CMULTVLRDESCFIXO, 0 ) CMULTVLRDESCFIXO,
nvl( Y.CMULTVLRDESCRESTICMSTRANSF, 0 ) CMULTVLRDESCRESTICMSTRANSF ,

nvl( Y.CMULTVERBACOMPRA, 0 ) CMULTVERBACOMPRA,
nvl( Y.CMULTVERBABONIFINCID, 0 ) CMULTVERBABONIFINCID,
nvl( Y.CMULTVERBABONIFSEMINCID, 0 ) CMULTVERBABONIFSEMINCID,
nvl( Y.CMULTVLRDESCVERBATRANSFSELLIN, 0 ) CMULTVLRDESCVERBATRANSFSELLIN,
nvl( Y.CENTRULTVLRNF, 0 ) CENTRULTVLRNF,
nvl( Y.CENTRULTIPI, 0 ) CENTRULTIPI,
nvl( Y.CENTRULTICMSST, 0 ) CENTRULTICMSST,
nvl( Y.CENTRULTDESPNF, 0 ) CENTRULTDESPNF,
nvl( Y.CENTRULTDESPFORANF, 0 ) CENTRULTDESPFORANF,
nvl( Y.CENTRULTDCTOFORANF, 0 ) CENTRULTDCTOFORANF,
nvl( Y.CENTRULTCREDICMS, 0 ) CENTRULTCREDICMS,
nvl( Y.CENTRULTCREDIPI, 0 ) CENTRULTCREDIPI,
nvl( Y.CENTRULTCREDPIS, 0 ) CENTRULTCREDPIS,
nvl( Y.CENTRULTCREDCOFINS, 0 ) CENTRULTCREDCOFINS,
nvl( Y.QENTRULTCUSTO, 0 ) QENTRULTCUSTO,
Y.INDPOSICAOCATEG,
nvl( Y.CMULTDCTOFORANFEMP, 0 ) CMULTDCTOFORANFEMP,
nvl( Y.ESTQMINIMOLOJA, 0 ) QTDESTOQUEMINIMO, 
nvl( Y.ESTQMAXIMOLOJA, 0 ) QTDESTOQUEMAXIMO,
Y.DTAULTVENDA DTAULTVENDA,
null CLNCUSTOM1, 
null CLNCUSTOM2, 
null CLNCUSTOM3, 
null CLNCUSTOM4, 
null CLNCUSTOM5, 
null CLNCUSTOM6, 
null CLNCUSTOM7, 
null CLNCUSTOM8, 
null CLSCUSTOM9, 
null CLSCUSTOM10, 
null CLSCUSTOM11, 
null CLSCUSTOM12

from ( select SEQPRODUTO, NROEMPRESA, max( QTDEMBALAGEM ) QTDEMBALAGEMSEG, 
 max( case when statusvenda = 'I' or decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) = 0 then null
 else ( decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) / qtdembalagem )
 end ) PRECO, 
 min( case when statusvenda = 'I' or decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) = 0 then null
 else ( decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) / qtdembalagem )
 end ) MENORPRECO,
 max( case when statusvenda = 'I' or decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) = 0 then null
 else ( decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) / qtdembalagem )
 end ) MAIORPRECO,
 decode( min( STATUSVENDA ), 'A', min( STATUSVENDA ), 'I' ) STATUSVENDA

 from MRL_PRODEMPSEG
 where NROEMPRESA in ( 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,25,26,27,28,101,103,108,102,104,106,112,125,131,215,219,222,29,109,117 )
 group by SEQPRODUTO, NROEMPRESA ) X,
 MRL_PRODUTOEMPRESA Y 
, MAX_EMPRESA E 
where E.NROEMPRESA = Y.NROEMPRESA 
 and Y.NROEMPRESA = X.NROEMPRESA and Y.SEQPRODUTO = X.SEQPRODUTO
and X.SEQPRODUTO in ( select JP2.SEQPRODUTO
from MAP_FAMDIVCATEG JX2, MAP_PRODUTO JP2
where JP2.SEQFAMILIA = JX2.SEQFAMILIA
and JX2.STATUS = 'A'
and JX2.SEQCATEGORIA in ( 1, 1946, 1948, 1947 )
)
 


and Y.SEQPRODUTO in ( select FF.SEQPRODUTO
 from MAP_PRODUTO FF
 where FF.SEQFAMILIA not in ( select SEQFAMILIA
from MAP_FAMDIVISAO
where SEQCOMPRADOR = 14 ) )
and Y.SEQPRODUTO in ( select FF.SEQPRODUTO
 from MAP_PRODUTO FF
 where FF.SEQFAMILIA in ( select MAP_FAMDIVCATEG.SEQFAMILIA
 from MAP_CATEGORIA, MAP_FAMDIVCATEG
 where MAP_CATEGORIA.NRODIVISAO = E.NRODIVISAO
 and MAP_FAMDIVCATEG.SEQCATEGORIA = MAP_CATEGORIA.SEQCATEGORIA
 and MAP_FAMDIVCATEG.NRODIVISAO = MAP_CATEGORIA.NRODIVISAO
 and MAP_FAMDIVCATEG.STATUS = 'A'
 and MAP_CATEGORIA.TIPCATEGORIA = 'M'
 and MAP_CATEGORIA.STATUSCATEGOR in ( 'A', 'F' )
 and MAP_FAMDIVCATEG.SEQCATEGORIA in ( 1, 1946, 1948, 1947 )
 )
 ) 

) C, 
MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E, MAD_PARAMETRO J3, 
MAX_DIVISAO I2, MAP_CLASSIFABC Z2, MAD_FAMSEGMENTO H, MAP_REGIMETRIBUTACAO RT
, MAP_TRIBUTACAOUF T3 , MAPV_PISCOFINSTRIBUT SS, MAX_COMPRADOR O, MAP_FAMDIVCATEG W, MAD_SEGMENTO SE, MAP_PRODACRESCCUSTORELAC PR, 
MAP_FAMDIVCATEG FDC, MAP_CATEGORIA CAT

where A.SEQPRODUTO = C.SEQPRODUTO
and B.SEQFAMILIA = A.SEQFAMILIA 
and C.NROEMPRESA in ( 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,25,26,27,28,101,103,108,102,104,106,112,125,131,215,219,222,29,109,117 )
and D.SEQFAMILIA = A.SEQFAMILIA 
and D.NRODIVISAO = E.NRODIVISAO
and K.SEQFAMILIA = D.SEQFAMILIA 
and K.QTDEMBALAGEM = 1
and E.NROEMPRESA = C.NROEMPRESA
and J3.NROEMPRESA = E.NROEMPRESA 
and I2.NRODIVISAO = E.NRODIVISAO 
and I2.NRODIVISAO = D.NRODIVISAO
and Z2.NROSEGMENTO = H.NROSEGMENTO 
and Z2.CLASSIFCOMERCABC = H.CLASSIFCOMERCABC 
and Z2.NROSEGMENTO = SE.NROSEGMENTO 
and T3.NROTRIBUTACAO = D.NROTRIBUTACAO 
and T3.UFEMPRESA = nvl( E.UFFORMACAOPRECO, E.UF ) 
and T3.UFCLIENTEFORNEC = E.UF
and T3.TIPTRIBUTACAO = decode( I2.TIPDIVISAO, 'V', 'SN', 'SC' ) 
and T3.NROREGTRIBUTACAO = nvl( E.NROREGTRIBUTACAO, 0 ) 
and a.seqfamilia = fdc.seqfamilia
and cat.nrodivisao = e.nrodivisao
and fdc.seqcategoria = cat.seqcategoria
and fdc.nrodivisao = cat.nrodivisao
and b.seqfamilia = a.seqfamilia
and cat.nivelhierarquia = 1
and cat.statuscategor in ('A','F')
and fdc.status = 'A'
and cat.tipcategoria = 'M' 
and C.SEQPRODUTO = PR.SEQPRODUTO(+) 
and C.DTAENTRADASAIDA = PR.DTAMOVIMENTACAO(+) 
and SS.NROEMPRESA = E.NROEMPRESA
and SS.NROTRIBUTACAO = T3.NROTRIBUTACAO 
and SS.UFEMPRESA = T3.UFEMPRESA
and SS.UFCLIENTEFORNEC = T3.UFCLIENTEFORNEC
and SS.TIPTRIBUTACAO = T3.TIPTRIBUTACAO
and SS.NROREGTRIBUTACAO = T3.NROREGTRIBUTACAO 
and SS.SEQFAMILIA = B.SEQFAMILIA and O.SEQCOMPRADOR = D.SEQCOMPRADOR
and W.SEQFAMILIA = D.SEQFAMILIA
and W.NRODIVISAO = D.NRODIVISAO
and W.STATUS = 'A'
and W.SEQCATEGORIA in ( 1, 1946, 1948, 1947 ) and H.SEQFAMILIA = A.SEQFAMILIA and H.NROSEGMENTO = E.NROSEGMENTOPRINC and T3.NROREGTRIBUTACAO = RT.NROREGTRIBUTACAO

and D.SEQCOMPRADOR != 14
and ( ESTQTROCA ) != 0 
 and A.SEQPRODUTOBASE IS NULL 
group by E.NROEMPRESA
having round( round( sum( ( ESTQTROCA ) / K.QTDEMBALAGEM ), 6 ) , 6 ) != 0
""",
    },

    "prev_ind_inv_geral": {
        "nome": "Prevenção - Inventário Geral (snapshot)",
        "destino": "meta/prevIndInvGeral",
        "sql": """
select 
E.NROEMPRESA as LOJA,
count(distinct C.SEQPRODUTO) as NROITENS

from MAP_PRODUTO A, MAP_FAMILIA B,
( select Y.SEQPRODUTO, Y.NROEMPRESA, Y.SEQCLUSTER ,
decode( ( ESTQLOJA + ESTQDEPOSITO ), 0, null, Y.SEQPRODUTO ) SEQPRODUTOCOMESTQ,
 decode( X.PRECO, 0, X.MENORPRECO, X.PRECO ) PRECO, X.MENORPRECO, X.MAIORPRECO, Y.NROGONDOLA, Y.ESTQLOJA, Y.ESTQDEPOSITO, Y.ESTQTROCA, Y.ESTQALMOXARIFADO, Y.ESTQOUTRO, nvl( Y.ESTQTERCEIRO, 0 ) ESTQTERCEIRO,
Y.QTDPENDPEDCOMPRA, Y.QTDPENDPEDEXPED, 
Y.QTDRESERVADAVDA, Y.QTDRESERVADARECEB, Y.QTDRESERVADAFIXA, 
Y.MEDVDIAPROMOC, Y.MEDVDIAGERAL, Y.MEDVDIAFORAPROMOC, 
Y.CMULTVLRNF, 
Y.CMULTIPI, 
Y.CMULTCREDICMS, 
Y.CMULTICMSST, 
Y.CMULTDESPNF, 
Y.CMULTDESPFORANF, 
Y.CMULTDCTOFORANF, 
nvl( Y.CMULTIMPOSTOPRESUM, 0 ) CMULTIMPOSTOPRESUM,
nvl( Y.CMULTCREDICMSPRESUM, 0 ) CMULTCREDICMSPRESUM,
nvl( Y.CMULTCREDICMSANTECIP, 0 ) CMULTCREDICMSANTECIP,
nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) CMULTCUSLIQUIDOEMP,
nvl( Y.CMULTCREDICMSEMP, 0 ) CMULTCREDICMSEMP,
nvl( Y.CMULTCREDPISEMP, 0 ) CMULTCREDPISEMP,
nvl( Y.CMULTCREDCOFINSEMP, 0 ) CMULTCREDCOFINSEMP,
nvl( Y.CMULTCREDPIS, 0 ) CMULTCREDPIS,
nvl( Y.CMULTCREDCOFINS, 0 ) CMULTCREDCOFINS,
Y.STATUSCOMPRA,  X.STATUSVENDA,
trunc( sysdate ) - Y.DTAULTENTRADA DIASULTENTRADA, 
nvl( Y.NROSEGPRODUTO, E.NROSEGMENTOPRINC ) NROSEGPRODUTO, 
Y.LOCENTRADA, Y.LOCSAIDA,
nvl( Y.CLASSEABASTQTD, '**Sem Classificação**' ) CLASSEABASTQTD, 
nvl( Y.CLASSEABASTVLR, '**Sem Classificação**' ) CLASSEABASTVLR,
nvl( Y.CMULTVLRCOMPROR, 0 ) CMULTVLRCOMPROR,
nvl( Y.CMULTVLRDESCPISTRANSF, 0 ) CMULTVLRDESCPISTRANSF,
nvl( Y.CMULTVLRDESCCOFINSTRANSF, 0 ) CMULTVLRDESCCOFINSTRANSF,
nvl( Y.CMULTVLRDESCICMSTRANSF, 0 ) CMULTVLRDESCICMSTRANSF, 
nvl( Y.CMULTVLRDESCLUCROTRANSF, 0 ) CMULTVLRDESCLUCROTRANSF,
nvl( Y.CMULTVLRDESCIPITRANSF, 0 ) CMULTVLRDESCIPITRANSF,
nvl( Y.CMULTVLRDESCVERBATRANSF, 0 ) CMULTVLRDESCVERBATRANSF,
nvl( Y.CMULTVLRDESCDIFERENCATRANSF, 0 ) CMULTVLRDESCDIFERENCATRANSF,
nvl( Y.CMULTCREDIPI, 0 ) CMULTCREDIPI, 
trunc( sysdate ) - Y.DTAULTENTRCUSTO DIASULTENTRCUSTO,
( nvl( Y.CMULTVLRDESCPISTRANSF, 0 ) + nvl( Y.CMULTVLRDESCCOFINSTRANSF, 0 ) + nvl( Y.CMULTVLRDESCICMSTRANSF, 0 ) + nvl( Y.CMULTVLRDESCIPITRANSF, 0 )
  + nvl( Y.CMULTVLRDESCLUCROTRANSF, 0 ) + nvl( Y.CMULTVLRDESCVERBATRANSF, 0 ) + nvl( Y.CMULTVLRDESCDIFERENCATRANSF, 0 ) ) VLRDESCTRANSFCB,
Y.SEQSENSIBILIDADE, 
Y.FORMAABASTECIMENTO, case when nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 ) < 0 
 then 0 
 else nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 )
end CUSTOFISCALUNIT, 

case when nvl( ( nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 ) ) * Y.ESTQEMPRESA, 0 ) < 0 
 then 0
 else nvl( ( nvl( Y.CMULTCUSLIQUIDOEMP, 0 ) - nvl( Y.CMULTDCTOFORANFEMP, 0 ) ) * Y.ESTQEMPRESA, 0 ) 
end CUSTOFISCALTOTAL, 


coalesce(
                            
        (select  ( CUSTOA.QTDESTQINICIALEMP + CUSTOA.QTDENTRADAEMP - CUSTOA.QTDSAIDAEMP)
           from MRL_CUSTODIAEMP CUSTOA
         where CUSTOA.SEQPRODUTO = Y.SEQPRODUTO
            and CUSTOA.NROEMPRESA = Y.NROEMPRESA
            and CUSTOA.DTAENTRADASAIDA = nvl('', sysdate ) ),

           ( select  ( CUSTOA.QTDESTQINICIALEMP + CUSTOA.QTDENTRADAEMP - CUSTOA.QTDSAIDAEMP)
           from MRL_CUSTODIAEMP CUSTOA
         where CUSTOA.SEQPRODUTO = Y.SEQPRODUTO
            and CUSTOA.NROEMPRESA = Y.NROEMPRESA
            and CUSTOA.DTAENTRADASAIDA = ( select max( CUSTOB.DTAENTRADASAIDA )
     from MRL_CUSTODIAEMP CUSTOB
     where CUSTOB.SEQPRODUTO = CUSTOA.SEQPRODUTO
        and CUSTOB.NROEMPRESA = CUSTOA.NROEMPRESA
        and CUSTOB.DTAENTRADASAIDA <= nvl('', sysdate ) ) ),

0

 ) ESTQFISCALEMPRESA,

nvl( Y.ESTQEMPRESA, 0 ) ESTQEMPRESA,
 sysdate DTAENTRADASAIDA, 
nvl( Y.CMULTVLRDESPFIXA, 0 ) CMULTVLRDESPFIXA,
nvl( Y.CMULTVLRDESCFIXO, 0 ) CMULTVLRDESCFIXO,
nvl( Y.CMULTVLRDESCRESTICMSTRANSF, 0 ) CMULTVLRDESCRESTICMSTRANSF ,

nvl( Y.CMULTVERBACOMPRA, 0 ) CMULTVERBACOMPRA,
nvl( Y.CMULTVERBABONIFINCID, 0 ) CMULTVERBABONIFINCID,
nvl( Y.CMULTVERBABONIFSEMINCID, 0 ) CMULTVERBABONIFSEMINCID,
nvl( Y.CMULTVLRDESCVERBATRANSFSELLIN, 0 ) CMULTVLRDESCVERBATRANSFSELLIN,
nvl( Y.CENTRULTVLRNF, 0 ) CENTRULTVLRNF,
nvl( Y.CENTRULTIPI, 0 ) CENTRULTIPI,
nvl( Y.CENTRULTICMSST, 0 ) CENTRULTICMSST,
nvl( Y.CENTRULTDESPNF, 0 ) CENTRULTDESPNF,
nvl( Y.CENTRULTDESPFORANF, 0 ) CENTRULTDESPFORANF,
nvl( Y.CENTRULTDCTOFORANF, 0 ) CENTRULTDCTOFORANF,
nvl( Y.CENTRULTCREDICMS, 0 ) CENTRULTCREDICMS,
nvl( Y.CENTRULTCREDIPI, 0 ) CENTRULTCREDIPI,
nvl( Y.CENTRULTCREDPIS, 0 ) CENTRULTCREDPIS,
nvl( Y.CENTRULTCREDCOFINS, 0 ) CENTRULTCREDCOFINS,
nvl( Y.QENTRULTCUSTO, 0 ) QENTRULTCUSTO,
Y.INDPOSICAOCATEG,
nvl( Y.CMULTDCTOFORANFEMP, 0 ) CMULTDCTOFORANFEMP,
nvl( Y.ESTQMINIMOLOJA, 0 ) QTDESTOQUEMINIMO, 
nvl( Y.ESTQMAXIMOLOJA, 0 ) QTDESTOQUEMAXIMO,
Y.DTAULTVENDA DTAULTVENDA,
null CLNCUSTOM1, 
null CLNCUSTOM2, 
null CLNCUSTOM3, 
null CLNCUSTOM4, 
null CLNCUSTOM5, 
null CLNCUSTOM6, 
null CLNCUSTOM7, 
null CLNCUSTOM8, 
null CLSCUSTOM9, 
null CLSCUSTOM10, 
null CLSCUSTOM11, 
null CLSCUSTOM12

from  ( select SEQPRODUTO, NROEMPRESA, max( QTDEMBALAGEM ) QTDEMBALAGEMSEG, 
 max( case when statusvenda = 'I' or decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) = 0 then null
                        else ( decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) / qtdembalagem )
                        end ) PRECO, 
 min( case when statusvenda = 'I' or decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) = 0 then null
                           else ( decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) / qtdembalagem )
                           end ) MENORPRECO,
 max( case when statusvenda = 'I' or decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) = 0 then null
                           else ( decode( precovalidpromoc, 0, precovalidnormal, precovalidpromoc ) / qtdembalagem )
                           end ) MAIORPRECO,
 decode( min( STATUSVENDA ), 'A', min( STATUSVENDA ), 'I' ) STATUSVENDA

 from MRL_PRODEMPSEG
 where NROEMPRESA in (5,7,10,11,13,14,16,18,20,21,23,26,27,28,101,103,108,102,104,106,112,125,131,215,219,222,29,109,117)
 and SEQPRODUTO not in ( 14627,14628,14629,14641,14636,14640,14638,14635,14637,14634,14633,14632,14631,14630,14639,14642 ) group by SEQPRODUTO, NROEMPRESA ) X,
  MRL_PRODUTOEMPRESA  Y 
, MAX_EMPRESA E 
where E.NROEMPRESA = Y.NROEMPRESA 
 and Y.NROEMPRESA = X.NROEMPRESA and Y.SEQPRODUTO = X.SEQPRODUTO
and X.SEQPRODUTO in ( select JP2.SEQPRODUTO
from MAP_FAMDIVCATEG JX2, MAP_PRODUTO JP2
where JP2.SEQFAMILIA = JX2.SEQFAMILIA
and JX2.STATUS = 'A'
and JX2.SEQCATEGORIA in ( 1, 1946, 1948, 1947 )
)
  


and Y.SEQPRODUTO in ( select FF.SEQPRODUTO
                                   from MAP_PRODUTO FF
                                where FF.SEQFAMILIA not in ( select SEQFAMILIA
from MAP_FAMDIVISAO
where SEQCOMPRADOR = 14 ) )
and Y.SEQPRODUTO in ( select FF.SEQPRODUTO
                                   from MAP_PRODUTO FF
                                where FF.SEQFAMILIA in ( select MAP_FAMDIVCATEG.SEQFAMILIA
   from MAP_CATEGORIA, MAP_FAMDIVCATEG
   where MAP_CATEGORIA.NRODIVISAO = E.NRODIVISAO
   and MAP_FAMDIVCATEG.SEQCATEGORIA = MAP_CATEGORIA.SEQCATEGORIA
   and MAP_FAMDIVCATEG.NRODIVISAO = MAP_CATEGORIA.NRODIVISAO
   and MAP_FAMDIVCATEG.STATUS = 'A'
   and MAP_CATEGORIA.TIPCATEGORIA = 'M'
   and MAP_CATEGORIA.STATUSCATEGOR in ( 'A', 'F' )
   and MAP_FAMDIVCATEG.SEQCATEGORIA in ( 1, 1946, 1948, 1947 )
                              )
                          ) 

) C, 
MAP_FAMDIVISAO D, MAP_FAMEMBALAGEM K, MAX_EMPRESA E, MAD_PARAMETRO J3, 
MAX_DIVISAO I2, MAP_CLASSIFABC Z2, MAD_FAMSEGMENTO H, MAP_REGIMETRIBUTACAO RT
, MAP_TRIBUTACAOUF T3 , MAPV_PISCOFINSTRIBUT SS, MAP_FAMDIVCATEG W, MAD_SEGMENTO SE, MAP_PRODACRESCCUSTORELAC PR, 
MAP_FAMDIVCATEG FDC, MAP_CATEGORIA CAT

where A.SEQPRODUTO = C.SEQPRODUTO
and B.SEQFAMILIA = A.SEQFAMILIA 
and C.NROEMPRESA in (5,7,10,11,13,14,16,18,20,21,23,26,27,28,101,103,108,102,104,106,112,125,131,215,219,222,29,109,117)
and D.SEQFAMILIA = A.SEQFAMILIA 
and D.NRODIVISAO = E.NRODIVISAO
and K.SEQFAMILIA = D.SEQFAMILIA 
and K.QTDEMBALAGEM = 1
and E.NROEMPRESA = C.NROEMPRESA
and J3.NROEMPRESA = E.NROEMPRESA 
and I2.NRODIVISAO = E.NRODIVISAO 
and I2.NRODIVISAO = D.NRODIVISAO
and Z2.NROSEGMENTO = H.NROSEGMENTO 
and Z2.CLASSIFCOMERCABC = H.CLASSIFCOMERCABC 
and Z2.NROSEGMENTO = SE.NROSEGMENTO  
and T3.NROTRIBUTACAO = D.NROTRIBUTACAO 
and T3.UFEMPRESA = nvl( E.UFFORMACAOPRECO, E.UF ) 
and T3.UFCLIENTEFORNEC = E.UF
and T3.TIPTRIBUTACAO = decode( I2.TIPDIVISAO, 'V', 'SN', 'SC' ) 
and T3.NROREGTRIBUTACAO = nvl( E.NROREGTRIBUTACAO, 0 ) 
and a.seqfamilia      = fdc.seqfamilia
and cat.nrodivisao = e.nrodivisao
and    fdc.seqcategoria    = cat.seqcategoria
and    fdc.nrodivisao      = cat.nrodivisao
and    b.seqfamilia      = a.seqfamilia
and    cat.nivelhierarquia = 1
and    cat.statuscategor   in ('A','F')
and    fdc.status          =  'A'
and    cat.tipcategoria = 'M' 
and C.SEQPRODUTO = PR.SEQPRODUTO(+) 
and C.DTAENTRADASAIDA = PR.DTAMOVIMENTACAO(+)  
and SS.NROEMPRESA = E.NROEMPRESA
and SS.NROTRIBUTACAO = T3.NROTRIBUTACAO 
and SS.UFEMPRESA = T3.UFEMPRESA
and SS.UFCLIENTEFORNEC = T3.UFCLIENTEFORNEC
and SS.TIPTRIBUTACAO = T3.TIPTRIBUTACAO
and SS.NROREGTRIBUTACAO = T3.NROREGTRIBUTACAO 
and SS.SEQFAMILIA = B.SEQFAMILIA 
and W.SEQFAMILIA = D.SEQFAMILIA
and W.NRODIVISAO = D.NRODIVISAO
and W.STATUS = 'A'
and W.SEQCATEGORIA in ( 1, 1946, 1948, 1947 ) and H.SEQFAMILIA = A.SEQFAMILIA and H.NROSEGMENTO = E.NROSEGMENTOPRINC and T3.NROREGTRIBUTACAO = RT.NROREGTRIBUTACAO

and fstatusvendaproduto( c.Seqproduto, c.Nroempresa, se.Nrosegmento ) = 'A'
and D.SEQCOMPRADOR != 14
and A.SEQPRODUTO not in ( 14627,14628,14629,14641,14636,14640,14638,14635,14637,14634,14633,14632,14631,14630,14639,14642 )
and ( ESTQLOJA + ESTQDEPOSITO ) < 0 
 and A.SEQPRODUTOBASE IS NULL 
group by E.NROEMPRESA
having round( round( sum( ( ESTQLOJA + ESTQDEPOSITO ) / K.QTDEMBALAGEM ), 6 ) , 6 ) < 0
""",
    },

}

# ─────────────────────────────────────────────────────────────────────────────
# Slugs EXCLUÍDOS do carregamento diário automático (agente _scheduler_diario /
# task "tudo"). Continuam definidos em QUERIES/QUERIES_DIMENSOES e podem ser
# rodados sob demanda (passando slug/slugs), mas NÃO entram no run noturno.
# Decisão do user (2026-05-23): Prevenção não é mais usada no controllsv e não
# é consumida pelo projeto-comercial. Todas as prev_* (consultas pesadas, ex.
# "Vendas por Produto" levava ~8min) saem do diário.
# ─────────────────────────────────────────────────────────────────────────────
SLUGS_SKIP_DIARIO = {s for s in {**QUERIES, **QUERIES_DIMENSOES} if s.startswith("prev_")}
