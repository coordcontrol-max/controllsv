"""Sobe o snapshot de Energia (Contas de Energia - SUPERMERCADOS) pro Firestore.

Lê /root/projeto_dre/energia.json (gerado por etl_energia.py) e grava na coleção
`energia` do projeto-686e2, em docs chunkados (limite de 1 MiB por doc).

Estrutura no Firestore (coleção `energia`):
  meta          -> { geradoEm, fonte, lojas, meses, anos, classificacao,
                     status_ml_gd, contas_abertas, situacao, class_status,
                     regChunks, regCount }
  reg_0000..N   -> { rows: [ {registro de consumo por UC/mês}, ... ] }

`registros` (≈630 KB, 970 linhas) é a fonte de consumo: por loja/UC/mês traz
kWh, injeção, cativo R$, GD/ML R$, total R$ (= valor de competência da fatura),
R$/kWh, economia (desconto), venda e % s/venda. As demais arrays (status,
contas, situação, class_status) são leves e cabem no doc meta.

Idempotente: regrava os docs e remove chunks órfãos de uma carga anterior maior.

Uso: python3 upload_energia.py
"""
import json
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "projeto-686e2"
ROOT = Path("/root/projeto_dre")
SA_PATH = ROOT / "serviceAccount.json"
DATA_PATH = ROOT / "energia.json"
COL = "energia"

# registros ~650 bytes/linha; mira ~350 KB/doc.
REG_CHUNK = 500


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client()

    print(f"Lendo {DATA_PATH.name} ({DATA_PATH.stat().st_size/1024/1024:.2f} MB)...")
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    registros = data.get("registros", [])
    reg_batches = list(_chunks(registros, REG_CHUNK))

    # 1) doc meta (tudo menos os registros) -------------------------------
    meta_doc = {
        "geradoEm":       data.get("geradoEm"),
        "fonte":          data.get("fonte"),
        "lojas":          data.get("lojas", []),
        "meses":          data.get("meses", []),
        "anos":           data.get("anos", []),
        "classificacao":  data.get("classificacao", []),
        "status_ml_gd":   data.get("status_ml_gd", []),
        "contas_abertas": data.get("contas_abertas", []),
        "situacao":       data.get("situacao", []),
        "class_status":   data.get("class_status", []),
        "regChunks":      len(reg_batches),
        "regCount":       len(registros),
    }
    sz = len(json.dumps(meta_doc).encode()) / 1024
    db.collection(COL).document("meta").set(meta_doc)
    print(f"  meta: {sz:.0f} KB ({len(registros)} registros em {len(reg_batches)} chunks)")

    # 2) reg chunks --------------------------------------------------------
    for i, batch in enumerate(reg_batches):
        doc_id = f"reg_{i:04d}"
        sz = len(json.dumps(batch).encode()) / 1024
        if sz > 950:
            print(f"  WARN {doc_id} = {sz:.0f} KB (perto do limite)")
        db.collection(COL).document(doc_id).set({"rows": batch})
    print(f"  reg: {len(reg_batches)} chunks de até {REG_CHUNK} linhas")

    # 3) limpa chunks órfãos de carga anterior maior ----------------------
    i = len(reg_batches)
    while True:
        doc_id = f"reg_{i:04d}"
        ref = db.collection(COL).document(doc_id)
        if ref.get().exists:
            ref.delete()
            print(f"  removido órfão {doc_id}")
            i += 1
        else:
            break

    print("OK — Energia no Firestore (coleção energia).")


if __name__ == "__main__":
    main()
