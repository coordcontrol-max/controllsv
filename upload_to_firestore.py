"""Upload do dados.json para o Firestore + sincroniza usuários do Auth.

Estrutura no banco:

  meta/
    dimensoes      -> { anos, meses, lojas, grupos, agrupamentos, mapeamentoKPI }
    whitelist      -> { emails: [...] }       (apenas Admin SDK lê)

  meses/
    2026-01        -> { ano: 2026, mes: 1, fatos: { porGrupo, porAgrupamento, porLinha } }
    ...

Além disso, para cada item em USUARIOS:
  - cria a conta no Firebase Auth se ainda não existir, gerando uma SENHA
    ALEATÓRIA exibida UMA ÚNICA VEZ no terminal (anote e mande pro usuário);
  - se já existir, apenas garante que `email_verified=True` (necessário pra
    regra do Firestore liberar leitura) e atualiza o display_name.

Senhas NUNCA são gravadas neste arquivo nem em qualquer outro do projeto.
Para resetar uma senha esquecida, use o Firebase Console
(Authentication → Users → ⋮ no usuário → "Redefinir senha").

Pré-requisitos:
    pip install firebase-admin
    Baixe a chave da service account e salve em
       /root/projeto_dre/serviceAccount.json   (NÃO commitar!)
    No console: Authentication → Sign-in method → ative "E-mail/senha".

Uso:
    python3 upload_to_firestore.py                       # tudo (usuários + dados)
    python3 upload_to_firestore.py --apenas-usuarios     # pula upload do Firestore
"""
from __future__ import annotations
import argparse
import json
import secrets
import string
from collections import defaultdict
from pathlib import Path

import firebase_admin
from firebase_admin import auth, credentials, firestore

PROJECT_ID = "projeto-686e2"
ROOT       = Path("/root/projeto_dre")
SA_PATH    = ROOT / "serviceAccount.json"
DADOS_PATH = ROOT / "dados.json"

# Usuários autorizados. Cada item vira:
#   (1) uma conta no Firebase Auth — usada no login da página
#   (2) uma entrada em meta/whitelist no Firestore — gate para ler dados
#
# Não há senha aqui de propósito: na 1ª criação o script gera uma aleatória
# (impressa UMA VEZ no terminal) e o usuário troca depois. Em contas que já
# existem, a senha atual é preservada.
USUARIOS = [
    {"email": "weswish@gmail.com",             "nome": "Master",       "role": "administrador", "lojas": []},
    {"email": "coord.control@supervs.com.br",  "nome": "Coordenação",  "role": "diretoria",     "lojas": []},
    {"email": "tiagovalentimcsilva@gmail.com", "nome": "Analista",     "role": "administrador", "lojas": []},
]

# Whitelist é derivada dos USUARIOS — mantém um único ponto de verdade.
EMAILS_PERMITIDOS = [u["email"] for u in USUARIOS]

# Roles válidos (mantém em sincronia com o front em dashboard.html: const ROLES)
ROLES_VALIDOS = {"gerente", "supervisor", "diretoria", "administrador"}
ROLES_QUE_PRECISAM_LOJAS = {"gerente", "supervisor"}


def gerar_senha_inicial(tamanho: int = 14) -> str:
    """Gera senha forte para uso temporário no primeiro login.

    Inclui letras, dígitos e alguns símbolos seguros para URL/copy-paste.
    """
    alfabeto = string.ascii_letters + string.digits + "!@#$%&*-_=+"
    while True:
        s = "".join(secrets.choice(alfabeto) for _ in range(tamanho))
        # Garante variedade mínima (1 maiúscula, 1 dígito, 1 símbolo)
        if (any(c.isupper() for c in s)
                and any(c.isdigit() for c in s)
                and any(c in "!@#$%&*-_=+" for c in s)):
            return s

