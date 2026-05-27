#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ledger de TRANSFERÊNCIAS entre grupos (Intercompany) — fonte: LUMI (base SAC).

Produz dados_fluxo_intercompany/transferencias.json com 3 blocos pro relatório:
  • recebimentos : entradas de transferência/mútuo (TIPO 9)
  • pagamentos   : saídas de transferência/mútuo (TIPO 4, EMPRE2/TRANSFER)
  • conciliacao  : casa cada pagamento (origem→destino, valor, data) com um
                   recebimento de mesmo valor e data próxima. O que não casa
                   fica como contrapartida PENDENTE (ex.: saída p/ posto cujo
                   recebimento é registrado no sistema do posto, fora do LUMI).

Cada transferência tem origem e destino:
  • SAÍDA  (TIPO 4): origem = banco do título (CONTA→loja das outras),
                     destino = token após "PARA" no histórico.
  • ENTRADA(TIPO 9): "X PARA Y" → origem X, destino Y; "MUTUO A RECEBER X" →
                     origem X, destino "" (recebedor é uma das outras, hub CVL).

Segmento de cada entidade: as 5 'outras' (FLUXO/LP/PEGUI/RETA/TARES) = Outras;
qualquer outro token = Posto/Externo (supermercados não são separáveis no LUMI).

