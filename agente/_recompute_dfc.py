"""Recomputa só o DFC (fluxoCaixa/) de meses específicos: roda as 4 queries de
fluxo no Oracle + engine_fluxo. Não toca a DRE (meses/). Usado pra consertar
meses cujo DFC ficou zerado (queries fluxo falharam por queda de Oracle).

Uso: python3 _recompute_dfc.py 2025 6 10   # ano, mês inicial, mês final
"""
import sys
import agente

ano = int(sys.argv[1]); m0 = int(sys.argv[2]); m1 = int(sys.argv[3])
SLUGS_FLUXO = ["fluxo_pago", "fluxo_juros", "fluxo_opfin", "fluxo_transitorias"]

for mes in range(m0, m1 + 1):
    print(f"\n======== DFC {ano}-{mes:02d} ========")
    try:
        agente.atualizar(ano=ano, mes=mes, slug=None, slugs=SLUGS_FLUXO, resume=False)
        r = agente.engine_fluxo.executar_fluxo(agente.db, ano, mes)
        print(f"  ✓ {ano}-{mes:02d}: si={r.get('saldoInicial')} sf={r.get('saldoFinal')} lojas={r.get('lojasGravadas')}")
    except Exception as e:
        print(f"  ✗ ERRO {ano}-{mes:02d}: {e}")
print("\n===== DFC recomputado =====")
