#!/usr/bin/env bash
# Polling de main (a cada 5min via cron) — se houver commits novos,
# faz `git reset --hard origin/main` e dispara `firebase deploy` canônico.
# Roda na WSL, que tem os dados_*/ locais (gerados pelo run_etl.sh).
#
# Instalação no cron (já feito uma vez):
#   */5 * * * * /root/projeto_dre/sync_and_deploy.sh >> /root/projeto_dre/logs/sync.log 2>&1
#
# Não conflita com o run_etl.sh (cron 03h) — os dois fazem deploy idempotente.

set -euo pipefail
cd /root/projeto_dre

mkdir -p logs
TS=$(date -Iseconds)

# Garante que estamos no main e fetch
git checkout main --quiet 2>/dev/null || true
BEFORE=$(git rev-parse HEAD)
git fetch origin main --quiet
AFTER=$(git rev-parse origin/main)

if [ "$BEFORE" = "$AFTER" ]; then
  exit 0   # sem mudanças, nada pra fazer
fi

echo "── $TS · main mudou: $BEFORE → $AFTER · pulling + deploying ──"

# Reset duro pra ficar idêntico ao remoto (evita conflitos com mudanças
# locais — nenhum dev deveria editar a WSL diretamente).
git reset --hard origin/main

# Mostra o que mudou (pro log)
git log --oneline "$BEFORE..$AFTER"

# Deploy canônico (usa firebase.json, que inclui dados_*/)
export PATH="/usr/local/bin:/usr/bin:/bin:/root/.nvm/versions/node/$(ls /root/.nvm/versions/node 2>/dev/null | tail -1)/bin:$PATH"
firebase deploy --only hosting:controllsv --non-interactive 2>&1 || {
  echo "[ERRO] firebase deploy falhou — próxima execução tenta de novo."
  exit 1
}

echo "── $TS · deploy OK ──"
