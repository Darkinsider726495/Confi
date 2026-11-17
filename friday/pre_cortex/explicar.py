"""Raciocínio operacional observável: as 12 perguntas auditáveis, respondidas SÓ com o que está no dossiê (dados e eventos reais), nunca com texto fixo.

Cada resposta traz `itens` (cada um com `tipo` — fato, inferência, hipótese ou desconhecido — e a `fonte` dentro do dossiê) e, quando a fase ainda não rodou, diz isso em vez de inventar.
O que o painel mostra e o que `perguntas()` devolve vêm da mesma função: não há uma explicação «bonita» separada do que aconteceu.
"""
from . import dossie as D

PERGUNTAS = (
    "O que estou tentando resolver?", "Quais fatos conheço?", "Quais informações estão ausentes?", "Quais hipóteses estou considerando?", "Que evidências sustentam essas hipóteses?",
    "Quais alternativas existem?", "Qual resultado espero de cada etapa?", "O que pode dar errado?", "Por que selecionei esta estratégia?", "Como vou verificar se ela funcionou?",
    "O que aprendi com o resultado observado?", "O que mudou no plano depois dessa experiência?")


def _it(texto, tipo, fonte):
    return {"texto": str(texto), "tipo": tipo, "fonte": fonte}


def _plano(d):
    for p in d.get("planos") or []:
        if p["versao"] == d.get("plano_atual"):
            return p
    return None


def _pend(fase):
    return {"disponivel": False, "resposta": f"ainda não sei: a fase «{fase}» não rodou neste objetivo.", "itens": [], "fontes": []}


def _q1(d):
    i = d.get("interpretacao")
    if not i:
        return _pend("interpretação")
    itens = [_it(f"pedido recebido: «{d['descricao']}»", "fato", "dossie.descricao"), _it(f"entendido como «{i.get('tipo_objetivo')}»", "inferencia", "dossie.interpretacao.tipo_objetivo"),
             _it(f"resultado esperado: {i.get('resultado_esperado') or '—'}", "inferencia", "dossie.interpretacao.resultado_esperado")]
    itens += [_it(f"restrição: {r}", "fato", "dossie.interpretacao.restricoes") for r in i.get("restricoes") or []]
    itens += [_it(f"critério de conclusão: {c}", "inferencia", "dossie.criterios_de_conclusao") for c in d.get("criterios_de_conclusao") or []]
    return {"disponivel": True, "resposta": f"Resolver o pedido «{d['descricao'][:140]}» ({D.ROTULO_ESTADO.get(d['estado'], d['estado'])}). Origem: {d['origem'].replace('_', ' ')}. Esperado: {i.get('resultado_esperado') or '—'}.",
            "itens": itens, "fontes": ["interpretacao", "criterios_de_conclusao"]}


def _q2(d):
    i, c = d.get("interpretacao"), d.get("contexto")
    if not i:
        return _pend("interpretação")
    itens = [_it(f"{x['nome']} = {x['valor']} ({x['fonte']})", "fato", "dossie.interpretacao.campos") for x in i.get("campos") or [] if x.get("tipo") == "fato"]
    if c:
        itens += [_it(f["texto"], "fato", f"contexto.fatos ← {f.get('origem')}") for f in c.get("fatos") or [] if f.get("tipo") == "fato"]
    for p in d.get("planos") or []:
        ex, ve = p.get("execucao"), p.get("verificacao")
        if ex:
            itens.append(_it(f"o corretor terminou a tarefa {ex.get('tarefa')} como «{ex.get('rotulo')}» (plano v{p['versao']}) — isto é o que a ferramenta disse, não prova do efeito", "fato", "execucao.observar"))
        if ve:
            itens.append(_it(f"leitura independente do plano v{p['versao']}: {ve.get('observado_resumo')}", "fato", f"verificacao ← {ve.get('fonte')}"))
    return {"disponivel": True, "resposta": f"{len(itens)} fato(s) observados ou lidos diretamente (inferências e hipóteses ficam em listas separadas).", "itens": itens, "fontes": ["interpretacao.campos", "contexto.fatos", "planos[].verificacao"]}


