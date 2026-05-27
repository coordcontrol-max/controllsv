# Aba "META x REAL" — passo a passo

## 1. Criar a página
- Clique no **+** na barra inferior das páginas.
- Renomeie para **`META x REAL`** (ou **`Meta e Real`** para alinhar com seu padrão).
- Tamanho recomendado: **16:9** (Exibição > Tamanho da página > 16:9).
- Tema/Background: combine com o "Dashboard Executivo" (header verde escuro `#1a3a2f`).

## 2. Slicers (Ano / Mês / Loja / Empresa)
Topo da página, em linha. Para cada slicer:

1. Painel **Visualizações** > **Segmentação de dados**.
2. Estilo: **Lista suspensa** (compacta) — clique nos três pontos do visual > Formatar visual > Configurações de slicer > Estilo > "Lista suspensa".
3. Arraste as colunas:

| Slicer       | Campo                         | Posição sugerida |
|--------------|-------------------------------|------------------|
| ANO          | `ANO[ANO]`                    | Topo esquerda    |
| MÊS          | `MÊS[MÊS]`                    | Topo +1          |
| LOJA         | `LOJA[LOJA]`                  | Topo +2          |
| EMPRESA      | `EMPRESAS[EMPRESAS]`          | Topo direita     |

Tamanho: largura ~140 px × altura ~50 px cada. Cor do título: `#1a3a2f`.

> Os slicers filtram todos os visuais da página automaticamente, incluindo a medida HTML — o `Real R$`, `Meta R$` (derivada de Venda Bruta), Real AV% e o ranking se recalculam vivo conforme a seleção.

## 3. Visual principal: HTML Content
Conforme `06_visual_html.md`. Já inclui:
- Tabela detalhada com 8 colunas (Real R$ • Meta R$ • Δ R$ • Real AV% • Meta AV% • Δ p.p. • Comparativo)
- **Ranking de Impacto (Δ R$)** — linha por agrupamento, ordenado da maior contribuição positiva à maior negativa
- Cabeçalho verde escuro alinhado ao Dashboard Executivo

Tamanho: **1300 × 800** px ocupando o corpo da página abaixo dos slicers.

## 4. Alternativa nativa do PBI para o ranking (opcional)
Se preferir um ranking interativo separado do HTML:

1. Visual **Gráfico de barras agrupadas horizontais** (próximo ao HTML ou substituindo o ranking dele).
2. Eixo Y: `AGRUPAMENTO[AGRUPAMENTO]`
3. Eixo X: `Variação R$ (Real vs Meta)`
4. **Classificar eixo > Classificar por Variação R$ (Real vs Meta) (Decrescente)** — ranking automático
5. Cor dos dados > **fx** > Field value = `Cor Variação Meta`
6. Linha de referência constante em 0.

## 5. Cartões de KPI (acima da tabela, opcional)
Quatro cartões "Multi-row card" com os totalizadores principais:

| Cartão                | Filtro de visual                                    | Campos        |
|-----------------------|------------------------------------------------------|---------------|
| Margem S/ Acordos     | `AGRUPAMENTO[AGRUPAMENTO] = "Margem S/ Acordos"`     | `Real R$`, `Meta R$`, `Variação R$ (Real vs Meta)` |
| Margem Operacional    | `= "Margem Operacional"`                              | mesma combinação |
| EBITDA                | `= "EBITDA"`                                          | mesma combinação |
| Lucro Líquido         | `= "Lucro Líquido"`                                   | mesma combinação |

Cor de fundo de cada cartão: usar a cor do card correspondente no Dashboard Executivo.

## 6. Ordenação correta nos visuais com AGRUPAMENTO
Clique na coluna `AGRUPAMENTO[AGRUPAMENTO]` no painel Dados > **"Classificar por outra coluna"** > escolha `AGRUPAMENTO[Ordem]`.
Isso garante a sequência DRE em qualquer visual (Venda Bruta primeiro, Lucro Líquido por último).
