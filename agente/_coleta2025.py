import os, time, json, datetime as dt
from dotenv import load_dotenv
load_dotenv()
import oracledb
cd=os.getenv("ORACLE_CLIENT_DIR")
if cd:
    try: oracledb.init_oracle_client(lib_dir=cd)
    except Exception: pass
from queries import QUERIES
# firestore p/ mapa de lojas
from google.cloud import firestore
from google.oauth2 import service_account
fcred=service_account.Credentials.from_service_account_file('../serviceAccount.json')
fdb=firestore.Client(credentials=fcred, project='projeto-686e2')
lojas_doc=fdb.document('meta/lojas').get().to_dict() or {}
nro2loja={}
for it in (lojas_doc.get('items') or []):
    nome=it.get('descricao') or ''
    for nro in (it.get('nroempresa') or []):
        if nome: nro2loja[int(nro)]=nome

dsn=f'{os.getenv("ORACLE_HOST")}:{os.getenv("ORACLE_PORT")}/{os.getenv("ORACLE_SERVICE")}'
conn=oracledb.connect(user=os.getenv("ORACLE_USER"),password=os.getenv("ORACLE_PASSWORD"),dsn=dsn)
sql=QUERIES['venda_atual']['sql']
print("conectado; mapa lojas:", len(nro2loja), flush=True)

def coleta(label, ini, fim):
    cur=conn.cursor(); t=time.time()
    cur.execute(sql, dta_ini=ini, dta_fim=fim)
    cols=[d[0] for d in cur.description]; rows=cur.fetchall(); cur.close()
    iN=cols.index('NROEMPRESA'); iV=cols.index('VENDA'); iM=cols.index('MARGEM'); iVb=cols.index('VERBA')
    porLoja={}; tv=tm=tvb=0.0; semcad=set()
    for r in rows:
        nro=int(r[iN]); v=float(r[iV] or 0); m=float(r[iM] or 0); vb=float(r[iVb] or 0)
        loja=nro2loja.get(nro)
        if loja is None: semcad.add(nro); loja=f"NRO {nro}"
        d=porLoja.setdefault(loja, {"venda":0.0,"margem":0.0,"verba":0.0})
        d["venda"]+=v; d["margem"]+=m; d["verba"]+=vb
        tv+=v; tm+=m; tvb+=vb
    print(f"[{label}] {len(rows)} linhas em {time.time()-t:.0f}s | Venda={tv:,.2f} Margem={tm:,.2f} Verba={tvb:,.2f} | semcad={sorted(semcad)}", flush=True)
    return {"venda":tv,"margem":tm,"verba":tvb,"porLoja":porLoja,"ini":ini.isoformat(),"fim":fim.isoformat()}

out={}
out["2025-01"]=coleta("2025-01 (validação)", dt.date(2025,1,1), dt.date(2025,1,31))
json.dump(out, open("/tmp/venda2025.json","w")); print("...salvo parcial", flush=True)
out["2025-04"]=coleta("2025-04 (mês cheio)", dt.date(2025,4,1), dt.date(2025,4,30))
json.dump(out, open("/tmp/venda2025.json","w")); print("...salvo parcial", flush=True)
out["2025-05"]=coleta("2025-05 (1-22)", dt.date(2025,5,1), dt.date(2025,5,22))
json.dump(out, open("/tmp/venda2025.json","w"))
print("FIM — /tmp/venda2025.json gravado", flush=True)
conn.close()
