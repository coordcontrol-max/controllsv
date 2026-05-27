"""Recalcula o Balanço Patrimonial do MÊS CORRENTE e grava em dados_bp/{ano}.json.

Só mexe no mês corrente (posição month-to-date / até hoje); meses anteriores
permanecem como estão (congelados no último status gravado). Roda na madrugada
pelo run_etl.sh (antes do upload_bp.py). Linhas ainda sem fonte (Tributos,
Impostos a Recolher, Parcelamento Federal/Estadual, Capital Social, Outras
Receitas) são preservadas como estão (default 0).

Fontes: Oracle (FI_TITULO, FI_CTACORRENTESALDO, CONSINCODW.FATO_ESTOQUE) +
Firestore (fluxoCaixa saldoFinal, DRE coleção `meses`).
"""
import os, json, datetime as dt
os.environ.setdefault('LD_LIBRARY_PATH', '/opt/oracle/instantclient_23_5')
import oracledb
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

ROOT = '/root/projeto_dre'
load_dotenv(f'{ROOT}/agente/.env')
oracledb.init_oracle_client(lib_dir=os.environ.get('ORACLE_LIB', '/opt/oracle/instantclient_23_5'))

EMP = "5,7,10,101,102,103,104,106,108,109,11,112,117,125,13,131,14,16,18,20,21,215,219,222,23,26,27,28,29"
RECBTO = ["ACRA22","ACRA23","ACRA24","ACRA25","ACRA26","ACRCOM","ACREX2","ACRFOR","ACRINA","ACRINT","ACRLOG","ACRMGM","ACRMKT","ACRPEN","ACRPON","ACRPRE","ACRQUE","ACRTRO","ACRXTR","CONTRT","DEVREC","DUPR"]
SAL = ['13SAL','13SAL1','13SAL2','ORDSAL','SALADM','SALARD','SALARE','SALARI','SALARL','SALARM','SALARO','SALARP','SALARR','SALCOM','SALDUP','SALEXT']
# (nome_linha, codespecies, OD, aging None/'CP'/'LP', sinal +1 ATIVO / -1 PASSIVO)
LINES = [
 ('Cartões de Crédito a Receber', ['CARTAO'], 'D', None, +1),
 ('Tickets a Receber', ['TICKET'], 'D', None, +1),
 ('Venda Entre Unidades a Receber', ['DRCOL','DRCOL2'], 'D', None, +1),
 ('Mútuos a Receber', ['MUTREC','EMPREC'], 'D', None, +1),
 ('Contratos a Receber', RECBTO, 'D', 'CP', +1),
 ('Contratos a Receber - Longo Prazo', RECBTO, 'D', 'LP', +1),
 ('Fornecedores de Mercadorias', ['DUPP'], 'O', None, -1),
 ('Fornecedores Diversos', ['DESPU'], 'O', None, -1),
 ('Empréstimo a Pagar', ['EMPRE2'], 'O', 'CP', -1),
 ('Empréstimo a Pagar - Longo Prazo', ['EMPRE2'], 'O', 'LP', -1),
 ('Compra Entre Unidades a Pagar', ['DPCOL','DPCOL2'], 'O', None, -1),
 ('Mútuos a Pagar', ['MUTPAG','EMPRES'], 'O', None, -1),
]
BP_SET = sorted({c for (_, cods, _, _, _) in LINES for c in cods})


def add12(d: dt.date) -> str:
    try: return dt.date(d.year+1, d.month, d.day).isoformat()
    except ValueError: return dt.date(d.year+1, d.month, 28).isoformat()


