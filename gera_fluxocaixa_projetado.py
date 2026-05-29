"""Projeção do DFC pros meses futuros a partir dos títulos em aberto.

Pega `titulosAberto/porDiaLinha` (que já tem agregação data×linha pra todas as
datas futuras de títulos em aberto — vencimento) e monta um doc
`fluxoCaixa/{ano-mes}` projetado pra cada mês ≥ hoje, no MESMO shape do
realizado. O DFC Consolidado/Diário do site lê do mesmo lugar, então funciona
out-of-the-box.

Lógica:
- Mês corrente: MERGE — preserva dias < hoje do realizado existente, adiciona
  dias ≥ hoje vindos da projeção. saldoFinalDiario re-encadeado a partir do
  último dia realizado.
- Meses futuros (mês > corrente): doc 100% projetado.
- Saldo inicial em cadeia: cada mês começa com o `saldoFinalDiario[-1]` do
  mês anterior (real ou projetado).

Idempotente: grava com flag `projetado=true`. Re-rodar sobrescreve.

Roda 1x daqui ou diariamente via run_etl.sh (depois do upload_titulos_aberto).
"""
import os, sys
import datetime as dt
from collections import defaultdict
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

# Carrega .env do agente
env_path = Path('/root/projeto_dre/agente/.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

SA = os.environ['FIREBASE_SA_PATH']
firebase_admin.initialize_app(credentials.Certificate(SA))
db = firestore.client()

HOJE = dt.date.today()
print(f"\n=== gera_fluxocaixa_projetado · hoje={HOJE.isoformat()} ===\n")

# ─── 1) Carrega mapeamentos DFC ──────────────────────────────────────────────
def load_meta(doc_name):
    snap = db.collection('meta').document(doc_name).get()
    return (snap.to_dict() or {}).get('items') or []

lf_items = load_meta('linhasFluxo')         # {nome, agrupamento}
af_items = load_meta('agrupamentosFluxo')   # {nome, grupo}
gf_items = load_meta('gruposFluxo')         # {nome, ordem}

linha_to_agrup = {it['nome']: it['agrupamento'] for it in lf_items if it.get('agrupamento')}
agrup_to_grupo = {it['nome']: it['grupo'] for it in af_items if it.get('grupo')}
agrup_ordem    = {it['nome']: i for i, it in enumerate(af_items)}
linha_ordem    = {it['nome']: i for i, it in enumerate(lf_items)}
grupos_ordem   = [it['nome'] for it in sorted(gf_items, key=lambda x: x.get('ordem', 9999))]

print(f"  mapeamentos DFC: {len(linha_to_agrup)} linhas, {len(agrup_to_grupo)} agrups, {len(grupos_ordem)} grupos\n")

# ─── 2) Carrega porDiaLinha (projeção por data) ──────────────────────────────
snap = db.collection('titulosAberto').document('porDiaLinha').get()
pdl = (snap.to_dict() or {}).get('data') or {}
datas_futuras = sorted(d for d in pdl.keys() if d >= HOJE.isoformat())
print(f"  porDiaLinha: {len(pdl)} datas total, {len(datas_futuras)} ≥ hoje")
if not datas_futuras:
    print("  nenhuma data futura — nada a projetar"); sys.exit(0)
print(f"  range projeção: {datas_futuras[0]} .. {datas_futuras[-1]}\n")

# ─── 3) Descobre meses alvo (do mês corrente até o último com dado) ──────────
ultimo = datas_futuras[-1]
ano_ini, mes_ini = HOJE.year, HOJE.month
ano_fim, mes_fim = int(ultimo[:4]), int(ultimo[5:7])

meses_alvo = []
y, m = ano_ini, mes_ini
while (y, m) <= (ano_fim, mes_fim):
    meses_alvo.append((y, m))
    m += 1
    if m > 12: m = 1; y += 1
print(f"  meses alvo: {len(meses_alvo)} ({meses_alvo[0]} .. {meses_alvo[-1]})\n")

# ─── 4) Pra cada mês, mescla realizado + projetado ───────────────────────────
def saldo_final_mes(ano, mes):
    """Lê saldoFinalDiario[-1] de fluxoCaixa/{ano-mes}. Retorna None se não existe."""
    snap = db.collection('fluxoCaixa').document(f'{ano:04d}-{mes:02d}').get()
    if not snap.exists: return None
    sfd = (snap.to_dict() or {}).get('saldoFinalDiario') or []
    if not sfd: return None
    return float(sfd[-1].get('v') or 0)

# Saldo inicial do PRIMEIRO mês: vem do mês anterior real (Abr/2026 → maio)
ano_ant, mes_ant = (ano_ini, mes_ini-1) if mes_ini > 1 else (ano_ini-1, 12)
saldo_corrente = saldo_final_mes(ano_ant, mes_ant)
print(f"  saldo final {ano_ant}-{mes_ant:02d} (mês ant): R$ {saldo_corrente or 0:,.2f}\n")

gravados = []
for (ano, mes) in meses_alvo:
    chave = f'{ano:04d}-{mes:02d}'
    is_corrente = (ano, mes) == (HOJE.year, HOJE.month)
    print(f"--- {chave} ({'mês corrente — merge' if is_corrente else 'futuro — projetado'}) ---")

    # 4.1) Pega projetado do porDiaLinha
    proj_por_dia = {}   # 'DD' → {linha: valor}
    for d_str, linhas in pdl.items():
        if d_str[:7] != chave: continue
        date_obj = dt.date.fromisoformat(d_str)
        if date_obj < HOJE: continue   # ignora projeção de datas passadas (já deveriam ter pago)
        proj_por_dia[d_str[8:10]] = linhas

    # 4.2) Pega realizado (só pra mês corrente)
    real_por_dia_linha = {}  # 'DD' → {linha: valor} (do realizado)
    real_saldoInicial = None
    if is_corrente:
        snap = db.collection('fluxoCaixa').document(chave).get()
        if snap.exists:
            real = snap.to_dict() or {}
            real_dim = real.get('dim') or {}
            real_linhas = real_dim.get('linhas') or []
            real_dias = real_dim.get('dias') or []
            real_saldoInicial = float(real.get('saldoInicial') or 0)
            # Reconstrói dia → linha → valor a partir do porLinha. engine_fluxo
            # grava 'd' 0-based (idia = enumerate(dias)); o frontend também lê
            # 0-based (fluxoValorDia: dIdx = dias.indexOf(dia)). Ler 0-based.
            tmp = defaultdict(lambda: defaultdict(float))
            for r in (real.get('porLinha') or []):
                d_idx = (r.get('d') or 0)
                if d_idx < 0 or d_idx >= len(real_dias): continue
                dd = real_dias[d_idx]   # 'DD'
                date_obj = dt.date(ano, mes, int(dd))
                if date_obj >= HOJE: continue   # vai ser sobrescrito pela projeção
                n_idx = r.get('n') or 0
                if n_idx >= len(real_linhas): continue
                tmp[dd][real_linhas[n_idx]] += float(r.get('v') or 0)
            real_por_dia_linha = {k: dict(v) for k, v in tmp.items()}
            print(f"  realizado: {len(real_por_dia_linha)} dias < hoje preservados")

    # 4.3) Junta tudo num único dict {DD: {linha: valor}}
    por_dia = {**real_por_dia_linha}
    for dd, linhas in proj_por_dia.items():
        por_dia.setdefault(dd, {})
        for ln, v in linhas.items():
            por_dia[dd][ln] = por_dia[dd].get(ln, 0) + float(v or 0)

    if not por_dia:
        print(f"  vazio — pula"); continue

    # 4.4) Constrói arrays no shape do fluxoCaixa
    linhas_set = set()
    for vals in por_dia.values():
        for ln in vals: linhas_set.add(ln)
    agrups_set = set()
    grupos_set = set()
    linhas_ignoradas = set()
    for ln in linhas_set:
        ag = linha_to_agrup.get(ln)
        if not ag: linhas_ignoradas.add(ln); continue
        agrups_set.add(ag)
        gr = agrup_to_grupo.get(ag)
        if gr: grupos_set.add(gr)
    if linhas_ignoradas:
        print(f"  ⚠ {len(linhas_ignoradas)} linhas sem mapeamento em meta/linhasFluxo (ex: {list(linhas_ignoradas)[:3]})")

    grupos_list = [g for g in grupos_ordem if g in grupos_set]
    agrups_list = sorted(agrups_set, key=lambda a: agrup_ordem.get(a, 9999))
    linhas_list = sorted(
        (l for l in linhas_set if l not in linhas_ignoradas),
        key=lambda l: linha_ordem.get(l, 9999)
    )
    dias_list = sorted(por_dia.keys())

    g_idx = {g: i for i, g in enumerate(grupos_list)}
    a_idx = {a: i for i, a in enumerate(agrups_list)}
    l_idx = {l: i for i, l in enumerate(linhas_list)}
    d_idx = {dd: i for i, dd in enumerate(dias_list)}   # 0-based (igual engine_fluxo + frontend fluxoValorDia)

    porLinha = []
    porAg_acc = defaultdict(float)
    porGr_acc = defaultdict(float)
    for dd, valores in por_dia.items():
        di = d_idx[dd]
        for ln, v in valores.items():
            if ln in linhas_ignoradas: continue
            li = l_idx[ln]
            ag = linha_to_agrup[ln]; ai = a_idx[ag]
            gr = agrup_to_grupo.get(ag, ''); gi = g_idx.get(gr, -1)
            if gi < 0: continue
            porLinha.append({'n': li, 'a': ai, 'g': gi, 'd': di, 'v': round(float(v), 2)})
            porAg_acc[(ai, di)] += float(v)
            porGr_acc[(gi, di)] += float(v)
    porAgrupamento = [{'a': a, 'd': d, 'v': round(v, 2)} for (a, d), v in porAg_acc.items()]
    porGrupo       = [{'g': g, 'd': d, 'v': round(v, 2)} for (g, d), v in porGr_acc.items()]

    # 4.5) saldoFinalDiario em cadeia.
    # Igual ao engine_fluxo (GRUPOS_FORA_DO_LIQUIDO={"SALDO"}): o grupo SALDO
    # tem só linhas informativas (Saldo Conta Transitória) que NÃO são fluxo
    # de caixa — somar elas duplicaria o saldo e estouraria o saldoFinalDiario.
    GRUPOS_FORA_DO_LIQUIDO = {"SALDO"}
    grupos_no_liquido = [i for i, g in enumerate(grupos_list) if g not in GRUPOS_FORA_DO_LIQUIDO]
    si = real_saldoInicial if (is_corrente and real_saldoInicial is not None) else (saldo_corrente or 0.0)
    saldo = si
    saldoFinalDiario = []
    for dd in dias_list:
        di = d_idx[dd]
        mov_dia = sum(porGr_acc.get((g, di), 0) for g in grupos_no_liquido)
        saldo += mov_dia
        saldoFinalDiario.append({'d': dd, 'v': round(saldo, 2)})

    doc = {
        'v': 1, 'ano': ano, 'mes': mes,
        'saldoInicial': round(si, 2),
        'dim': {
            'grupos': grupos_list,
            'agrupamentos': agrups_list,
            'linhas': linhas_list,
            'dias': dias_list,
        },
        'porLinha': porLinha,
        'porAgrupamento': porAgrupamento,
        'porGrupo': porGrupo,
        'saldoFinalDiario': saldoFinalDiario,
        'projetado': not is_corrente or any(dd >= HOJE.strftime('%d') for dd in dias_list),
        'projetadoEm': firestore.SERVER_TIMESTAMP,
        'geradoEm': firestore.SERVER_TIMESTAMP,
    }
    db.collection('fluxoCaixa').document(chave).set(doc, merge=False)
    print(f"  ✓ gravado: si=R$ {si:,.2f} → sf=R$ {saldoFinalDiario[-1]['v']:,.2f}  "
          f"({len(dias_list)} dias, {len(porLinha)} pontos)")
    saldo_corrente = saldoFinalDiario[-1]['v']  # cadeia: próximo mês começa daqui
    gravados.append(chave)

print(f"\n=== FIM · {len(gravados)} meses gravados: {gravados} ===")
