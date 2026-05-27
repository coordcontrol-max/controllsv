"""Classificador: transforma rawOracle (resultado das queries Consinco) em
fatosClassificados — formato (ANO, MÊS, NROEMPRESA, LINHA, VALOR) que alimenta
o engine de rateio.

Implementação por ondas (do mais simples pro mais complexo):

ONDA 1 — queries cuja saída já tem LINHA implícita ou explícita:
  BASE4  (despesas)              → query devolve g.DESCRICAO = LINHA
  BASE9  (quebra/sobra)          → 2 LINHAs fixas via CASE no SQL
  BASE12 (juros recebidos)       → LINHA "Juros e Multas Recebidos"
  BASE14 (descontos obtidos)     → LINHA "Descontos Obtidos"
  BASE15 (material expediente op)→ LINHA "Material de Expediente da Operacao"

ONDA 2 — queries com lookup por código (CODOPERACAO, CODESPECIE):
  BASE5  (operação financeira)   → lookup em meta/operacoes pelo CODOPERACAO
  BASE6  (despesas c/ vendas)    → lookup em meta/especiesDireitos pelo CODESPECIE

ONDA 3 — queries com cálculos derivados:
  BASE1  (vendas) — combina venda_atual+venda_acum, faz CMV = VENDA - MARGEM - VERBA
  BASE10 (compra func)  → composição
  BASE13 (juros emp + pago) → combinação de duas queries
  BASE7+11 (transf consumo + compra transf) → mesmas categorias de materiais
  BASE2 (consumo interno) → categorização de produtos/famílias
  BASE3 (receitas comerciais) → CODESPECIE → categoria de acordo
  BASE8 (folha) → query separada (não está nas 18 atuais)
"""

from __future__ import annotations
from typing import Any
import datetime as dt


# ─── ONDA 1 ────────────────────────────────────────────────────────────────

def _to_int(v) -> int | None:
    """Converte string/número pra int. Retorna None se não conseguir."""
    if v is None: return None
    try: return int(v)
    except (ValueError, TypeError): return None


def _val(row: dict, *names) -> Any:
    """Tenta vários nomes de coluna (Oracle pode devolver em diferentes cases)."""
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
        if n.upper() in row and row[n.upper()] is not None:
            return row[n.upper()]
        if n.lower() in row and row[n.lower()] is not None:
            return row[n.lower()]
    return None


# Mapa de correção: nomes de LINHA que vêm do banco (g.DESCRICAO) com erro de
# digitação ou divergência do plano de contas atual em meta/linhas. Normaliza
# pra LINHA cadastrada antes de agregar.
DESPESAS_LINHA_NORMALIZADA = {
    "FGTS Multa Recisoria ADM":       "FGTS Multa Rescisória ADM",
    "FGTS Multa Recisoria Comercial": "FGTS Multa Rescisória Comercial",
    # "FGTS Multa Recisoria Operacao" já casa com a versão sem acento em
    # meta/linhas, então não normaliza.
}

# Espécies/LINHAs a descartar do BASE4 (decisão do usuário, não vão pra DRE).
DESPESAS_LINHA_IGNORAR = {
    "Despesas Pagas na Tesouraria  (TESCPG)",   # codespecie TESCPG
    # Material de Expediente da Operação: a conta contábil dos títulos (BASE4)
    # superestima ~25x (decisão do usuário 2026-05). A fonte correta dessa linha
    # é a NF de despesa CODHISTORICO=2119 (slug material_expediente_op / BASE15).
    # Os títulos da conta contábil saem da DRE.
    "Material de Expediente da Operaçao",
    "Material de Expediente da Operação",
}


