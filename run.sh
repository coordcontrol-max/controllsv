#!/usr/bin/env bash
# Atualiza dados.json a partir dos 3 Excel no Desktop e sobe o servidor local.
# Uso:   ./run.sh              # ETL + servidor
#        ./run.sh --etl-only   # só recalcula o JSON
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/2] Rodando ETL..."
python3 etl.py

if [[ "${1:-}" == "--etl-only" ]]; then
  echo "JSON atualizado. Saindo."
  exit 0
fi

PORT="${PORT:-8765}"
echo "[2/2] Servindo em http://localhost:${PORT}/dashboard.html  (Ctrl+C p/ parar)"
exec python3 -m http.server "${PORT}" --directory .