Uso: LUMI_PW=xxxx python3 gera_transferencias_intercompany.py [ano]
"""
import os, sys, re, json, datetime as dt
import pymysql

LUMI = dict(host=os.environ.get("LUMI_HOST", "10.17.0.100"),
            port=int(os.environ.get("LUMI_PORT", "3306")),
            user=os.environ.get("LUMI_USER", "sac"),
            password=os.environ.get("LUMI_PW", "2713"),
            database="SAC", connect_timeout=10, charset="utf8mb4")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_fluxo_intercompany")
CONTA_LOJA = {"0004": "FLUXO", "0006": "LP", "0008": "LP", "0007": "TARES", "0009": "PEGUI", "0010": "RETA"}
OUTRAS = {"FLUXO", "LP", "PEGUI", "RETA", "TARES"}
MATCH_DIAS = 15   # janela de data pra casar as duas pernas

# Supermercados (Firestore rawOracle/{ym}__fluxo_pago) — incluímos no relatório
# de Controle de Mútuos APENAS os mútuos/empréstimos (CODESPECIE MUTPAG/MUTREC).
# "Todo o restante fica apartado" — pedido do usuário 2026-05-26.
SERVICE_ACCT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serviceAccount.json")
PROJECT_ID = "projeto-686e2"
SUPER_CODS = {"MUTPAG", "MUTREC"}
# Razões que identificam "Entre Grupos" no super (espelho do dashboard.html).
SUPER_GRUPOS_HOLDINGS = ["WITHI PARTICIPACOES", "TIGO HOLDING"]
SUPER_GRUPOS_DEMAIS   = ["AUTO POSTO IRMAOS PACIFICOS", "PEGUI COMERCIAL", "TAVARES CONSTRUTORA"]


def is_transfer(h):
    h = (h or "").upper()
    return ("TRANSFER" in h or "TRANFER" in h or h.startswith("EMPRE2")
            or h.startswith("MUTUO") or h.startswith("MÚTUO"))


def segmento(ent):
    if not ent:
        return ""
    return "Outras" if ent in OUTRAS else "Posto/Externo"


def seg_contraparte_super(razao):
    """Classifica a contraparte (NOMERAZAO) de um mútuo do super.
       Razões em SUPER_GRUPOS* = Supermercado (entre grupos); demais = externo."""
    r = (razao or "").upper()
    if any(p in r for p in SUPER_GRUPOS_HOLDINGS) or any(p in r for p in SUPER_GRUPOS_DEMAIS):
        return "Supermercado"
    if any(o in r for o in OUTRAS):
        return "Outras"
    return "Posto/Externo"


def _parse_data(s):
    """Aceita 'YYYY-MM-DD...', 'DD/MM/YYYY...' ou Timestamp do Firestore."""
    if s is None:
        return ""
    # Firestore Timestamp → tem .isoformat()
    iso = getattr(s, "isoformat", None)
    if callable(iso):
        s = iso()
    s = str(s).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    if re.match(r'^\d{2}/\d{2}/\d{4}', s):
        return f"{s[6:10]}-{s[3:5]}-{s[0:2]}"
    return ""


def coletar_super_mutuos(ano):
    """Lê mútuos (MUTPAG/MUTREC) do Supermercados do Firestore (rawOracle).
       Devolve (pagamentos, recebimentos) no mesmo schema do LUMI."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print("[super] firebase_admin ausente — pulando mútuos do Supermercados.")
        return [], []
    if not os.path.exists(SERVICE_ACCT):
        print("[super] serviceAccount.json não encontrado — pulando mútuos do Supermercados.")
        return [], []
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(SERVICE_ACCT), {"projectId": PROJECT_ID})
    db = firestore.client()
    # NROEMPRESA → loja descritiva (L01..L117)
    try:
        dim = (db.collection("meta").document("dimensoes").get().to_dict() or {})
        epl = dim.get("empresaParaLoja") or {}
    except Exception as e:
        print(f"[super] falha lendo meta/dimensoes: {e}")
        epl = {}

    pagamentos, recebimentos = [], []
    for mes in range(1, 13):
        ym = f"{ano}-{mes:02d}"
        try:
            ref = db.collection("rawOracle").document(f"{ym}__fluxo_pago")
            snap = ref.get()
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            rows = list(data.get("rows") or [])
            if data.get("chunked"):
                rows = []
                for c in ref.collection("chunks").stream():
                    rows.extend((c.to_dict() or {}).get("rows") or [])
        except Exception as e:
            print(f"[super] {ym}: erro lendo rawOracle: {e}")
            continue
        for r in rows:
            cod = r.get("CODESPECIE") or r.get("codespecie")
            if cod not in SUPER_CODS:
                continue
            valor_raw = r.get("VLROPERACAO") or r.get("vlroperacao") or 0
            try: v = round(abs(float(valor_raw)), 2)
            except (TypeError, ValueError): continue
            if v <= 0:
                continue
            nro = str(r.get("NROEMPRESA") or r.get("nroempresa") or "")
            loja = epl.get(nro) or (f"Empresa {nro}" if nro else "")
            razao = (r.get("NOMERAZAO") or r.get("nomerazao") or "").strip()
            nrotit = str(r.get("NROTITULO") or r.get("nrotitulo") or "")
            obs = (r.get("OBSERVACAO") or r.get("observacao") or "").strip()
            data_str = _parse_data(r.get("DTAQUITACAO") or r.get("dtaquitacao")
                                   or r.get("DTACONTABILIZA") or r.get("dtacontabiliza")
                                   or r.get("DTAOPERACAO") or r.get("dtaoperacao"))
            if not data_str:
                continue
            hist = f"{cod} {razao}".strip() + (f" — {obs}" if obs else "")
            seg_cp = seg_contraparte_super(razao)
            if cod == "MUTPAG":
                pagamentos.append({"data": data_str, "valor": v,
                                   "origem": loja, "destino": razao,
                                   "origemSeg": "Supermercado", "destinoSeg": seg_cp,
                                   "historico": hist, "titulo": nrotit, "nome": razao})
            else:  # MUTREC
                recebimentos.append({"data": data_str, "valor": v,
                                     "origem": razao, "destino": loja,
                                     "origemSeg": seg_cp, "destinoSeg": "Supermercado",
                                     "historico": hist, "titulo": nrotit, "nome": razao})
    return pagamentos, recebimentos


