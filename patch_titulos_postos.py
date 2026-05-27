#!/usr/bin/env python3
"""
Patch: adiciona view 'Títulos em Aberto (Postos)' ao dashboard.html
e atualiza o service-worker.js (cache version).
Rode: python3 /root/projeto_dre/patch_titulos_postos.py
"""
import re, sys, shutil
from datetime import datetime

DASHBOARD = "/root/projeto_dre/dashboard.html"
SW        = "/root/projeto_dre/service-worker.js"

# ── Backup ─────────────────────────────────────────────────────────────────
ts = datetime.now().strftime("%Y%m%d%H%M%S")
shutil.copy(DASHBOARD, DASHBOARD + f".bak{ts}")
print(f"Backup: {DASHBOARD}.bak{ts}")

with open(DASHBOARD, encoding="utf-8") as f:
    html = f.read()

# ══════════════════════════════════════════════════════════════════════════════
# 1. MENU – adiciona item "Títulos em Aberto" após "DFC Diário (Adaptive)"
# ══════════════════════════════════════════════════════════════════════════════
MENU_ANCHOR = 'data-view="dfc-postos"'   # link do DFC Diário (Adaptive)
MENU_NEW = '''
          <a class="side-menu-item" data-view="titulos-postos" data-seg-only="postos">
            Títulos em Aberto
          </a>'''

if 'data-view="titulos-postos"' in html:
    print("⚠ Menu já existe — pulando item de menu.")
else:
    # Encontra o bloco do item DFC Postos e insere depois do fechamento </a>
    pat = r'(<a[^>]*data-view="dfc-postos"[^>]*>.*?</a>)'
    m = re.search(pat, html, re.DOTALL)
    if not m:
        print("ERRO: ancora de menu DFC Postos não encontrada.")
        sys.exit(1)
    html = html[:m.end()] + MENU_NEW + html[m.end():]
    print("✓ Item de menu adicionado.")

# ══════════════════════════════════════════════════════════════════════════════
# 2. VIEW HTML – insere antes do fechamento </main> ou antes da primeira view
#    Procura a view do DFC postos e insere logo depois dela
# ══════════════════════════════════════════════════════════════════════════════
VIEW_HTML = '''
  <!-- ═══════════════════ TÍTULOS EM ABERTO – POSTOS ═══════════════════ -->
  <section id="view-titulos-postos" class="view" data-seg-only="postos">
    <div class="cmp-shell">
      <div class="cmp-toolbar" style="flex-wrap:wrap;gap:8px;align-items:center;">
        <span style="font-weight:700;font-size:15px;">Títulos em Aberto · Postos</span>
        <span id="titpStatus" style="font-size:12px;color:#888;margin-left:8px;"></span>
        <div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
          <label style="font-size:12px;font-weight:600;">Tipo</label>
          <select id="titpTipo" style="font-size:13px;padding:3px 8px;border-radius:6px;border:1px solid #ccc;">
            <option value="PAGAR">A Pagar</option>
            <option value="RECEBER">A Receber</option>
          </select>
          <button id="titpRefresh" class="btn-icon" title="Recarregar">↻</button>
        </div>
      </div>
      <!-- Pills de posto -->
      <div id="titpPostos" style="display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px;border-bottom:1px solid #e8f0e8;"></div>
      <!-- Cards -->
      <div id="titpCards" class="dre-cards" style="padding:12px 12px 4px;"></div>
      <!-- Tabela -->
      <div style="overflow-x:auto;padding:0 4px 12px;">
        <table class="dre-table" id="titpTable" style="width:100%;min-width:700px;"></table>
      </div>
    </div>
    <!-- Modal detalhe títulos -->
    <div id="titpModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;align-items:center;justify-content:center;">
      <div style="background:#fff;border-radius:12px;max-width:900px;width:95vw;max-height:88vh;display:flex;flex-direction:column;overflow:hidden;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #e0e0e0;">
          <span id="titpModalTitle" style="font-weight:700;font-size:14px;"></span>
          <button id="titpModalClose" style="background:none;border:none;font-size:20px;cursor:pointer;line-height:1;">×</button>
        </div>
        <div style="overflow-y:auto;padding:12px 16px;">
          <table class="dre-table" id="titpModalTable" style="width:100%;"></table>
        </div>
      </div>
    </div>
  </section>'''

