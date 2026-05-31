"""Balanço Patrimonial dos POSTOS — versão inicial.

Gera dados_bp_postos/{ano}.json com a MESMA estrutura do BP supermercados
(dados_bp/{ano}.json), pra dashboard.html reutilizar as 4 views (Dashboard
BP, Tabela, Análise Horizontal, Indicadores) trocando só o segmento.

Fontes disponíveis HOJE (sem acesso direto ao Adaptive PG):
  • dados_fluxo_postos/{ano}-{mes:02d}.json
      saldoFinalDiario[-1].v  →  linha 'Bancos' do mês m
  • dados_dre_postos_adaptive/{ano}.json
      dados[POSTO].dre  label '(=) Lucro Líquido' .meses[mes-1]
      somado pelos 11 postos = Resultado do Período + Lucro Acumulado
  • dados_dre_postos_adaptive/titulos_aberto_{ano}.json
      dados[CODIGO].PAGAR.porNatureza   → Fornecedores / Frete / Adiantamentos
      dados[CODIGO].RECEBER.porNatureza → Cartões / Vendas a Prazo
      (POSIÇÃO ATUAL — sem histórico por mês; só popula o mês corrente)

Linhas pendentes (preservadas como 0/manuais até termos mais fontes):
  • Caixa (Tesouraria) — postos não tem tesouraria separada
  • Estoques (combustível: medicao_tanque_lmc, não wired aqui)
  • Salários a Pagar, Tributos, Impostos a Recolher
  • Empréstimos CP/LP, Parcelamentos
  • Capital Social

Convenção: Passivos NEGATIVOS (igual ao BP supermercados).
"""
from __future__ import annotations
import os, json, datetime as dt

ROOT = "/root/projeto_dre"
OUT_DIR = os.path.join(ROOT, "dados_bp_postos")
os.makedirs(OUT_DIR, exist_ok=True)


