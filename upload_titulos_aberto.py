"""Sobe o snapshot de Títulos em Aberto (Oracle FI_TITULO) pro Firestore.

Lê /root/projeto_dre/titulos_aberto_data.json e titulos_aberto_detalhe.json
(gerados por gera_titulos_aberto.py) e grava na coleção `titulosAberto` do
projeto-686e2, em docs chunkados (limite de 1 MiB por doc do Firestore).

Estrutura no Firestore (coleção `titulosAberto`):
  meta            -> { geradoEm, hoje, especies, empresas, aging, proximos7d,
                       top5Atraso, aggChunks, detChunks }
  agg_0000..N     -> { rows: [ {od,cod,ano,mes,emp,qtd,vn,vp,sld,vnc}, ... ] }
  det_0000..N     -> { rows: [ {dta,linha,emp,nro,serie,parc,seqp,nome,cod,sld,obs}, ... ] }
  porDia          -> { data: {YYYY-MM-DD: {D/O:{sld,qtd}}} }   (cabe em 1 doc)
  porDiaLinha     -> { data: {YYYY-MM-DD: {linha: sld}} }       (cabe em 1 doc)

Idempotente: regrava os docs e remove chunks órfãos de uma carga anterior maior.

Uso: python3 upload_titulos_aberto.py
"""
import json, math
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "projeto-686e2"
ROOT = Path("/root/projeto_dre")
SA_PATH = ROOT / "serviceAccount.json"
DATA_PATH = ROOT / "titulos_aberto_data.json"
DET_PATH = ROOT / "titulos_aberto_detalhe.json"
COL = "titulosAberto"

# ~chunk: agg rows ~120 bytes; det rows ~250 bytes. Mira ~700 KB/doc.
AGG_CHUNK = 4000
DET_CHUNK = 2500


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client()

    print(f"Lendo {DATA_PATH.name} ({DATA_PATH.stat().st_size/1024/1024:.2f} MB)...")
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"Lendo {DET_PATH.name} ({DET_PATH.stat().st_size/1024/1024:.2f} MB)...")
    det = json.loads(DET_PATH.read_text(encoding="utf-8"))

    agg = data.get("agg", [])
    agg_dia = data.get("aggDia", [])
    det_items = det.get("items", [])

    agg_batches = list(_chunks(agg, AGG_CHUNK))
    aggdia_batches = list(_chunks(agg_dia, AGG_CHUNK))
    det_batches = list(_chunks(det_items, DET_CHUNK))

    # 1) doc meta (campos leves) ------------------------------------------
    meta_doc = {
        "geradoEm":   data.get("geradoEm"),
        "hoje":       data.get("hoje"),
        "especies":   data.get("especies", {}),
        "empresas":   data.get("empresas", []),
        "aging":      data.get("aging", {}),
        "proximos7d": data.get("proximos7d", []),
        "top5Atraso": data.get("top5Atraso", []),
        "aggChunks":    len(agg_batches),
        "aggDiaChunks": len(aggdia_batches),
        "detChunks":    len(det_batches),
        "aggCount":     len(agg),
        "aggDiaCount":  len(agg_dia),
        "detCount":     len(det_items),
    }
    sz = len(json.dumps(meta_doc).encode()) / 1024
    db.collection(COL).document("meta").set(meta_doc)
    print(f"  meta: {sz:.0f} KB ({len(agg)} agg, {len(det_items)} det)")

    # 2) porDia / porDiaLinha (cabe em 1 doc cada) ------------------------
    for nome, key in [("porDia", "porDia"), ("porDiaLinha", "porDiaLinha")]:
        payload = {"data": data.get(key, {})}
        sz = len(json.dumps(payload).encode()) / 1024
        db.collection(COL).document(nome).set(payload)
        print(f"  {nome}: {sz:.0f} KB ({len(payload['data'])} dias)")

    # 3) agg chunks --------------------------------------------------------
    for i, batch in enumerate(agg_batches):
        doc_id = f"agg_{i:04d}"
        sz = len(json.dumps(batch).encode()) / 1024
        if sz > 950:
            print(f"  WARN {doc_id} = {sz:.0f} KB (perto do limite)")
        db.collection(COL).document(doc_id).set({"rows": batch})
    print(f"  agg: {len(agg_batches)} chunks de até {AGG_CHUNK} linhas")

    # 3b) aggDia chunks (espécie × dia de vencimento × OD) -----------------
    for i, batch in enumerate(aggdia_batches):
        doc_id = f"aggdia_{i:04d}"
        sz = len(json.dumps(batch).encode()) / 1024
        if sz > 950:
            print(f"  WARN {doc_id} = {sz:.0f} KB (perto do limite)")
        db.collection(COL).document(doc_id).set({"rows": batch})
    print(f"  aggDia: {len(aggdia_batches)} chunks de até {AGG_CHUNK} linhas")

    # 4) det chunks --------------------------------------------------------
    for i, batch in enumerate(det_batches):
        doc_id = f"det_{i:04d}"
        sz = len(json.dumps(batch).encode()) / 1024
        if sz > 950:
            print(f"  WARN {doc_id} = {sz:.0f} KB (perto do limite)")
        db.collection(COL).document(doc_id).set({"rows": batch})
    print(f"  det: {len(det_batches)} chunks de até {DET_CHUNK} linhas")

    # 5) limpa chunks órfãos de carga anterior maior ----------------------
    for prefix, n in [("agg_", len(agg_batches)), ("aggdia_", len(aggdia_batches)), ("det_", len(det_batches))]:
        i = n
        while True:
            doc_id = f"{prefix}{i:04d}"
            ref = db.collection(COL).document(doc_id)
            if ref.get().exists:
                ref.delete()
                print(f"  removido órfão {doc_id}")
                i += 1
            else:
                break

    print("OK — Títulos em Aberto no Firestore (coleção titulosAberto).")


if __name__ == "__main__":
    main()
