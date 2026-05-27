"""Sobe o snapshot de Balanço Patrimonial pro Firestore (projeto-686e2).

O BP do controllsv NÃO está no Firestore — a função loadBP() do dashboard.html
lê de um arquivo estático em Hosting (/dados_bp/{ano}.json). Como o app
Supervendas é PROIBIDO de fazer fetch a controllsv.web.app, este script publica
o(s) JSON(s) de /root/projeto_dre/dados_bp/*.json na coleção `balancoPatrimonial`
do mesmo Firestore usado pela DRE/Fluxo/Títulos.

Estrutura no Firestore (coleção `balancoPatrimonial`):
  meta              -> { anos:[2026, ...], geradoEm }
  {ano}             -> { ano, geradoEm, v, mesAtual, comentario, meses:[...],
                         linhas:[...], valores:{...} }   (cabe folgado em 1 doc;
                         cada ano ~7-50 KB << limite de 1 MiB)

O shape de cada doc de ano é IDÊNTICO ao JSON original (linhas[] = plano de
contas hierárquico com {nome,lado,grupo,agrupamento,ordem,tipo,fonte};
valores = { "Nome da Conta__MES": valor }). Passivos são valores NEGATIVOS
(convenção: receita +, obrigação -).

Idempotente: regrava os docs a cada execução.

Uso: python3 upload_bp.py
"""
import json
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "projeto-686e2"
ROOT = Path("/root/projeto_dre")
SA_PATH = ROOT / "serviceAccount.json"
DADOS_DIR = ROOT / "dados_bp"
COL = "balancoPatrimonial"


def main():
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client()

    arquivos = sorted(DADOS_DIR.glob("*.json"))
    if not arquivos:
        raise SystemExit(f"Nenhum JSON em {DADOS_DIR}")

    anos = []
    ultimo_gerado = None
    for fp in arquivos:
        data = json.loads(fp.read_text(encoding="utf-8"))
        ano = int(data.get("ano") or fp.stem)
        sz = len(json.dumps(data).encode()) / 1024
        if sz > 950:
            print(f"  WARN {ano} = {sz:.0f} KB (perto do limite de 1 MiB)")
        # Doc do ano = shape original (linhas + valores + metadados).
        doc = {
            "ano":        ano,
            "geradoEm":   data.get("geradoEm"),
            "v":          data.get("v"),
            "mesAtual":   data.get("mesAtual"),
            "comentario": data.get("comentario"),
            "meses":      data.get("meses", []),
            "linhas":     data.get("linhas", []),
            "valores":    data.get("valores", {}),
        }
        db.collection(COL).document(str(ano)).set(doc)
        anos.append(ano)
        if data.get("geradoEm"):
            ultimo_gerado = data["geradoEm"]
        print(f"  {ano}: {sz:.0f} KB ({len(doc['linhas'])} linhas, {len(doc['valores'])} valores)")

    anos = sorted(set(anos), reverse=True)
    db.collection(COL).document("meta").set({"anos": anos, "geradoEm": ultimo_gerado})
    print(f"  meta: anos={anos}")
    print(f"OK — Balanço Patrimonial no Firestore (coleção {COL}).")


if __name__ == "__main__":
    main()