if 'id="view-titulos-postos"' in html:
    print("⚠ View HTML já existe — pulando.")
else:
    # Insere antes de </main> ou depois da view DFC postos
    anchor = 'id="view-dfc-postos"'
    idx = html.find(anchor)
    if idx == -1:
        # fallback: antes de </main>
        idx = html.rfind('</main>')
        if idx == -1:
            print("ERRO: âncora de view não encontrada.")
            sys.exit(1)
        html = html[:idx] + VIEW_HTML + "\n" + html[idx:]
    else:
        # Encontra o fechamento </section> dessa view
        sec_end = html.find('</section>', idx)
        if sec_end == -1:
            print("ERRO: </section> do DFC postos não encontrado.")
            sys.exit(1)
        ins = sec_end + len('</section>')
        html = html[:ins] + "\n" + VIEW_HTML + html[ins:]
    print("✓ View HTML inserida.")

# ══════════════════════════════════════════════════════════════════════════════
# 3. CSS – adiciona estilos de situação para a tabela de títulos
# ══════════════════════════════════════════════════════════════════════════════
CSS_NEW = """
  /* Títulos em Aberto – Postos */
  .titp-vencido    { color: #c0392b; font-weight: 700; }
  .titp-hoje       { color: #e67e22; font-weight: 700; }
  .titp-avencer    { color: #27ae60; font-weight: 600; }
  #titpTable tbody tr.titp-row-vencido { background: #fff5f5; }
  #titpTable tbody tr.titp-row-hoje    { background: #fff8f0; }
  #titpTable tbody tr.titp-nat td.label { font-weight:700; padding-left:8px; background:#f4f8f4; cursor:pointer; }
  #titpTable tbody tr.titp-det { display:none; }
  #titpTable tbody tr.titp-det td { padding-left:28px; font-size:11.5px; color:#444; }
"""
if 'titp-vencido' not in html:
    # Insere antes de </style> principal (primeira ocorrência)
    idx = html.find('</style>')
    if idx != -1:
        html = html[:idx] + CSS_NEW + html[idx:]
        print("✓ CSS adicionado.")
    else:
        print("⚠ </style> não encontrado — CSS não adicionado.")
else:
    print("⚠ CSS já existe — pulando.")

