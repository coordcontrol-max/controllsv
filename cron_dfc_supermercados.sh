#!/usr/bin/env bash
# Worker da fila "DFC Supermercados — Atualizar" (botão no fluxo-caixa.html).
#
# Agendado via cron WSL a cada minuto:
#   * * * * * /root/projeto_dre/cron_dfc_supermercados.sh
#
# Comportamento por execução:
#   - Login no site (admin)
#   - Bate em /api/admin/dfc-supermercados/proxima-pendente
#   - Se NÃO há solicitação → exit silencioso (custo: ~200ms)
#   - Se há → roda agente/_run_tudo_mes.py (mês corrente) + projeção DFC
#   - Finaliza com status=ok|erro
#
# Lockfile previne dupla execução (pipeline leva 30-90 min).

set -e
cd "$(dirname "$0")"

mkdir -p logs
LOG="logs/dfc-supermercados-$(date +%Y-%m-%d).log"
LOCK="/tmp/dfc-supermercados.lock"

if [ -e "$LOCK" ]; then
  PID=$(cat "$LOCK" 2>/dev/null || echo 0)
  if kill -0 "$PID" 2>/dev/null; then
    # Worker anterior ainda rodando — sai silencioso (cron próximo tenta de novo)
    exit 0
  fi
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# Credenciais admin do site (.env do projeto-comercial-gh)
ENV_FILE=/root/projeto-comercial-gh/.env
if [ ! -f "$ENV_FILE" ]; then
  echo "[$(date '+%H:%M:%S')] ERRO: $ENV_FILE não encontrado" >> "$LOG"
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

if [ -z "$SITE_URL" ] || [ -z "$ADMIN_USERNAME" ] || [ -z "$ADMIN_PASSWORD" ]; then
  echo "[$(date '+%H:%M:%S')] ERRO: SITE_URL/ADMIN_USERNAME/ADMIN_PASSWORD faltando" >> "$LOG"
  exit 1
fi

COOKIE_JAR=$(mktemp)
trap 'rm -f "$LOCK" "$COOKIE_JAR" /tmp/dfc_*.json' EXIT

# Login
LOGIN_BODY=$(python3 -c "import json,os; print(json.dumps({'username':os.environ['ADMIN_USERNAME'],'password':os.environ['ADMIN_PASSWORD']}))")
HTTP=$(curl -s -o /tmp/dfc_login.json -w "%{http_code}" -c "$COOKIE_JAR" \
  -X POST "$SITE_URL/api/login" -H "Content-Type: application/json" -d "$LOGIN_BODY")
if [ "$HTTP" != "200" ]; then
  echo "[$(date '+%H:%M:%S')] login falhou (HTTP $HTTP)" >> "$LOG"
  exit 1
fi

# Pega próxima pendente (idempotente — marca como 'processando')
PENDENTE=$(curl -s -b "$COOKIE_JAR" -X POST "$SITE_URL/api/admin/dfc-supermercados/proxima-pendente" -H "Content-Type: application/json" -d '{}')
ID=$(echo "$PENDENTE" | python3 -c "import json,sys; d=json.load(sys.stdin); p=d.get('pendente'); print(p['id'] if p else '')")

if [ -z "$ID" ]; then
  exit 0   # nada na fila — sai silencioso
fi

echo "" >> "$LOG"
echo "── $(date '+%Y-%m-%d %H:%M:%S') · solicitação #$ID ──" >> "$LOG"

finalizar() {
  local status="$1"
  local msg="$2"
  curl -s -o /dev/null -b "$COOKIE_JAR" -X POST "$SITE_URL/api/admin/dfc-supermercados/finalizar" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json,sys; print(json.dumps({'id': $ID, 'status': '$status', 'mensagem': sys.argv[1]}))" "$msg")" \
    || true
}

# Probe Oracle (30s — _run_tudo_mes.py precisa do Oracle)
if ! nc -zw30 10.61.1.1 1521 2>/dev/null; then
  MSG="Oracle não respondeu em 30s"
  echo "  ⚠ $MSG" >> "$LOG"
  finalizar erro "$MSG"
  exit 0