def sincroniza_usuarios() -> None:
    """Cria contas faltantes (com senha aleatória) e mantém o resto idempotente.

    - Conta nova: gera senha forte, cria, IMPRIME a senha UMA vez.
    - Conta já existente: não toca na senha. Garante email_verified=True e
      atualiza display_name se mudou.
    """
    senhas_geradas: list[tuple[str, str]] = []

    for u in USUARIOS:
        email, nome = u["email"], u.get("nome")
        try:
            existente = auth.get_user_by_email(email)
            mudancas = {}
            if not existente.email_verified:
                mudancas["email_verified"] = True
            if nome and existente.display_name != nome:
                mudancas["display_name"] = nome
            if mudancas:
                auth.update_user(existente.uid, **mudancas)
                rotulo = ", ".join(mudancas.keys())
                print(f"   ↻ {email}  (atualizado: {rotulo})")
            else:
                print(f"   ✓ {email}  (já existia, uid={existente.uid[:8]}…)")
        except auth.UserNotFoundError:
            senha = gerar_senha_inicial()
            novo = auth.create_user(
                email=email, password=senha,
                display_name=nome, email_verified=True,
            )
            print(f"   + {email}  (criado, uid={novo.uid[:8]}…)")
            senhas_geradas.append((email, senha))

    if senhas_geradas:
        print()
        print("   " + "─" * 60)
        print("   🔑 SENHAS INICIAIS — anote e envie por canal seguro.")
        print("       (não serão exibidas novamente)")
        print("   " + "─" * 60)
        for email, senha in senhas_geradas:
            print(f"   {email:40s}  {senha}")
        print("   " + "─" * 60)


def sincroniza_users_firestore(db) -> None:
    """Cria/atualiza um doc por usuário em users/{email}.

    Não sobrescreve campos editados via UI (status, lojas etc.) — usa merge.
    Apenas preenche os campos canônicos (nome, email, role, lojas) na primeira
    criação. Em runs seguintes, mantém o que já existe.
    """
    from firebase_admin import firestore as _fs   # SERVER_TIMESTAMP
    for u in USUARIOS:
        email = u["email"]
        role = u.get("role", "administrador")
        if role not in ROLES_VALIDOS:
            print(f"   ⚠ {email}: role '{role}' inválido — usando 'administrador'")
            role = "administrador"
        lojas = u.get("lojas", []) if role in ROLES_QUE_PRECISAM_LOJAS else []

        ref = db.collection("users").document(email)
        snap = ref.get()
        if snap.exists:
            # mantém status/lojas que possam ter sido editados pela UI;
            # sobrescreve apenas nome/role pra refletir a "fonte" do .py
            ref.set({
                "email":  email,
                "nome":   u.get("nome", ""),
                "role":   role,
                "atualizadoEm": _fs.SERVER_TIMESTAMP,
            }, merge=True)
            print(f"   ↻ users/{email}  (atualizado nome+role; status/lojas preservados)")
        else:
            ref.set({
                "email":  email,
                "nome":   u.get("nome", ""),
                "role":   role,
                "status": "ativo",
                "lojas":  lojas,
                "criadoEm":     _fs.SERVER_TIMESTAMP,
                "atualizadoEm": _fs.SERVER_TIMESTAMP,
            })
            print(f"   + users/{email}  (criado, role={role})")


def upload_dados(db) -> None:
    if not DADOS_PATH.exists():
        raise SystemExit(f"❌  {DADOS_PATH} não encontrado. Rode `python3 etl.py` antes.")

    print(f"   Lendo {DADOS_PATH.name} ({DADOS_PATH.stat().st_size/1024/1024:.2f} MB)...")
    dados = json.loads(DADOS_PATH.read_text(encoding="utf-8"))

    db.collection("meta").document("dimensoes").set({
        "geradoEm":       dados.get("geradoEm"),
        "fontes":         dados.get("fontes"),
        "dimensoes":      dados["dimensoes"],
        "mapeamentoKPI":  dados["mapeamentoKPI"],
    })

    # Agrupa fatos por (ano, mês) — cada um vai virar 1 doc em meses/
    porGrupoBucket       = defaultdict(list)
    porAgrupamentoBucket = defaultdict(list)
    porLinhaBucket       = defaultdict(list)

    for r in dados["fatos"]["porGrupo"]:
        porGrupoBucket[(r["ANO"], r["MÊS"])].append(
            (r["LOJA"], r["GRUPO"], r["VALORES"])
        )
    for r in dados["fatos"]["porAgrupamento"]:
        porAgrupamentoBucket[(r["ANO"], r["MÊS"])].append(
            (r["LOJA"], r["AGRUPAMENTO"], r["VALORES"])
        )
    for r in dados["fatos"]["porLinha"]:
        porLinhaBucket[(r["ANO"], r["MÊS"])].append(
            (r["LOJA"], r["GRUPO"], r["AGRUPAMENTO"], r["LINHAS"], r["VALORES"])
        )

    print(f"   Gravando {len(porGrupoBucket)} documentos em meses/ (formato compacto v2)...")
    for (ano, mes), pg in sorted(porGrupoBucket.items()):
        doc_id = f"{ano}-{mes:02d}"
        payload = _compactar_mes(
            ano, mes,
            pg,
            porAgrupamentoBucket.get((ano, mes), []),
            porLinhaBucket.get((ano, mes), []),
        )
        size_kb = len(json.dumps(payload).encode("utf-8")) / 1024
        if size_kb > 950:
            print(f"   ⚠ {doc_id} tem {size_kb:.0f} KB (próximo do limite de 1 MiB).")
        db.collection("meses").document(doc_id).set(payload)
        print(f"   ✓ meses/{doc_id}  "
              f"({len(payload['porGrupo'])} porGrupo, "
              f"{len(payload['porAgrupamento'])} porAgrupamento, "
              f"{len(payload['porLinha'])} porLinha, "
              f"{size_kb:.0f} KB)")


