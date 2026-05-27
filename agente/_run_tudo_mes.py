"""Roda o pipeline 'tudo' do agente pro mês corrente, SEM precisar do agente
da 225 ligado. Replica _executar_task(tipo='tudo'):
  atualizar (Oracle→rawOracle + classifica) → rateio (DRE) → fluxo (DFC)
  → dimensoes.
Uso: python3 _run_tudo_mes.py [ano] [mes]   (default = mês corrente)
"""
import sys, json, datetime as dt

# Importa o agente (roda init de Oracle + Firebase no nível de módulo)
import agente
from agente import atualizar, atualizar_dimensoes, engine, engine_fluxo, db

hoje = dt.date.today()
ano = int(sys.argv[1]) if len(sys.argv) > 1 else hoje.year
mes = int(sys.argv[2]) if len(sys.argv) > 2 else hoje.month
cenario = "realizado"

print(f"\n======== PIPELINE 'tudo' {ano}-{mes:02d} ========\n")

# 1) atualizar — queries Oracle → rawOracle + classificação → fatosClassificados
print(">>> [1/4] atualizar (Oracle → rawOracle + classifica)")
try:
    r1 = atualizar(ano=ano, mes=mes, slug=None, slugs=None, resume=False)
    print("    atualizar OK")
except Exception as e:
    print(f"    atualizar ERRO: {e}")

# 2) rateio — engine.executar_rateio → meses/{ano-mes} (DRE)
print(">>> [2/4] rateio (DRE → meses/)")
try:
    r2 = engine.executar_rateio(db, ano, mes, cenario)
    print(f"    rateio OK: {r2}")
except Exception as e:
    print(f"    rateio ERRO: {e}")

# 3) fluxo — engine_fluxo.executar_fluxo → fluxoCaixa/{ano-mes} (DFC)
print(">>> [3/4] fluxo (DFC → fluxoCaixa/)")
try:
    r3 = engine_fluxo.executar_fluxo(db, ano, mes)
    print(f"    fluxo OK: si={r3.get('saldoInicial')} sf={r3.get('saldoFinal')} lojas={r3.get('lojasGravadas')}")
except Exception as e:
    print(f"    fluxo ERRO: {e}")

# 4) dimensoes — snapshots (classif produtos, etc.)
print(">>> [4/4] dimensoes (snapshots Prevenção)")
try:
    atualizar_dimensoes()
    print("    dimensoes OK")
except Exception as e:
    print(f"    dimensoes ERRO: {e}")

print(f"\n======== FIM {ano}-{mes:02d} ========\n")
