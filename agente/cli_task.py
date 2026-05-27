"""CLI pra enfileirar tasks no Firestore — funciona de qualquer máquina
com serviceAccount.json (não precisa de browser nem do agente local).

O agente da 225 consome a task em até 3s. Este CLI fica esperando o
status virar 'done' ou 'error' e imprime o resultado.

Uso:
  # Atualizar uma query específica num mês
  python cli_task.py atualizar --ano 2026 --mes 1 --slug venda_atual

  # Atualizar TUDO (todas as queries) num mês
  python cli_task.py atualizar --ano 2026 --mes 1

  # Atualizar TUDO num ano inteiro
  python cli_task.py atualizar --ano 2026

  # Rodar engine de rateio
  python cli_task.py rateio --ano 2026 --mes 1

  # Rodar engine de fluxo
  python cli_task.py fluxo --ano 2026 --mes 1

  # Pipeline completo (atualizar + rateio + fluxo)
  python cli_task.py tudo --ano 2026 --mes 1
"""

import argparse
import sys
import time
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

SA = Path(__file__).resolve().parent.parent / "serviceAccount.json"
if not SA.exists():
    print(f"✗ serviceAccount.json não encontrado em {SA}")
    sys.exit(1)

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(str(SA)))
db = firestore.client()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tipo", choices=["atualizar", "rateio", "fluxo", "tudo"])
    p.add_argument("--ano", type=int, required=True)
    p.add_argument("--mes", type=int, default=None)
    p.add_argument("--slug", type=str, default=None, help="Só pra tipo=atualizar")
    p.add_argument("--cenario", type=str, default="realizado", help="Só pra tipo=rateio")
    p.add_argument("--timeout", type=int, default=600, help="Segundos pra esperar o agente")
    args = p.parse_args()

    payload = {
        "tipo": args.tipo,
        "ano": args.ano,
        "status": "pending",
        "criadoEm": firestore.SERVER_TIMESTAMP,
        "criadoPor": "cli_task.py",
    }
    if args.mes is not None: payload["mes"] = args.mes
    if args.slug:            payload["slug"] = args.slug
    if args.tipo == "rateio": payload["cenario"] = args.cenario

    ref = db.collection("tasks").add(payload)[1]
    print(f"► Task enfileirada: {ref.id}")
    print(f"  payload: {payload}")
    print(f"  Aguardando agente da 225 consumir (timeout={args.timeout}s)...")

    t0 = time.time()
    last_status = "pending"
    while time.time() - t0 < args.timeout:
        snap = ref.get()
        d = snap.to_dict() or {}
        status = d.get("status", "pending")
        if status != last_status:
            print(f"  status: {status}")
            last_status = status
        if status == "done":
            print("\n✓ DONE")
            r = d.get("resultado", {})
            _imprimir_resumo(r, args.tipo)
            return 0
        if status == "error":
            print(f"\n✗ ERROR: {d.get('erro')}")
            return 1
        time.sleep(2)

    print(f"\n⚠ Timeout após {args.timeout}s — task ainda em '{last_status}'.")
    print(f"  Veja em Firestore: tasks/{ref.id}")
    return 2


def _imprimir_resumo(r, tipo):
    if tipo == "atualizar":
        for m in r.get("meses", []):
            print(f"\n  {r.get('ano')}-{m.get('mes'):02d}:")
            for q in m.get("queries", []):
                mark = "✓" if q.get("ok") else "✗"
                print(f"    {mark} {q.get('slug'):25} {q.get('count'):>6} linhas {q.get('ms')}ms"
                      + (f"  ERRO: {q.get('error')}" if not q.get("ok") else ""))
            cls = m.get("classificacao", {})
            if cls:
                print(f"    >> {cls.get('totalFatos')} fatos, {cls.get('totalDetalhes')} detalhes")
    elif tipo in ("rateio", "fluxo"):
        for m in r.get("meses", []):
            erro = m.get("erro")
            print(f"  {m.get('ano')}-{m.get('mes'):02d}: " + (f"ERRO {erro}" if erro else "OK"))
    else:
        # "tudo"
        print(f"  resultado: {r}")


if __name__ == "__main__":
    sys.exit(main())
