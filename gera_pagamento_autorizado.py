#!/usr/bin/env python3
"""Pagamento Autorizado (postos e outras empresas) a partir da CONCILIAÇÃO.

Fonte: \\10.61.1.13\\cvl\\CONTAS A PAGAR\\PLANILHA DE CONCILIAÇÃO\\2026
       (montada em /mnt/cvl). Um par de arquivos por dia útil:
         • CONCILIAÇÃO BANCARIA - POSTOS.xlsx
         • CONCILIAÇÃO BANCARIA -TTR.xlsx
       Em CADA arquivo, considera-se SÓ a aba PAINEL (a aba Planilha2 = LOJAS
       = supermercados, que já têm seu próprio fluxo via PDF).

Cada PAINEL tem blocos por entidade. Em cada bloco, o valor logo abaixo do
rótulo "AUTORIZADO DIRETORIA" é o pagamento autorizado do dia para aquela
entidade. O rodapé "TOTAL DE OPERAÇÕES" é ignorado (é só o consolidado do
arquivo).

Classificação (separar postos vs outras — conforme pedido):
  • Entidades em OUTRAS_NAMES  → segmento "outras"  (FLUXO/LP/PEGUI/RETA/TARES + TTR)
  • Qualquer outra entidade    → segmento "postos"  (AUTO POSTO *, SETOR SUL, GM CENTRAL, ...)

Saída: grava bancos[DD]["pagamentoAutorizado"] (soma do segmento no dia) nos
JSONs mensais dados_fluxo_postos/AAAA-MM.json e dados_fluxo_outras/AAAA-MM.json,
e recalcula bancos[DD]["diferencasPagAutorizado"] = pagtoDia(dia) + pagamentoAutorizado.
NÃO mexe em totalBancos (não existe "SALDO PLANILHA" nas planilhas).
"""
from __future__ import annotations
import os
import re
import json
import warnings
import unicodedata
from collections import defaultdict

from openpyxl import load_workbook

warnings.filterwarnings("ignore")

# Fonte: mount de rede (/mnt/cvl). Abrir ~140 xlsx direto pela rede (9p/drvfs)
# falha de forma intermitente, então a árvore é COPIADA p/ um diretório local
# (um único `cp -r` é confiável) e lida do disco. Use --refresh p/ recopiar.
CONC_MOUNT = "/mnt/cvl/CONTAS A PAGAR/PLANILHA DE CONCILIAÇÃO/2026"
CONC_LOCAL = "/tmp/concil_2026"
ANO        = 2026  # a árvore copiada perde o nome "2026" da pasta-base
PROJ      = "/root/projeto_dre"
OUT_DIRS  = {"postos": os.path.join(PROJ, "dados_fluxo_postos"),
             "outras": os.path.join(PROJ, "dados_fluxo_outras")}

FILES = ["CONCILIAÇÃO BANCARIA - POSTOS.xlsx", "CONCILIAÇÃO BANCARIA -TTR.xlsx"]

# Agrupamentos que compõem o (−) Pagamentos (dia) de cada DFC Consolidado.
# Espelha as fontes de pagtoDia no dashboard (DFC_CONSOLIDADO_ESTRUTURA_*).
PAGTO_AGRUPS = {
    "postos": {"Fornecedores", "Pagto Entre Unidades", "Despesas"},
    "outras": {"Despesas"},
}

# Entidades que pertencem ao segmento "outras". Tudo que não estiver aqui é
# tratado como posto. (TTR vem do arquivo -TTR; é uma outra empresa.)
OUTRAS_NAMES = {"RETA", "COMERCIAL TARES", "TARES", "FLUXO", "LP", "PEGUI", "TTR"}

LABEL_AUTORIZADO = "AUTORIZADO DIRETORIA"
LABEL_TOTAL      = "TOTAL DE OPERACOES"   # normalizado (sem acento)


def _norm(s) -> str:
    """Normaliza texto p/ comparação: sem acento, sem espaço duplicado, upper.
    Remove data digitada no fim do cabeçalho (ex.: 'COMERCIAL TARES 16/03/2026')."""
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s).strip().upper()
    s = re.sub(r"\s+\d{1,2}/\d{1,2}/\d{2,4}$", "", s)  # tira data no fim
    return s


def classifica(entidade_norm: str) -> str:
    """outras se o nome for (ou começar com) uma das empresas de OUTRAS_NAMES."""
    for nome in OUTRAS_NAMES:
        if entidade_norm == nome or entidade_norm.startswith(nome + " "):
            return "outras"
    return "postos"