# ══════════════════════════════════════════════════════════════════════════════
# 4. JS – adiciona funções renderTitulosPostos antes de </script> final
# ══════════════════════════════════════════════════════════════════════════════
JS_NEW = r"""
// ═══════════════════ TÍTULOS EM ABERTO – POSTOS ═══════════════════
(function(){
  const BASE = "/dados_dre_postos_adaptive/";
  let _titpData = null, _titpAno = null, _titpPosto = null, _titpTipo = "PAGAR";

  const fmt = v => v == null ? "—" : "R$ " + Number(v).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});
  const fmtN = v => v == null ? "—" : Number(v).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});

  async function _titpLoad(ano){
    if(_titpAno === ano && _titpData) return _titpData;
    const url = BASE + "titulos_aberto_" + ano + ".json?z=" + Date.now();
    const r = await fetch(url);
    if(!r.ok) throw new Error("HTTP " + r.status);
    _titpData = await r.json();
    _titpAno  = ano;
    return _titpData;
  }

  function _titpRenderPills(postos, posto){
    const el = document.getElementById("titpPostos"); if(!el) return;
    el.innerHTML = "";
    postos.forEach(p => {
      const b = document.createElement("button");
      b.className = "drepostos-pill" + (p === posto ? " active" : "");
      b.textContent = p;
      b.onclick = () => { _titpPosto = p; renderTitulosPostos(); };
      el.appendChild(b);
    });
  }

  function _titpRenderCards(dados){
    const el = document.getElementById("titpCards"); if(!el) return;
    const d = dados || {};
    const cards = [
      {label:"Total em Aberto", val: fmt(d.total),      color:"#1a6b3c"},
      {label:"Vencido",         val: fmt(d.vencido),    color:"#c0392b"},
      {label:"Vence Hoje",      val: fmt(d.vence_hoje), color:"#e67e22"},
      {label:"A Vencer",        val: fmt(d.a_vencer),   color:"#27ae60"},
      {label:"Qtd Títulos",     val: (d.qtd||0).toLocaleString("pt-BR"), color:"#2c6e9e"},
    ];
    el.innerHTML = cards.map(c =>
      `<div class="dre-card"><div class="dre-card-label">${c.label}</div>
       <div class="dre-card-value" style="color:${c.color}">${c.val}</div></div>`
    ).join("");
  }

  function _titpRenderTable(dados){
    const tbl = document.getElementById("titpTable"); if(!tbl) return;
    const resumo = (dados && dados.resumo) || {};
    const titulos = (dados && dados.titulos) || [];

    // Agrupa títulos por natureza
    const byNat = {};
    titulos.forEach(t => {
      if(!byNat[t.natureza]) byNat[t.natureza] = [];
      byNat[t.natureza].push(t);
    });

    const HEAD = ["Natureza / Pessoa","Emissão","Vencimento","Valor","Dias","Situação"];
    let rows = `<thead><tr>${HEAD.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>`;

    const nats = Object.keys(resumo).sort((a,b) => resumo[b].total - resumo[a].total);
    nats.forEach(nat => {
      const r = resumo[nat];
      const uid = "nat_" + Math.random().toString(36).slice(2);
      rows += `<tr class="titp-nat" onclick="_titpToggleNat('${uid}')">
        <td class="label" colspan="5">▶ ${nat}</td>
        <td style="text-align:right;font-weight:700;">${fmtN(r.total)}</td>
      </tr>`;
      (byNat[nat]||[]).forEach(t => {
        const sc = t.situacao==="VENCIDO"?"titp-vencido":t.situacao==="VENCE HOJE"?"titp-hoje":"titp-avencer";
        const rc = t.situacao==="VENCIDO"?"titp-row-vencido":t.situacao==="VENCE HOJE"?"titp-row-hoje":"";
        rows += `<tr class="titp-det ${uid} ${rc}">
          <td style="padding-left:28px;">${t.pessoa}</td>
          <td>${t.dt_emissao||"—"}</td>
          <td>${t.dt_venc||"—"}</td>
          <td style="text-align:right;">${fmtN(t.vl_aberto)}</td>
          <td style="text-align:center;">${t.dias>0?t.dias:"—"}</td>
          <td class="${sc}">${t.situacao}</td>
        </tr>`;
      });
    });
    rows += "</tbody>";
    tbl.innerHTML = rows;
  }

  window._titpToggleNat = function(uid){
    document.querySelectorAll(".titp-det." + uid).forEach(tr => {
      tr.style.display = tr.style.display === "table-row" ? "none" : "table-row";
    });
    // Troca ▶/▼
    const nat = document.querySelector(".titp-nat[onclick*='" + uid + "'] td");
    if(nat) nat.textContent = nat.textContent.replace(/^[▶▼] /, t => t.includes("▶") ? "▼ " : "▶ ");
  };

  window.renderTitulosPostos = async function(){
    const statusEl = document.getElementById("titpStatus");
    try {
      if(statusEl) statusEl.textContent = "carregando…";
      const ano = (document.getElementById("titpAno")||{}).value ||
                  new Date().getFullYear().toString();
      const d = await _titpLoad(ano);
      const postos = d.postos || [];
      if(!_titpPosto || !postos.includes(_titpPosto)) _titpPosto = postos[0];
      const tipo = (document.getElementById("titpTipo")||{}).value || "PAGAR";
      _titpTipo = tipo;

      _titpRenderPills(postos, _titpPosto);
      const dadosPosto = (d.dados[tipo]||{})[_titpPosto] || {};
      _titpRenderCards(dadosPosto);
      _titpRenderTable(dadosPosto);

      if(statusEl) statusEl.textContent = "Atualizado: " + (d.gerado_em||"");
    } catch(e){
      if(statusEl) statusEl.textContent = "Erro: " + e.message;
      console.error("renderTitulosPostos:", e);
    }
  };

  // Wiring ao tornar visível
  document.addEventListener("viewChanged", e => {
    if(e.detail && e.detail.view === "titulos-postos") renderTitulosPostos();
  });

  // Bind select tipo
  document.addEventListener("DOMContentLoaded", () => {
    const sel = document.getElementById("titpTipo");
    if(sel) sel.addEventListener("change", renderTitulosPostos);
    const ref = document.getElementById("titpRefresh");
    if(ref) ref.addEventListener("click", () => { _titpData=null; renderTitulosPostos(); });
    const mc = document.getElementById("titpModalClose");
    if(mc) mc.addEventListener("click", () => {
      const m = document.getElementById("titpModal");
      if(m) m.style.display = "none";
    });
  });
})();
"""

