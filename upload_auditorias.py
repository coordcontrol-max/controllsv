"""Sobe os snapshots dos relatórios de AUDITORIAS pro Firestore (projeto-686e2).

Os relatórios de Auditorias do controllsv (dashboard.html) leem de arquivos
ESTÁTICOS no Hosting (apuracao_contratos.json, dados_fluxo_{seg}/comparativo_protege.json,
dados_fluxo_{seg}/taxas_cartoes.json) e de docs do Firestore (fluxoCaixa, rawOracle).
Como o app Supervendas é PROIBIDO de fazer fetch a controllsv.web.app, este script
publica os snapshots estáticos no MESMO Firestore usado pela DRE/Fluxo/Títulos/BP.

Coleções criadas:
  apuracaoContratos/
     meta            -> { meses:[...], geradoEm }
     {YYYY-MM}       -> { ano, mes, items:[...], totais:{...} }  (1 doc por mês)

  auditoriasProtege/
     meta            -> { segmentos:[...], geradoEm }
     {seg}           -> { segmento, items:[...], geradoEm, obs }  (1 doc por segmento)

  auditoriasTaxas/
     meta            -> { segmentos:[...], geradoEm }
     {seg}           -> { segmento, items:[...], taxa_contratual:{...}, geradoEm }

Mútuos entre Grupos NÃO precisa de snapshot estático para supermercados (vem de
fluxoCaixa + rawOracle, já no Firestore), mas postos/outras vêm de arquivos
mensais estáticos -> use upload_fluxo_segmentos.py para esses.

Idempotente: regrava os docs a cada execução.

Uso: python3 upload_auditorias.py
"""
import json
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "projeto-686e2"
ROOT = Path("/root/projeto_dre")
SA_PATH = ROOT / "serviceAccount.json"

APURACAO_FILE = ROOT / "apuracao_contratos.json"
SEGMENTOS = ["supermercados", "postos"]  # protege/taxas não se aplicam a "outras"


def _set(db, col, doc_id, payload):
    sz = len(json.dumps(payload).encode()) / 1024
    if sz > 950:
        print(f"  WARN {col}/{doc_id} = {sz:.0f} KB (perto do limite de 1 MiB)")
    db.collection(col).document(doc_id).set(payload)
    return sz


def upload_apuracao(db):
    if not APURACAO_FILE.exists():
        print(f"  SKIP apuração: {APURACAO_FILE} não existe")
        return
    data = json.loads(APURACAO_FILE.read_text(encoding="utf-8"))
    meses_obj = data.get("meses", {})
    chaves = sorted(meses_obj.keys())
    for chave in chaves:
        bloco = meses_obj[chave]
        ano, mes = chave.split("-")
        doc = {
            "ano": int(ano),
            "mes": int(mes),
            "items": bloco.get("items", []),
            "totais": bloco.get("totais", {}),
        }
        sz = _set(db, "apuracaoContratos", chave, doc)
        print(f"  apuracaoContratos/{chave}: {sz:.0f} KB ({len(doc['items'])} itens)")
    _set(db, "apuracaoContratos", "meta",
         {"meses": chaves, "geradoEm": data.get("geradoEm")})
    print(f"  apuracaoContratos/meta: meses={chaves}")


def upload_protege(db):
    segs = []
    ger = None
    for seg in SEGMENTOS:
        fp = ROOT / f"dados_fluxo_{seg}" / "comparativo_protege.json"
        if not fp.exists():
            print(f"  SKIP protege {seg}: {fp} não existe")
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        doc = {
            "segmento": seg,
            "items": data.get("items", []),
            "geradoEm": data.get("geradoEm"),
            "obs": data.get("obs", ""),
        }
        sz = _set(db, "auditoriasProtege", seg, doc)
        segs.append(seg)
        ger = data.get("geradoEm") or ger
        print(f"  auditoriasProtege/{seg}: {sz:.0f} KB ({len(doc['items'])} itens)")
    _set(db, "auditoriasProtege", "meta", {"segmentos": segs, "geradoEm": ger})
    print(f"  auditoriasProtege/meta: segmentos={segs}")


def upload_taxas(db):
    segs = []
    ger = None
    for seg in SEGMENTOS:
        fp = ROOT / f"dados_fluxo_{seg}" / "taxas_cartoes.json"
        if not fp.exists():
            print(f"  SKIP taxas {seg}: {fp} não existe")
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        doc = {
            "segmento": seg,
            "items": data.get("items", []),
            "taxa_contratual": data.get("taxa_contratual", {}),
            "geradoEm": data.get("geradoEm"),
        }
        sz = _set(db, "auditoriasTaxas", seg, doc)
        segs.append(seg)
        ger = data.get("geradoEm") or ger
        print(f"  auditoriasTaxas/{seg}: {sz:.0f} KB ({len(doc['items'])} itens)")
    _set(db, "auditoriasTaxas", "meta", {"segmentos": segs, "geradoEm": ger})
    print(f"  auditoriasTaxas/meta: segmentos={segs}")


def main():
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client()

    print("== Apuração de Contratos de Retorno ==")
    upload_apuracao(db)
    print("== Comparativo Protege ==")
    upload_protege(db)
    print("== Taxas de Cartões ==")
    upload_taxas(db)
    print("OK — snapshots de Auditorias no Firestore.")


if __name__ == "__main__":
    main()
