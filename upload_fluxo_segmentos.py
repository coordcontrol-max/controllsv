"""Sobe os docs MENSAIS de Fluxo de Caixa dos segmentos POSTOS e OUTRAS pro
Firestore (projeto-686e2) — usados pelo relatório "Mútuos entre Grupos" das
Auditorias.

No controllsv, o consolidado de Mútuos lê:
  • supermercados -> Firestore fluxoCaixa/{YYYY-MM}  (já existe) + rawOracle (já existe)
  • postos/outras -> arquivos estáticos dados_fluxo_{seg}/{YYYY-MM}.json (Hosting)

Como o app Supervendas é PROIBIDO de fazer fetch a controllsv.web.app, este
script publica os JSONs mensais de postos/outras numa coleção própria do MESMO
Firestore. O shape é IDÊNTICO ao doc compacto de fluxoCaixa (dim + porLinha +
porAgrupamento + porGrupo), então o servidor reusa _fluxoUnpackDoc/fluxoTotalMes.

Coleção criada:
  fluxoSegmentos/
     meta                    -> { segmentos:[...], mesesPorSeg:{seg:[...]}, geradoEm }
     {seg}__{YYYY-MM}        -> doc compacto (ano, mes, dim, porLinha, ...)

Pula os arquivos por-loja (sufixo __XXX) e os auxiliares (detalhe_, meta, etc.) —
só sobe os agregados mensais {YYYY-MM}.json.

Idempotente: regrava os docs a cada execução.

Uso: python3 upload_fluxo_segmentos.py
"""
import json
import re
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "projeto-686e2"
ROOT = Path("/root/projeto_dre")
SA_PATH = ROOT / "serviceAccount.json"
COL = "fluxoSegmentos"
SEGMENTOS = ["postos", "outras", "intercompany"]
MES_RE = re.compile(r"^(\d{4})-(\d{2})\.json$")  # só agregados mensais, sem __loja


def main():
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client()

    meses_por_seg = {}
    geradoEm = None

    for seg in SEGMENTOS:
        d = ROOT / f"dados_fluxo_{seg}"
        if not d.exists():
            print(f"  SKIP {seg}: {d} não existe")
            continue
        meses = []
        for fp in sorted(d.glob("*.json")):
            m = MES_RE.match(fp.name)
            if not m:
                continue
            data = json.loads(fp.read_text(encoding="utf-8"))
            chave = f"{m.group(1)}-{m.group(2)}"
            doc = {
                "ano": int(data.get("ano") or m.group(1)),
                "mes": int(data.get("mes") or m.group(2)),
                "segmento": seg,
                "dim": data.get("dim", {}),
                "porLinha": data.get("porLinha", []),
                "porAgrupamento": data.get("porAgrupamento", []),
                "porGrupo": data.get("porGrupo", []),
            }
            doc_id = f"{seg}__{chave}"
            sz = len(json.dumps(doc).encode()) / 1024
            if sz > 950:
                print(f"  WARN {COL}/{doc_id} = {sz:.0f} KB (perto do limite)")
            db.collection(COL).document(doc_id).set(doc)
            meses.append(chave)
            geradoEm = data.get("geradoEm") or geradoEm
            print(f"  {COL}/{doc_id}: {sz:.0f} KB")
        meses_por_seg[seg] = meses

    db.collection(COL).document("meta").set({
        "segmentos": [s for s in SEGMENTOS if meses_por_seg.get(s)],
        "mesesPorSeg": meses_por_seg,
        "geradoEm": geradoEm,
    })
    print(f"  {COL}/meta: {meses_por_seg}")
    print(f"OK — Fluxo de Caixa (postos/outras) no Firestore (coleção {COL}).")


if __name__ == "__main__":
    main()