def _q3(d):
    i, c = d.get("interpretacao"), d.get("contexto")
    if not i:
        return _pend("interpretação")
    itens = [_it(f"não foi dito: {f}", "desconhecido", "interpretacao.faltando") for f in i.get("faltando") or []]
    itens += [_it(f"assumi {s['valor']} para «{s['campo']}»: {s['motivo']}", "hipotese", "interpretacao.suposicoes") for s in i.get("suposicoes") or []]
    if c:
        itens += [_it(x["texto"], "desconhecido", f"contexto.desconhecidos ← {x.get('origem')}") for x in c.get("desconhecidos") or []]
    h = d.get("hipoteses") or {}
    vistos = set()
    for x in h.get("hipoteses") or []:
        for inc in x.get("incertezas") or []:
            if inc not in vistos:
                vistos.add(inc)
                itens.append(_it(f"«{x['estrategia']}»: {inc}", "desconhecido", "hipoteses[].incertezas"))
    for dg in d.get("degradado") or []:
        itens.append(_it(f"módulo «{dg['modulo']}» indisponível: {dg['consequencia']}", "desconhecido", "dossie.degradado"))
    return {"disponivel": True, "resposta": f"{len(itens)} lacuna(s) conhecida(s)." if itens else "Nenhuma lacuna declarada pelos módulos (isso não garante que não existam outras).", "itens": itens,
            "fontes": ["interpretacao.faltando", "interpretacao.suposicoes", "contexto.desconhecidos", "hipoteses[].incertezas"]}


def _q4(d):
    h = d.get("hipoteses")
    if not h:
        return _pend("hipóteses")
    itens = []
    for x in h.get("hipoteses") or []:
        c = x["confianca"]
        itens.append(_it(f"{x['texto']} — confiança {c['valor']:.2f} ({c['n']} registro(s); não calibrada); previsão: {x['previsao']['texto']}; status: {x['status']}", "hipotese", f"hipoteses[{x['id']}]"))
    for x in (d.get("contexto") or {}).get("hipoteses_previas") or []:
        itens.append(_it(f"de registros anteriores: {x['texto']} (resultado então: {x.get('resultado')})", "hipotese", x.get("origem", "contexto.hipoteses_previas")))
    if h.get("degradado"):
        return {"disponivel": True, "resposta": "O módulo de hipóteses estava indisponível: não comparei hipóteses; usei a ordem do catálogo.", "itens": itens, "fontes": ["hipoteses"]}
    return {"disponivel": True, "resposta": f"{len(h.get('hipoteses') or [])} hipótese(s) sobre qual estratégia cumpre o objetivo, uma por estratégia viável.", "itens": itens, "fontes": ["hipoteses.hipoteses"]}


def _q5(d):
    h = d.get("hipoteses")
    if not h:
        return _pend("hipóteses")
    itens = []
    for x in h.get("hipoteses") or []:
        for e in x.get("evidencias_a_favor") or []:
            itens.append(_it(f"a favor de «{x['estrategia']}»: {e['texto']}", e.get("tipo", "fato"), e.get("fonte", "")))
        for e in x.get("evidencias_contra") or []:
            itens.append(_it(f"contra «{x['estrategia']}»: {e['texto']}", e.get("tipo", "fato"), e.get("fonte", "")))
    return {"disponivel": True, "resposta": (f"{len(itens)} evidência(s) registradas, cada uma com a fonte; onde não há experiência, a hipótese diz «sem experiência» e vale 0,50." if itens else "Nenhuma evidência registrada para as hipóteses."),
            "itens": itens, "fontes": ["hipoteses[].evidencias_a_favor", "hipoteses[].evidencias_contra"]}