def parse_painel(path):
    """Retorna lista de (entidade_original, entidade_norm, valor_float) do PAINEL."""
    wb = load_workbook(path, data_only=True)
    if "PAINEL" not in wb.sheetnames:
        wb.close()
        return []
    ws = wb["PAINEL"]
    out = []
    for r in range(1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            if _norm(ws.cell(r, c).value) != _norm(LABEL_AUTORIZADO):
                continue
            entidade = ws.cell(r - 1, c).value if r > 1 else None  # nome do bloco
            ent_norm = _norm(entidade)
            if not ent_norm or ent_norm == LABEL_TOTAL:
                continue  # bloco vazio ou rodapé consolidado
            val = ws.cell(r + 1, c).value
            val = float(val) if isinstance(val, (int, float)) else 0.0
            out.append((entidade, ent_norm, val))
    wb.close()
    return out


def mes_de_pasta(nome: str):
    m = re.match(r"\s*(\d{1,2})", nome)
    return int(m.group(1)) if m else None


def dia_de_pasta(nome: str):
    m = re.match(r"\s*(\d{1,2})", nome)
    return int(m.group(1)) if m else None


def stage_local(refresh=False):
    """Garante uma cópia local da árvore da conciliação e devolve o caminho.
    Um único `cp -r` é confiável onde 139 aberturas via 9p não são."""
    import subprocess
    if refresh or not os.path.isdir(CONC_LOCAL):
        if not os.path.isdir(CONC_MOUNT):
            return None
        os.makedirs(CONC_LOCAL, exist_ok=True)
        print(f"Copiando conciliação p/ {CONC_LOCAL} …")
        subprocess.run(["cp", "-r", f"{CONC_MOUNT}/.", CONC_LOCAL + "/"], check=True)
    return CONC_LOCAL


def coleta(base):
    """Varre a conciliação (em `base`). Retorna:
       somas[(ano,mes,seg)][dia] = soma AUTORIZADO DIRETORIA
       audit[seg] = {entidade_norm: contagem}
    """
    ano = ANO
    somas = defaultdict(lambda: defaultdict(float))
    audit = defaultdict(lambda: defaultdict(int))
    dias_vistos = defaultdict(set)  # (ano,mes,seg) -> {dias com arquivo}

    for mes_pasta in sorted(os.listdir(base)):
        mes_dir = os.path.join(base, mes_pasta)
        if not os.path.isdir(mes_dir):
            continue
        mes = mes_de_pasta(mes_pasta)
        if not mes:
            continue
        for dia_pasta in sorted(os.listdir(mes_dir)):
            dia_dir = os.path.join(mes_dir, dia_pasta)
            if not os.path.isdir(dia_dir):
                continue
            dia = dia_de_pasta(dia_pasta)
            if not dia:
                continue
            for fname in FILES:
                fpath = os.path.join(dia_dir, fname)
                if not os.path.exists(fpath) or os.path.basename(fpath).startswith("~$"):
                    continue
                try:
                    blocos = parse_painel(fpath)
                except Exception as e:
                    print(f"  ! erro lendo {fpath}: {e}")
                    continue
                for _, ent_norm, val in blocos:
                    seg = classifica(ent_norm)
                    somas[(ano, mes, seg)][dia] += val
                    audit[seg][ent_norm] += 1
                    dias_vistos[(ano, mes, seg)].add(dia)
    return somas, audit, dias_vistos


def pagto_dia_map(doc, seg):
    """{dia_int: pagtoDia} a partir de porAgrupamento (= (−) Pagamentos do dia)."""
    dim = doc.get("dim", {})
    agr_names = dim.get("agrupamentos", [])
    alvo_idx = {i for i, n in enumerate(agr_names) if n in PAGTO_AGRUPS[seg]}
    out = defaultdict(float)
    for e in doc.get("porAgrupamento", []):
        if e.get("a") in alvo_idx:
            out[e["d"]] += e.get("v", 0.0)
    return out


def aplica(somas, dias_vistos, dry_run=False):
    relatorio = []
    chaves = sorted({(a, m, s) for (a, m, s) in somas})
    # agrupa por (ano,mes,seg) — mas precisamos de 1 doc por (seg, ano, mes)
    for (ano, mes, seg) in sorted(somas):
        path = os.path.join(OUT_DIRS[seg], f"{ano:04d}-{mes:02d}.json")
        if not os.path.exists(path):
            print(f"  · sem JSON p/ {seg} {ano}-{mes:02d} (pulado: {path})")
            continue
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        bancos = doc.get("bancos") or {}
        pagtos = pagto_dia_map(doc, seg)
        for dia, soma in sorted(somas[(ano, mes, seg)].items()):
            dd = f"{dia:02d}"
            antigo = bancos.get(dd, {}).get("pagamentoAutorizado")
            novo = round(soma, 2)
            ent = bancos.setdefault(dd, {})
            ent["pagamentoAutorizado"] = novo
            pagto = round(pagtos.get(dia, 0.0), 2)
            ent["diferencasPagAutorizado"] = round(pagto + novo, 2)
            relatorio.append((seg, ano, mes, dia, antigo, novo, pagto))
        doc["bancos"] = bancos
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
    return relatorio


def main():
    import sys
    dry = "--dry-run" in sys.argv
    refresh = "--refresh" in sys.argv
    base = stage_local(refresh=refresh)
    if not base or not os.path.isdir(base):
        print(f"ERRO: conciliação não acessível ({CONC_MOUNT})")
        print("      (no WSL: mount -t drvfs '\\\\10.61.1.13\\cvl' /mnt/cvl)")
        sys.exit(1)

    print(f"Lendo conciliação de {base} … {'(DRY-RUN)' if dry else ''}")
    somas, audit, dias_vistos = coleta(base)

    print("\n=== Classificação de entidades (auditoria) ===")
    for seg in ("postos", "outras"):
        nomes = sorted(audit[seg])
        print(f"  {seg.upper()} ({len(nomes)}): {', '.join(nomes)}")

    rel = aplica(somas, dias_vistos, dry_run=dry)

    print("\n=== Pagamento Autorizado por dia (antigo → novo) ===")
    cur = None
    for seg, ano, mes, dia, antigo, novo, pagto in rel:
        chave = (seg, ano, mes)
        if chave != cur:
            cur = chave
            print(f"\n[{seg.upper()} {ano}-{mes:02d}]  (pagtoDia | pagAutorizado | dif)")
        a = f"{antigo:,.2f}" if isinstance(antigo, (int, float)) else "—"
        print(f"   dia {dia:02d}:  pagto {pagto:>14,.2f}  |  {a:>14} → {novo:>14,.2f}  |  dif {pagto+novo:>12,.2f}")

    print(f"\n{'(dry-run, nada gravado)' if dry else 'JSONs atualizados.'}  Linhas: {len(rel)}")


if __name__ == "__main__":
    main()