def _compactar_mes(ano, mes, pg_rows, pa_rows, pl_rows):
    """Converte os fatos do mês para o formato compacto v2.

    Em vez de cada linha ser `{"loja":"L01","grupo":"X","valor":42}` (verboso,
    repete strings), separa as strings únicas em `dim` (dicionários por
    dimensão) e os fatos viram arrays posicionais com índices:

        porLinha: [[lojaIdx, grupoIdx, agrupIdx, linhaIdx, valor], ...]

    Reduz ~70% do tamanho do doc. O dashboard expande de volta no
    `loadFromFirestore` mantendo o resto do código inalterado.
    """
    lojas, grupos, agrupamentos, linhas = [], [], [], []
    li, gi, ai, ni = {}, {}, {}, {}

    def _idx(s, lst, mp):
        if s not in mp:
            mp[s] = len(lst)
            lst.append(s)
        return mp[s]

    # Firestore não aceita arrays aninhados — então usamos objects com chaves
    # curtas (l, g, a, n, v). Ainda economiza muito porque os valores das
    # strings repetidas viram índices de inteiro via `dim`.
    porGrupo = [
        {"l": _idx(l, lojas, li), "g": _idx(g, grupos, gi), "v": v}
        for (l, g, v) in pg_rows
    ]
    porAgrupamento = [
        {"l": _idx(l, lojas, li), "a": _idx(a, agrupamentos, ai), "v": v}
        for (l, a, v) in pa_rows
    ]
    porLinha = [
        {"l": _idx(l, lojas, li), "g": _idx(g, grupos, gi),
         "a": _idx(a, agrupamentos, ai), "n": _idx(n, linhas, ni), "v": v}
        for (l, g, a, n, v) in pl_rows
    ]
    return {
        "ano": ano,
        "mes": mes,
        "v": 2,                      # versão do schema (1 = verboso, 2 = compacto)
        "dim": {
            "lojas":         lojas,
            "grupos":        grupos,
            "agrupamentos":  agrupamentos,
            "linhas":        linhas,
        },
        "porGrupo":       porGrupo,
        "porAgrupamento": porAgrupamento,
        "porLinha":       porLinha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload dados + sync usuários (Firebase).")
    parser.add_argument("--apenas-usuarios", action="store_true",
                        help="Sincroniza só os usuários (Auth + whitelist) e pula o upload de dados.")
    args = parser.parse_args()

    if not SA_PATH.exists():
        raise SystemExit(
            f"\n❌  {SA_PATH} não encontrado.\n"
            f"   Vá em https://console.firebase.google.com/project/{PROJECT_ID}/settings/serviceaccounts/adminsdk\n"
            f"   clique em 'Gerar nova chave privada' e salve o JSON nesse caminho.\n"
        )

    print(f"[1/4] Inicializando Firebase Admin SDK ({PROJECT_ID})...")
    cred = credentials.Certificate(str(SA_PATH))
    firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    db = firestore.client()

    print(f"[2/4] Sincronizando {len(USUARIOS)} usuário(s) no Firebase Auth...")
    sincroniza_usuarios()

    print(f"[3/4] Gravando meta/whitelist no Firestore...")
    db.collection("meta").document("whitelist").set({"emails": EMAILS_PERMITIDOS})
    print(f"        ✓ whitelist: {EMAILS_PERMITIDOS}")

    print(f"        Sincronizando coleção users/ (perfis + permissões)...")
    sincroniza_users_firestore(db)

    if args.apenas_usuarios:
        print("[4/4] Pulando upload de dados (--apenas-usuarios).")
    else:
        print("[4/4] Subindo meta/dimensoes + meses/ ...")
        upload_dados(db)

    print("\n✅  Concluído.")
    print(f"    Firestore:    https://console.firebase.google.com/project/{PROJECT_ID}/firestore/data")
    print(f"    Auth users:   https://console.firebase.google.com/project/{PROJECT_ID}/authentication/users")


if __name__ == "__main__":
    main()