# Estrutura fixa do BP postos (mesmas chaves de coluna do BP supermercados).
LINHAS_TEMPLATE = [
    # ATIVO
    {"nome": "Ativo Circulante",                         "lado": "ATIVO",    "grupo": "Ativo Circulante",     "ordem": 10, "tipo": "section", "fonte": "calc"},
    {"nome": "Caixa (Tesouraria)",                       "lado": "ATIVO",    "grupo": "Ativo Circulante",     "agrupamento": "Disponibilidades", "ordem": 20, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Bancos",                                   "lado": "ATIVO",    "grupo": "Ativo Circulante",     "agrupamento": "Disponibilidades", "ordem": 21, "tipo": "item",    "fonte": "fluxo:saldoFinalDiario"},
    {"nome": "Cartões de Crédito a Receber",             "lado": "ATIVO",    "grupo": "Ativo Circulante",     "agrupamento": "Contas a Receber", "ordem": 31, "tipo": "item",    "fonte": "titulos_aberto:Crédito"},
    {"nome": "Cartões de Débito a Receber",              "lado": "ATIVO",    "grupo": "Ativo Circulante",     "agrupamento": "Contas a Receber", "ordem": 32, "tipo": "item",    "fonte": "titulos_aberto:Débito"},
    {"nome": "Vendas a Prazo a Receber",                 "lado": "ATIVO",    "grupo": "Ativo Circulante",     "agrupamento": "Contas a Receber", "ordem": 33, "tipo": "item",    "fonte": "titulos_aberto:Venda a Prazo"},
    {"nome": "Estoques",                                 "lado": "ATIVO",    "grupo": "Ativo Circulante",     "agrupamento": "Estoques",         "ordem": 40, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Ativo Não Circulante",                     "lado": "ATIVO",    "grupo": "Ativo Não Circulante", "ordem": 50, "tipo": "section", "fonte": "calc"},
    {"nome": "Imobilizado",                              "lado": "ATIVO",    "grupo": "Ativo Não Circulante", "agrupamento": "Imobilizado",      "ordem": 60, "tipo": "item",    "fonte": "pendente"},
    # PASSIVO + PL
    {"nome": "Passivo Circulante",                       "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "ordem": 100, "tipo": "section", "fonte": "calc"},
    {"nome": "Fornecedores de Mercadorias",              "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Fornecedores",     "ordem": 110, "tipo": "item",    "fonte": "titulos_aberto:Compra a Prazo"},
    {"nome": "Fornecedores Diversos",                    "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Fornecedores",     "ordem": 111, "tipo": "item",    "fonte": "titulos_aberto:Despesas"},
    {"nome": "Fretes a Pagar",                           "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Fornecedores",     "ordem": 112, "tipo": "item",    "fonte": "titulos_aberto:Conhecimento de Frete"},
    {"nome": "Adiantamentos de Clientes",                "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Outras Obrigações","ordem": 120, "tipo": "item",    "fonte": "titulos_aberto:Adiantamento de Clientes"},
    {"nome": "Salários a Pagar",                         "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Obrigações Trabalhistas", "ordem": 130, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Empréstimos a Pagar",                      "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Empréstimos",      "ordem": 140, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Tributos a Recolher",                      "lado": "PASSIVO",  "grupo": "Passivo Circulante",   "agrupamento": "Tributos",         "ordem": 150, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Passivo Não Circulante",                   "lado": "PASSIVO",  "grupo": "Passivo Não Circulante","ordem": 200, "tipo": "section", "fonte": "calc"},
    {"nome": "Empréstimos a Pagar - Longo Prazo",        "lado": "PASSIVO",  "grupo": "Passivo Não Circulante","agrupamento": "Empréstimos",     "ordem": 210, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Patrimônio Líquido",                       "lado": "PASSIVO",  "grupo": "Patrimônio Líquido",   "ordem": 300, "tipo": "section", "fonte": "calc"},
    {"nome": "Capital Social",                           "lado": "PASSIVO",  "grupo": "Patrimônio Líquido",   "agrupamento": "Capital",          "ordem": 310, "tipo": "item",    "fonte": "pendente"},
    {"nome": "Resultado do Período",                     "lado": "PASSIVO",  "grupo": "Patrimônio Líquido",   "agrupamento": "Resultado",        "ordem": 320, "tipo": "item",    "fonte": "dre:lucro_mes"},
    {"nome": "Lucro/Prejuízo Acumulado",                 "lado": "PASSIVO",  "grupo": "Patrimônio Líquido",   "agrupamento": "Resultado",        "ordem": 321, "tipo": "item",    "fonte": "dre:lucro_acum"},
]


def saldo_bancario_do_mes(ano: int, mes: int) -> int:
    """Lê dados_fluxo_postos/{ano}-{mes:02d}.json → último saldoFinalDiario.v não-nulo."""
    path = f"{ROOT}/dados_fluxo_postos/{ano:04d}-{mes:02d}.json"
    if not os.path.exists(path):
        return 0
    try:
        doc = json.load(open(path))
    except Exception:
        return 0
    sfd = doc.get("saldoFinalDiario") or []
    if not sfd: return 0
    # pega último dia com valor != 0 (no início do mês pode estar 0 enquanto não roda o ETL diário)
    vals = [(x.get("d"), x.get("v")) for x in sfd if isinstance(x, dict) and x.get("v") is not None]
    if not vals: return 0
    vals.sort(key=lambda t: t[0] if t[0] is not None else -1)
    return int(round(float(vals[-1][1])))


def lucro_postos_por_mes(ano: int) -> dict[int, int]:
    """Soma o (=) Lucro Líquido dos 11 postos por mês (regime caixa do Adaptive)."""
    path = f"{ROOT}/dados_dre_postos_adaptive/{ano:04d}.json"
    if not os.path.exists(path): return {}
    doc = json.load(open(path))
    dados = doc.get("dados") or {}
    out: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    for posto_nome, posto in dados.items():
        dre = posto.get("dre") or []
        for l in dre:
            if l.get("label", "").strip() != "(=) Lucro Líquido":
                continue
            meses = l.get("meses") or []
            for i, v in enumerate(meses):
                out[i + 1] += float(v or 0)
    return {m: int(round(v)) for m, v in out.items()}


def titulos_aberto_por_natureza(ano: int) -> tuple[dict[str, int], dict[str, int]]:
    """Retorna (RECEBER, PAGAR) = {natureza: total_int}. Posição atual."""
    path = f"{ROOT}/dados_dre_postos_adaptive/titulos_aberto_{ano:04d}.json"
    if not os.path.exists(path): return {}, {}
    doc = json.load(open(path))
    dados = doc.get("dados") or {}
    rec: dict[str, float] = {}
    pag: dict[str, float] = {}
    for codigo, posto in dados.items():
        for lado_key, sink in (("RECEBER", rec), ("PAGAR", pag)):
            bloco = posto.get(lado_key) or {}
            pn = bloco.get("porNatureza") or {}
            for nat, info in pn.items():
                sink[nat] = sink.get(nat, 0.0) + float((info or {}).get("total", 0))
    return ({k: int(round(v)) for k, v in rec.items()},
            {k: int(round(v)) for k, v in pag.items()})


def carrega_existente(path: str) -> dict:
    if os.path.exists(path):
        try: return json.load(open(path))
        except Exception: pass
    return {}


def main():
    hoje = dt.date.today()
    ano = hoje.year
    mes_atual = hoje.month
    out_path = f"{OUT_DIR}/{ano:04d}.json"

    # Preserva 'valores' já gravados (override manual no Firestore/dashboard futuro
    # pode persistir aqui — não sobrescreve se NÃO temos dado novo pra a linha).
    existente = carrega_existente(out_path)
    valores: dict[str, int] = dict(existente.get("valores") or {})

    # 1) Bancos por mês (todos os meses até o atual)
    for m in range(1, mes_atual + 1):
        v = saldo_bancario_do_mes(ano, m)
        if v:
            valores[f"Bancos__{m}"] = v

    # 2) Lucro do Período + Acumulado (todos os meses do ano)
    lucros = lucro_postos_por_mes(ano)
    acc = 0
    for m in range(1, 13):
        # passivo (PL) → positivo aqui (lucro = aumenta PL; perda = negativo)
        valores[f"Resultado do Período__{m}"] = int(lucros.get(m, 0))
        valores[f"Lucro/Prejuízo Acumulado__{m}"] = int(acc)
        acc += int(lucros.get(m, 0))

    # 3) Títulos em aberto (POSIÇÃO ATUAL → grava só no mês corrente)
    rec, pag = titulos_aberto_por_natureza(ano)
    NAT_RECEBER = {
        "Crédito":       "Cartões de Crédito a Receber",
        "Débito":        "Cartões de Débito a Receber",
        "Venda a Prazo": "Vendas a Prazo a Receber",
    }
    NAT_PAGAR = {
        "Compra a Prazo":           "Fornecedores de Mercadorias",
        "Despesas":                 "Fornecedores Diversos",
        "Conhecimento de Frete":    "Fretes a Pagar",
        "Adiantamento de Clientes": "Adiantamentos de Clientes",
    }
    for nat, linha in NAT_RECEBER.items():
        if nat in rec:
            valores[f"{linha}__{mes_atual}"] = rec[nat]  # ATIVO: positivo
    for nat, linha in NAT_PAGAR.items():
        if nat in pag:
            valores[f"{linha}__{mes_atual}"] = -pag[nat]  # PASSIVO: negativo

    # 4) Preenche zeros pras linhas pendentes do mês atual (se ainda não tem)
    for l in LINHAS_TEMPLATE:
        if l["tipo"] != "item": continue
        key = f"{l['nome']}__{mes_atual}"
        if key not in valores:
            valores[key] = 0

    doc = {
        "ano": ano,
        "geradoEm": dt.datetime.now().isoformat(timespec="seconds"),
        "v": 1,
        "mesAtual": mes_atual,
        "segmento": "postos",
        "comentario": (
            "BP Postos — versão inicial. Alimentado pelos JSONs locais "
            "(dados_fluxo_postos, dados_dre_postos_adaptive). Linhas marcadas "
            "como 'pendente' (Caixa, Estoques, Salários, Tributos, Empréstimos, "
            "Capital Social) ficam em 0 até termos fonte direta no Adaptive PG."
        ),
        "meses": list(range(1, 13)),
        "linhas": LINHAS_TEMPLATE,
        "valores": valores,
    }

    json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # auditoria
    a = sum(valores.get(f"{l['nome']}__{mes_atual}", 0)
            for l in LINHAS_TEMPLATE if l["tipo"] == "item" and l["lado"] == "ATIVO")
    p = sum(valores.get(f"{l['nome']}__{mes_atual}", 0)
            for l in LINHAS_TEMPLATE if l["tipo"] == "item" and l["lado"] == "PASSIVO")
    print(f"BP Postos mês {ano}-{mes_atual:02d}: Ativo={a:,} | Passivo+PL={p:,} | dif={a+p:,}")
    print(f"OK — {out_path} atualizado.")


if __name__ == "__main__":
    main()
