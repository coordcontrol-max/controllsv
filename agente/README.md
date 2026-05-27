# Agente Oracle Consinco

Agente local que conecta no Oracle do Consinco, roda 18 queries e grava o
resultado RAW no Firestore. Quando o usuário clica "Atualizar Tudo" na aba
Importação SQL do dashboard, o browser chama esse agente em
`http://localhost:8765/atualizar`.

Deve rodar na máquina **192.168.0.225** (a mesma que hoje atualiza o Excel).

## 1. Pré-requisitos

Instalar uma vez só, antes:

| O quê | Onde baixar | Detalhe |
|---|---|---|
| **Python 3.12+** | https://python.org | Marcar "Add Python to PATH" no instalador |
| **Oracle Instant Client (Basic Lite)** | https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html | Extrair pra `C:\oracle\instantclient_23_5` |

## 2. Setup (uma vez só)

Abra um Prompt de Comando (cmd) na pasta `agente`:

```cmd
cd C:\caminho\para\projeto_dre\agente
pip install -r requirements.txt
```

Copie o template e preencha:

```cmd
copy .env.example .env
notepad .env
```

Edite o `.env`:
- `ORACLE_USER`, `ORACLE_PASSWORD` — credenciais Consinco
- `ORACLE_CLIENT_DIR` — caminho onde você extraiu o Instant Client
- `FIREBASE_SA_PATH` — caminho do `serviceAccount.json` (mesmo arquivo que
  `upload_to_firestore.py` usa hoje, normalmente fica na pasta `projeto_dre/`)

## 3. Rodar

```cmd
python agente.py
```

Vai mostrar:
```
✓ Oracle Instant Client carregado de C:\oracle\instantclient_23_5
✓ Firebase conectado (serviceAccount em ...)

► Agente subindo em http://localhost:8765
  Origens permitidas: ...
  Endpoints: /, /health, POST /atualizar?ano=YYYY[&mes=MM]
```

**Deixa essa janela aberta enquanto for usar o dashboard.** Ctrl+C pra parar.

## 4. Testar manualmente

Abra outra janela cmd:

```cmd
curl http://localhost:8765/health
```

Deve voltar `{"oracle": true, "firebase": true, "queries": 18}`.

Pra rodar todas as queries de um mês específico:

```cmd
curl -X POST "http://localhost:8765/atualizar?ano=2026&mes=5"
```

(Demora 30-90s dependendo do volume.)

## 5. Usar pelo dashboard

1. Abre o dashboard nessa máquina (controllsv.web.app)
2. Vai em **Importação > Importação SQL**
3. Clica em **Atualizar Mês X** ou **Atualizar Tudo**

Os dados aparecem em `rawOracle/{ano-mes}__{slug}` no Firestore.

## 6. Subir como serviço Windows (opcional, futuro)

Quando quiser que o agente suba sozinho no boot do PC, dá pra usar
`nssm` (https://nssm.cc/) ou criar um Task Scheduler. Por enquanto a
recomendação é deixar rodando manual numa janela cmd.

## Estrutura de arquivos

```
agente/
├── agente.py           ← servidor FastAPI
├── queries.py          ← 18 queries Consinco parametrizadas
├── requirements.txt
├── .env                ← suas credenciais (NÃO commitar)
├── .env.example        ← template
└── README.md
```

## Schema de saída no Firestore

Cada query vira um doc em `rawOracle/`:

```
rawOracle/
├── 2026-05__venda_atual         { ano, mes, slug, nome, count, rows: [...], ms, geradoEm }
├── 2026-05__despesas            { ..., chunked: true, totalChunks: 3 }
│   └── chunks/0                  { n: 0, rows: [primeiras 1000] }
│   └── chunks/1                  { n: 1, rows: [próximas 1000] }
│   └── chunks/2                  { n: 2, rows: [últimas N] }
├── 2026-05__operacao_financeira { ... }
└── ... (18 queries × 12 meses)
```

Linhas que excedem 1MB (limite de doc Firestore) são quebradas em chunks
de 1000 linhas em sub-collections. O dashboard reconcilia isso na leitura.
