#!/usr/bin/env bash
# Rotina diária de atualização do dashboard.
# Disparada pelo Task Scheduler do Windows (ver instruções em PIPELINE.md).
#
# Fluxo:
#   1. Garante que /mnt/controller está montado (re-monta se preciso)
#   2b. _run_tudo_mes.py — atualiza DRE (meses/) + DFC (fluxoCaixa/) do mês
#       corrente, daqui mesmo. Replica o pipeline 'tudo' do agente da .225
#       (atualizar + executar_rateio + executar_fluxo + dimensoes) e usa o
#       Render do João (render_reader) para a venda do mês corrente. ~40-70min.
#   3. etl_fluxo_segmentos.py    — Excels de postos/outras → dados_fluxo_*/
#   3b. etl_dfc_outras_lumi.py   — MySQL LUMI (SAC) → dados_fluxo_outras/ (sobrescreve)
#   4. gera_saldos_iniciais.py + etl_dre_postos.py
#   5. gera_titulos_aberto.py    — Oracle → titulos_aberto_*.json (supermercados)
#   6. gera_supermercados_extras.py (taxas+protege) + gera_apuracao_contratos.py
#      + etl_energia.py (energia.json)
#   7. uploads p/ Firestore do projeto-comercial: upload_titulos_aberto,
#      upload_fluxo_segmentos, upload_auditorias, upload_bp, upload_energia
#   8. firebase deploy           — publica os JSONs no controllsv.web.app
#   + Loga tudo em logs/etl-YYYYMMDD.log
#
# Cada etapa é independente e guardada — falha de uma não derruba as outras.

set -euo pipefail

cd /root/projeto_dre
mkdir -p logs
LOG="logs/etl-$(date +%Y%m%d).log"

# PATH explícito — Task Scheduler dispara WSL com ambiente limpo, sem
# herdar o PATH do usuário interativo. Inclui firebase CLI via nvm.
export PATH="/root/.nvm/versions/node/v24.15.0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Oracle Instant Client — necessário pra gera_titulos_aberto.py
# (oracledb.init_oracle_client carrega libclntsh.so + libnnz.so)
export LD_LIBRARY_PATH="/opt/oracle/instantclient_23_5:${LD_LIBRARY_PATH:-}"

# Credenciais sensíveis (LUMI_PW, etc.) — sourceadas de fora do git.
# Crie ~/.controllsv.env com: export LUMI_PW=...; export ORA_PWD=...
[ -f /root/.controllsv.env ] && source /root/.controllsv.env

