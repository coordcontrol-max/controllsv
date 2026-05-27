#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL DFC OUTRAS — fonte: banco LUMI (MySQL, base SAC) — direto, sem Excel.

Substitui a leitura do export manual "02 - Fluxo de Caixa Diário - Outras
Empresas.xlsx" (etl_fluxo_segmentos.py) por consulta direta ao MySQL do LUMI.

Modelo (regime de caixa):
  • SAÍDAS  = TITULO TIPO=4, data = DTLIQUIDA, valor = -VLPAGO.
  • ENTRADAS= TITULO TIPO=9, data = VENCIMENTO (DTLIQUIDA fica vazio nos
              recebíveis), valor = +VLPAGO.
  • LOJA    = banco do título (TITULO.CONTA → CONTA.DESCRICAO):
              0004→FLUXO 0006/0008→LP 0007→TARES 0009→PEGUI 0010→RETA.
  • LINHA   = natureza do lançamento (TABMOVTO, casada por melhor-prefixo no
              HISTORICO/DESCRICAO) → linha amigável da DFC. O bucket genérico
              DESPU ("Despesas de Uso e Consumo") é sub-classificado por
              palavra-chave do histórico.

NÃO inclui receitas de VENDA (PIX/Crédito/Débito/Dinheiro): essas não vivem
neste banco LUMI (tabelas de cupom/cartão zeradas) — decisão do usuário.

Saída: dados_fluxo_outras_lumi/{ano}-{mes:02d}.json (consolidado),
       {ano}-{mes:02d}__{LOJA}.json, detalhe_{ano}-{mes:02d}.json, meta.json
no MESMO schema consumido pelo dashboard (v=2, porLinha/porAgrupamento/porGrupo).