def classify_despesas(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """BASE4 — Despesas.

    A query "despesas" devolve g.DESCRICAO direto (= LINHA do plano de contas).
    Retorna 2 listas:
      - fatos: agregado por (ano, mes, nroempresa, linha) com soma do VALOR_LIQUIDO
      - detalhes: 1 registro por nota fiscal (com NROTITULO, FORNECEDOR, OBSERVACAO)
    """
    detalhes = []
    agregado_map: dict[tuple, float] = {}

    for r in rows:
        ano = _to_int(_val(r, "ANO", "Ano"))
        mes = _to_int(_val(r, "MÊS", "MES"))
        nroempresa = _to_int(_val(r, "NROEMPRESA"))
        linha = _val(r, "DESCRICAO", "DESC_PLANO")
        valor = _val(r, "VALOR_LIQUIDO", "VLRNOMINAL", "VLROPERACAO")
        if ano is None or mes is None or linha is None or valor is None:
            continue
        # Aluguel de Imoveis: jan-abr/2026 ficou FECHADO no valor do contrato
        # (provisão, slug provisao_aluguel) — os títulos do ERP saem do valor da
        # DRE (mas seguem no rawOracle p/ detalhamento). De maio/2026 em diante o
        # título do sistema ENTRA normalmente; o engine só provisiona o contrato
        # nas lojas sem lançamento (decisão do usuário 2026-05-24).
        if linha == "Aluguel de Imoveis" and ano == 2026 and mes <= 4:
            continue
        if linha in DESPESAS_LINHA_IGNORAR:
            continue
        linha = DESPESAS_LINHA_NORMALIZADA.get(linha, linha)
        valor = float(valor) * -1   # despesas são saída → negativo no DRE

        # Detalhe (drill-down)
        detalhes.append({
            "ano": ano, "mes": mes, "nroempresa": nroempresa,
            "linha": linha, "valor": valor,
            "nrotitulo":   _val(r, "NROTITULO"),
            "dta_contabil": _val(r, "DTA_CONTABIL", "Dta_Contabil"),
            "dta_vencimento": _val(r, "DTA_VENCIMENTO", "Dta_Vencimento"),
            "fornecedor":   _val(r, "NOMERAZAO", "FORNECEDOR"),
            "observacao":   _val(r, "OBSERVACAO", "OBS"),
            "codespecie":   _val(r, "CODESPECIE"),
            "usuario":      _val(r, "USUARIO"),
        })

        # Agregado
        k = (ano, mes, nroempresa, linha)
        agregado_map[k] = agregado_map.get(k, 0.0) + valor

    fatos = [
        {"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
        for (a, m, n, l), v in agregado_map.items()
    ]
    return fatos, detalhes


def classify_quebra_sobra(rows: list[dict]) -> list[dict]:
    """BASE9 — Quebra/Sobra. SQL já devolve coluna ATRIBUTO com '(-) Quebra Caixa' ou 'Sobra de Caixa PDV'."""
    out = {}
    for r in rows:
        ano = _to_int(_val(r, "ANO"))
        mes = _to_int(_val(r, "MES", "MÊS"))
        nroempresa = _to_int(_val(r, "NROEMPRESA"))
        linha = _val(r, "ATRIBUTO")
        valor = _val(r, "VALOR")
        if ano is None or linha is None or valor is None:
            continue
        k = (ano, mes, nroempresa, linha)
        out[k] = out.get(k, 0.0) + float(valor)
    return [{"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
            for (a, m, n, l), v in out.items()]


def _ano_mes_de_data(r: dict, *colunas) -> tuple[int | None, int | None]:
    """Extrai (ano, mes) de uma coluna de data ISO. Tenta cada coluna em ordem."""
    for c in colunas:
        v = _val(r, c)
        if not v: continue
        if isinstance(v, str):
            try:
                d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
                return d.year, d.month
            except Exception:
                continue
        if isinstance(v, (dt.datetime, dt.date)):
            return v.year, v.month
    return None, None


def _classify_simple(rows: list[dict], linha_fixa: str, valor_col: str | tuple, sign: int = 1,
                     data_cols: tuple = ("DTACONTABILIZA", "DTAOPERACAO", "DTAENTRADA")) -> list[dict]:
    """Classificador genérico pra BASEs com 1 LINHA fixa.

    Soma o `valor_col` por (ANO, MES, NROEMPRESA), atribui à LINHA fixa.
    Pra extrair ANO/MES, primeiro tenta colunas explícitas (ANO/MÊS) e depois
    extrai de uma das `data_cols`. sign=-1 inverte sinal.
    """
    cols = (valor_col,) if isinstance(valor_col, str) else valor_col
    out = {}
    for r in rows:
        # 1) tenta colunas explícitas
        ano = _to_int(_val(r, "ANO", "Ano"))
        mes = _to_int(_val(r, "MES", "MÊS"))
        # 2) se não tiver, extrai da data
        if ano is None or mes is None:
            ano2, mes2 = _ano_mes_de_data(r, *data_cols)
            ano = ano or ano2
            mes = mes or mes2
        nroempresa = _to_int(_val(r, "NROEMPRESA", "EMPRESA", "LOJA"))
        valor = _val(r, *cols)
        if ano is None or valor is None:
            continue
        k = (ano, mes, nroempresa, linha_fixa)
        out[k] = out.get(k, 0.0) + float(valor) * sign
    return [{"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
            for (a, m, n, l), v in out.items()]


def classify_juros_recebidos(rows: list[dict]) -> list[dict]:
    """BASE12 — Juros recebidos: tudo vai pra LINHA 'Juros e Multas Recebidos'."""
    return _classify_simple(rows, "Juros e Multas Recebidos", "VLROPERACAO", sign=+1)


def classify_descontos_obtidos(rows: list[dict]) -> list[dict]:
    """BASE14 — Descontos Obtidos: tudo vai pra LINHA 'Descontos Obtidos'."""
    return _classify_simple(rows, "Descontos Obtidos", "VLROPERACAO", sign=+1)


def classify_material_expediente_op(rows: list[dict]) -> list[dict]:
    """BASE15 — Material de Expediente da Operação (despesa)."""
    return _classify_simple(rows, "Material de Expediente da Operaçao",
                            ("VALOR_LIQUIDO", "VLRNOMINAL"), sign=-1)


# ─── ONDA 3 (parcial — LINHAs fixas a confirmar com usuário) ──────────────

# Mapa SEQPRODUTO → LINHA (categoria de material de expediente).
# Usado por material_expediente, transf_consumo e compra_transf — todos
# classificam o produto pela mesma categoria.
SEQPRODUTO_TO_LINHA_EXPEDIENTE = {
    # Cartaz Faixa e Outdoor
    5501: "Cartaz Faixa e Outdoor", 5502: "Cartaz Faixa e Outdoor",
    5503: "Cartaz Faixa e Outdoor", 5505: "Cartaz Faixa e Outdoor",
    5506: "Cartaz Faixa e Outdoor", 5507: "Cartaz Faixa e Outdoor",
    5508: "Cartaz Faixa e Outdoor", 5509: "Cartaz Faixa e Outdoor",
    5510: "Cartaz Faixa e Outdoor", 13877: "Cartaz Faixa e Outdoor",
    13878: "Cartaz Faixa e Outdoor", 13880: "Cartaz Faixa e Outdoor",
    13881: "Cartaz Faixa e Outdoor", 14194: "Cartaz Faixa e Outdoor",
    14195: "Cartaz Faixa e Outdoor",
    # Matéria-prima Padaria
    5892: "Matéria-prima Padaria", 6365: "Matéria-prima Padaria",
    6366: "Matéria-prima Padaria", 6370: "Matéria-prima Padaria",
    6373: "Matéria-prima Padaria", 6375: "Matéria-prima Padaria",
    6376: "Matéria-prima Padaria", 6379: "Matéria-prima Padaria",
    6388: "Matéria-prima Padaria", 6395: "Matéria-prima Padaria",
    6397: "Matéria-prima Padaria", 8410: "Matéria-prima Padaria",
    8411: "Matéria-prima Padaria", 9648: "Matéria-prima Padaria",
    11198: "Matéria-prima Padaria", 14762: "Matéria-prima Padaria",
    26281: "Matéria-prima Padaria", 33761: "Matéria-prima Padaria",
    34162: "Matéria-prima Padaria", 35050: "Matéria-prima Padaria",
    35051: "Matéria-prima Padaria",
    # Sacolas Outros
    6473: "Sacolas Outros", 6475: "Sacolas Outros", 6477: "Sacolas Outros",
    6479: "Sacolas Outros", 6480: "Sacolas Outros", 7495: "Sacolas Outros",
    7510: "Sacolas Outros", 7511: "Sacolas Outros", 7512: "Sacolas Outros",
    7513: "Sacolas Outros", 7514: "Sacolas Outros", 7515: "Sacolas Outros",
    7577: "Sacolas Outros", 7578: "Sacolas Outros", 20637: "Sacolas Outros",
    20638: "Sacolas Outros", 20639: "Sacolas Outros", 20640: "Sacolas Outros",
    26309: "Sacolas Outros", 31975: "Sacolas Outros",
    # Etiquetas e Ribbon
    6559: "Etiquetas e Ribbon", 6562: "Etiquetas e Ribbon",
    6563: "Etiquetas e Ribbon", 6564: "Etiquetas e Ribbon",
    6573: "Etiquetas e Ribbon", 31695: "Etiquetas e Ribbon",
    34553: "Etiquetas e Ribbon",
    # Bandejas
    7551: "Bandejas", 7564: "Bandejas", 13624: "Bandejas",
    13627: "Bandejas", 17293: "Bandejas", 33027: "Bandejas",
    33028: "Bandejas", 33030: "Bandejas",
    # Bobina Acougue / FLV / PDV
    7556: "Bobina Acougue",
    7557: "Bobina FLV",
    6568: "Bobina PDV",
    # Strech e Outros Materiais
    7559: "Strech e Outros Materiais", 7560: "Strech e Outros Materiais",
    7561: "Strech e Outros Materiais", 7591: "Strech e Outros Materiais",
    13630: "Strech e Outros Materiais",
    # Toucas, Mascaras e Luvas
    7567: "Toucas, Mascaras e Luvas", 7568: "Toucas, Mascaras e Luvas",
    7583: "Toucas, Mascaras e Luvas", 7651: "Toucas, Mascaras e Luvas",
    26291: "Toucas, Mascaras e Luvas", 34890: "Toucas, Mascaras e Luvas",
    # Materiais de Limpeza
    11012: "Materiais de Limpeza", 13712: "Materiais de Limpeza",
    13715: "Materiais de Limpeza", 13716: "Materiais de Limpeza",
    13717: "Materiais de Limpeza", 13763: "Materiais de Limpeza",
    13828: "Materiais de Limpeza", 15508: "Materiais de Limpeza",
    15908: "Materiais de Limpeza", 16203: "Materiais de Limpeza",
    25924: "Materiais de Limpeza", 25925: "Materiais de Limpeza",
    29897: "Materiais de Limpeza",
    # Sacolas PDV
    7579: "Sacolas PDV", 21073: "Sacolas PDV", 25500: "Sacolas PDV",
    # Material de Expediente da Operação
    10419: "Material de Expediente da Operaçao",
    13566: "Material de Expediente da Operaçao",
}


def _classify_por_seqproduto(rows: list[dict], *, sign: int,
                             valor_cols: tuple, data_cols: tuple,
                             slug: str) -> list[dict]:
    """Classificador genérico: lookup SEQPRODUTO → LINHA via map de expediente.

    Linhas com SEQPRODUTO não mapeado são logadas (warn) e ignoradas.
    """
    out: dict[tuple, float] = {}
    nao_mapeados: dict[int, str] = {}
    for r in rows:
        seqproduto = _to_int(_val(r, "SEQPRODUTO", "PLU", "COD"))
        linha = SEQPRODUTO_TO_LINHA_EXPEDIENTE.get(seqproduto)
        if not linha:
            if seqproduto is not None:
                nao_mapeados[seqproduto] = _val(r, "PRODUTO", "DESCCOMPLETA", "DESCPRODUTO") or ""
            continue
        ano = _to_int(_val(r, "ANO"))
        mes = _to_int(_val(r, "MES", "MÊS"))
        if ano is None or mes is None:
            ano2, mes2 = _ano_mes_de_data(r, *data_cols)
            ano = ano or ano2
            mes = mes or mes2
        nroempresa = _to_int(_val(r, "NROEMPRESA", "EMPRESA", "LOJA"))
        valor = _val(r, *valor_cols)
        if ano is None or valor is None:
            continue
        k = (ano, mes, nroempresa, linha)
        out[k] = out.get(k, 0.0) + float(valor) * sign
    if nao_mapeados:
        print(f"  ⚠ classify_{slug}: {len(nao_mapeados)} SEQPRODUTOs não mapeados em SEQPRODUTO_TO_LINHA_EXPEDIENTE:")
        for sp in sorted(nao_mapeados):
            print(f"      {sp:>6}  {nao_mapeados[sp]}")
    return [{"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
            for (a, m, n, l), v in out.items()]


def classify_consumo_interno(rows: list[dict]) -> list[dict]:
    """BASE2 — Consumo Interno. VLRCTOLIQUIDO já vem negativo do Oracle
    (saída > entrada). Mantém sinal natural pra refletir despesa."""
    return _classify_simple(rows, "Consumo Interno", "VLRCTOLIQUIDO",
                            sign=+1, data_cols=("MES",))


def classify_cesta_basica(rows: list[dict]) -> list[dict]:
    """BASE2-sub — Cesta Básica. Mesma fórmula do consumo_interno, sinal natural."""
    return _classify_simple(rows, "Cesta Básica", "VLRCTOLIQUIDO",
                            sign=+1, data_cols=("MES",))


def classify_material_expediente(rows: list[dict]) -> list[dict]:
    """BASE7 — Material de Expediente (entrada do fornecedor, reduz margem).
    LINHA é determinada por SEQPRODUTO via SEQPRODUTO_TO_LINHA_EXPEDIENTE."""
    return _classify_por_seqproduto(
        rows, sign=-1,
        valor_cols=("COMPRA",),
        data_cols=("DTAENTRADA",),
        slug="material_expediente",
    )


def classify_perdas_quebras(rows: list[dict]) -> list[dict]:
    """Perdas e Quebras — sum(VALORLANCTO) por loja/data."""
    return _classify_simple(rows, "Perdas e Quebras", "VLRLIQUIDO",
                            sign=-1, data_cols=("DATA", "DTAENTRADASAIDA"))


def classify_inventario(rows: list[dict]) -> list[dict]:
    """Inventario — sum(entradas) − sum(saídas) por loja/mês.
    Linha: 'Inventario' (sob agrupamento 'Quebra Contábil')."""
    return _classify_simple(rows, "Inventario", "VLRCTOLIQUIDO",
                            sign=+1, data_cols=("DTAENTRADASAIDA",))


def classify_juros_emprestimo(rows: list[dict]) -> list[dict]:
    """BASE13a — Juros de Empréstimo (despesa financeira).
    codoperacao=7 + codespecie='EMPRE2'. LINHA: 'Juros e Multas Pagos Sobre Emp'."""
    return _classify_simple(rows, "Juros e Multas Pagos Sobre Emp", "VLROPERACAO",
                            sign=-1, data_cols=("DTACONTABILIZA", "DTAOPERACAO"))


def classify_juros_pago(rows: list[dict]) -> list[dict]:
    """BASE13b — Juros e Multas (despesa financeira).
    codoperacao=7 + codespecie != 'EMPRE2' (juros sobre títulos a pagar)."""
    return _classify_simple(rows, "Juros e Multas", "VLROPERACAO",
                            sign=-1, data_cols=("DTACONTABILIZA", "DTAOPERACAO"))


def classify_venda_atual(rows: list[dict]) -> list[dict]:
    """BASE1 — Venda Atual. Gera 3 fatos por (ano, mes, nroempresa):

      • LINHA "Venda Bruta"                   = VENDA                       (sign +1)
      • LINHA "Margem C/ Acordos Lançados"    = MARGEM                      (sign +1)
      • LINHA "Mercadoria para Revenda - CMV" = -(VENDA - MARGEM + VERBA)   (sign -1)

    Margem S/ Acordos NÃO é gravada aqui — o engine recalcula como
    `Venda Bruta + grupo CMV` (Mercadoria + Embalagens) em LINHAS_CALCULADAS.
    """
    venda_map:  dict[tuple, float] = {}
    margem_map: dict[tuple, float] = {}
    cmv_map:    dict[tuple, float] = {}
    for r in rows:
        ano = _to_int(_val(r, "ANO"))
        mes = _to_int(_val(r, "MES", "MÊS"))
        nroempresa = _to_int(_val(r, "NROEMPRESA"))
        venda = _val(r, "VENDA")
        margem = _val(r, "MARGEM") or 0
        verba = _val(r, "VERBA") or 0
        if ano is None or venda is None:
            continue
        k = (ano, mes, nroempresa)
        venda_map[k]  = venda_map.get(k, 0.0)  + float(venda)
        margem_map[k] = margem_map.get(k, 0.0) + float(margem)
        # CMV em magnitude positiva (negativado na hora de gravar)
        cmv_map[k]    = cmv_map.get(k, 0.0)    + (float(venda) - float(margem) + float(verba))

    fatos = []
    for k, v in venda_map.items():
        a, m, n = k
        fatos.append({"ano": a, "mes": m, "nroempresa": n, "linha": "Venda Bruta", "valor": round(v, 2)})
    for k, v in margem_map.items():
        a, m, n = k
        fatos.append({"ano": a, "mes": m, "nroempresa": n, "linha": "Margem C/ Acordos Lançados", "valor": round(v, 2)})
    for k, v in cmv_map.items():
        a, m, n = k
        fatos.append({"ano": a, "mes": m, "nroempresa": n, "linha": "Mercadoria para Revenda - CMV", "valor": round(-v, 2)})
    return fatos


def classify_transf_consumo(rows: list[dict]) -> list[dict]:
    """BASE7 — Transf Consumo. Venda de material de expediente pra outra loja.
    Credita a margem da loja vendedora (sign +1). LINHA por SEQPRODUTO."""
    return _classify_por_seqproduto(
        rows, sign=+1,
        valor_cols=("VLRVENDA",),
        data_cols=("DTAVDA",),
        slug="transf_consumo",
    )


def classify_compra_transf(rows: list[dict]) -> list[dict]:
    """BASE11 — Compra Transf. Compra de material de expediente de outra loja.
    Reduz a margem da loja compradora (sign -1). LINHA por SEQPRODUTO."""
    return _classify_por_seqproduto(
        rows, sign=-1,
        valor_cols=("VLRENTRADA",),
        data_cols=("DTAENTRADA",),
        slug="compra_transf",
    )


def classify_compra_func(rows: list[dict]) -> list[dict]:
    """BASE10 — Compra Func. Vendas a funcionários (forma de pagamento 20).
    Mesma LINHA da "compra func acumulada" — engine soma as duas no mesmo destino.
    LINHA "(-) Compras Funcionarios" (existe em meta/linhas, agrupamento Despesas c/ Pessoal)."""
    return _classify_simple(rows, "(-) Compras Funcionarios", "VENDA",
                            sign=-1, data_cols=("DTAVDA",))


# BASE3 — Receitas Comerciais (acordos com fornecedores).
# Mapa CODESPECIE → LINHA fornecido pelo usuário (Excel Classificação).
CODESPECIE_TO_LINHA_RECEITAS_COMERCIAIS = {
    "ACRA23": "Acordo Aniversário 2023",
    "ACRA24": "Acordo Aniversário 2023",   # conforme planilha do usuário
    "ACRA25": "Acordo Aniversário 2023",
    "ACRCOM": "Acordo Comercial",
    "ACRINT": "Acordo Introdução",
    "ACRLOG": "Acordo Logística e Recebimento",
    "ACRMGM": "Acordo de Compras",
    "ACRMKT": "Acordo Marketing",
    "ACRPON": "Acordo Ponta de Gondola",
    "ACRPRE": "Acordo Preço",
    "ACRQUE": "Acordo Quebra de Produtos Avariados",
    "ACRTRO": "Acordo Troca de Produtos Avariados",
    "CONTRT": "Contrato Retorno",
    "DEVREC": "Devolução de Fornecedores",
    # Pendentes de mapeamento (apareceram no IN da query mas não na planilha):
    # ACRA22, ACREX2, ACRFOR, ACRINA, ACRPEN, ACRXTR, CONTEV
}


def classify_receitas_comerciais(rows: list[dict]) -> list[dict]:
    """BASE3 — Receitas Comerciais. Lookup CODESPECIE → LINHA.

    Receitas → sinal positivo. Ano/mês de DTACONTABILIZA (mesma coluna do filtro).
    """
    out = {}
    nao_mapeados: set = set()
    for r in rows:
        codespecie = _val(r, "CODESPECIE")
        linha = CODESPECIE_TO_LINHA_RECEITAS_COMERCIAIS.get(codespecie)
        if not linha:
            nao_mapeados.add(codespecie)
            continue
        ano, mes = _ano_mes_de_data(r, "DTACONTABILIZA", "DTAOPERACAO")
        nroempresa = _to_int(_val(r, "NROEMPRESA"))
        valor = _val(r, "VLROPERACAO")
        if ano is None or valor is None:
            continue
        k = (ano, mes, nroempresa, linha)
        out[k] = out.get(k, 0.0) + float(valor)   # receita, sign +1
    if nao_mapeados:
        print(f"  ⚠ classify_receitas_comerciais: CODESPECIEs não mapeados: {sorted(s for s in nao_mapeados if s)}")
    return [{"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
            for (a, m, n, l), v in out.items()]


# ─── ONDA 2 ────────────────────────────────────────────────────────────────

# BASE5 — Operação Financeira.
# Mapa CODOPERACAO → LINHA pros 24 codops usados na query.
#
# Decisão (usuário, 2026-05): os 9 códigos "ambíguos" (sem LINHA dedicada na
# DRE) entram em "Tarifa Bancaria" e a descrição do FI_OPERACAO vai como
# observação no fato. O 140 (ESTORNO DE TITULO NO EXTRATO) fica de fora
# porque não tem nenhuma linha referenciada na DRE.
#
# Os 14 "óbvios" (rendimentos / IOF / IR / cartão) ainda precisam ser
# confirmados pelo usuário olhando a descrição real do FI_OPERACAO. Quando
# vierem unmapped no run, o classificador imprime a descrição pra revisão.
CODOPERACAO_TO_LINHA = {
    # --- IOF (LINHA dedicada) ---
    73:  "IOF",                 # IOF
    # --- Rendimentos / IR de Op Financeiras (LINHAs dedicadas) ---
    # Confirmado pela "02 - Valores Rateados.xlsx" (BASE5/VALORES RATEADOS).
    # Sinal correto pelo tipolancto: 130 é crédito (C→+), 139 é débito (D→-).
    130: "Rendimentos de Aplicacoes financeiras",   # RENDIMENTO BRUTO PAGO (jan +11.858,50)
    139: "IR Op Financeiras",                        # IMPOSTO DE RENDA (jan -3.844,45)
    # --- Tarifa Bancaria (todas as tarifas, com observação do FI_OPERACAO) ---
    34:  "Tarifa Bancaria",   # Tarifa de Cobranca
    69:  "Tarifa Bancaria",   # Outros Débitos
    108: "Tarifa Bancaria",   # TARIFA TED SISPAG
    112: "Tarifa Bancaria",   # TAR CONTA CERTA
    129: "Tarifa Bancaria",   # TARIFAS BANCARIAS
    132: "Tarifa Bancaria",   # TARIFA RECOLHIMENTO VALORES
    136: "Tarifa Bancaria",   # Taxas de Custas Cartorárias
    142: "Tarifa Bancaria",   # TARIFA PIX LOJA
    205: "Tarifa Bancaria",   # TARIFA GERACAO DE BOLETO BANC
    # --- Tarifas de Cartao Debito e Credito (grupo Despesas C/ Vendas) ---
    # DOC das operadoras de cartão/vale + taxa admin + aluguel de terminal.
    # Confirmado pela "02 - Valores Rateados.xlsx" (BASE5 = consulta Operação
    # Financeira / FI_CTACORLANCA): a soma desses 8 codops bate EXATO com a linha
    # "Tarifas de Cartao Debito e Credito" do PowerBI (jan -18.214,72 / fev -17.252,69).
    157: "Tarifas de Cartao Debito e Credito",   # TAXA GESTAO CARTAO
    167: "Tarifas de Cartao Debito e Credito",   # TAXA ANUIDADE (cartão)
    214: "Tarifas de Cartao Debito e Credito",   # GREENCARD - DOC
    216: "Tarifas de Cartao Debito e Credito",   # SODEXO - DOC
    217: "Tarifas de Cartao Debito e Credito",   # TICKET - DOC
    218: "Tarifas de Cartao Debito e Credito",   # VALE CARD - DOC
    219: "Tarifas de Cartao Debito e Credito",   # VR ALIMENTAÇÃO - DOC
    220: "Tarifas de Cartao Debito e Credito",   # TAXA ADMINISTRATIVA (VALECARD)
    223: "Tarifas de Cartao Debito e Credito",   # ALUGUEL NUMERO LOGICO (CIELO)
    225: "Tarifas de Cartao Debito e Credito",   # TED/DOC ALELO
    # --- 140 (ESTORNO DE TITULO NO EXTRATO) e 191 (DESBLOQUEIO JUDICIAL):
    #     propositalmente FORA (CODOPERACAO_IGNORAR). O PowerBI deixa o 191 cru
    #     (não é linha da DRE); incluí-lo em Tarifa Bancaria inflava ~+186k/mês
    #     e deixava a linha positiva. Removido (decisão do usuário 2026-05-24). ---
}

# Códigos que sempre carregam observação (descrição do FI_OPERACAO) no fato,
# pra dar rastreabilidade já que múltiplos códigos viram a mesma LINHA.
# Tudo que vai pra "Tarifa Bancaria" entra aqui — quando o usuário olhar o
# drill-down de Tarifa Bancaria, vê qual tipo de tarifa contribuiu.
CODOPERACAO_COM_OBS = {34, 69, 108, 112, 129, 132, 136, 142, 205,
                       157, 167, 214, 216, 217, 218, 219, 220, 223, 225}

# Códigos a ignorar silenciosamente (decisão consciente do usuário).
# 140 = ESTORNO DE TITULO NO EXTRATO; 191 = DESBLOQUEIO JUDICIAL (PowerBI deixa
# fora — não é linha da DRE; incluí-lo em Tarifa Bancaria deixava-a positiva).
CODOPERACAO_IGNORAR = {140, 191}


def classify_operacao_financeira(rows: list[dict]) -> list[dict]:
    """BASE5 — Operação Financeira. Lookup CODOPERACAO → LINHA.

    Pros códigos ambíguos lumpados em "Tarifa Bancaria", a descrição do
    FI_OPERACAO vai num campo `observacao` no fato. Pra preservar essa
    observação por código, agregamos por (ano, mes, nroempresa, linha, codop).
    Pros códigos com LINHA dedicada (sem observação), agregamos só por
    (ano, mes, nroempresa, linha).
    """
    out = {}
    obs_por_chave: dict[tuple, str] = {}
    nao_mapeados: dict[int, str] = {}

    for r in rows:
        codoperacao = _to_int(_val(r, "CODOPERACAO"))
        if codoperacao in CODOPERACAO_IGNORAR:
            continue
        linha = CODOPERACAO_TO_LINHA.get(codoperacao)
        descop = _val(r, "DESCOPERACAO", "DESCRICAO") or ""
        if not linha:
            nao_mapeados[codoperacao] = descop
            continue
        # Data lancto → ano/mes
        dta = _val(r, "DTALANCTO")
        if isinstance(dta, str):
            try: dta = dt.datetime.fromisoformat(dta)
            except Exception: dta = None
        ano = dta.year if dta else None
        mes = dta.month if dta else None
        nroempresa = _to_int(_val(r, "NROEMPRESA"))
        valor = _val(r, "VLRLANCAMENTO", "VLROPERACAO")
        tipo = _val(r, "TIPOLANCTO")  # 'D' (débito) ou 'C' (crédito)
        if ano is None or valor is None:
            continue
        sign = -1 if tipo == "D" else +1
        # Pros ambíguos, segrega por codop pra preservar observação
        if codoperacao in CODOPERACAO_COM_OBS:
            k = (ano, mes, nroempresa, linha, codoperacao)
            obs_por_chave[k] = descop
        else:
            k = (ano, mes, nroempresa, linha, None)
        out[k] = out.get(k, 0.0) + float(valor) * sign

    if nao_mapeados:
        print(f"  ⚠ classify_operacao_financeira: {len(nao_mapeados)} CODOPERACAOs não mapeados (revise e adicione em CODOPERACAO_TO_LINHA):")
        for codop in sorted(nao_mapeados):
            print(f"      {codop:>4}  {nao_mapeados[codop]}")

    fatos = []
    for (a, m, n, l, codop), v in out.items():
        f = {"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
        if codop is not None:
            f["codoperacao"] = codop
            f["observacao"] = obs_por_chave.get((a, m, n, l, codop), "")
        fatos.append(f)
    return fatos


# BASE6 — Despesas C/ Vendas (deságio operadoras).
# Mapeamento direto por CODESPECIE (sem ambiguidade, validado pelo usuário).
CODESPECIE_TO_LINHA_DESPESAS_C_VENDAS = {
    "TICKET": "Desagio Ticket",
    "CARTAO": "Desagio Cartao de Credito",
    "CARDEB": "Desagio Cartao de Debito",
    "CARDIG": "Desagio Sobre Carteira Digital",
}


def classify_despesas_c_vendas(rows: list[dict]) -> list[dict]:
    """BASE6 — Despesas C/ Vendas (deságio das operadoras de cartão/vale).

    A query devolve VLRADMINISTRACAO (valor pago à operadora) e CODESPECIE.
    Despesa → sinal negativo. Ano/mês extraído de DTAEMISSAO.
    """
    out = {}
    nao_mapeados: set = set()
    for r in rows:
        codespecie = _val(r, "CODESPECIE")
        linha = CODESPECIE_TO_LINHA_DESPESAS_C_VENDAS.get(codespecie)
        if not linha:
            nao_mapeados.add(codespecie)
            continue
        ano = _to_int(_val(r, "ANO"))
        mes = _to_int(_val(r, "MES", "MÊS"))
        if ano is None or mes is None:
            ano2, mes2 = _ano_mes_de_data(r, "DTAEMISSAO", "DTAOPERACAO", "DTACONTABILIZA")
            ano = ano or ano2
            mes = mes or mes2
        nroempresa = _to_int(_val(r, "NROEMPRESA"))
        valor = _val(r, "VLRADMINISTRACAO", "VLROPERACAO")
        if ano is None or valor is None:
            continue
        k = (ano, mes, nroempresa, linha)
        out[k] = out.get(k, 0.0) + float(valor) * -1   # despesa
    if nao_mapeados:
        print(f"  ⚠ classify_despesas_c_vendas: CODESPECIEs não mapeados: {sorted(s for s in nao_mapeados if s)}")
    return [{"ano": a, "mes": m, "nroempresa": n, "linha": l, "valor": round(v, 2)}
            for (a, m, n, l), v in out.items()]


# ─── DISPATCHER ────────────────────────────────────────────────────────────

# Dispatcher: slug da query → função classificadora.
# Onda 1 trivial está coberta. Onda 2 tem op_financeira parcial.
# As demais retornam [] por enquanto (Onda 3 — pendente).
CLASSIFIERS_ONDA_1 = {
    "despesas":              "despesas",   # ← retorna 2 listas (fatos + detalhes)
    "quebra_sobra":          classify_quebra_sobra,
    "juros_recebidos":       classify_juros_recebidos,
    "descontos_obtidos":     classify_descontos_obtidos,
    "material_expediente_op": classify_material_expediente_op,
}

CLASSIFIERS_ONDA_2 = {
    "operacao_financeira":   classify_operacao_financeira,   # 9 ambíguos OK; 14 óbvios pendentes
    "despesas_c_vendas":     classify_despesas_c_vendas,     # 4 CODESPECIEs OK
}

# Onda 3 (parcial) — LINHAs fixas a confirmar com usuário.
# Pendente ainda: venda_atual (BASE1, vendas+CMV), receitas_comerciais
# (BASE3, lookup CODESPECIE), transf_consumo (BASE7), compra_transf (BASE11),
# compra_func (BASE10).
CLASSIFIERS_ONDA_3 = {
    "consumo_interno":       classify_consumo_interno,
    "cesta_basica":          classify_cesta_basica,
    "material_expediente":   classify_material_expediente,
    "perdas_quebras":        classify_perdas_quebras,
    "inventario":            classify_inventario,
    "juros_emprestimo":      classify_juros_emprestimo,
    "juros_pago":            classify_juros_pago,
    "venda_atual":           classify_venda_atual,
    "transf_consumo":        classify_transf_consumo,
    "compra_transf":         classify_compra_transf,
    "compra_func":           classify_compra_func,
    "receitas_comerciais":   classify_receitas_comerciais,
}


def classificar_query(slug: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Classifica uma query pelo seu slug.

    Retorna (fatos, detalhes). detalhes só é populado pra "despesas".
    Pras queries não implementadas ainda, retorna ([], []).
    """
    if slug == "despesas":
        return classify_despesas(rows)
    fn = (CLASSIFIERS_ONDA_1.get(slug)
          or CLASSIFIERS_ONDA_2.get(slug)
          or CLASSIFIERS_ONDA_3.get(slug))
    if not fn or fn == "despesas":
        return [], []
    return fn(rows), []