# Limpa logs com mais de 30 dias (mantém o histórico recente)
find logs -name "etl-*.log" -mtime +30 -delete 2>/dev/null || true

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ETL iniciado ====="

  # Garante mount da rede (idempotente — mount -a só monta o que ainda não está)
  # `|| true` pra não derrubar o pipeline se /mnt/controller estiver offline
  # (postos/outras leem do /mnt/c local e não dependem dessa rede).
  if ! mountpoint -q /mnt/controller; then
    echo "[mount] /mnt/controller não está montado — tentando via /etc/fstab"
    mount -a 2>&1 || echo "[WARN] mount -a falhou; segue pra ver o que dá"
  fi
  # Share digitaliza (contratos + planilha de empréstimos) — não está no fstab.
  if ! mountpoint -q /mnt/digitaliza; then
    mkdir -p /mnt/digitaliza
    mount -t drvfs '\\10.61.1.13\digitaliza' /mnt/digitaliza 2>&1 || echo "[WARN] mount digitaliza falhou — endividamento usa o que houver."
  fi

  SM_OK=1   # supermercados (sempre 1 agora — engine assume)
  SEG_OK=1  # postos/outras

  # Restaura saldos_oficiais.json em dados_fluxo_{postos,outras}/ a partir do
  # arquivo-fonte saldos_oficiais_master.json (raiz). Os ETLs LUMI/segmentos
  # podem regenerar os diretórios e apagar esses JSONs manuais — sem eles a
  # DFC perde a âncora oficial diária. Roda ANTES dos ETLs por garantia.
  echo "----- [0.5/8] restaurar_saldos_oficiais.py (âncora oficial 27/04 etc.) -----"
  if ! python3 restaurar_saldos_oficiais.py; then
    echo "[WARN] restaurar_saldos_oficiais.py falhou — DFC pode perder a âncora oficial."
  fi

  # ░░ APOSENTADO em 2026-05-19 ░░
  # As etapas etl.py + upload_to_firestore (Excel → meses/*) foram desligadas.
  # Agora o pipeline do Supermercados é: Oracle → rawOracle (agente.py /atualizar)
  # → engine.executar_rateio → meses/{ano-mes}.
  echo "----- [1/2] (DESATIVADO) etl.py + upload_to_firestore — fonte agora é Oracle via engine.py -----"
  # echo "----- etl.py (supermercados) -----"   (legado Excel, mantido só como fallback comentado)

  # REATIVADO em 2026-05-29 (PR #20): DRE + DFC direto daqui (independente da .225
  # do João). _run_tudo_mes.py replica _executar_task(tipo='tudo'):
  #   atualizar (18 queries Oracle + render_reader pra venda_atual do João)
  #   → engine.executar_rateio → meses/{ano-mes} (DRE)
  #   → engine_fluxo.executar_fluxo → fluxoCaixa/{ano-mes} (DFC)
  #   → atualizar_dimensoes (snapshots Prevenção).
  # Inclui o slug pesado fluxo_transitorias (~25min). ~40-70 min.
  #
  # ⚠ Regra temporal (user 2026-05-30): meses passados ficam ESTÁTICOS após fechar.
  #   • Dia 1 do mês: roda APENAS o mês ANTERIOR (fechamento final). Mês corrente
  #     ainda não tem dado útil.
  #   • Dia 2+: roda APENAS o mês corrente.
  # Assim, fluxoCaixa/2026-01..04 já estão "fechados" e nunca mais são tocados pelo
  # cron; só a rodada de fechamento de 1/Mai/26 trouxe Abr ao estado final, e Jan-Mar
  # já vieram fechados das rodadas anteriores. O recompute manual de 30/05 (mover
  # 3 linhas pra "Despesas Financeiras / Expansão") foi exceção 1-shot.
  HOJE_DIA=$(date +%-d)
  HOJE_ANO=$(date +%Y)
  HOJE_MES=$(date +%-m)
  if [ "$HOJE_DIA" -eq 1 ]; then
    # Fecha mês anterior
    if [ "$HOJE_MES" -eq 1 ]; then ALVO_ANO=$((HOJE_ANO-1)); ALVO_MES=12
    else ALVO_ANO=$HOJE_ANO; ALVO_MES=$((HOJE_MES-1)); fi
    LABEL="fechamento $ALVO_ANO-$(printf '%02d' "$ALVO_MES")"
  else
    # Mês corrente
    ALVO_ANO=$HOJE_ANO; ALVO_MES=$HOJE_MES
    LABEL="mês corrente $ALVO_ANO-$(printf '%02d' "$ALVO_MES")"
  fi
  echo "----- [2b/8] _run_tudo_mes.py ($LABEL — DRE+DFC, venda via Render do João) -----"
  (
    set -a; . agente/.env; set +a
    cd agente
    if ! LD_LIBRARY_PATH="/opt/oracle/instantclient_23_5" timeout 4500 python3 _run_tudo_mes.py "$ALVO_ANO" "$ALVO_MES"; then
      echo "[WARN] _run_tudo_mes.py $ALVO_ANO-$ALVO_MES falhou. Próx noite tenta de novo."
    fi
  )

  echo "----- [3/7] etl_fluxo_segmentos.py (postos + outras → JSONs estáticos) -----"
  if ! python3 etl_fluxo_segmentos.py; then
    echo "[WARN] etl_fluxo_segmentos.py falhou — pulando deploy de postos/outras."
    SEG_OK=0
  fi

  # DFC do segmento OUTRAS agora vem DIRETO do MySQL do LUMI (base SAC), não do
  # Excel. Roda DEPOIS do etl_fluxo_segmentos pra SOBRESCREVER os JSONs de outras
  # (postos seguem do passo anterior). Não toca saldos_iniciais.json.
  OUTRAS_OK=1
  echo "----- [3b/7] etl_dfc_outras_lumi.py (DFC Outras — direto do MySQL LUMI) -----"
  if ! python3 etl_dfc_outras_lumi.py; then
    echo "[WARN] etl_dfc_outras_lumi.py falhou — outras fica com o que o etl_fluxo_segmentos gerou."
    OUTRAS_OK=0
  fi

  # (Intercompany = Postos + Outras é consolidado DEPOIS do adapter Adaptive dos
  #  postos — ver passo 4h, senão a parte de postos fica com a planilha velha.)

  # Ledger de transferências entre grupos (LUMI) + conciliação → relatório de 3
  # abas no segmento Intercompany. Lê direto do MySQL do LUMI.
  echo "----- [3d/7] gera_transferencias_intercompany.py (Transferências/Conciliação) -----"
  if ! python3 gera_transferencias_intercompany.py; then
    echo "[WARN] gera_transferencias_intercompany.py falhou — relatório de transferências não atualizado."
  fi

  echo "----- [4/7] gera_saldos_iniciais.py (Saldo Inicial DFC postos/outras) -----"
  if ! python3 gera_saldos_iniciais.py; then
    echo "[WARN] gera_saldos_iniciais.py falhou — Saldo Inicial DFC ficará desatualizado."
  fi

  # Checagem de frescor dos exports do Petros (gerados pelo Automate do Petros,
  # não por este script). Se o Automate falhou numa noite, os ETLs abaixo sobem
  # dado DEFASADO sem erro — este aviso deixa isso visível no log. Só WARN.
  echo "----- [4a/7] frescor dos exports do Petros (Automate) -----"
  PETROS_DIR="/mnt/controller/03 - POSTOS/Automate"
  PETROS_MAXAGE_H=20
  if [ -d "$PETROS_DIR" ]; then
    _chk_petros() {  # $1=rótulo  $2=arquivo exato
      local p="$PETROS_DIR/$2"
      if [ ! -f "$p" ]; then echo "[WARN] export Petros AUSENTE: $2 ($1)"; return; fi
      local age=$(( ( $(date +%s) - $(stat -c %Y "$p") ) / 3600 ))
      if [ "$age" -ge "$PETROS_MAXAGE_H" ]; then
        echo "[WARN] export Petros DEFASADO: $2 ($1) tem ${age}h — Automate pode ter falhado"
      else echo "  ok: $2 (${age}h)"; fi
    }
    _chk_petros "DRE caixa"       "DRE_Postos.xlsx"
    _chk_petros "DRE competência" "DRE_Postos_Competencia.xlsx"
    _chk_petros "DFC"             "DFC_Postos.xlsx"
    _chk_petros "Perdas"          "perdas.xlsx"
    find "$PETROS_DIR" -maxdepth 1 -iname '*titaberto*pagar*'   -mmin -1200 2>/dev/null | grep -q . || echo "[WARN] export Petros AUSENTE/DEFASADO: TITABERTO *pagar* (Títulos em Aberto)"
    find "$PETROS_DIR" -maxdepth 1 -iname '*titaberto*receber*' -mmin -1200 2>/dev/null | grep -q . || echo "[WARN] export Petros AUSENTE/DEFASADO: TITABERTO *receber* (Títulos em Aberto)"
  else
    echo "[WARN] pasta de exports do Petros não montada: $PETROS_DIR"
  fi

  echo "----- [4b/7] etl_dre_postos.py (DRE Postos — planilha /mnt/controller) -----"
  if ! python3 etl_dre_postos.py; then
    echo "[WARN] etl_dre_postos.py falhou — DRE Postos não foi regenerado."
  fi

  # DRE Postos (Adaptive) — "Mapa de Resultados". Lê o último export do relatório
  # "Mapa Anual de Resultados e Indicadores" que o usuário salva no Downloads
  # (prefere o consolidado "[postovivendas]...xlsx") e gera
  # dados_dre_postos_adaptive/{ano}.json. Idempotente: re-parseia o que houver.
  echo "----- [4c/7] etl_dre_postos_adaptive.py (DRE Postos — fallback Mapa Anual) -----"
  if ! python3 etl_dre_postos_adaptive.py; then
    echo "[WARN] etl_dre_postos_adaptive.py falhou — Mapa de Resultados não foi regenerado."
  fi

  # Fonte preferida da DRE Postos: o export da QUERY ÚNICA da Consulta SQL
  # (vendas + despesas título-a-título + taxas cartão + receitas, regime caixa).
  # Roda DEPOIS do Mapa pra sobrescrever {ano}.json/despesas_{ano}.json quando
  # o export existir; se não houver, não faz nada e o Mapa permanece.
  echo "----- [4d/7] etl_dre_postos_sql.py (DRE Postos — export Consulta SQL única) -----"
  if ! python3 etl_dre_postos_sql.py; then
    echo "[WARN] etl_dre_postos_sql.py falhou."
  fi

  # DRE Postos COMPETÊNCIA — parseia export da SQL de competência se existir.
  # Sem export: pula silenciosamente (Mapa Anual ETL [4c] já cobre os totalizadores).
  echo "----- [4d-comp/7] etl_dre_postos_competencia_sql.py (DRE Postos — competência) -----"
  if ! python3 etl_dre_postos_competencia_sql.py; then
    echo "[WARN] etl_dre_postos_competencia_sql.py falhou."
  fi

  # Indicadores Postos (cards do Dashboard DRE): METAS (METAS POSTO {ano}.xlsx) e
  # Perdas/Sobras = Variação de Estoque (export perdas.xls da Consulta SQL, litros).
  # Geram metas_postos_{ano}.json e perdas_postos_{ano}.json. Pulam se faltar fonte.
  echo "----- [4d-ind/7] etl_metas_postos.py + etl_perdas_postos.py (indicadores postos) -----"
  if ! python3 etl_metas_postos.py; then
    echo "[WARN] etl_metas_postos.py falhou — metas dos cards de postos mantêm valores anteriores."
  fi
  if ! python3 etl_perdas_postos.py; then
    echo "[WARN] etl_perdas_postos.py falhou — Variação de Estoque mantém valores anteriores."
  fi

  echo "----- [4e/7] etl_dfc_postos_sql.py (DFC Diário Postos — export DFC_Postos) -----"
  if ! python3 etl_dfc_postos_sql.py; then
    echo "[WARN] etl_dfc_postos_sql.py falhou."
  fi

  echo "----- [4f/7] etl_titulos_aberto.py (Títulos em Aberto Postos — TITABERTO*) -----"
  if ! python3 etl_titulos_aberto.py; then
    echo "[WARN] etl_titulos_aberto.py falhou."
  fi

  # Adapter: Adaptive → formato do Dashboard DFC (sobrescreve dados_fluxo_postos
  # da planilha, pro Dashboard DFC mostrar os números da Adaptive).
  echo "----- [4g/7] etl_dfc_postos_dashboard.py (Dashboard DFC postos ← Adaptive) -----"
  if ! python3 etl_dfc_postos_dashboard.py; then
    echo "[WARN] etl_dfc_postos_dashboard.py falhou — Dashboard DFC postos fica com a planilha."
  fi

  # Intercompany = Postos (já em Adaptive, passo acima) + Outras (LUMI, passo 3b).
  # Roda AQUI pra consolidar as duas fontes já atualizadas (+ saldos_oficiais união).
  echo "----- [4h/7] gera_fluxo_intercompany.py (Intercompany = Postos + Outras) -----"
  if ! python3 gera_fluxo_intercompany.py; then
    echo "[WARN] gera_fluxo_intercompany.py falhou — segmento Intercompany não atualizado."
  fi

  TA_OK=1
  echo "----- [5/7] gera_titulos_aberto.py (snapshot supermercados Oracle) -----"
  if ! python3 gera_titulos_aberto.py; then
    echo "[WARN] gera_titulos_aberto.py falhou — JSONs antigos serão re-publicados."
    TA_OK=0
  fi

  echo "----- [5b/7] gera_titulos_movimento.py (Movimento de Títulos: incluído×liquidado por mês → Firestore) -----"
  if ! python3 gera_titulos_movimento.py "$(date +%Y)"; then
    echo "[WARN] gera_titulos_movimento.py falhou — titulosMovimento mantém o anterior."
  fi

  echo "----- [5c/7] gera_endividamento.py (Endividamento Bancário: contratos planilha × pago Oracle/Firestore → Firestore) -----"
  if ! python3 gera_endividamento.py "$(date +%Y)"; then
    echo "[WARN] gera_endividamento.py falhou — endividamento mantém o anterior."
  fi

  echo "----- [5d/7] gera_extrato_supermercados.py (Extrato per-loja: AUTORIZADO DIRETORIA + SALDO PLANILHA → Firestore) -----"
  # Lê /mnt/exporta/FINANCEIRO/CONCILIAÇÃO/PLANILHA DE CONCILIAÇÃO/AAAA/MM - MES/
  # e popula extratoBancario/{AAAA-MM}.dias[DD].porLoja (uso pelo DFC Consolidado
  # com filtro de loja). Monta o share on-demand pq não está no fstab.
  if ! mountpoint -q /mnt/exporta; then
    mkdir -p /mnt/exporta
    mount -t drvfs '\\10.61.1.102\exporta' /mnt/exporta 2>&1 || echo "[WARN] mount /mnt/exporta falhou — extrato supermercado pulado."
  fi
  if mountpoint -q /mnt/exporta; then
    if ! python3 gera_extrato_supermercados.py "$(date +%Y)" "$(date +%-m)"; then
      echo "[WARN] gera_extrato_supermercados.py falhou — extratoBancario mantém o anterior."
    fi
  fi

  echo "----- [6/7] gera_supermercados_extras.py (taxas cartões + protege) -----"
  if ! python3 gera_supermercados_extras.py; then
    echo "[WARN] gera_supermercados_extras.py falhou."
  fi

  echo "----- [6b/8] gera_apuracao_contratos.py (apuração contratos de retorno) -----"
  if ! python3 gera_apuracao_contratos.py; then
    echo "[WARN] gera_apuracao_contratos.py falhou."
  fi

  echo "----- [6c/8] etl_energia.py (energia.json) -----"
  if ! python3 etl_energia.py; then
    echo "[WARN] etl_energia.py falhou — sobe o energia.json anterior."
  fi

  echo "----- [6c2/8] etl_metas_operacao_lojas.py (meta venda/loja → Metas Manuais operação) -----"
  if ! python3 etl_metas_operacao_lojas.py --write; then
    echo "[WARN] etl_metas_operacao_lojas.py falhou — metas de venda mantêm os valores anteriores."
  fi

  echo "----- [6c3/8] etl_metas_prevencao_bonus.py (Bônus Prevenção → Metas Manuais prevenção) -----"
  if ! python3 etl_metas_prevencao_bonus.py --write; then
    echo "[WARN] etl_metas_prevencao_bonus.py falhou — metas de prevenção mantêm os valores anteriores."
  fi

  echo "----- [6d/8] gera_bp.py (Balanço Patrimonial — recalcula só o mês corrente) -----"
  if ! python3 gera_bp.py; then
    echo "[WARN] gera_bp.py falhou — dados_bp mantém os valores anteriores."
  fi

  # Projeção DFC pros meses futuros (mês corrente + meses a frente com títulos
  # em aberto). Depende do upload_titulos_aberto (porDiaLinha) já ter rodado —
  # mas como o upload_titulos vai logo depois, na rodada de AMANHÃ esse script
  # vê o porDiaLinha de HOJE. Pra ele ver o porDiaLinha já gravado na MESMA
  # rodada, precisa rodar DEPOIS dos uploads. Plugado em [6e/8] = ANTES dos
  # uploads usando o porDiaLinha do dia anterior (suficiente — varia pouco).
  echo "----- [6e/8] gera_fluxocaixa_projetado.py (DFC futuro a partir de títulos em aberto) -----"
  if ! python3 gera_fluxocaixa_projetado.py; then
    echo "[WARN] gera_fluxocaixa_projetado.py falhou — DFC futuro fica com dados anteriores."
  fi

  echo "----- [7/8] uploads p/ Firestore do projeto-comercial -----"
  # projeto-comercial.onrender.com lê estas coleções do Firestore (projeto-686e2).
  # São snapshots: precisam ser reenviados a cada noite (os gera_*/etl_* acima
  # produzem os JSONs; estes uploads os empurram pro Firestore). Cada upload é
  # independente e guardado — falha de um não derruba os outros.
  for up in upload_titulos_aberto upload_fluxo_segmentos upload_auditorias upload_bp upload_energia; do
    echo "  · $up.py"
    if ! python3 "$up.py"; then echo "[WARN] $up.py falhou."; fi
  done

  echo "----- [8/8] firebase deploy --only hosting:controllsv -----"
  if [[ "$SEG_OK" == "1" || "$TA_OK" == "1" || "$OUTRAS_OK" == "1" ]]; then
    if ! firebase deploy --only hosting:controllsv --non-interactive 2>&1; then
      echo "[WARN] firebase deploy falhou. Próxima execução tenta de novo."
    fi
  else
    echo "[skip] Nada novo pra publicar."
  fi

  # ──────────────────────────────────────────────────────────────────────────
  # [9] (DESATIVADO) projeto-comercial · Prevenção — migrado pra .225
  # A Prevenção (5 extracts) agora roda na .225 enfileirada no fim do
  # cron-update.ps1 (etapa 13 lá), após o pipeline de Supervendas terminar.
  # Centralizar lá evita sobreposição com inv_rotativo do João + aproveita que
  # a máquina fica ligada 24/7 (boot trigger). Ver C:\projeto-margem\cron-update.ps1.
  echo "----- [9] (DESATIVADO) Prevenção migrada pra .225 -----"

  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ETL concluído (SM=$SM_OK SEG=$SEG_OK TA=$TA_OK OUTRAS=$OUTRAS_OK) ====="
} 2>&1 | tee -a "$LOG"
