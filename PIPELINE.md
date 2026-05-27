# Pipeline de dados — Dashboard Executivo (DRE)

## Arquitetura

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  00 - Base.xlsx             │    │  01 - Classificação.xlsx    │
│  (transacional, 21 abas)    │    │  (8 dimensões: PLANO,       │
│  ~17 MB                     │    │   EMPRESAS, MÊS, LOJA, …)   │
└──────────────┬──────────────┘    └──────────────┬──────────────┘
               │                                  │
               └────────────────┬─────────────────┘
                                ▼
              ┌──────────────────────────────────────┐
              │  02 - Valores Rateados.xlsx          │
              │  ─ aba 'VALORES RATEADOS' (21k rows) │
              │  ─ abas BASE1..BASE15 (pivots)       │
              │  ─ aba REGRAS_RATEIO (115 regras)    │
              │  Tabela JÁ consolidada por loja/mês  │
              └──────────────────┬───────────────────┘
                                 ▼
                          ┌──────────────┐
                          │   etl.py     │  Python (pandas+openpyxl)
                          └──────┬───────┘
                                 ▼
                       ┌───────────────────┐
                       │   dados.json      │  ~3,6 MB
                       │   (fato + dims)   │
                       └─────────┬─────────┘
                                 ▼
                       ┌───────────────────┐
                       │  dashboard.html   │  Chart.js (CDN)
                       └───────────────────┘
```

## Componentes

| Arquivo | Papel |
|---|---|
| `etl.py` | Lê os 3 Excel, faz join com `PLANO` para anexar `GRUPO`/`AGRUPAMENTO` a cada `LINHA`, agrega por `(ANO, MÊS, LOJA, GRUPO)` / `… AGRUPAMENTO` / `… LINHA` e grava `dados.json`. |
| `dados.json` | Payload consumido pelo painel. Contém dimensões (anos, meses, lojas, grupos), 3 tabelas de fatos pré-agregadas e o `mapeamentoKPI` (qual GRUPO alimenta cada cartão). |
| `dashboard.html` | Lê `dados.json` via `fetch`, monta os 10 cartões de KPI (com mini-barras Jan/Fev/Mar), o gráfico de barras horizontais (% das despesas) e o donut (composição das despesas). Filtros `ANO`/`MÊS`/`LOJA` recalculam tudo client-side. |
| `inspect_files.py` | Diagnóstico — lista abas, colunas, dtypes e amostra das 3 planilhas. |
| `inspect_domain.py` | Lista o domínio completo de `GRUPO/PLANO/LINHAS` (útil ao adicionar novos KPIs). |
| `validate_kpis.py` | Roda os 10 KPIs do painel a partir do JSON e compara com os números-alvo. |
| `run.sh` | Atalho: `./run.sh` recalcula o JSON e sobe `http://localhost:8765/dashboard.html`. |

## Mapeamento KPI → GRUPO

| Card no painel | GRUPO(s) somados |
|---|---|
| Receita Total | `Venda Bruta` |
| CMV | `CMV` |
| Margem PDV | `Margem S/ Acordos` |
| Margem c/ Acordos Recebidos | `Margem C/ Acordos` |
| Margem c/ Acordos Lançados | `Margem C/ Acordos Lançados` |
| Quebras | `Quebra Contábil` |
| Despesas | `Despesas Operacionais` + `Despesa Comerciais` + `Despesas Administrativas` + `Despesas C/ Vendas` |
| Ajustes e Novas Unidades | `Novas Unidades e Ajustes Gerenciais` |
| Carga Total de Despesas | `Despesas` (acima) + `Novas Unidades e Ajustes Gerenciais` |
| Lucro Líquido | `Lucro Líquido` |

Validação contra o painel original (ano 2026, todas as lojas, todos os meses):

```
RECEITA_TOTAL              R$ +153,28M   +100,00%   ✓
CMV                        R$ -127,26M    -83,02%   ✓
MARGEM_PDV                 R$  +26,02M    +16,98%   ✓
MARGEM_ACORDOS_RECEBIDOS   R$  +33,68M    +21,97%   ✓
MARGEM_ACORDOS_LANCADOS    R$  +29,34M    +19,14%   ✓
QUEBRAS                    R$   -2,66M     -1,74%   ✓
DESPESAS                   R$  -32,87M    -21,45%   ✓
AJUSTES_NOVAS_UNIDADES     R$   -8,86M     -5,78%   ✓
CARGA_TOTAL_DESPESAS       R$  -41,74M    -27,23%   ✓
LUCRO_LIQUIDO              R$   -2,89M     -1,89%   ✓
```

## Como rodar

```bash
cd /root/projeto_dre

# Recalcular dados.json a partir do Desktop e subir o servidor:
./run.sh

# Apenas atualizar o JSON (sem servidor):
./run.sh --etl-only

# Validar KPIs contra os números-alvo do painel:
python3 validate_kpis.py
```

Abra: <http://localhost:8765/dashboard.html>

## Observações sobre o fluxo Excel → Excel

A planilha `02 - Valores Rateados.xlsx` **já é** o produto consolidado. As 15 abas `BASE1..BASE15` contêm tabelas dinâmicas (pivots) que extraem do `00 - Base.xlsx` os números agregados por `(ANO, MÊS, LOJA)` para cada categoria (compras, despesas, juros, etc). A aba `REGRAS_RATEIO` aplica os pesos finais sobre esses pivots para gerar a tabela `VALORES RATEADOS`.

**Esta pipeline em Python NÃO recalcula o rateio** — ela respeita o trabalho já feito na planilha do usuário e apenas consome a tabela final consolidada (`VALORES RATEADOS`). Isso evita risco de divergência com a fórmula original, que envolve regras complexas (rateio por venda bruta, peso de 13º salário, INSS, etc.).

Se for necessário **regerar** `02 - Valores Rateados.xlsx` automaticamente a partir do zero (em vez de só consumi-lo), as regras precisam ser documentadas explicitamente — ou a planilha mantida atualizada via Excel/Power Query no fluxo do usuário e o ETL aqui simplesmente reflete o resultado.

## Adicionando um novo KPI

1. Identifique o(s) `GRUPO(s)` correspondente(s) na aba `PLANO` (use `inspect_domain.py`).
2. Adicione a entrada em `etl.py` no dicionário `mapeamentoKPI`.
3. Inclua o card em `dashboard.html` no array `KPI_CONFIG`.
4. Re-rode `./run.sh --etl-only`.
