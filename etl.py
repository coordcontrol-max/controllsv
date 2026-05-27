"""ETL — consolida fato (Excel) + dimensões (Firestore) em dados.json.

Fluxo (Fase 3):
  Firestore meta/{lojas, grupos, agrupamentos, linhas, mapeamentoKPI}
       └─► dimensões (cadastro feito direto pelo site)

  00 - Base.xlsx, 02 - Valores Rateados.xlsx
       └─► fato (números mensais por loja/linha)
                   │
                   ▼  enriquece com dimensões do Firestore
                   ▼
                dados.json → upload pro Firestore → dashboard

Bootstrap: se algum doc do Firestore estiver vazio na primeira execução,
fazemos seed a partir do antigo `01 - Classificação.xlsx` (one-shot, depois
o Excel pode ser apagado).
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "projeto-686e2"
SA_PATH    = Path("/root/projeto_dre/serviceAccount.json")

# ── Localização dos Excel ──────────────────────────────────────────────────
# Fonte canônica: rede compartilhada controller (\\10.61.1.13\controller).
# Em WSL, a rede pode estar acessível por:
#   /mnt/z/...          (se Z: estiver mapeado no Windows pra \\10.61.1.13\controller)
#   /mnt/controller/... (se feito mount cifs no WSL)
# Para casos especiais, pode-se sobrescrever via env var DRE_DATA_DIR.
#
# Pra mapear no Windows (recomendado):
#   Explorer → Este Computador → Mapear unidade de rede →
#     Letra: Z   Pasta: \\10.61.1.13\controller   ☑ Reconectar ao entrar
PASTA_REL = Path("-- PROJETOS BUSINESS INTELLIGENCE") / "00 - Dados"

CANDIDATOS = [
    # 1) override explícito por env var (DRE_DATA_DIR=/mnt/x/...)
    *( [Path(os.environ["DRE_DATA_DIR"])] if os.environ.get("DRE_DATA_DIR") else [] ),
    # 2) drive Z: mapeado pra \\10.61.1.13\controller
    Path("/mnt/z") / PASTA_REL,
    # 3) mount cifs direto em /mnt/controller
    Path("/mnt/controller") / PASTA_REL,
    # 4) fallback: desktop do Wesley (modo legado)
    Path("/mnt/c/Users/wesley/Desktop"),
]
DATA_DIR = next((p for p in CANDIDATOS if p.exists()), None)
if DATA_DIR is None:
    raise SystemExit(
        "❌ Nenhum dos caminhos esperados existe.\n"
        f"   Procurei em: {[str(p) for p in CANDIDATOS]}\n"
        "   Mapeie '\\\\10.61.1.13\\controller' como Z: no Windows ou exporte DRE_DATA_DIR."
    )
print(f"   Lendo Excel de: {DATA_DIR}")

F_BASE    = DATA_DIR / "00 - Base.xlsx"
F_CLASSIF = DATA_DIR / "01 - Classificação.xlsx"   # legacy — só usado em bootstrap
F_RATEADO = DATA_DIR / "02 - Valores Rateados.xlsx"
OUT       = Path("/root/projeto_dre/dados.json")

# Os 2 arquivos de fato são obrigatórios; o de classificação só se for bootstrap.
for f in (F_BASE, F_RATEADO):
    if not f.exists():
        raise SystemExit(f"❌ Arquivo não encontrado: {f}")

# ── 0) FIREBASE ─────────────────────────────────────────────────────────────
print("[0/5] Conectando ao Firestore...")
if not SA_PATH.exists():
    raise SystemExit(f"❌  {SA_PATH} não encontrado. Baixe do console do Firebase.")
if not firebase_admin._apps:
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
db = firestore.client()

# ── 1) DIMENSÕES (Firestore, com bootstrap do Excel se vazio) ───────────────
print("[1/5] Lendo dimensões do Firestore...")

def _doc(name: str) -> dict:
    snap = db.collection("meta").document(name).get()
    return snap.to_dict() or {}

lojas_doc   = _doc("lojas")
grupos_doc  = _doc("grupos")
agrup_doc   = _doc("agrupamentos")
linhas_doc  = _doc("linhas")
kpi_doc     = _doc("mapeamentoKPI")

needs_bootstrap = (
    not lojas_doc.get("items")
    or not grupos_doc.get("items")
    or not agrup_doc.get("items")
    or not linhas_doc.get("items")
)

if needs_bootstrap:
    if not F_CLASSIF.exists():
        raise SystemExit(
            "❌ Firestore vazio E '01 - Classificação.xlsx' não encontrado.\n"
            "   Não tenho como fazer bootstrap. Restaure o Excel ou popule\n"
            "   manualmente as dimensões em Configurações > Dimensões."
        )
    print("   ⚠ Algum doc de dimensão está vazio — fazendo bootstrap a partir do Excel...")
    plano    = pd.read_excel(F_CLASSIF, sheet_name="PLANO")[["GRUPO","AGRUPAMENTO","CONTA"]].dropna(subset=["CONTA"])
    empresas = pd.read_excel(F_CLASSIF, sheet_name="EMPRESAS")[["GRUPO","EMPRESAS","LOJA"]]
    lojas_x  = pd.read_excel(F_CLASSIF, sheet_name="LOJA")["LOJA"].dropna().tolist()

    # Lojas: agrupar por loja → lista de nroempresa
    if not lojas_doc.get("items"):
        e_map = empresas.dropna(subset=["EMPRESAS","LOJA"]).copy()
        e_map["EMPRESAS"] = e_map["EMPRESAS"].astype(int)
        loja_to_nros: dict[str, list[str]] = {}
        for _, r in e_map.iterrows():
            loja_to_nros.setdefault(r["LOJA"], []).append(str(int(r["EMPRESAS"])))
        items = [{"nroempresa": sorted(loja_to_nros.get(l, []), key=int) if loja_to_nros.get(l) else [],
                  "descricao":  l,
                  "ativo":      True}
                 for l in sorted(set(lojas_x) | set(loja_to_nros.keys()))]
        db.collection("meta").document("lojas").set({"items": items, "atualizadoEm": firestore.SERVER_TIMESTAMP})
        lojas_doc = {"items": items}
        print(f"     + meta/lojas seedado ({len(items)} lojas)")

    if not grupos_doc.get("items"):
        grupos_uniq = plano["GRUPO"].drop_duplicates().dropna().tolist()
        items = [{"nome": g, "ordem": (i + 1) * 10} for i, g in enumerate(grupos_uniq)]
        db.collection("meta").document("grupos").set({"items": items, "atualizadoEm": firestore.SERVER_TIMESTAMP})
        grupos_doc = {"items": items}
        print(f"     + meta/grupos seedado ({len(items)})")

    if not agrup_doc.get("items"):
        ag_g = (plano[["GRUPO","AGRUPAMENTO"]]
                .dropna().drop_duplicates(subset=["AGRUPAMENTO"], keep="first"))
        items = [{"nome": r["AGRUPAMENTO"], "grupo": r["GRUPO"]} for _, r in ag_g.iterrows()]
        db.collection("meta").document("agrupamentos").set({"items": items, "atualizadoEm": firestore.SERVER_TIMESTAMP})
        agrup_doc = {"items": items}
        print(f"     + meta/agrupamentos seedado ({len(items)})")

    if not linhas_doc.get("items"):
        ln = plano.drop_duplicates(subset=["CONTA"], keep="first")
        items = [{"nome": r["CONTA"], "agrupamento": r["AGRUPAMENTO"]} for _, r in ln.iterrows()]
        db.collection("meta").document("linhas").set({"items": items, "atualizadoEm": firestore.SERVER_TIMESTAMP})
        linhas_doc = {"items": items}
        print(f"     + meta/linhas seedado ({len(items)})")

    if not kpi_doc.get("items"):
        # KPI default — mesmo set de antes
        default_kpi = {
            "RECEITA_TOTAL":            ["Venda Bruta"],
            "CMV":                      ["CMV"],
            "MARGEM_PDV":               ["Margem S/ Acordos"],
            "MARGEM_ACORDOS_RECEBIDOS": ["Margem C/ Acordos"],
            "MARGEM_ACORDOS_LANCADOS":  ["Margem C/ Acordos Lançados"],
            "QUEBRAS":                  ["Quebra Contábil"],
            "DESPESAS":                 ["Despesas Operacionais","Despesa Comerciais","Despesas Administrativas","Despesas C/ Vendas"],
            "AJUSTES_NOVAS_UNIDADES":   ["Novas Unidades e Ajustes Gerenciais"],
            "LUCRO_LIQUIDO":            ["Lucro Líquido"],
            "CARGA_TOTAL_DESPESAS":     ["Despesas Operacionais","Despesa Comerciais","Despesas Administrativas","Despesas C/ Vendas","Novas Unidades e Ajustes Gerenciais"],
        }
        items = [{"nome": k, "grupos": v} for k, v in default_kpi.items()]
        db.collection("meta").document("mapeamentoKPI").set({"items": items, "atualizadoEm": firestore.SERVER_TIMESTAMP})
        kpi_doc = {"items": items}
        print(f"     + meta/mapeamentoKPI seedado ({len(items)})")

# Reconstrói as estruturas que o resto do ETL espera, agora a partir do Firestore
agrup_to_grupo = {a["nome"]: a.get("grupo", "") for a in agrup_doc["items"]}
plano_lookup: dict[str, dict] = {}
for ln in linhas_doc["items"]:
    nome  = ln["nome"]
    agrup = ln.get("agrupamento", "")
    grupo = agrup_to_grupo.get(agrup, "")
    plano_lookup[nome] = {"GRUPO": grupo, "AGRUPAMENTO": agrup}

# Lista de lojas (descrições, lojas inativas ainda contam como dimensão)
lojas_dim = [l["descricao"] for l in lojas_doc["items"]]

# Empresa → loja (nroempresa pode ser lista; deveria ser int único na chave)
empresa_map: dict[int, str] = {}
for l in lojas_doc["items"]:
    nros = l.get("nroempresa") or []
    if isinstance(nros, str): nros = [nros]
    for n in nros:
        try: empresa_map[int(n)] = l["descricao"]
        except (TypeError, ValueError): pass

# Meses: nomes hardcoded (eram da aba MÊS, agora fixos)
mes_map = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
           7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}

# DataFrames pra compatibilidade com o código de agregação abaixo
plano = pd.DataFrame(
    [{"GRUPO": v["GRUPO"], "AGRUPAMENTO": v["AGRUPAMENTO"], "CONTA": k}
     for k, v in plano_lookup.items()]
)
print(f"   {len(lojas_dim)} lojas · {len(grupos_doc['items'])} grupos · "
      f"{len(agrup_doc['items'])} agrupamentos · {len(plano_lookup)} linhas")

# ── 2) FATO PRINCIPAL ───────────────────────────────────────────────────────
print("[2/5] Lendo VALORES RATEADOS...")
fato = pd.read_excel(
    F_RATEADO,
    sheet_name="VALORES RATEADOS",
    usecols=["ANO", "MÊS", "LOJA", "LINHAS", "VALORES", "Venda Bruta"],
)
fato = fato.dropna(subset=["LINHAS", "VALORES"])
fato["ANO"] = fato["ANO"].astype(int)
fato["MÊS"] = fato["MÊS"].astype(int)
fato["LOJA"] = fato["LOJA"].astype(str).str.strip()
fato["VALORES"] = fato["VALORES"].astype(float)

# Enriquecimento com PLANO
def lookup_grupo(linha: str) -> tuple[str | None, str | None]:
    info = plano_lookup.get(linha)
    if info:
        return info["GRUPO"], info["AGRUPAMENTO"]
    return None, None

fato[["GRUPO", "AGRUPAMENTO"]] = fato["LINHAS"].apply(
    lambda x: pd.Series(lookup_grupo(x))
)

faltantes = fato.loc[fato["GRUPO"].isna(), "LINHAS"].unique().tolist()
if faltantes:
    print(f"   ⚠ {len(faltantes)} LINHAS sem mapeamento no PLANO (ex.: {faltantes[:5]})")

print(f"   linhas={len(fato):,}  anos={sorted(fato['ANO'].unique())}  "
      f"meses={sorted(fato['MÊS'].unique())}  lojas={fato['LOJA'].nunique()}")

# ── 3) AGREGADOS POR (ANO, MÊS, LOJA, GRUPO/AGRUPAMENTO) ────────────────────
print("[3/5] Agregando por dimensões...")

# Pivot fato em formato compacto - apenas linhas com mapeamento
fato_ok = fato.dropna(subset=["GRUPO"]).copy()

agg_grupo = (
    fato_ok.groupby(["ANO", "MÊS", "LOJA", "GRUPO"], as_index=False)["VALORES"]
           .sum()
)
agg_agrup = (
    fato_ok.groupby(["ANO", "MÊS", "LOJA", "AGRUPAMENTO"], as_index=False)["VALORES"]
           .sum()
)
agg_linha = (
    fato_ok.groupby(["ANO", "MÊS", "LOJA", "GRUPO", "AGRUPAMENTO", "LINHAS"], as_index=False)["VALORES"]
           .sum()
)

# ── 4) MONTAGEM DO JSON ─────────────────────────────────────────────────────
print("[4/5] Montando dados.json...")

def df_records(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["VALORES"] = df["VALORES"].round(2)
    return df.to_dict(orient="records")

dados = {
    "geradoEm": pd.Timestamp.now().isoformat(timespec="seconds"),
    "fontes": {
        "base":           str(F_BASE),
        "classificacao":  str(F_CLASSIF),
        "valoresRateados": str(F_RATEADO),
    },
    "dimensoes": {
        "anos":  sorted(int(a) for a in fato["ANO"].unique()),
        "meses": [{"num": k, "nome": v} for k, v in sorted(mes_map.items())],
        "lojas": sorted(set(fato["LOJA"].unique()) | set(lojas_dim)),
        "grupos": (
            plano[["GRUPO"]].drop_duplicates()
                            .dropna()["GRUPO"].tolist()
        ),
        "agrupamentos": (
            plano[["AGRUPAMENTO"]].drop_duplicates()
                                  .dropna()["AGRUPAMENTO"].tolist()
        ),
        "empresaParaLoja": {str(k): v for k, v in empresa_map.items()},
    },
    "fatos": {
        # nível mais agregado: ANO, MÊS, LOJA, GRUPO
        "porGrupo":       df_records(agg_grupo),
        # ANO, MÊS, LOJA, AGRUPAMENTO  (alimenta donut e bar charts)
        "porAgrupamento": df_records(agg_agrup),
        # ANO, MÊS, LOJA, GRUPO, AGRUPAMENTO, LINHA (drilldown)
        "porLinha":       df_records(agg_linha),
    },
    # KPIs vêm do Firestore (cadastráveis via Configurações > Dimensões)
    "mapeamentoKPI": {item["nome"]: item.get("grupos", []) for item in kpi_doc["items"]},
}

OUT.write_text(
    json.dumps(dados, ensure_ascii=False, separators=(",", ":")),
    encoding="utf-8",
)
size_mb = OUT.stat().st_size / 1024 / 1024
print(f"[5/5] OK → {OUT}  ({size_mb:.2f} MB, "
      f"{len(dados['fatos']['porLinha']):,} linhas no fato detalhado)")

# Sanity check rápido
total_receita = (
    agg_grupo.loc[(agg_grupo["GRUPO"] == "Venda Bruta") & (agg_grupo["ANO"] == 2026), "VALORES"].sum()
)
total_cmv = (
    agg_grupo.loc[(agg_grupo["GRUPO"] == "CMV") & (agg_grupo["ANO"] == 2026), "VALORES"].sum()
)
total_lucro = (
    agg_grupo.loc[(agg_grupo["GRUPO"] == "Lucro Líquido") & (agg_grupo["ANO"] == 2026), "VALORES"].sum()
)
print(f"\nValidação 2026 (todas as lojas):")
print(f"  Receita Total       = R$ {total_receita/1e6:>8,.2f}M  (esperado ≈ 153,28M)")
print(f"  CMV                 = R$ {total_cmv/1e6:>8,.2f}M  (esperado ≈ -127,26M)")
print(f"  Lucro Líquido       = R$ {total_lucro/1e6:>8,.2f}M  (esperado ≈ -2,89M)")