def _q6(d):
    p, h = _plano(d), d.get("hipoteses")
    if not p and not h:
        return _pend("plano")
    esc = (p["plano"].get("escolha") if p else None) or (h or {}).get("escolha") or {}
    itens = [_it(f"«{r['id']}» (posição {r['posicao']}): {r['motivo']}", "inferencia", "escolha.ranking") for r in esc.get("ranking") or [] if r["id"] != esc.get("escolhida")]
    itens += [_it(f"«{x['id']}» fora da fila: {x['motivo']}", "fato", "escolha.excluidas") for x in esc.get("excluidas") or []]
    for t in d.get("tentativas_anteriores") or []:
        itens.append(_it(f"«{t['estrategia']}» já foi tentada neste objetivo: {t['resultado']} ({t.get('motivo')})", "fato", "dossie.tentativas_anteriores"))
    return {"disponivel": True, "resposta": f"{len(itens)} alternativa(s) ou estratégia(s) fora da fila, além de «{esc.get('escolhida')}»." if itens else "Não há outra estratégia permitida para este objetivo.", "itens": itens,
            "fontes": ["plano.alternativas", "escolha.ranking", "escolha.excluidas"]}


def _q7(d):
    p = _plano(d)
    if not p:
        return _pend("plano")
    pl = p["plano"]
    itens = [_it(f"{e['id']} {e['descricao']} → esperado: {e['resultado_esperado']}", "hipotese" if e["tipo"] in ("execucao", "verificacao") else "inferencia", f"plano.v{pl['versao']}.etapas[{e['id']}]") for e in pl["etapas"]]
    itens += [_it(f"critério {c['id']}: {c['descricao']}", "inferencia", "plano.criterios_de_sucesso") for c in pl["criterios_de_sucesso"]]
    return {"disponivel": True, "resposta": f"Plano v{pl['versao']} com {len(pl['etapas'])} etapa(s); o resultado esperado de cada uma está abaixo e a previsão vira critério conferível.", "itens": itens, "fontes": ["plano.etapas", "plano.previsao"]}


def _q8(d):
    p = _plano(d)
    if not p:
        return _pend("plano")
    pl, cr = p["plano"], p.get("critica")
    itens = [_it(r["texto"], r.get("tipo", "hipotese") if r.get("tipo") != "evidencia_contra" else "fato", r.get("fonte", "")) for r in pl["riscos_e_incertezas"]]
    if cr:
        itens += [_it(f"exige o dono: {e['motivo']}", "fato", f"critica ← {e['fonte']}") for e in cr.get("exigencias_de_autorizacao") or []]
        itens += [_it(f"regra falhou: {c['regra']}: {c['detalhe']}", "fato", "critica.checagens") for c in cr["checagens"] if not c["ok"]]
    itens += [_it(f"interrompo se: {c}", "inferencia", "plano.condicoes_para_interromper") for c in pl["condicoes_para_interromper"]]
    return {"disponivel": True, "resposta": f"{len(pl['riscos_e_incertezas'])} risco(s)/incerteza(s) no plano" + (f"; a crítica disse «{cr['veredito']}»." if cr else "; a crítica ainda não rodou."), "itens": itens,
            "fontes": ["plano.riscos_e_incertezas", "critica.checagens", "plano.condicoes_para_interromper"]}


def _q9(d):
    p = _plano(d)
    if not p:
        return _pend("plano")
    pl = p["plano"]
    esc = pl.get("escolha") or {}
    r = next((x for x in esc.get("ranking") or [] if x["id"] == pl.get("estrategia")), None)
    itens = [_it(f"regra: {esc.get('regra')}", "fato", "escolha.regra")]
    if r:
        itens.append(_it(f"«{r['id']}»: {r['motivo']} ({r['n']} registro(s) compatíveis; condições: {', '.join(f'{k}={v}' for k, v in (r.get('condicoes_da_contagem') or {}).items())})", "fato", "escolha.ranking"))
    if pl.get("revisao"):
        for m in pl["revisao"]["mudou"]:
            itens.append(_it(f"mudei de «{m['de']}» para «{m['para']}»: {m['motivo']}", "fato", "plano.revisao"))
    return {"disponivel": True, "resposta": f"Escolhi «{pl.get('estrategia')}»" + (f" porque {r['motivo']}" if r else "") + ". A confiança é uma contagem, não uma probabilidade calibrada.", "itens": itens, "fontes": ["plano.escolha", "plano.revisao"]}


