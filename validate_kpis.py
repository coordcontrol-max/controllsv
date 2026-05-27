"""Simula o cálculo dos KPIs do dashboard a partir do JSON e compara com o painel-alvo."""
import json
from pathlib import Path

dados = json.loads(Path("/root/projeto_dre/dados.json").read_text(encoding="utf-8"))
fato = dados["fatos"]["porGrupo"]
mapa = dados["mapeamentoKPI"]

ANO = 2026
def calc(kpi, mes="Todos", loja="Todos"):
    grupos = mapa[kpi]
    return sum(r["VALORES"] for r in fato
               if r["ANO"] == ANO
               and r["GRUPO"] in grupos
               and (mes == "Todos" or r["MÊS"] == mes)
               and (loja == "Todos" or r["LOJA"] == loja))

receita = calc("RECEITA_TOTAL")
print(f"{'KPI':<32} {'VALOR':>16} {'%RECEITA':>10}   ESPERADO (painel)")
print("-" * 90)
esperados = {
    "RECEITA_TOTAL":            ("R$ 153,28M",   "100%"),
    "CMV":                      ("-R$ 127,26M",  "-83,02%"),
    "MARGEM_PDV":               ("R$ 26,02M",    "16,98%"),
    "MARGEM_ACORDOS_RECEBIDOS": ("R$ 33,68M",    "21,97%"),
    "MARGEM_ACORDOS_LANCADOS":  ("R$ 29,34M",    "19,14%"),
    "QUEBRAS":                  ("-R$ 2,66M",    "-1,74%"),
    "DESPESAS":                 ("-R$ 32,87M",   "-21,45%"),
    "AJUSTES_NOVAS_UNIDADES":   ("-R$ 8,86M",    "-5,78%"),
    "CARGA_TOTAL_DESPESAS":     ("-R$ 41,74M",   "-27,23%"),
    "LUCRO_LIQUIDO":            ("-R$ 2,89M",    "-1,89%"),
}
for kpi in mapa:
    v = calc(kpi)
    pct = (v / receita * 100) if receita else 0
    val_str = f"R$ {v/1e6:>+8.2f}M"
    pct_str = f"{pct:>+6.2f}%"
    esp_v, esp_p = esperados.get(kpi, ("?", "?"))
    print(f"{kpi:<32} {val_str:>16} {pct_str:>10}   {esp_v} / {esp_p}")
