"""Recomputa só o rateio (engine.executar_rateio) pros meses informados,
SEM rodar Oracle — lê de fatosClassificados já no Firestore. Usado quando
muda regra de rateio no engine.py (ex: linhas que passam a ratear por venda).

Uso: python3 _recompute_rateio.py            # 2025 inteiro + 2026 Jan-mês corrente
     python3 _recompute_rateio.py 2026 1 5   # ano e range de meses
"""
import sys
import datetime as dt
import agente
from agente import engine, db

hoje = dt.date.today()
if len(sys.argv) >= 4:
    ano = int(sys.argv[1]); m0 = int(sys.argv[2]); m1 = int(sys.argv[3])
    meses = [(ano, m) for m in range(m0, m1 + 1)]
else:
    meses = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, hoje.month + 1)]

for ano, mes in meses:
    try:
        r = engine.executar_rateio(db, ano, mes, "realizado")
        print(f"  OK {ano}-{mes:02d}: {r['lojas']} lojas, {r['pontos']} pontos")
    except Exception as e:
        print(f"  ERRO {ano}-{mes:02d}: {e}")
print("=== rateio recomputado ===")
