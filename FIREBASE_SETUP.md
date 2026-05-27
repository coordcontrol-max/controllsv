# Setup Firebase — projeto-686e2

Roteiro com 6 passos. Os **3 primeiros** dependem de você (precisam do navegador
e do console Firebase). Os **3 últimos** rodo eu via CLI assim que a configuração
estiver pronta.

## Visão geral da arquitetura

```
Excel (Desktop)  ──► etl.py ──► dados.json
                                    │
                                    ▼
                       upload_to_firestore.py    ◄── serviceAccount.json
                                    │                  (chave privada)
                                    ▼
                            ┌─────────────────┐
                            │   Firestore     │
                            │  meta/          │
                            │  meses/         │
                            └────────┬────────┘
                                     │ (leitura autenticada)
                                     ▼
                ┌──────────────────────────────────────┐
                │  dashboard.html (Firebase Auth)      │
                │  Google Sign-In + allow-list e-mails │
                └──────────────────────────────────────┘
```

---

## 1) Habilitar Firestore e Google Sign-In no Console

### 1a — Criar o database Firestore (se ainda não existe)
1. Abra <https://console.firebase.google.com/project/projeto-686e2/firestore>
2. Clique em **Criar banco de dados**
3. Escolha **modo de produção** (regras de segurança serão deployadas pelo CLI)
4. Região: `southamerica-east1` (São Paulo) ou `us-central1` — qualquer uma serve.

### 1b — Ativar autenticação com Google
1. Abra <https://console.firebase.google.com/project/projeto-686e2/authentication/providers>
2. Em **Sign-in method**, clique em **Google** → ative → escolha um e-mail de
   suporte → **Salvar**

## 2) Gerar a chave de service account (uploader)

1. Abra <https://console.firebase.google.com/project/projeto-686e2/settings/serviceaccounts/adminsdk>
2. Clique em **Gerar nova chave privada** → **Gerar chave** → baixa um JSON
3. **Mova esse arquivo para** `/root/projeto_dre/serviceAccount.json`
   (no Windows você pode arrastar para o WSL, ou usar `cp` de `/mnt/c/...`)
4. Confira: `ls -la /root/projeto_dre/serviceAccount.json`

> ⚠ Esse arquivo dá poder total no projeto. Já está no `.gitignore`. Nunca
> compartilhe nem suba pro Git.

## 3) Pegar a config web do dashboard

1. Abra <https://console.firebase.google.com/project/projeto-686e2/settings/general>
2. Role até **Seus aplicativos**. Se não houver nenhum, clique em **`</>`** (web)
   → registre com nome qualquer (ex.: "dashboard") → não precisa "Configurar
   Hosting" agora → **Registrar app**
3. Em "SDK do Firebase" → **Configuração**, copie o objeto `firebaseConfig` (vai
   ter `apiKey`, `authDomain`, `projectId`, `storageBucket`, `messagingSenderId`,
   `appId`)
4. **Cole esses valores em** `dashboard.html`, no bloco `const firebaseConfig`
   (procure por `PASTE_API_KEY` e substitua os 3 placeholders)

> Esses valores **não são segredo** — eles vão pro client de qualquer jeito.
> Quem garante segurança são as regras do Firestore + a allow-list de e-mails.

---

## 4) `firebase login` (CLI)

Eu vou rodar isso pra você. Vai aparecer uma URL longa no terminal — copie ela,
cole no navegador do Windows, autorize com a conta Google e copie o código de
volta.

```bash
firebase login --no-localhost
```

## 5) Deploy das regras de segurança

```bash
cd /root/projeto_dre
firebase deploy --only firestore:rules
```

Resultado: as regras em [firestore.rules](firestore.rules) vão pro projeto. A
partir daí só usuários autenticados cujo e-mail está em `meta/whitelist` podem
ler dados.

## 6) Upload dos dados

```bash
cd /root/projeto_dre
python3 upload_to_firestore.py
```

Esperado:

```
[1/5] Inicializando Firebase Admin SDK (projeto-686e2)...
[2/5] Lendo dados.json (3.58 MB)...
[3/5] Subindo meta/dimensoes e meta/whitelist...
        ✓ whitelist: ['weswish@gmail.com', 'coord.control@supervs.com.br']
[4/5] Reorganizando fatos por (ano, mês)...
[5/5] Gravando 3 documentos em meses/ ...
   ✓ meses/2026-01  (...)
   ✓ meses/2026-02  (...)
   ✓ meses/2026-03  (...)
✅ Upload concluído.
```

Confira em <https://console.firebase.google.com/project/projeto-686e2/firestore/data>.

---

## Como roda o painel

### Modo local (desenvolvimento)
```bash
cd /root/projeto_dre
./run.sh
```
Abre <http://localhost:8765/dashboard.html>. Como o `firebaseConfig.apiKey` ainda
está como `PASTE_*` (em desenvolvimento), o painel detecta que está sem Firebase
e lê o `dados.json` local — **sem auth, sem login**.

> Quando você preencher o `firebaseConfig` com os valores reais, mesmo o modo
> local vai exigir login. Se quiser manter dev sem login, comente os valores
> reais ou mantenha um `dashboard.html` separado para o ambiente de produção.

### Modo Firebase (produção)
1. `firebaseConfig` em `dashboard.html` preenchido
2. `firebase deploy --only hosting` (vou rodar quando estiver pronto)
3. Painel vai estar em `https://projeto-686e2.web.app/`
4. Acesso pede login Google. Só os e-mails da whitelist passam.

---

## Adicionar/remover usuários

Edite a constante `EMAILS_PERMITIDOS` em
[upload_to_firestore.py](upload_to_firestore.py) e re-rode:

```bash
python3 upload_to_firestore.py
```

(Só o documento `meta/whitelist` é regravado em segundos — os fatos não.)

Alternativa: edite direto em
<https://console.firebase.google.com/project/projeto-686e2/firestore/data/~2Fmeta~2Fwhitelist>.

---

## Custos esperados

- **Leituras por usuário/sessão**: ~5 (1 dimensoes + 1 whitelist + 3 meses)
- **Cota grátis**: 50.000 leituras/dia
- **Cabe**: ~10.000 carregamentos do painel por dia. Mais que suficiente.

A allow-list está hardcoded no `upload_to_firestore.py` por ora; se a equipe
crescer muito, dá pra trocar por uma coleção `users/{uid}` ou usar Custom Claims.
