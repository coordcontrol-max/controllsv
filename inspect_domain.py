"""Read the full domain of GRUPO/PLANO/LINHAS to build a precise KPI mapping."""
import pandas as pd
from pathlib import Path

DESKTOP = Path("/mnt/c/Users/wesley/Desktop")

# --- Classificação ---
plano = pd.read_excel(DESKTOP / "01 - Classificação.xlsx", sheet_name="PLANO")
grupos = pd.read_excel(DESKTOP / "01 - Classificação.xlsx", sheet_name="GRUPO")
empresas = pd.read_excel(DESKTOP / "01 - Classificação.xlsx", sheet_name="EMPRESAS")
agrup = pd.read_excel(DESKTOP / "01 - Classificação.xlsx", sheet_name="AGRUPAMENTO")

print("\n=== GRUPOS (todos) ===")
print(grupos["GRUPO"].dropna().to_list())

print("\n=== AGRUPAMENTOS (todos) ===")
print(agrup["AGRUPAMENTO"].dropna().to_list())

print("\n=== PLANO (GRUPO → AGRUPAMENTO → CONTA) ===")
plano_clean = plano.dropna(subset=["GRUPO"])
for grp, sub in plano_clean.groupby("GRUPO", sort=False):
    print(f"\n  ◆ {grp}")
    for ag, sub2 in sub.groupby("AGRUPAMENTO", sort=False):
        print(f"      └─ {ag}")
        for c in sub2["CONTA"].dropna().unique():
            print(f"            • {c}")

print("\n=== EMPRESAS (NROEMPRESA → LOJA) ===")
print(empresas.head(60).to_string(index=False))
print(f"... total {len(empresas)} linhas")

# --- LINHAS distintas em VALORES RATEADOS ---
print("\n=== LINHAS distintas em VALORES RATEADOS ===")
vr = pd.read_excel(
    DESKTOP / "02 - Valores Rateados.xlsx",
    sheet_name="VALORES RATEADOS",
    usecols=["ANO", "MÊS", "LOJA", "LINHAS", "VALORES"],
)
print(f"linhas totais: {len(vr)}")
print(f"anos: {sorted(vr['ANO'].dropna().unique().tolist())}")
print(f"meses: {sorted(vr['MÊS'].dropna().unique().tolist())}")
print(f"lojas: {sorted(vr['LOJA'].dropna().unique().tolist())}")
print(f"\nLINHAS distintas ({vr['LINHAS'].nunique()}):")
for l in vr["LINHAS"].dropna().unique():
    s = vr.loc[vr["LINHAS"] == l, "VALORES"].sum()
    print(f"   • {l!r:55}  total={s:>16,.2f}")
