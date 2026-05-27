# Visual HTML — META x REAL

## Pré-requisito: instalar visual "HTML Content"
1. No Power BI Desktop, vá em **Visualizações** > **três pontos** (…) > **Obter mais visuais**.
2. Procure por **"HTML Content"** (de Daniel Marsh-Patrick) — gratuito, certificado pela Microsoft.
3. Instale e ele aparece no painel de Visualizações.

> Alternativas (qualquer um destes funciona com a mesma medida):
> - **HTML Viewer** (CloudScope)
> - **simple HTML Viewer**

## Adicionar a medida HTML
1. Na tabela **`Metas AV%`** (botão direito) > **Nova medida**.
2. Cole TODO o conteúdo de `05_html_meta_x_real.dax` (sem o cabeçalho).
3. Confirme.

## Adicionar o visual à aba
1. Vá na página **META x REAL** (já criada conforme `04_aba_meta_x_real.md`).
2. Clique no visual **HTML Content** no painel de Visualizações.
3. No painel **Dados do visual**, arraste a medida `META x REAL HTML` para o campo **Values** (Valores).
4. Redimensione o visual para algo como **1100 x 700** px.

## Resultado esperado
Visual HTML com **duas seções**:

### 1) Tabela detalhada META x REAL
- Cabeçalho **verde escuro** (`#1a3a2f`) — alinhado ao Dashboard Executivo.
- 30 linhas ordenadas conforme sua planilha (Venda Bruta → Lucro Líquido).
- **Totalizadores** (Margem S/ Acordos, Margem C/ Acordos, Margem Operacional, EBITDA, LAIR, Lucro Líquido) destacados em **amarelo** (`#FFF2A8`).
- 8 colunas: Agrupamento • **Real R$** • **Meta R$** • **Δ R$** • Real AV% • Meta AV% • Δ p.p. • Comparativo.
- Valores em R$ formatados em milhões (`R$ X,XX M`).
- **Meta R$ = Venda Bruta Realizada × Meta AV%** — a meta em valor é derivada dinamicamente do top-line realizado, então sobe e desce conforme o filtro (loja/mês/ano).
- Na linha de **Venda Bruta**, `Meta R$` coincide com `Real R$` por construção (Meta% = 100%).
- Variações favoráveis em verde (`#1e7a4a`), desfavoráveis em vermelho (`#c0392b`).

### 2) Ranking de Impacto (Δ R$ vs Meta)
- Logo abaixo da tabela.
- Cada agrupamento como uma linha com barra horizontal **centrada em zero**.
- Verde à direita = contribuição positiva (acima da meta).
- Vermelho à esquerda = contribuição negativa (abaixo da meta).
- Ordenado da maior contribuição positiva no topo até a maior negativa no fundo.
- Escala compartilhada (mesma régua para todas as linhas), com referência no zero.

## Características da medida HTML
- Itera sobre `Metas AV%` com `CONCATENATEX` ordenado por `Ordem`.
- Calcula `Venda Bruta R$` UMA vez fora do loop (no contexto da página/visual) — depois multiplica pela meta% de cada linha para obter `Meta R$`.
- Usa `FILTER(ALL('PLANO'[AGRUPAMENTO]), ...)` para `Real R$` — funciona **mesmo sem o relacionamento ativo** entre `Metas AV%` e `AGRUPAMENTO` (mas o relacionamento ainda é útil para filtros cruzados em outros visuais).
- Reage normalmente a slicers de `ANO`, `MÊS`, `LOJA`, `EMPRESAS` da aba — Venda Bruta R$ se recalcula no filtro e arrasta todas as metas R$ junto.
- Encoding: UTF-8 nativo — acentos preservados.

## Customização rápida
Dentro da medida você pode trocar:
- `#1F4E79` (azul do header) — cor primária do tema da empresa
- `#FFF2A8` (amarelo dos totais)
- `#1e7a4a` / `#c0392b` (verde / vermelho)
- `width:90px` na `.bar-track` para barras mais largas/curtas