def _q10(d):
    p = _plano(d)
    if not p:
        return _pend("plano")
    pl = p["plano"]
    itens = [_it(f"{v['id']}: {v['como']} (executor: {v['executor']}; fonte independente: {'sim' if v['fonte_independente'] else 'não'})", "inferencia", "plano.criterios_de_verificacao") for v in pl["criterios_de_verificacao"]]
    itens += [_it(f"critério {c['id']}: {c['descricao']}", "inferencia", "plano.criterios_de_sucesso") for c in pl["criterios_de_sucesso"]]
    return {"disponivel": True, "resposta": "Releio o armazenamento real por outro módulo, depois da execução, e comparo com cada critério. «A ferramenta respondeu ok» não conta como prova." if pl.get("executavel") else
            "Reconfiro o conteúdo gerado contra os parâmetros pedidos (nada é executado neste plano).", "itens": itens, "fontes": ["plano.criterios_de_verificacao", "plano.criterios_de_sucesso"]}


def _q11(d):
    ap = [p for p in d.get("planos") or [] if p.get("verificacao")]
    if not ap:
        return {"disponivel": False, "resposta": "ainda não há resultado observado para aprender: a verificação independente não rodou.", "itens": [], "fontes": []}
    itens = []
    for p in ap:
        v, a = p["verificacao"], p.get("aprendizagem") or {}
        itens.append(_it(f"plano v{p['versao']} («{p['plano'].get('estrategia')}»): {v['veredito']} — {v.get('observado_resumo')}", "fato", "planos[].verificacao"))
        for c in a.get("comparacao") or []:
            itens.append(_it(f"previsto «{c['previsto']}» × observado {c['observado']} → {'confere' if c['ok'] else 'NÃO confere' if c['ok'] is False else 'inconclusivo'}", "fato", "aprendizagem.comparacao"))
        for f in a.get("fatores") or []:
            itens.append(_it(f["texto"], f["tipo"], "aprendizagem.fatores"))
        for l in a.get("licoes") or []:
            itens.append(_it(l["texto"] + (f" [revisável se: {l['revisavel_se']}]" if l.get("revisavel_se") else ""), l["tipo"], "aprendizagem.licoes"))
        for q in a.get("investigar") or []:
            itens.append(_it(f"a investigar: {q}", "desconhecido", "aprendizagem.investigar"))
        if (a.get("efeito_na_selecao") or {}).get("texto"):
            itens.append(_it(a["efeito_na_selecao"]["texto"], "fato", "aprendizagem.efeito_na_selecao"))
    ultimo = ap[-1].get("aprendizagem") or {}
    return {"disponivel": True, "resposta": (f"Registrei {ultimo.get('id')}: {ultimo.get('resultado')}. " if ultimo.get("registrado") else "A lição desta tentativa não foi registrada. ")
            + "Uma observação não vira regra: as lições ficam como hipóteses revisáveis.", "itens": itens, "fontes": ["planos[].verificacao", "planos[].aprendizagem"]}


def _q12(d):
    ps = d.get("planos") or []
    itens = []
    for p in ps:
        rev = p["plano"].get("revisao")
        if rev:
            for m in rev["mudou"]:
                itens.append(_it(f"plano v{rev['de_versao']} → v{rev['para_versao']}: «{m['de']}» → «{m['para']}» — {m['motivo']}", "fato", f"planos[v{p['versao']}].revisao"))
    for t in d.get("tentativas_anteriores") or []:
        itens.append(_it(f"depois de «{t['estrategia']}» ({t['resultado']}): a lição {t.get('aprendizado') or '—'} entrou na contagem e mudou a ordem das estratégias", "fato", "dossie.tentativas_anteriores"))
    for x in d.get("historico_decisoes") or []:
        if x["quem"] == "coordenacao" and x["decisao"].startswith("replanejar"):
            itens.append(_it(f"{x['decisao']}: {x['motivo']}", "fato", "dossie.historico_decisoes"))
    if not ps:
        return _pend("plano")
    return {"disponivel": True, "resposta": (f"O plano foi revisado {len(ps) - 1} vez(es) depois de experiência." if len(ps) > 1 else "Ainda nada mudou no plano: houve uma única versão."), "itens": itens, "fontes": ["planos[].revisao", "tentativas_anteriores"]}