def parse_saida(conta, historico):
    origem = CONTA_LOJA.get((conta or "").strip(), "?")
    h = (historico or "").upper()
    m = re.search(r'PARA\s+([A-ZÇÃÕ0-9]+)', h)
    destino = m.group(1) if m else ""
    # casos "X - Y", "ENTRE X E Y", "POSTO X-RETA"
    if not destino:
        toks = [t for t in re.findall(r'[A-ZÇÃÕ]+', h) if t in OUTRAS]
        toks = [t for t in toks if t != origem]
        destino = toks[0] if toks else ""
    return origem, destino


def parse_entrada(historico):
    h = (historico or "").upper()
    m = re.search(r'([A-ZÇÃÕ0-9]+)\s+PARA\s+([A-ZÇÃÕ0-9]+)', h)
    if m:
        return m.group(1), m.group(2)
    # "MUTUO A RECEBER X" / "MUTUO A DEVOLVER X" → origem X, destino = hub (vazio)
    m = re.search(r'(?:MUTUO|MÚTUO)\s+A\s+\w+\s+([A-ZÇÃÕ0-9]+)', h)
    if m:
        return m.group(1), ""
    return "", ""


def coletar(cur, ano):
    ini, fim = f"{ano}0101", f"{ano+1}0101"
    pagamentos, recebimentos = [], []
    cur.execute("""SELECT TIPO,CONTA,DTLIQUIDA,VENCIMENTO,VLPAGO,TRIM(HISTORICO),NUMERO,TRIM(NOME)
                   FROM TITULO WHERE VLPAGO>0 AND (
                     (TIPO=4 AND DTLIQUIDA>=%s AND DTLIQUIDA<%s) OR
                     (TIPO=9 AND VENCIMENTO>=%s AND VENCIMENTO<%s))""", (ini, fim, ini, fim))
    for tipo, conta, dtl, venc, vlpago, hist, nro, nome in cur.fetchall():
        if not is_transfer(hist):
            continue
        v = round(float(vlpago), 2)
        if tipo == 4:
            data = dtl
            origem, destino = parse_saida(conta, hist)
            pagamentos.append({"data": f"{data[:4]}-{data[4:6]}-{data[6:8]}", "valor": v,
                               "origem": origem, "destino": destino,
                               "origemSeg": segmento(origem), "destinoSeg": segmento(destino),
                               "historico": hist, "titulo": str(nro or ""), "nome": nome or ""})
        else:
            data = venc
            origem, destino = parse_entrada(hist)
            recebimentos.append({"data": f"{data[:4]}-{data[4:6]}-{data[6:8]}", "valor": v,
                                 "origem": origem, "destino": destino,
                                 "origemSeg": segmento(origem), "destinoSeg": segmento(destino),
                                 "historico": hist, "titulo": str(nro or ""), "nome": nome or ""})
    return pagamentos, recebimentos


