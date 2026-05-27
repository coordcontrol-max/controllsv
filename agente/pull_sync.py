"""Baixa do Firestore (meta/agentSync) as ultimas versoes de
classifier_fluxo.py e engine_fluxo.py e substitui os locais.

Uso (PowerShell na 225, dentro da pasta do agente):
  python pull_sync.py

Requer firebase-admin instalado e serviceAccount.json no mesmo dir.
"""
import hashlib, os, sys, datetime as dt
import firebase_admin
from firebase_admin import credentials, firestore

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# serviceAccount.json fica no diretorio pai (mesma logica que o agente.py
# usa via FIREBASE_SA_PATH=../serviceAccount.json). Aceita os 2 lugares.
_CANDIDATOS = [
    os.path.join(SCRIPT_DIR, "serviceAccount.json"),
    os.path.join(os.path.dirname(SCRIPT_DIR), "serviceAccount.json"),
]
SA = next((p for p in _CANDIDATOS if os.path.exists(p)), _CANDIDATOS[0])
print(f"  serviceAccount: {SA}")

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(SA),
                                  {"projectId": "projeto-686e2"})
db = firestore.client()

doc = db.collection("meta").document("agentSync").get()
if not doc.exists:
    print("✗ meta/agentSync nao existe no Firestore."); sys.exit(1)

data = doc.to_dict()
print(f"  origem: {data.get('origem')}")
print(f"  atualizadoEm: {data.get('atualizadoEm')}")
print(f"  motivo: {data.get('motivo')}")
print()

ok = True
for name, info in (data.get("arquivos") or {}).items():
    dest = os.path.join(SCRIPT_DIR, name)
    content = info["content"]
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if sha != info.get("sha256"):
        print(f"  ✗ {name}: sha256 nao confere"); ok = False; continue
    # backup do antigo
    if os.path.exists(dest):
        bkp = dest + dt.datetime.now().strftime(".%Y%m%d-%H%M%S.bak")
        os.replace(dest, bkp)
        print(f"  backup: {os.path.basename(bkp)}")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  ✓ {name}: {info['bytes']} bytes (sha256={sha[:12]})")

print()
print("Reinicie o agente para aplicar:")
print("  - Ctrl+C na janela do uvicorn")
print("  - python agente.py")