_RESPOSTAS = (_q1, _q2, _q3, _q4, _q5, _q6, _q7, _q8, _q9, _q10, _q11, _q12)


def perguntas(d):
    """As 12 perguntas, na ordem da missão, respondidas só com o dossiê."""
    return [{"n": i + 1, "pergunta": PERGUNTAS[i], **f(d)} for i, f in enumerate(_RESPOSTAS)]


# ---------------------------------------------------------------------- visão compacta para o painel
def _etapas(d, p):
    fase = d.get("fase")
    pl = p["plano"]
    est = {}
    est["e1"] = "concluida" if p.get("coerencia") and p["coerencia"].get("coerente") else ("falhou" if p.get("coerencia") else ("atual" if fase == "revisao" else "pendente"))
    cr = p.get("critica")
    est["e2"] = ("concluida" if cr["veredito"] == "aprovado" else "falhou") if cr else ("atual" if fase == "revisao" else "pendente")
    au = p.get("autorizacao")
    est["e3"] = ("concluida" if au and au["estado"] in ("concedida", "dispensada") else "falhou" if au and au["estado"] == "negada" else "aguardando" if d["estado"] == "aguardando_autorizacao" else
                 "atual" if fase == "autorizacao" else "pendente")
    if not pl.get("executavel"):
        est["e3"] = "concluida" if d["estado"] == "plano_pronto" else est["e3"]
    ex = p.get("execucao")
    est["e4"] = (("concluida" if ex["estado"] == "CONCLUIDA" else "falhou") if ex else ("aguardando" if d["estado"] == "aguardando_confirmacao_do_corretor" else "atual" if fase == "execucao" else "pendente"))
    ve = p.get("verificacao")
    est["e5"] = (("concluida" if ve["veredito"] == "sucesso" else "falhou" if ve["veredito"] in ("parcial", "falha_total") else "inconclusiva") if ve else ("atual" if fase == "verificacao" else "pendente"))
    ap = p.get("aprendizagem")
    est["e6"] = ("concluida" if ap and ap.get("registrado") else "falhou") if ap else ("atual" if fase == "aprendizagem" else "pendente")
    return [{"id": e["id"], "tipo": e["tipo"], "descricao": e["descricao"], "feito_por": e["feito_por"], "depende_de": e["depende_de"], "resultado_esperado": e["resultado_esperado"], "estado": est.get(e["id"], "pendente")} for e in pl["etapas"]]