def _d(s):
    return dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def conciliar(pagamentos, recebimentos):
    """Casa pagamento↔recebimento por 2 regras (em ordem de confiança):
       (A) Super-interno: ambos lados são Supermercado (origemSeg/destinoSeg) E
           mesmo NROTITULO + valor + data±janela — a mesma operação registrada
           pelas duas empresas no rawOracle.
       (B) Origem casada: mesma ORIGEM (pagador) + valor + data, com destino
           compatível (igual, ou recebimento sem destino só entre 'outras').
       Greedy, prioriza score menor (rank A < B; depois data mais próxima)."""
    usados = set()
    conciliados, pend_pag = [], []
    ordem = sorted(range(len(pagamentos)), key=lambda i: pagamentos[i]["data"])
    for pi in ordem:
        p = pagamentos[pi]
        melhor, melhor_score = None, None
        for ri in range(len(recebimentos)):
            if ri in usados:
                continue
            r = recebimentos[ri]
            if r["valor"] != p["valor"]:
                continue
            dif = abs((_d(p["data"]) - _d(r["data"])).days)
            if dif > MATCH_DIAS:
                continue
            # Regra A — par super-interno: NROTITULO (lote) + valor + data + as
            # CONTRAPARTES ESPELHADAS. Sem o espelhamento, um mesmo lote com
            # vários valores iguais gera falsos pares.
            super_pair = (p.get("origemSeg") == "Supermercado"
                          and r.get("destinoSeg") == "Supermercado"
                          and p.get("titulo") and r.get("titulo") and p["titulo"] == r["titulo"]
                          and p.get("destino") and p["destino"] == r.get("origem")
                          and p.get("origem")  and p["origem"]  == r.get("destino"))
            if super_pair:
                score = (0, dif)
            elif p["origem"] and p["origem"] == r["origem"]:
                # Regra B — origem (pagador) é a mesma
                if r["destino"]:
                    if p["destino"] and r["destino"] != p["destino"]:
                        continue
                else:
                    # recebimento sem destino só casa quando o pagamento é entre 'outras'
                    if p["destino"] not in OUTRAS:
                        continue
                destino_ok = 0 if (r["destino"] and p["destino"] and r["destino"] == p["destino"]) else 1
                score = (1, destino_ok, dif)
            else:
                continue
            if melhor_score is None or score < melhor_score:
                melhor, melhor_score = ri, score
        if melhor is not None:
            usados.add(melhor)
            r = recebimentos[melhor]
            conciliados.append({"valor": p["valor"], "difDias": melhor_score[-1],
                                "regra": "titulo-super" if melhor_score[0] == 0 else "origem",
                                "pagamento": p, "recebimento": r})
        else:
            pend_pag.append(p)
    pend_rec = [recebimentos[ri] for ri in range(len(recebimentos)) if ri not in usados]
    return conciliados, pend_pag, pend_rec


def main():
    ano = int(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today().year
    os.makedirs(OUT, exist_ok=True)
    conn = pymysql.connect(**LUMI); cur = conn.cursor()
    pagamentos, recebimentos = coletar(cur, ano)
    conn.close()
    # SUPER: traz só os mútuos/empréstimos (MUTPAG/MUTREC) do Firestore p/ o
    # Controle de Mútuos. Todo o restante do super fica APARTADO (não vem).
    sup_pag, sup_rec = coletar_super_mutuos(ano)
    pagamentos.extend(sup_pag)
    recebimentos.extend(sup_rec)
    conciliados, pend_pag, pend_rec = conciliar(pagamentos, recebimentos)

    def soma(xs, k="valor"):
        return round(sum(x[k] for x in xs), 2)
    resumo = {
        "totalPagamentos": soma(pagamentos), "nPagamentos": len(pagamentos),
        "totalRecebimentos": soma(recebimentos), "nRecebimentos": len(recebimentos),
        "totalConciliado": round(sum(c["valor"] for c in conciliados), 2), "nConciliados": len(conciliados),
        "totalPendentePagamento": soma(pend_pag), "nPendentePagamento": len(pend_pag),
        "totalPendenteRecebimento": soma(pend_rec), "nPendenteRecebimento": len(pend_rec),
    }
    out = {"ano": ano, "geradoEm": dt.datetime.now().isoformat(), "fonte": "LUMI/MySQL (SAC)",
           "recebimentos": sorted(recebimentos, key=lambda x: x["data"]),
           "pagamentos": sorted(pagamentos, key=lambda x: x["data"]),
           "conciliacao": {"conciliados": conciliados, "pendentesPagamento": pend_pag,
                           "pendentesRecebimento": pend_rec},
           "resumo": resumo}
    json.dump(out, open(os.path.join(OUT, "transferencias.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("✓ transferencias.json gerado")
    for k, v in resumo.items():
        print(f"   {k}: {v:,.2f}" if isinstance(v, float) else f"   {k}: {v}")


if __name__ == "__main__":
    main()
