# controllsv

Dashboard de gestão de resultados — Supermercados Vivendas, Postos VS e Outras Empresas.

- **Hosting:** https://controllsv.web.app (Firebase project `projeto-686e2`)
- **Frontend:** `dashboard.html` (SPA single-file) + `login.html`
- **Dados:** Firestore (`meses/`, `fluxoSegmentos/`, `meta/`, ...) + JSONs estáticos servidos por Hosting

## Workflow de desenvolvimento (3 devs)

```
        ┌──────────────────────────────────────────────────────┐
        │  GitHub controllsv (private)                          │
        │                                                       │
        │   feat/foo ──PR──> [CI: lint + preview deploy]        │
        │       │                                               │
        │       └──merge──> main ──┐                            │
        └─────────────────────────────────┬─────────────────────┘
                                          │ (a cada 5min)
                                          ▼
                              ┌──────────────────────┐
                              │ WSL: sync_and_deploy │
                              │   git pull origin    │
                              │   firebase deploy    │
                              └──────────┬───────────┘
                                         ▼
                                 controllsv.web.app
```

### Regras de ouro

1. **NUNCA push direto em `main`**. Sempre via Pull Request (branch protegida).
2. **Branch por feature/fix:** `feat/<desc>` ou `fix/<desc>`.
3. **PR aberto** → GitHub Actions sobe um *preview* numa URL efêmera tipo
   `controllsv--pr-42-xxxx.web.app` (expira em 7 dias). Use pra validar a UI
   antes de pedir review.
4. **PR aprovado e merged em main** → o `sync_and_deploy.sh` na WSL detecta
   em até 5min e faz o deploy canônico em `controllsv.web.app`.
5. **Nunca edite arquivos direto na WSL** sem PR — o sync vai sobrescrever
   suas mudanças locais com o `git reset --hard origin/main`.

### Por que esse fluxo (e não auto-deploy puro do GitHub Actions)?

Os dados financeiros (`dados_*/`, `dados.json`, etc.) são gerados por ETLs que
rodam **só na WSL** (acessam Oracle/MySQL/Adaptive da rede interna). Eles não
vão pro git (`.gitignore`). Se o CI fizesse o deploy canônico, jogaria fora
todos esses JSONs do Hosting. Por isso quem deploya canônico é a WSL — que
tem código (vindo do git) e dados (gerados pelo cron).

## Setup local (cada dev)

```bash
git clone git@github.com:<org>/controllsv.git
cd controllsv

# Firebase CLI (pra deploy local opcional — só se você for o operador da WSL)
npm install -g firebase-tools
firebase login
firebase use projeto-686e2
```

Os JSONs de dados ficam **só na WSL** que tem o cron rodando. Em outras máquinas
você só edita código (`dashboard.html`, `*.py`, etc.) e abre PR.

## Comandos úteis

```bash
# Criar branch e abrir PR
git checkout -b feat/minha-feature
# ... edita ...
git commit -am "feat: minha feature"
git push -u origin feat/minha-feature
gh pr create --fill

# Ver o preview do meu PR
gh pr view --web

# Cron status (na WSL)
crontab -l
tail -f /root/projeto_dre/logs/sync.log
tail -f /root/projeto_dre/logs/cron.log
```

## Estrutura de pastas

```
.
├── dashboard.html         # SPA principal (sidebar + todas as views)
├── login.html             # Tela de login (Firebase Auth)
├── server.js              # Middleware de admin gates (Cloud Function-like)
├── etl_*.py               # ETLs por segmento (postos, outras, supermercados)
├── gera_*.py              # Geradores (saldos, intercompany, transferências)
├── upload_*.py            # Sobe JSONs gerados pra Firestore
├── run_etl.sh             # Cron diário 03h — pipeline completo
├── sync_and_deploy.sh     # Cron 5min — detecta merge na main + deploya
├── firebase.json          # Config canônica (usada pelo cron WSL)
├── firebase.ci.json       # Config do CI (preview channels, ignora dados_*/)
├── firestore.rules        # Regras de acesso ao Firestore
├── importacoes_historicas_outras.json  # Snapshot estático Jan-Abr/2026
└── .github/workflows/     # CI (lint + preview deploy)
```

Pastas `dados_*/` e arquivos grandes de dados estão no `.gitignore` —
vivem só na WSL e são deployados pelo cron.

## Deploy de emergência (manual)

Se o cron estiver parado e você precisa deployar agora:

```bash
ssh wsl.maquina  # acesso ao servidor com dados
cd /root/projeto_dre
git pull origin main
firebase deploy --only hosting:controllsv
```

## Secrets / configuração

- **GitHub Actions** precisa de um secret `FIREBASE_SERVICE_ACCOUNT` com o
  JSON da service account do Firebase (papel: Firebase Hosting Admin).
- **WSL** usa o `firebase login` interativo do operador (cred local).
- **ETLs** usam vars de env (`LUMI_PW`, `ORA_PWD`, etc.) — ver `PIPELINE.md`.