fi

T0=$(date +%s)
ANO=$(date +%Y); MES=$(date +%-m)

# Pipeline RÁPIDO (~2 min) — só o que afeta DFC + Títulos em Aberto:
#   1. atualizar(slugs=[fluxo_*]) — 4 queries Oracle de fluxo (~40s)
#   2. engine_fluxo.executar_fluxo — DFC realizado no Firestore (~30s)
#   3. gera_titulos_aberto.py — Oracle TITABERTO → JSON (~28s)
#   4. upload_titulos_aberto.py — JSON → Firestore titulosAberto/ (~10s)
#   5. gera_fluxocaixa_projetado.py — DFC futuro a partir de titulosAberto (~5s)
# NÃO roda as 14 queries pesadas de DRE (Compra Func Atual sozinha = 16 min).
# A DRE realizada (meses/) continua sendo atualizada SEPARADO se o usuário pedir
# (ou via novo botão futuro). Pra esse botão de DFC, foco em fluxo + títulos.
cd /root/projeto_dre/agente
set -a; . ./.env; set +a
if LD_LIBRARY_PATH=/opt/oracle/instantclient_23_5 timeout 1800 \
   python3 /root/projeto_dre/_atualizar_dfc_realizado.py "$ANO" "$MES" >> "$LOG" 2>&1
then
  T1=$(date +%s)
  echo "  ✓ DFC realizado em $((T1-T0))s" >> "$LOG"
  # 2b) Detalhe título-a-título do DFC (drilldown da UI) — best-effort, lê o
  #     rawOracle/__fluxo_* recém-gravado e reusa o classifier (bate exato).
  cd /root/projeto_dre
  if LD_LIBRARY_PATH=/opt/oracle/instantclient_23_5 timeout 600 python3 gera_fluxocaixa_detalhe.py "$ANO" "$MES" >> "$LOG" 2>&1; then
    echo "  ✓ detalhe DFC (drilldown) atualizado" >> "$LOG"
  else
    echo "  ⚠ detalhe DFC falhou — drilldown pode ficar defasado" >> "$LOG"
  fi
  # 3) Títulos em Aberto: Oracle → JSON
  cd /root/projeto_dre
  if LD_LIBRARY_PATH=/opt/oracle/instantclient_23_5 timeout 300 python3 gera_titulos_aberto.py >> "$LOG" 2>&1; then
    T2=$(date +%s)
    # 4) Upload JSON → Firestore
    if python3 upload_titulos_aberto.py >> "$LOG" 2>&1; then
      T3=$(date +%s)
      # 5) Projeção DFC pros meses futuros
      if python3 gera_fluxocaixa_projetado.py >> "$LOG" 2>&1; then
        T4=$(date +%s)
        MSG="DFC ${T1}-${T0}s + tit-gera $((T2-T1))s + tit-upload $((T3-T2))s + projeção $((T4-T3))s = $((T4-T0))s"
        MSG="DFC $((T1-T0))s + tit-gera $((T2-T1))s + tit-upload $((T3-T2))s + projeção $((T4-T3))s = $((T4-T0))s"
        echo "  ✓ $MSG" >> "$LOG"
        finalizar ok "$MSG"
      else
        echo "  ⚠ projeção falhou — DFC e títulos OK" >> "$LOG"
        finalizar ok "DFC+Títulos OK (projeção falhou)"
      fi
    else
      echo "  ⚠ upload_titulos_aberto falhou — DFC e gera OK" >> "$LOG"
      finalizar ok "DFC OK, upload títulos falhou"
    fi
  else
    echo "  ⚠ gera_titulos_aberto falhou — DFC OK" >> "$LOG"
    finalizar ok "DFC OK, títulos em aberto não atualizou"
  fi
else
  MSG="DFC realizado falhou — ver log"
  echo "  ✗ $MSG" >> "$LOG"
  finalizar erro "$MSG"
fi
