"""Gera o DETALHE título-a-título do DFC Supermercado p/ o drilldown da UI.

Lê rawOracle/{ano-mm}__fluxo_pago|_juros|_opfin (Firestore), reusa o MESMO
classifier do engine (classifier_fluxo.classificar_fluxo) — então o detalhe bate
exatamente com os valores do DFC — e grava:

    fluxoCaixaDet/{ano-mm} = {
      ano, mes,
      linhas: ["Aluguel De Imoveis", ...],   # index = l
      chunked: bool, totalChunks?: int,
      rows?: [{l, d, e, p, o, c, v}]          # se não chunked
    }
    + subcoleção chunks/{n} = {n, rows:[...]}  # se chunked

  l = índice da linha em `linhas`; d = dia "DD"; e = nroempresa;
  p = pessoa/favorecido; o = observação/histórico; c = nº documento; v = valor.

Não usa Oracle (lê só do rawOracle já carregado no Firestore). fluxo_transitorias
é ignorado (saldo consolidado, sem títulos).

Uso:
    python3 gera_fluxocaixa_detalhe.py [ano] [mes]      # 1 mês
    python3 gera_fluxocaixa_detalhe.py [ano]            # ano inteiro (meses com dado)
"""
import os
import sys
import datetime as dt

import firebase_admin
from firebase_admin import credentials, firestore

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTE = os.path.join(_HERE, "agente")
if _AGENTE not in sys.path:
    sys.path.insert(0, _AGENTE)

# Init Firestore SEM importar o agente (que dispara o cliente Oracle).
if not firebase_admin._apps:
    sa = os.path.join(_HERE, "serviceAccount.json")
    firebase_admin.initialize_app(credentials.Certificate(sa))
db = firestore.client()

import engine_fluxo        # noqa: E402  (só importa classifier_fluxo + firestore)
import classifier_fluxo    # noqa: E402

CHUNK = 3000               # linhas compactas por chunk (~120B → <0.5MB)
SLUGS = ["fluxo_pago", "fluxo_juros", "fluxo_opfin"]   # transitorias não tem título


def montar_detalhe(ano: int, mes: int) -> dict | None:
    raws = engine_fluxo._carregar_raw_fluxo(db, ano, mes)
    if not any(raws.get(s) for s in SLUGS):
        return None
    linhas_idx: dict[str, int] = {}
    rows_out: list[dict] = []
    for slug in SLUGS:
        rows = raws.get(slug) or []
        if not rows:
            continue
        fatos, _w = classifier_fluxo.classificar_fluxo(slug, rows)
        for f in fatos:
            linha = f.get("linha")
            valor = f.get("valor")
            if not linha or not valor:        # pula vazio/zero (igual ao engine)
                continue
            data = f.get("data") or ""
            dia = data[8:10] if len(data) >= 10 else ""
            if not dia:
                continue
            li = linhas_idx.setdefault(linha, len(linhas_idx))
            det = f.get("_det") or {}
            rows_out.append({
                "l": li,
                "d": dia,
                "e": f.get("nroempresa"),
                "p": det.get("p", ""),
                "o": det.get("o", ""),
                "c": det.get("c", ""),
                "v": valor,
            })
    linhas = [None] * len(linhas_idx)
    for nome, i in linhas_idx.items():
        linhas[i] = nome
    return {"ano": ano, "mes": mes, "linhas": linhas, "rows": rows_out}


def gravar(ano: int, mes: int, det: dict) -> None:
    chave = f"{ano:04d}-{mes:02d}"
    ref = db.collection("fluxoCaixaDet").document(chave)
    rows = det["rows"]
    base = {
        "ano": ano, "mes": mes,
        "linhas": det["linhas"],
        "count": len(rows),
        "geradoEm": firestore.SERVER_TIMESTAMP,
    }
    # apaga chunks antigos (por índice — evita .stream() incompatível no 3.14)
    prev = ref.get()
    if prev.exists:
        velho = (prev.to_dict() or {}).get("totalChunks") or 0
        for n in range(int(velho)):
            ref.collection("chunks").document(str(n)).delete()
    if len(rows) <= CHUNK:
        base["chunked"] = False
        base["rows"] = rows
        ref.set(base)
    else:
        total = (len(rows) + CHUNK - 1) // CHUNK
        base["chunked"] = True
        base["totalChunks"] = total
        ref.set(base)
        for i in range(0, len(rows), CHUNK):
            n = i // CHUNK
            ref.collection("chunks").document(str(n)).set({"n": n, "rows": rows[i:i + CHUNK]})
    print(f"   fluxoCaixaDet/{chave}: {len(rows)} título(s), {len(det['linhas'])} linha(s)"
          f"{', chunked ' + str(base.get('totalChunks')) if base['chunked'] else ''}")


def rodar(ano: int, mes: int | None) -> None:
    meses = [mes] if mes else list(range(1, 13))
    for m in meses:
        print(f">>> detalhe DFC {ano}-{m:02d}")
        det = montar_detalhe(ano, m)
        if det is None:
            if mes:
                print("   sem rawOracle de fluxo p/ esse mês — nada a gravar")
            continue
        gravar(ano, m, det)


if __name__ == "__main__":
    hoje = dt.date.today()
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else hoje.year
    mes = int(sys.argv[2]) if len(sys.argv) > 2 else None
    rodar(ano, mes)
    print("OK")