Uso:  LUMI_PW=xxxx python3 etl_dfc_outras_lumi.py [ano]   (default ano=2026)
"""
import os, sys, json, re, calendar, datetime as dt
from collections import defaultdict
import pymysql

LUMI = dict(host=os.environ.get("LUMI_HOST", "10.17.0.100"),
            port=int(os.environ.get("LUMI_PORT", "3306")),
            user=os.environ.get("LUMI_USER", "sac"),
            password=os.environ["LUMI_PW"],   # obrigatório — exporte em ~/.controllsv.env
            database="SAC", connect_timeout=10, charset="utf8mb4")

# Diretório canônico do segmento 'outras' (mesmo que o dashboard/upload consomem).
# Sobrescreve os JSONs mensais/por-loja/detalhe/meta; NÃO toca saldos_iniciais.json.
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       os.environ.get("DFC_OUTRAS_OUT", "dados_fluxo_outras"))

GRUPOS = ["ATIVIDADES OPERACIONAIS", "ATIVIDADES DE FINANCIAMENTO", "ATIVIDADES DE INVESTIMENTO"]
AGRUPAMENTOS = ["Recebimentos Operacionais", "Despesas", "Atividades de Financiamento", "Atividades de Investimento"]
LOJAS = ["FLUXO", "LP", "PEGUI", "RETA", "TARES"]

# banco do título → loja do grupo
CONTA_LOJA = {"0004": "FLUXO", "0006": "LP", "0008": "LP",
              "0007": "TARES", "0009": "PEGUI", "0010": "RETA"}

# Ajustes manuais DURÁVEIS (não existem no banco LUMI). Hoje VAZIO — os lançamentos
# que existem na planilha mas não no LUMI vêm via `coletar_importacao_manual_excel`
# (ler abaixo). Antes tinha 3 entradas de vendas PIX jan/2026 reclassificadas como
# Aluguel; foram REMOVIDAS 2026-05-26: agora o auto-import detecta direto da
# planilha do controller (com ALIAS Venda PIX → Recebmto de Aluguéis).
# (ano, mes, dia, loja, linha, valor, descricao)
AJUSTES_MANUAIS = []

# Importação Histórica — snapshot ESTÁTICO dos lançamentos que existiam na
# planilha do controller (Jan-Abr/2026) mas NÃO no LUMI. Foi gerado UMA vez
# (2026-05-27) lendo a planilha; agora vive como JSON no repo. Decisão do
# usuário: "importe só o que precisar do excel e depois exclua a importação.
# Deverá vir tudo pelo Lumi" — Maio/2026 em diante só LUMI, sem Excel.
IMPORTACOES_HISTORICAS_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "importacoes_historicas_outras.json")

OP, FIN, INV = GRUPOS
AG_REC, AG_DESP, AG_FIN, AG_INV = AGRUPAMENTOS
# taxonomia: linha -> (grupo, agrupamento). Ordem = ordem de exibição.
TAXONOMIA = [
    ("Recebmto de Aluguéis", OP, AG_REC), ("Outras Receitas", OP, AG_REC),
    ("Agua", OP, AG_DESP), ("Aluguel", OP, AG_DESP),
    ("Aquisição e Financiamento de Veículos", OP, AG_DESP), ("COFINS", OP, AG_DESP),
    ("Despesa Bancária", OP, AG_DESP), ("Despesas Gerais", OP, AG_DESP),
    ("Energia Eletrica", OP, AG_DESP), ("FGTS", OP, AG_DESP),
    ("Honorarios Contabeis", OP, AG_DESP), ("Imposto", OP, AG_DESP),
    ("INSS", OP, AG_DESP), ("IPTU", OP, AG_DESP), ("ITBI", OP, AG_DESP),
    ("Licença De Software", OP, AG_DESP), ("Manutenção De Equipamentos", OP, AG_DESP),
    ("Manutenção Predial", OP, AG_DESP), ("PIS", OP, AG_DESP),
    ("Plano de Saúde", OP, AG_DESP), ("Premiação/Bonus", OP, AG_DESP),
    ("Salarios", OP, AG_DESP), ("Segurança", OP, AG_DESP),
    ("Seguro Veicular", OP, AG_DESP), ("Serviços De Terceiros", OP, AG_DESP),
    ("Tarifa De Manutenção Frota", OP, AG_DESP), ("Taxas Administrativas", OP, AG_DESP),
    ("Mútuos a Receber", FIN, AG_FIN), ("Mútuos a Pagar", FIN, AG_FIN),
    ("Transferencia Bancaria", FIN, AG_FIN),
    ("Mútuos a Receber (Entre Grupos)", FIN, AG_FIN), ("Mútuo a Pagar (Entre Grupos)", FIN, AG_FIN),
    ("Investimento Compra De Imoveis", INV, AG_INV), ("Investimento Compra De Materiais", INV, AG_INV),
    ("Investimento Compra Moveis", INV, AG_INV), ("Socio 30", INV, AG_INV),
    # Linhas de cartão (Crédito/Débito/Dinheiro Protege/PIX) NÃO existem em Outras
    # (não tem PDV/combustível) — removidas em 2026-05-26 a pedido do usuário.
    ("Impostos Federais Pagos", OP, AG_DESP), ("Manutenção Informatica", OP, AG_DESP),
    ("Taxa Fiscalização", OP, AG_DESP), ("Material De Uso E Consumo", OP, AG_DESP),
    ("Outras Despesas", OP, AG_DESP), ("Internet", OP, AG_DESP),
    ("Licenças Ambientais", OP, AG_DESP), ("Seguros", OP, AG_DESP),
    ("Convenio Medico", OP, AG_DESP), ("Despesas Eventuais", OP, AG_DESP),
    ("Locação Equipamentos", OP, AG_DESP), ("Consultoria E Assessoria", OP, AG_DESP),
    ("Investimento Compra De Equipamentos", INV, AG_INV),
]
LINHAS = [l for l, _, _ in TAXONOMIA]

# natureza (TABMOVTO.DESCRICAO) → linha direta da DFC
NAT2LINE = {
    "AGUA": "Agua", "ALUG": "Aluguel", "ENERGI": "Energia Eletrica",
    "INSS": "INSS", "FGTS": "FGTS", "PIS": "PIS", "COFINS": "COFINS",
    "IRPJ": "Impostos Federais Pagos", "CSLL": "Impostos Federais Pagos",
    "IRRF": "Impostos Federais Pagos", "IRPF": "Impostos Federais Pagos",
    "DAS": "Impostos Federais Pagos", "ISS": "Impostos Federais Pagos",
    "NPRVPA": "Impostos Federais Pagos", "ICMSPA": "Imposto", "IPVA": "Imposto",
    "IPTU": "IPTU", "ITBI": "ITBI",
    "ORDSAL": "Salarios", "ADIASAL": "Salarios", "VALETR": "Salarios", "RECISAO": "Salarios",
    "BONUS": "Premiação/Bonus", "CONT": "Honorarios Contabeis",
    "INFOLI": "Licença De Software", "PLANO": "Plano de Saúde",
    "SEGURV": "Seguro Veicular", "SERVT": "Serviços De Terceiros", "SERVTS": "Segurança",
    "TARBAN": "Despesa Bancária", "TAXADM": "Taxas Administrativas",
    "IMOV": "Investimento Compra De Imoveis", "AQUISE": "Investimento Compra De Equipamentos",
    "LOGFIN": "Aquisição e Financiamento de Veículos", "LOGV": "Aquisição e Financiamento de Veículos",
    "EMPRES": "Mútuos a Pagar", "MUTUO A PAGAR": "Mútuos a Pagar",
    "EMPREC": "Mútuos a Receber", "MUTUO A RECEBER": "Mútuos a Receber",
    "TED/DOC": "Transferencia Bancaria",   # EMPRE2 é tratado à parte (split por contraparte)
    "DUPP": "Despesas Gerais",
    "DIRET": "Socio 30", "DIRET2": "Socio 30", "DIRET3": "Socio 30", "DIRET4": "Socio 30",
    "CUSCOR": "Outras Despesas", "IMPCC": "Outras Despesas", "CONVFA": "Outras Despesas",
    "INCOMP": "Outras Despesas", "CUSTJU": "Outras Despesas", "ADIAFO": "Outras Despesas",
}

# sub-split do bucket DESPU (Despesas de Uso e Consumo) por palavra-chave no histórico.
# Avaliado em ordem; primeira regra que casa vence. Regras mais específicas primeiro.
DESPU_RULES = [
    (("INSTRUMENTO PARTICULAR", "COMPRA E VENDA", "IMOVEL", "IMÓVEL",
      "TERRENO", "LOTE ", "AQUISIÇÃO DE IMOV", "AQUISICAO DE IMOV"),        "Investimento Compra De Imoveis"),
    (("DIRETORIA", "PRO LABORE", "PRÓ LABORE", "PROLABORE"),                "Socio 30"),
    ((" VALE ", "VALE FUNCIONARIO", "ADIANTAMENTO SALAR"),                  "Salarios"),
    (("FINANCIAMENTO", "FINANC DO", "FINANC. DO", "LEASING"),               "Aquisição e Financiamento de Veículos"),
    (("PNEU", "VEICULO", "VEÍCULO", "MOTO", "CAMINHAO", "CAMINHÃO", "CANMINHAO",
      "PRISMA", "CARRO", "TORO", "FROTA", "OLEO", "ÓLEO", "REVISAO", "REVISÃO"),"Tarifa De Manutenção Frota"),
    (("CFTV", "CABEAMENTO", "CABO PP", "INFORMATICA", "INFORMÁTICA",
      "SOFTWARE", "SISTEMA", "COMPUTADOR", "NOTEBOOK", "SERVIDOR"),         "Manutenção Informatica"),
    (("INTERNET", "FIBRA", "LINK DE", "BANDA LARGA"),                       "Internet"),
    (("AMBIENT", "IBAMA", "LICENCIAMENTO AMBIENTAL"),                       "Licenças Ambientais"),
    (("FISCALIZ",),                                                         "Taxa Fiscalização"),
    (("CONSULTORIA", "ASSESSORIA"),                                         "Consultoria E Assessoria"),
    (("SEGURO", "ALLIANS", "ALLIANZ", "PORTO SEGURO", "APÓLICE", "APOLICE"),"Seguros"),
    (("LOCAÇÃO", "LOCACAO", "ALUGUEL DE EQUIP"),                            "Locação Equipamentos"),
    (("MANUTEN", "REFORM", "CONSTRU", "OBRA", "PINTURA", "TUBO", "ESGOTO",
      "PREDIAL", "REPARO", "ELÉTRICA", "ELETRICA", "HIDRA", "CAST", "PVC"), "Manutenção Predial"),
    (("EQUIPAMENTO", "MOVEIS", "MÓVEIS", "MOBILIA"),                        "Investimento Compra De Equipamentos"),
    (("INVESTIMENTO",),                                                     "Investimento Compra De Materiais"),
    (("MATERIAL", "MATERIAIS"),                                             "Material De Uso E Consumo"),
]


def carregar_naturezas(cur):
    cur.execute("SELECT TRIM(DESCRICAO), TRIM(HISTORICO) FROM TABMOVTO WHERE INATIVO<>'S' OR INATIVO IS NULL")
    cat = cur.fetchall()
    def best(historico):
        h = (historico or "").upper(); melhor = None; ln = -1
        for desc, hist in cat:
            for k in (hist, desc):
                k = (k or "").upper().strip()
                if k and h.startswith(k) and len(k) > ln:
                    melhor = (desc or "").upper(); ln = len(k)
        return melhor
    return best


def loja_de_entrada(historico):
    """Recebíveis (TIPO 9) têm CONTA vazia — a empresa vem do histórico:
       'ALUGUEL A RECEBER ... - TARES' ou 'TRANSFERENCIA ... PARA RETA'."""
    h = (historico or "").upper()
    m = re.search(r'\bPARA\s+([A-ZÇÃÕ]+)', h)
    if m and m.group(1) in LOJAS:
        return m.group(1)
    for l in LOJAS:
        if re.search(r'\b' + l + r'\b', h):
            return l
    return "RETA"   # hub financeiro do grupo — fallback p/ não descartar a entrada


def _saida_entre_outras(historico, loja):
    """SAÍDA: a loja (dona, via CONTA) é confiável. Contraparte = demais tokens de
       loja no histórico. True → entre as 5 'outras' (mútuo simples);
       False → posto/super/externo (Entre Grupos)."""
    toks = set(re.findall(r'[A-ZÇÃÕ]+', (historico or "").upper())) & set(LOJAS)
    toks.discard(loja)
    return len(toks) >= 1


def _entrada_entre_outras(historico):
    """ENTRADA: CONTA vazia. O token de loja é a CONTRAPARTE (quem deve/transfere).
       Em 'X PARA Y', Y é o recebedor (removido) e X é a contraparte.
       True → contraparte é outra 'outras' (mútuo simples); False → posto/externo."""
    hu = (historico or "").upper()
    toks = set(re.findall(r'[A-ZÇÃÕ]+', hu)) & set(LOJAS)
    m = re.search(r'PARA\s+([A-ZÇÃÕ]+)', hu)
    if m and m.group(1) in toks:
        toks.discard(m.group(1))   # remove o recebedor; sobra a contraparte
    return len(toks) >= 1


def classificar(tipo, historico, loja):
    """Retorna a linha da DFC para um título (tipo 4=saída, 9=entrada)."""
    h = (historico or "").upper()
    if tipo == 9:   # entradas (recebíveis)
        if h.startswith("ALUGUEL A RECEB"):
            return "Recebmto de Aluguéis"
        if (h.startswith("MUTUO") or h.startswith("MÚTUO")
                or "TRANSFERENCIA ENTRE CONTAS" in h or "TRANSFERÊNCIA ENTRE CONTAS" in h):
            return "Mútuos a Receber" if _entrada_entre_outras(h) else "Mútuos a Receber (Entre Grupos)"
        return "Outras Receitas"
    # saídas (tipo 4)
    nat = classificar._best(h)
    if nat == "EMPRE2":   # transferência que sai → split por contraparte
        return "Mútuos a Pagar" if _saida_entre_outras(h, loja) else "Mútuo a Pagar (Entre Grupos)"
    if nat == "DESPU":
        # transferência travestida de despesa → mesmo split de contraparte do EMPRE2
        if "TRANSFER" in h or "TRANFER" in h:
            return "Mútuos a Pagar" if _saida_entre_outras(h, loja) else "Mútuo a Pagar (Entre Grupos)"
        for kws, linha in DESPU_RULES:
            if any(k in h for k in kws):
                return linha
        return "Despesas Gerais"
    return NAT2LINE.get(nat, "Outras Despesas")


def coletar(cur, ano):
    """Retorna {loja: {linha: {dia_int: valor}}} e lista de itens (detalhe)."""
    classificar._best = carregar_naturezas(cur)
    ini, fim = f"{ano}0101", f"{ano+1}0101"
    dados = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # loja->linha->dia->v
    itens = []   # detalhe transacional

    def push(loja, data, linha, valor, razao, hist, nro):
        dia = data.day
        dados[loja][linha][dia] += valor
        itens.append({
            "ano": str(data.year), "mes": f"{data.month:02d}",
            "data": data.strftime("%Y-%m-%d"), "linha": linha,
            "loja": loja, "nroempresa": loja, "valor": round(valor, 2),
            "nomerazao": razao or "", "observacao": (hist or "").strip(),
            "nrotitulo": str(nro or ""), "descricao": linha,
        })

    # SAÍDAS — TIPO 4, por DTLIQUIDA
    cur.execute("""SELECT CONTA, DTLIQUIDA, VLPAGO, TRIM(HISTORICO), TRIM(NOME), NUMERO
                   FROM TITULO WHERE TIPO=4 AND VLPAGO>0
                     AND DTLIQUIDA>=%s AND DTLIQUIDA<%s""", (ini, fim))
    for conta, dtliq, vlpago, hist, nome, nro in cur.fetchall():
        loja = CONTA_LOJA.get((conta or "").strip())
        if not loja:
            continue
        try: data = dt.datetime.strptime(dtliq, "%Y%m%d")
        except (ValueError, TypeError): continue
        linha = classificar(4, hist, loja)
        push(loja, data, linha, -abs(float(vlpago)), nome, hist, nro)

    # ENTRADAS — TIPO 9, por VENCIMENTO (recebíveis não usam DTLIQUIDA)
    cur.execute("""SELECT CONTA, VENCIMENTO, VLPAGO, TRIM(HISTORICO), TRIM(NOME), NUMERO
                   FROM TITULO WHERE TIPO=9 AND VLPAGO>0
                     AND VENCIMENTO>=%s AND VENCIMENTO<%s""", (ini, fim))
    for conta, venc, vlpago, hist, nome, nro in cur.fetchall():
        loja = CONTA_LOJA.get((conta or "").strip()) or loja_de_entrada(hist)
        try: data = dt.datetime.strptime(venc, "%Y%m%d")
        except (ValueError, TypeError): continue
        linha = classificar(9, hist, loja)
        push(loja, data, linha, abs(float(vlpago)), nome, hist, nro)

    # ajustes manuais duráveis (do ano sendo processado)
    for (a, m, dia, loja, linha, valor, desc) in AJUSTES_MANUAIS:
        if a != ano:
            continue
        push(loja, dt.datetime(a, m, dia), linha, abs(float(valor)), "", desc, "")

    # Importação Histórica — aplica snapshot estático de lançamentos que
    # existiam na planilha do controller (Jan-Abr/2026) e não no LUMI.
    aplicar_importacoes_historicas(ano, push)

    return dados, itens


def aplicar_importacoes_historicas(ano, push):
    """Aplica os ajustes do snapshot estático importacoes_historicas_outras.json.
       Marcados como '[IMPORTAÇÃO MANUAL]' no detalhe pra aparecerem destacados."""
    if not os.path.exists(IMPORTACOES_HISTORICAS_JSON):
        return
    try:
        itens = json.load(open(IMPORTACOES_HISTORICAS_JSON, encoding="utf-8"))
    except Exception as e:
        print(f"[import-historico] erro lendo {IMPORTACOES_HISTORICAS_JSON}: {e}")
        return
    n = 0; soma = 0.0
    for it in itens:
        if int(it.get("ano", 0)) != ano: continue
        push(it["loja"], dt.datetime(ano, int(it["mes"]), 1), it["linha"],
             float(it["valor"]),
             "[IMPORTAÇÃO MANUAL]",
             "Lançamento histórico (snapshot da planilha do controller, sem contrapartida no LUMI)",
             "")
        n += 1; soma += float(it["valor"])
    print(f"[import-historico] {n} ajustes aplicados de {os.path.basename(IMPORTACOES_HISTORICAS_JSON)} | R$ {soma:,.2f}")


def montar_doc(ano, mes, valores_por_linha_e_dia, loja=""):
    linha_idx = {l: i for i, l in enumerate(LINHAS)}
    grupo_idx = {g: i for i, g in enumerate(GRUPOS)}
    agrup_idx = {a: i for i, a in enumerate(AGRUPAMENTOS)}
    dias_mes = calendar.monthrange(ano, mes)[1]
    porLinha, accA, accG = [], defaultdict(float), defaultdict(float)
    for linha, grupo, agrup in TAXONOMIA:
        n, g, a = linha_idx[linha], grupo_idx[grupo], agrup_idx[agrup]
        for dia, v in valores_por_linha_e_dia.get(linha, {}).items():
            if round(v, 2) == 0: continue
            d = dia - 1
            porLinha.append({"d": d, "g": g, "a": a, "n": n, "v": round(v, 2)})
            accA[(d, g, a)] += v; accG[(d, g)] += v
    return {
        "ano": ano, "mes": mes, "v": 2, "segmento": "outras", "loja": loja,
        "dim": {"dias": [f"{d:02d}" for d in range(1, dias_mes + 1)],
                "grupos": GRUPOS, "agrupamentos": AGRUPAMENTOS, "linhas": LINHAS},
        "porLinha": porLinha,
        "porAgrupamento": [{"d": d, "g": g, "a": a, "v": round(v, 2)}
                           for (d, g, a), v in accA.items() if abs(v) >= 0.005],
        "porGrupo": [{"d": d, "g": g, "v": round(v, 2)}
                     for (d, g), v in accG.items() if abs(v) >= 0.005],
    }


def main():
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today().year
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = pymysql.connect(**LUMI); cur = conn.cursor()
    dados, itens = coletar(cur, ano)
    conn.close()

    # meses presentes; reagrupa a partir dos itens (que já carregam a data completa)
    meses = sorted({int(it["mes"]) for it in itens})
    por_mes = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))
    det_por_mes = defaultdict(list)
    for it in itens:
        mes = int(it["mes"]); dia = int(it["data"][8:10])
        por_mes[mes][it["loja"]][it["linha"]][dia] += it["valor"]
        det_por_mes[mes].append(it)

    nfiles = 0
    for mes in meses:
        # consolidado (todas as lojas)
        consol = defaultdict(lambda: defaultdict(float))
        for loja in LOJAS:
            for linha, dias in por_mes[mes].get(loja, {}).items():
                for dia, v in dias.items():
                    consol[linha][dia] += v
        doc = montar_doc(ano, mes, consol, loja="")
        with open(f"{OUT_DIR}/{ano}-{mes:02d}.json", "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False); nfiles += 1
        # por loja
        for loja in LOJAS:
            if loja not in por_mes[mes]: continue
            d = montar_doc(ano, mes, por_mes[mes][loja], loja=loja)
            with open(f"{OUT_DIR}/{ano}-{mes:02d}__{loja}.json", "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False); nfiles += 1
        # detalhe
        with open(f"{OUT_DIR}/detalhe_{ano}-{mes:02d}.json", "w", encoding="utf-8") as f:
            json.dump({"items": det_por_mes[mes]}, f, ensure_ascii=False); nfiles += 1

    meta = {
        "geradoEm": dt.datetime.now().isoformat(), "segmento": "outras", "fonte": "LUMI/MySQL (SAC)",
        "dimensoes": {"anos": [ano], "meses": meses, "lojas": LOJAS,
                      "grupos": GRUPOS, "agrupamentos": AGRUPAMENTOS, "linhas": LINHAS},
        "taxonomia": [{"nome": l, "grupo": g, "agrupamento": a} for l, g, a in TAXONOMIA],
        "obs": "Direto do banco LUMI. Saídas por DTLIQUIDA; entradas (TIPO9) por VENCIMENTO. "
               "Loja = banco do título (CONTA). Sem receitas de venda (não estão no LUMI).",
    }
    with open(f"{OUT_DIR}/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"✓ Outras (LUMI): {nfiles+1} arquivos em {OUT_DIR}  | meses {meses}")


if __name__ == "__main__":
    main()
