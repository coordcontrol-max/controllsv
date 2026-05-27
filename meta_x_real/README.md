# META x REAL — Comparativo por AGRUPAMENTO

Ordem para aplicar no Power BI Desktop (arquivo `dree.pbix` já aberto):

| # | Arquivo                       | Onde colar                                          |
|---|-------------------------------|-----------------------------------------------------|
| 1 | `01_tabela_metas.dax`         | Modelagem > **Nova tabela**                         |
| 2 | `02_relacionamento.md`        | Modelo (diagrama) — criar relacionamento manual     |
| 3 | `03_medidas.dax`              | Botão direito em `Metas AV%` > **Nova medida** (uma por vez) |
| 4 | `04_aba_meta_x_real.md`       | Criar página nova e montar os visuais conforme guia |
| 5 | `05_html_meta_x_real.dax`     | Nova medida `META x REAL HTML` na tabela `Metas AV%` |
| 6 | `06_visual_html.md`           | Instalar visual "HTML Content" e adicionar à aba    |

## Validação rápida da meta importada

Após criar a tabela `Metas AV%`, esta DAX deve retornar 30 linhas e somar a 30 metas:

```dax
EVALUATE 'Metas AV%' ORDER BY [Ordem]
```

## Conferência de aderência

A coluna `AGRUPAMENTO` em `Metas AV%` foi nomeada com a grafia EXATA encontrada em `AGRUPAMENTO[AGRUPAMENTO]` no modelo (verificado em 2026-05-15). Os 30 valores casam 1-para-1 — relacionamento `*:1` funcionará sem inconsistências.

## Convenção de sinal

A coluna `Meta AV%` foi salva com sinal:
- **Receitas/Margens/Totais**: positivo (ex.: Venda Bruta = 100,00%, EBITDA = 2,90%).
- **Custos/Despesas**: negativo (ex.: Mercadoria para Revenda = -79,30%, Despesas c/ Pessoal = -12,00%).

Assim `Variação p.p. (Real vs Meta) = Real - Meta` é sempre interpretável da mesma forma: positivo = favorável.

## Coluna `Tipo`

Adicionada para facilitar formatação (destaque dos totais em amarelo, semelhante à planilha):
- `Receita`, `Custo`, `Margem`, `Despesa`, `Total`.

## Por que não pushei direto no arquivo .pbix?

Tentei pushar a tabela e medidas via XMLA/TMSL no SSAS local do Power BI Desktop (porta 60413). **Resultado: rejeitado.** O endpoint da versão Desktop só aceita TMSL no nível `model`/`database` completo — não permite `createOrReplace` granular de medidas ou tabelas. Para fazer push granular seria preciso reescrever o modelo inteiro num único comando, o que é arriscado num arquivo aberto numa pasta de rede (`\\10.61.1.13\controller\...`).

Por isso o caminho seguro é copy-paste pela UI do Power BI Desktop, que valida tudo automaticamente e o save fica gravado no `dree.pbix`.
