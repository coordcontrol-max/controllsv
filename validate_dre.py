"""Valida os 5 cards da aba DRE e a estrutura da tabela DRE contra a imagem."""
import json
from pathlib import Path

dados = json.loads(Path("/root/projeto_dre/dados.json").read_text(encoding="utf-8"))
fato = dados["fatos"]["porGrupo"]

ANO = 2026
def soma(grupos, mes="Todos", loja="Todos"):
    return sum(r["VALORES"] for r in fato
               if r["ANO"] == ANO and r["GRUPO"] in grupos
               and (mes == "Todos" or r["MÊS"] == mes)
               and (loja == "Todos" or r["LOJA"] == loja))

receita = soma(["Venda Bruta"])

# Cards do topo da aba DRE
cards = {
    "VENDA BRUTA":        soma(["Venda Bruta"]),
    "Margem C/ Acordos":  soma(["Margem C/ Acordos"]),
    "Despesas R$":        soma(["Despesas Operacionais", "Despesa Comerciais",
                                "Despesas Administrativas", "Despesas C/ Vendas",
                                "Resultado Financeiro", "IRPJ/CSLL"]),
    "Despesa Total R$":   soma(["Despesas Operacionais", "Despesa Comerciais",
                                "Despesas Administrativas", "Despesas C/ Vendas",
                                "Resultado Financeiro", "IRPJ/CSLL",
                                "Novas Unidades e Ajustes Gerenciais"]),
    "Lucro Líquido":      soma(["Lucro Líquido"]),
}
esperado = {
    "VENDA BRUTA":       (153.28, 100.00),
    "Margem C/ Acordos": ( 33.68,  21.97),
    "Despesas R$":       (-33.91, -22.12),
    "Despesa Total R$":  (-42.77, -27.90),
    "Lucro Líquido":     ( -2.89,  -1.89),
}
print("CARDS DRE")
print("-" * 70)
for k, v in cards.items():
    pct = v / receita * 100 if receita else 0
    e_v, e_p = esperado[k]
    print(f"  {k:<22} R$ {v/1e6:+8.2f}M ({pct:+6.2f}%)   esperado: {e_v:+.2f}M / {e_p:+.2f}%")

# Linha por linha da tabela DRE — totais por GRUPO
print("\nTABELA DRE (totais por GRUPO)")
print("-" * 70)
ordem = ["Venda Bruta", "CMV", "Margem C/ Acordos Lançados", "Margem S/ Acordos",
         "Receitas Comerciais", "Margem C/ Acordos", "Quebra Contábil",
         "Margem Operacional", "Despesas Operacionais", "Despesa Comerciais",
         "Despesas Administrativas", "Despesas C/ Vendas", "Resultado Financeiro",
         "IRPJ/CSLL", "EBITDA", "LAIR", "Lucro Líquido",
         "Novas Unidades e Ajustes Gerenciais", "Lucro Líquido Ajustado"]
for g in ordem:
    v = soma([g])
    pct = v / receita * 100 if receita else 0
    print(f"  {g:<38} {v:>16,.0f}  {pct:+6.2f}%")

# % Linhas por Loja — assume que é Lucro Líquido Ajustado AV% por LOJA
print("\n% LINHAS POR LOJA (Lucro Líquido Ajustado / Venda Bruta da loja)")
print("-" * 70)
lojas = sorted({r["LOJA"] for r in fato if r["LOJA"].startswith("L")})
saidas = []
for l in lojas:
    rec_l = soma(["Venda Bruta"], loja=l)
    lla_l = soma(["Lucro Líquido Ajustado"], loja=l)
    pct = lla_l / rec_l * 100 if rec_l else 0
    saidas.append((l, pct))
saidas.sort(key=lambda x: x[1])
for l, p in saidas:
    print(f"  {l}  {p:+6.2f}%")