if 'renderTitulosPostos' in html:
    print("⚠ JS já existe — pulando.")
else:
    # Insere antes do último </script>
    idx = html.rfind('</script>')
    if idx == -1:
        print("ERRO: </script> não encontrado.")
        sys.exit(1)
    html = html[:idx] + JS_NEW + "\n" + html[idx:]
    print("✓ JS adicionado.")

# ══════════════════════════════════════════════════════════════════════════════
# 5. renderAll dispatch – adiciona caso 'titulos-postos'
# ══════════════════════════════════════════════════════════════════════════════
DISPATCH_ANCHOR = "case 'dfc-postos':"
DISPATCH_NEW    = "\n      case 'titulos-postos': renderTitulosPostos(); break;"

if "'titulos-postos'" in html:
    print("⚠ Dispatch já existe — pulando.")
else:
    idx = html.find(DISPATCH_ANCHOR)
    if idx == -1:
        print("⚠ Dispatch anchor não encontrado — dispatch não adicionado.")
    else:
        end = html.find('\n', idx)
        html = html[:end] + DISPATCH_NEW + html[end:]
        print("✓ Dispatch adicionado.")

# ══════════════════════════════════════════════════════════════════════════════
# 6. Salva dashboard.html
# ══════════════════════════════════════════════════════════════════════════════
with open(DASHBOARD, "w", encoding="utf-8") as f:
    f.write(html)
print(f"✓ {DASHBOARD} salvo ({len(html)//1024} KB)")

# ══════════════════════════════════════════════════════════════════════════════
# 7. Bump cache version no service-worker.js
# ══════════════════════════════════════════════════════════════════════════════
try:
    with open(SW, encoding="utf-8") as f:
        sw = f.read()
    m = re.search(r'(CACHE_VERSION\s*=\s*["\'])v(\d+)(["\'])', sw)
    if m:
        old_v = int(m.group(2))
        new_v = old_v + 1
        sw = sw[:m.start()] + f"{m.group(1)}v{new_v}{m.group(3)}" + sw[m.end():]
        with open(SW, "w", encoding="utf-8") as f:
            f.write(sw)
        print(f"✓ service-worker.js: v{old_v} → v{new_v}")
    else:
        print("⚠ CACHE_VERSION não encontrado no service-worker.js")
except Exception as e:
    print(f"⚠ service-worker.js: {e}")

print("\n✅ Patch concluído. Agora rode:")
print("   cd /root/projeto_dre && firebase deploy --only hosting:controllsv --non-interactive")
