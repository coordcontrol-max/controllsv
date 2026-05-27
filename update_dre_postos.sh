#!/usr/bin/env bash
# Ponte do agente RPA → site. Roda DEPOIS que o RPA exportou as queries do
# Adaptive pra \\10.61.1.13\controller\03 - POSTOS\Automate. Lê os exports,
# regenera os JSONs (DRE / DFC / Títulos em Aberto dos postos) e publica.
#
# O agente (Windows) chama assim, no fim do fluxo:
#   wsl bash /root/projeto_dre/update_dre_postos.sh
#
# É independente do run_etl.sh diário — só mexe nos relatórios dos Postos.
set -euo pipefail
cd /root/projeto_dre
mkdir -p logs
LOG="logs/dre-postos-$(date +%Y%m%d).log"
export PATH="/root/.nvm/versions/node/v24.15.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') update Postos (Adaptive/SQL) ====="

  # Garante a rede montada (o export do RPA fica em \\10.61.1.13\controller\...).
  if ! mountpoint -q /mnt/controller; then
    echo "[mount] /mnt/controller não montado — tentando mount -a"
    mount -a 2>&1 || echo "[WARN] mount -a falhou; ETL tentará Downloads como reserva"
  fi

  echo "----- etl_dre_postos_sql.py (DRE — lê DRE_Postos.xlsx) -----"
  if ! python3 etl_dre_postos_sql.py; then
    echo "[ERRO] ETL DRE falhou — abortando (não publica dado quebrado)."
    exit 1
  fi

  echo "----- etl_dfc_postos_sql.py (DFC Diário — lê DFC_Postos.xlsx) -----"
  if ! python3 etl_dfc_postos_sql.py; then
    echo "[WARN] ETL DFC falhou — DFC Diário não atualizado (DRE segue)."
  fi

  echo "----- etl_titulos_aberto.py (Títulos em Aberto — lê TITABERTO*.xlsx) -----"
  if ! python3 etl_titulos_aberto.py; then
    echo "[WARN] ETL Títulos em Aberto falhou — relatório não atualizado (resto segue)."
  fi

  echo "----- etl_dfc_postos_dashboard.py (Dashboard DFC postos ← Adaptive) -----"
  if ! python3 etl_dfc_postos_dashboard.py; then
    echo "[WARN] etl_dfc_postos_dashboard.py falhou — Dashboard DFC fica com a planilha."
  fi

  echo "----- firebase deploy --only hosting:controllsv -----"
  if ! firebase deploy --only hosting:controllsv --non-interactive 2>&1; then
    echo "[WARN] deploy falhou; próxima execução tenta de novo."
    exit 1
  fi

  echo "===== $(date '+%Y-%m-%d %H:%M:%S') concluído ====="
} 2>&1 | tee -a "$LOG"