def detalhe(d, agora):
    """Tudo que o painel precisa de UM objetivo, tirado do dossiê."""
    p = _plano(d)
    h = d.get("hipoteses") or {}
    ordem = D.FASES
    fi = ordem.index(d["fase"]) if d["fase"] in ordem else 0
    fases = [{"fase": f, "estado": "concluida" if i < fi or d["estado"] == "concluido" else ("atual" if i == fi else "pendente")} for i, f in enumerate(ordem[:-1])]
    uso = d["uso"]
    pausa = uso["pausas_s"] + ((agora - uso["pausa_desde"]) if uso.get("pausa_desde") else 0.0)
    out = {"resumo": D.resumo(d),
           "objetivo": {"id": d["id"], "descricao": d["descricao"], "origem": d["origem"], "prioridade": d["prioridade"], "estado": d["estado"], "rotulo": D.ROTULO_ESTADO.get(d["estado"], d["estado"]), "fase": d["fase"],
                        "proxima_etapa": d["proxima_etapa"], "restricoes": d["restricoes"], "recursos": d["recursos"], "resultado_esperado": d["resultado_esperado"], "criterios_de_conclusao": d["criterios_de_conclusao"],
                        "dependencias": d["dependencias"], "historico_decisoes": d["historico_decisoes"][-14:], "so_planejar": d["so_planejar"], "bloqueio": d["bloqueio"], "degradado": d["degradado"],
                        "resultado_final": d["resultado_final"]},
           "uso": {"mensagens": uso["mensagens"], "nos": uso["nos"], "replanos": uso["replanos"], "revisoes_critica": uso["revisoes_critica"], "tempo_ativo_s": round(max(0.0, agora - uso["inicio"] - pausa), 2),
                   "limites": d["limites"]},
           "fases": fases, "grafo": d["grafo"][-40:], "interpretacao": d.get("interpretacao"),
           "hipoteses": [{"id": x["id"], "estrategia": x["estrategia"], "texto": x["texto"], "confianca": x["confianca"], "a_favor": len(x["evidencias_a_favor"]), "contra": len(x["evidencias_contra"]),
                          "incertezas": x["incertezas"], "previsao": x["previsao"], "condicoes_de_revisao": x["condicoes_de_revisao"], "status": x["status"], "posicao": x["posicao"], "viavel": x["viavel"],
                          "evidencias_a_favor": x["evidencias_a_favor"], "evidencias_contra": x["evidencias_contra"]} for x in h.get("hipoteses") or []],
           "escolha": {k: (h.get("escolha") or {}).get(k) for k in ("escolhida", "regra", "ranking", "excluidas", "faixa_tamanho", "condicoes")} if h else None,
           "tentativas": d["tentativas_anteriores"], "aprendizados": d["aprendizados"], "verificacoes": d["verificacoes"], "autorizacao": d.get("autorizacao"),
           "planos": [{"versao": q["versao"], "hash": q["hash"], "estrategia": q["plano"].get("estrategia"), "critica": (q.get("critica") or {}).get("veredito"),
                       "resultado": (q.get("verificacao") or {}).get("veredito"), "aprendizado": (q.get("aprendizagem") or {}).get("id")} for q in d["planos"]]}
    if p:
        pl = p["plano"]
        cr = p.get("critica")
        out["plano"] = {"versao": pl["versao"], "hash": pl["hash"], "estrategia": pl.get("estrategia"), "executavel": pl.get("executavel"), "objetivo": pl["objetivo"], "etapas": _etapas(d, p),
                        "criterios_de_sucesso": pl["criterios_de_sucesso"], "previsao": pl["previsao"], "riscos": pl["riscos_e_incertezas"], "alternativas": pl["alternativas"],
                        "condicoes_para_interromper": pl["condicoes_para_interromper"], "criterios_de_verificacao": pl["criterios_de_verificacao"], "revisao": pl.get("revisao"),
                        "estado_inicial": {"fatos": len(pl["estado_inicial"]["fatos"]), "desconhecidos": len(pl["estado_inicial"]["desconhecidos"])},
                        "critica": ({"veredito": cr["veredito"], "resumo": cr["resumo"], "regras": [{"regra": c["regra"], "ok": c["ok"], "detalhe": c["detalhe"]} for c in cr["checagens"]],
                                     "exigencias": cr["exigencias_de_autorizacao"], "efeitos": cr["efeitos_avaliados"]} if cr else None),
                        "coerencia": p.get("coerencia"), "execucao": p.get("execucao"),
                        "verificacao": ({k: p["verificacao"].get(k) for k in ("veredito", "observado_resumo", "criterios", "medidas", "fonte", "discordancia_com_a_execucao")} if p.get("verificacao") else None),
                        "aprendizagem": ({k: p["aprendizagem"].get(k) for k in ("registrado", "id", "resultado", "licoes", "fatores", "investigar", "propostas_de_teste", "efeito_na_selecao", "hipotese_status", "comparacao",
                                                                            "qualidade_da_previsao")} if p.get("aprendizagem") else None)}
    out["perguntas"] = perguntas(d)
    return out
