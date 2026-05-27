#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restaura dados_fluxo_{postos,outras}/saldos_oficiais.json a partir do
arquivo-fonte saldos_oficiais_master.json (raiz do projeto). Idempotente.

Por que existe: os ETLs (etl_dfc_outras_lumi, etl_fluxo_segmentos, etc.)
regeneram os diretórios dados_fluxo_* e podem apagar saldos_oficiais.json
(arquivo manual com o saldo oficial diário usado pela DFC pra ancorar).

Roda no início do run_etl.sh (passo 0.5) e antes do gera_fluxo_intercompany
(que une postos+outras pra criar o saldos_oficiais do intercompany).
"""
import os, json, sys

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(BASE, "saldos_oficiais_master.json")


def main():
    if not os.path.exists(MASTER):
        print(f"  · (sem {MASTER} — nada a restaurar)")
        return
    master = json.load(open(MASTER, encoding="utf-8"))
    n = 0
    for seg in ("postos", "outras"):
        bloco = master.get(seg)
        if not bloco:
            continue
        dir_seg = os.path.join(BASE, f"dados_fluxo_{seg}")
        if not os.path.isdir(dir_seg):
            os.makedirs(dir_seg, exist_ok=True)
        out = os.path.join(dir_seg, "saldos_oficiais.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(bloco, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {out} ({len(bloco)} data(s))")
        n += 1
    print(f"  ✓ saldos_oficiais restaurados em {n} segmento(s)")


if __name__ == "__main__":
    main()
