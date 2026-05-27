"""Tenta identificar qual GRUPO produz o ranking '% Linhas por Loja' do painel.
Alvos do painel: L05=-7,87%, L22=-7,69%, L04=-7,67%, L17=+0,89%, L31=+0,99%."""
import json
from pathlib import Path

dados = json.loads(Path("/root/projeto_dre/dados.json").read_text(encoding="utf-8"))
fato = dados["fatos"]["porGrupo"]
ANO = 2026

def soma(grupos, loja):
    return sum(r["VALORES"] for r in fato
               if r["ANO"] == ANO and r["LOJA"] == loja and r["GRUPO"] in grupos)

# Para cada GRUPO candidato, compute AV% por loja e veja se L04 ≈ -7,67%
candidatos = ["Lucro Líquido", "Lucro Líquido Ajustado", "LAIR", "EBITDA",
              "Margem Operacional", "Despesa Comerciais"]
lojas = sorted({r["LOJA"] for r in fato if r["LOJA"].startswith("L")})

print(f"{'GRUPO':<32}  L04        L05        L17        L31")
print("-" * 80)
for g in candidatos:
    vals = {}
    for l in lojas:
        vb = soma(["Venda Bruta"], l)
        v = soma([g], l)
        vals[l] = (v / vb * 100) if vb else 0
    print(f"{g:<32}  {vals.get('L04',0):+7.2f}%   {vals.get('L05',0):+7.2f}%   "
          f"{vals.get('L17',0):+7.2f}%   {vals.get('L31',0):+7.2f}%")

# Também tentar denominador global em vez de per-loja
print("\n=== Com denominador = Venda Bruta GLOBAL ===")
total_vb = sum(r["VALORES"] for r in fato if r["ANO"] == ANO and r["GRUPO"] == "Venda Bruta")
for g in candidatos:
    print(f"{g:<32} ", end="")
    for l in ["L04", "L05", "L17", "L31"]:
        v = soma([g], l)
        print(f" {l}={v/total_vb*100:+6.2f}%", end="")
    print()