def main():
    hoje = dt.date.today()
    ano, mes = hoje.year, hoje.month
    D = hoje.isoformat()              # posição do mês corrente = hoje (month-to-date)
    bnd = add12(hoje)                 # corte CP/LP = hoje + 12 meses
    mes_ini = dt.date(ano, mes, 1).isoformat()

    conn = oracledb.connect(user=os.environ['ORACLE_USER'], password=os.environ['ORACLE_PASSWORD'],
                            dsn=os.environ.get('ORACLE_DSN', '10.61.1.1:1521/orcl'))
    cur = conn.cursor()

    # 1) títulos abertos na posição D (emitido<=D e não quitado até D)
    inlist = ",".join(f"'{c}'" for c in BP_SET)
    cur.execute(f"""
      SELECT t.CODESPECIE, t.OBRIGDIREITO, t.VLRNOMINAL, t.VLRPAGO,
             TO_CHAR(t.DTAQUITACAO,'YYYY-MM-DD'),
             TO_CHAR(NVL(t.DTAPROGRAMADA,t.DTAVENCIMENTO),'YYYY-MM-DD')
      FROM FI_TITULO t
      WHERE t.SITUACAO<>'C' AND t.OBRIGDIREITO IN ('D','O')
        AND t.CODESPECIE IN ({inlist})
        AND t.DTAINCLUSAO <= TO_DATE('{D}','YYYY-MM-DD')
        AND (t.DTAQUITACAO IS NULL OR t.DTAQUITACAO > TO_DATE('{D}','YYYY-MM-DD'))
    """)
    tit = [{'cod': r[0], 'od': r[1], 'nom': float(r[2] or 0), 'pago': float(r[3] or 0),
            'quit': r[4], 'venc': r[5]} for r in cur.fetchall()]

    def linha_valor(cods, od, aging):
        cset = set(cods); s = 0.0
        for t in tit:
            if t['od'] != od or t['cod'] not in cset: continue
            v = t['nom'] if t['quit'] is not None else (t['nom'] - t['pago'])
            if v == 0: continue
            if aging:
                cp = (t['venc'] or '9999-12-31') <= bnd
                if (aging == 'CP') != cp: continue
            s += v
        return s

    # 2) Caixa = crédito do mês corrente (conta 4507)
    cur.execute(f"""SELECT NVL(SUM(VLRCREDITO),0) FROM FI_CTACORRENTESALDO
      WHERE SEQCTACORRENTE=4507 AND DATA BETWEEN TO_DATE('{mes_ini}','YYYY-MM-DD') AND TO_DATE('{D}','YYYY-MM-DD')""")
    caixa = float(cur.fetchone()[0] or 0)

    # 3) Salários pagos no mês ANTERIOR (quitação)
    pm = dt.date(ano-1, 12, 1) if mes == 1 else dt.date(ano, mes-1, 1)
    salinlist = ",".join(f"'{c}'" for c in SAL)
    cur.execute(f"""SELECT NVL(SUM(VLRPAGO),0) FROM FI_TITULO
      WHERE OBRIGDIREITO='O' AND CODESPECIE IN ({salinlist})
        AND DTAQUITACAO BETWEEN TO_DATE('{pm.isoformat()}','YYYY-MM-DD') AND LAST_DAY(TO_DATE('{pm.isoformat()}','YYYY-MM-DD'))""")
    sal = float(cur.fetchone()[0] or 0)

    # 4) Estoque = valor do KPI Comercial (MESMA query SQL_ESTOQUE do card DDE).
    # Mês corrente usa o KPI (live); meses retroativos usam FATO_ESTOQUE (histórico).
    import sys as _sys
    if '/root/projeto-comercial-gh' not in _sys.path:
        _sys.path.insert(0, '/root/projeto-comercial-gh')
    from extract_kpis_db import SQL_ESTOQUE
    cur.execute(SQL_ESTOQUE)
    estoque = sum(float(r[4] or 0) for r in cur.fetchall())  # col 4 = VLRCTOBRUTO (total)
    cur.close(); conn.close()

    # 5) Firestore: saldo final do mês (Bancos) + Lucro Líquido DRE (Resultado/Acum)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(f'{ROOT}/serviceAccount.json'), {'projectId': 'projeto-686e2'})
    db = firestore.client()
    fc = db.document(f'fluxoCaixa/{ano}-{mes:02d}').get().to_dict() or {}
    sfd = [(x.get('d') if isinstance(x, dict) else None, (x.get('v') if isinstance(x, dict) else x)) for x in (fc.get('saldoFinalDiario') or [])]
    sfd = sorted([(d, v) for d, v in sfd if v is not None], key=lambda t: (t[0] is None, t[0]))
    saldo_final = float(sfd[-1][1]) if sfd else 0.0
    lucro = {}
    for s in db.collection('meses').stream():
        md = s.to_dict() or {}
        if md.get('ano') != ano: continue
        grupos = (md.get('dim') or {}).get('grupos') or []
        comp = md.get('v') == 2 or md.get('dim') is not None
        tot = 0.0
        for r in (md.get('porGrupo') or []):
            g = grupos[r['g']] if (comp and r.get('g') is not None and r['g'] < len(grupos)) else r.get('grupo')
            v = r.get('v') if comp else r.get('valor')
            if g == 'Lucro Líquido': tot += float(v or 0)
        lucro[md.get('mes')] = tot

    # 6) monta valores SÓ do mês corrente; preserva demais meses e linhas pendentes
    path = f'{ROOT}/dados_bp/{ano}.json'
    bp = json.load(open(path))
    itens = [l['nome'] for l in bp['linhas'] if l['tipo'] == 'item']
    vals = {}
    for (nome, cods, od, aging, sgn) in LINES:
        vals[nome] = sgn * int(round(linha_valor(cods, od, aging)))
    vals['Caixa (Saldo Tesouraria)'] = int(round(caixa))
    vals['Bancos'] = int(round(saldo_final - caixa))
    vals['Estoques'] = int(round(estoque))
    vals['Salários a Pagar'] = -int(round(sal))
    vals['Resultado do Período'] = int(round(lucro.get(mes, 0)))
    vals['Lucro/Prejuízo Acumulado'] = int(round(sum(lucro.get(k, 0) for k in range(1, mes))))
    for nome in itens:
        key = f'{nome}__{mes}'
        if nome in vals:
            bp['valores'][key] = vals[nome]
        elif key not in bp['valores']:
            bp['valores'][key] = 0   # pendente sem valor → 0 (não sobrescreve se já existir)
    bp['mesAtual'] = mes
    bp['geradoEm'] = dt.datetime.now().isoformat(timespec='seconds')
    json.dump(bp, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    a = sum(bp['valores'].get(f"{l['nome']}__{mes}", 0) for l in bp['linhas'] if l['tipo'] == 'item' and l['lado'] == 'ATIVO')
    p = sum(bp['valores'].get(f"{l['nome']}__{mes}", 0) for l in bp['linhas'] if l['tipo'] == 'item' and l['lado'] == 'PASSIVO')
    print(f"BP mês {ano}-{mes:02d} (posição {D}): Ativo={a:,} | Passivo+PL={p:,} | dif={a+p:,}")
    print("OK — dados_bp/%d.json atualizado (só mês %d)." % (ano, mes))


if __name__ == '__main__':
    main()
