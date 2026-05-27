# Adicionar card "Receitas Comerciais" na Home

O dashboard Home usa **uma única medida HTML chamada `Medida`** que renderiza todos os 10 cards de uma vez. Para incluir um 11º (Receitas Comerciais), siga 3 passos.

## Passo 1 — Criar 2 medidas KPI base

Clique direito na tabela `dree` (ou `VALORES RATEADOS`) > **Nova medida**. Cole uma por vez:

```dax
KPI Receitas Comerciais =
CALCULATE( [VALORES], 'PLANO'[GRUPO] = "Receitas Comerciais" )
```

```dax
KPI Receitas Comerciais % =
DIVIDE(
    CALCULATE( [VALORES], 'PLANO'[GRUPO] = "Receitas Comerciais" ),
    CALCULATE( [VALORES], 'PLANO'[GRUPO] = "Venda Bruta" )
)
```

Formate `KPI Receitas Comerciais` como **Moeda 2 casas** e `KPI Receitas Comerciais %` como **Porcentagem 2 casas**.

## Passo 2 — Adicionar VARs ao topo da `Medida`

Abra a medida `Medida` (na tabela `dree`). No início, junto com os outros `VAR Vendas = ...`, `VAR cmv = ...`, **cole estes VARs**:

```dax
VAR RComR  = FORMAT([KPI Receitas Comerciais]               / 1000000, "\R$\ #,##0.00\M\")
VAR RComR2 = FORMAT([KPI Receitas Comerciais %],                       "0.00%")
```

Mais abaixo, depois das outras blocadas mensais (após `-- Ajustes por mês` ou similar), **cole esta blocada inteira**:

```dax
-- Receitas Comerciais por mês
VAR RCJ  = ABS(CALCULATE([KPI Receitas Comerciais] / 1000000, 'MÊS'[MÊS] = 1))
VAR RCF  = ABS(CALCULATE([KPI Receitas Comerciais] / 1000000, 'MÊS'[MÊS] = 2))
VAR RCM  = ABS(CALCULATE([KPI Receitas Comerciais] / 1000000, 'MÊS'[MÊS] = 3))
VAR RCA  = ABS(CALCULATE([KPI Receitas Comerciais] / 1000000, 'MÊS'[MÊS] = 4))
VAR RCMax = MAX(RCJ, MAX(RCF, MAX(RCM, RCA))) + 0.001
VAR RCAVJ = FORMAT(DIVIDE(CALCULATE([KPI Receitas Comerciais], 'MÊS'[MÊS] = 1), VendasJN), "+0.00%;-0.00%")
VAR RCAVF = FORMAT(DIVIDE(CALCULATE([KPI Receitas Comerciais], 'MÊS'[MÊS] = 2), VendasFN), "+0.00%;-0.00%")
VAR RCAVM = FORMAT(DIVIDE(CALCULATE([KPI Receitas Comerciais], 'MÊS'[MÊS] = 3), VendasMN), "+0.00%;-0.00%")
VAR RCAVA = FORMAT(DIVIDE(CALCULATE([KPI Receitas Comerciais], 'MÊS'[MÊS] = 4), VendasAN), "+0.00%;-0.00%")
```

E na seção de alturas das barras (onde tem `VAR hVJ = ...`, `VAR hCJ = ...`, etc.), **cole**:

```dax
VAR hRCJ = FORMAT(DIVIDE(RCJ, RCMax) * 28, "0")
VAR hRCF = FORMAT(DIVIDE(RCF, RCMax) * 28, "0")
VAR hRCM = FORMAT(DIVIDE(RCM, RCMax) * 28, "0")
VAR hRCA = FORMAT(DIVIDE(RCA, RCMax) * 28, "0")
```

## Passo 3 — Adicionar o card no HTML

No `RETURN` da `Medida`, dentro do `<div class='wrap'>`, **adicione um novo bloco** entre os cards existentes (sugiro depois do "Margem C/ Acordos Lançados" e antes de "Quebras"):

```text
<div class='card c-teal'>
    <div class='lbl'>Receitas Comerciais</div>
    <div class='val' style='color:#16a085'>" & RComR & "</div>
    <div class='av' style='color:#16a085'>" & RComR2 & "</div>
    <div class='spark'>
      <div class='spark-row'>
        <div class='bar-wrap'><div class='pct' style='color:#16a085'>" & RCAVJ & "</div><div class='bar' style='height:" & hRCJ & "px;background:rgba(26,58,47,0.15)'></div></div>
        <div class='bar-wrap'><div class='pct' style='color:#16a085'>" & RCAVF & "</div><div class='bar' style='height:" & hRCF & "px;background:rgba(26,58,47,0.15)'></div></div>
        <div class='bar-wrap'><div class='pct' style='color:#16a085'>" & RCAVM & "</div><div class='bar' style='height:" & hRCM & "px;background:rgba(26,58,47,0.15)'></div></div>
        <div class='bar-wrap'><div class='pct' style='color:#16a085'>" & RCAVA & "</div><div class='bar' style='height:" & hRCA & "px;background:#16a085'></div></div>
      </div>
      <div style='display:flex;gap:3px;margin-top:3px;'>
        <div class='mlbl'>Jan</div>
        <div class='mlbl'>Fev</div>
        <div class='mlbl'>Mar</div>
        <div class='mlbl'>Abr</div>
      </div>
    </div>
  </div>
```

> Esse texto fica DENTRO da string que a medida retorna. Lembre-se de manter as **aspas** (`"`) abertas/fechadas e os operadores **`&`** entre os pedaços de string e as variáveis.

## Resultado

Depois de salvar a medida, o visual **HTML Content** que já renderiza `Medida` na Home vai mostrar automaticamente o 11º card. Nada mais precisa ser arrastado/configurado.

## Layout dos cards (após adição)

Você tem hoje 10 cards em **2 linhas × 5 colunas**. Com 11 cards, a grade vai virar **2 linhas × 6 colunas** OU **3 linhas × 4 colunas** dependendo do CSS no `<style>` da `Medida`. Se ficar apertado, ajuste no início da string CSS:

```css
.wrap { display:grid; grid-template-columns: repeat(6, 1fr); gap:8px; }
```

Trocando o `repeat(5, 1fr)` (atual) por `repeat(6, 1fr)` cabem 11 lado a lado em duas linhas (6 + 5).
