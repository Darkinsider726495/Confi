"""Objetivos propostos por ela mesma (Fase 4): a FRIDAY pode PROPOR algo a fazer; só o dono AUTORIZA; só o planejador PLANEJA e executa, pelo corretor.

Três coisas diferentes, de propósito:
  • propor    — `propor()` grava uma proposta, com justificativa e evidências. Não cria tarefa, não chama ferramenta, não muda nada fora do arquivo de propostas.
  • planejar  — `planejador.executar_objetivo()` monta o plano e escolhe a estratégia. Só roda para uma proposta que o dono aprovou.
  • autorizar — `aprovar()` (voz: «aprova o objetivo 2»). Respostas vagas («sim», «pode», «faz aí») nunca aprovam; a ação continua passando pelo corretor, que pede a confirmação dela como sempre.

O que uma proposta precisa para existir:
  • tipo que o catálogo do planejador permite para objetivos próprios (hoje só «registrar_informacao»: nível 1, reversível, sem sair do aparelho);
  • justificativa rastreável: ids de experiências reais (`experiencias.py`) e a tarefa do dono de onde vieram. Sem vínculo com algo que o dono pediu, não nasce;
  • conteúdo limpo (nada sensível) e limites explícitos: nível máximo 1, poucas tentativas, nenhuma ação externa.
Elas não conseguem alterar regras de segurança: o catálogo é código, e o corretor, os protocolos, a autonomia e a curiosidade não são ferramentas de nenhum tipo próprio.
O dono pode listar, pausar, retomar e cancelar. Cancelada, uma proposta daquele padrão nunca volta (a recusa é respeitada).
"""
import copy, json, re, threading, time
import estado as ES
import experiencias as X
import memoria as M
import planejador as PL
import privacidade as P
import tarefas as T

ESTADOS = ("proposto", "pausado", "executando", "concluido", "falhou", "esperando", "cancelado")
FINAIS = ("concluido", "falhou", "cancelado")
ABERTAS = ("proposto", "pausado", "executando", "esperando")
MAX_ABERTAS = 5                 # propostas esperando o dono ao mesmo tempo (operacional: não inundar quem decide)
MIN_OBSERVACOES = 2             # com menos que isto não há padrão, só um caso
LIMITES = {"nivel_max": 1, "max_tentativas": 2, "acao_externa": False}
_ID = re.compile(r"o\d{2,5}")
_ID_X = re.compile(r"x\d{4,7}")
_ID_T = re.compile(r"t\d{4,6}")
_agora = time.time
_ERROS = {"n": 0, "ultimo": ""}
_EM_EXECUCAO = set()            # propostas que ESTE processo está executando agora: a conciliação não mexe nelas (a tarefa pode falhar e trocar de estratégia no meio)


# ---------------------------------------------------------------- estado em disco (validado ao ler)
def _s(v, n):
    return P.redigir(" ".join(v.split()), n)[:n] if isinstance(v, str) else ""


def _limpar_proposta(oid, x):
    if not isinstance(oid, str) or not _ID.fullmatch(oid) or not isinstance(x, dict) or x.get("id") != oid:
        return None
    tipo = x.get("tipo")
    obj = PL.OBJETIVOS.get(tipo) if isinstance(tipo, str) else None
    if not obj or not obj["permite_proprio"]:
        return None
    params, erro = PL._validar_params(obj, x.get("params"))
    if erro or any(isinstance(v, str) and M.sensivel(v) for v in params.values()):
        return None
    vin = x.get("vinculo") if isinstance(x.get("vinculo"), dict) else {}
    if not isinstance(vin.get("tarefa"), str) or not _ID_T.fullmatch(vin["tarefa"]):
        return None
    evid = [e for e in (x.get("evidencias") if isinstance(x.get("evidencias"), list) else [])[:10] if isinstance(e, str) and _ID_X.fullmatch(e)]
    if not evid:
        return None
    res = x.get("resultado") if isinstance(x.get("resultado"), dict) else None
    hist = [{"em": h["em"] if isinstance(h.get("em"), (int, float)) else 0.0, "para": h["para"], "motivo": _s(h.get("motivo"), 120)} for h in (x.get("historico") if isinstance(x.get("historico"), list) else [])[-20:]
            if isinstance(h, dict) and h.get("para") in ESTADOS]
    return {"id": oid, "estado": x["estado"] if x.get("estado") in ESTADOS else "pausado", "tipo": tipo, "params": params, "titulo": _s(x.get("titulo"), 100),
            "justificativa": _s(x.get("justificativa"), 400), "evidencias": evid, "vinculo": {"tarefa": vin["tarefa"], "origem": vin.get("origem") if vin.get("origem") in ("usuario", "meta", "ia") else "usuario"},
            "chave": _s(x.get("chave"), 160), "falhas_na_epoca": x["falhas_na_epoca"] if isinstance(x.get("falhas_na_epoca"), int) and not isinstance(x.get("falhas_na_epoca"), bool) and 0 <= x["falhas_na_epoca"] < 10**6 else 0,
            "limites": dict(LIMITES), "criada": x["criada"] if isinstance(x.get("criada"), (int, float)) else 0.0, "decidida": x["decidida"] if isinstance(x.get("decidida"), (int, float)) else None,
            "decidida_por": "dono" if x.get("decidida_por") == "dono" else None,
            "resultado": {"tarefa": res["tarefa"] if isinstance(res.get("tarefa"), str) and _ID_T.fullmatch(res["tarefa"]) else None, "decisao": _s(res.get("decisao"), 40), "mensagem": _s(res.get("mensagem"), 300)} if res else None,
            "historico": hist}


def _limpar(lido, padrao):
    props = {}
    bruto = lido.get("propostas") if isinstance(lido.get("propostas"), dict) else {}
    for oid, x in list(bruto.items())[:500]:
        p = _limpar_proposta(oid, x)
        if p:
            props[oid] = p
    padrao["propostas"] = props
    padrao["proximo"] = max(lido["proximo"] if isinstance(lido.get("proximo"), int) and not isinstance(lido.get("proximo"), bool) and 1 <= lido["proximo"] < 10**6 else 1,
                            max([int(i[1:]) for i in props] or [0]) + 1)
    return padrao


ARQ = ES.Arq("objetivos_proprios", {"v": 1, "proximo": 1, "propostas": {}}, _limpar)
_trava = ARQ.trava


def reiniciar():
    with _trava:
        ARQ.reiniciar()
        _ERROS.update(n=0, ultimo="")


def _historico(reg):
    if not M.ativo():
        return
    try:
        arq = M._dentro(M.base() / ".cerebro" / "objetivos_proprios_historico.jsonl")
        arq.parent.mkdir(parents=True, exist_ok=True)
        with open(arq, "a", encoding="utf-8") as f:
            f.write(json.dumps({"em": _agora(), **reg}, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass


def _mudar(p, novo, motivo, por=None):
    p["historico"] = (p["historico"] + [{"em": _agora(), "para": novo, "motivo": _s(motivo, 120)}])[-20:]
    p["estado"] = novo
    if por:
        p["decidida"], p["decidida_por"] = _agora(), por
    _historico({"proposta": p["id"], "para": novo, "motivo": _s(motivo, 120), "por": por})


def listar(estados=None):
    with _trava:
        return copy.deepcopy([p for p in ARQ.get()["propostas"].values() if estados is None or p["estado"] in estados])


def obter(oid):
    with _trava:
        p = ARQ.get()["propostas"].get(oid) if isinstance(oid, str) else None
        return copy.deepcopy(p)


# ---------------------------------------------------------------- propor (não executa nada)
def propor(tipo, params, *, titulo, justificativa, evidencias, vinculo, chave, falhas_na_epoca=0):
    """Grava uma proposta, se ela se sustenta. Devolve (True, proposta) ou (False, motivo). Nada é executado e nenhuma tarefa nasce aqui."""
    obj = PL.OBJETIVOS.get(tipo) if isinstance(tipo, str) else None
    if not obj or not obj["permite_proprio"]:
        return False, "esse tipo de objetivo não pode ser proposto por ela"
    limpos, erro = PL._validar_params(obj, params)
    if erro:
        return False, erro
    if any(isinstance(v, str) and M.sensivel(v) for v in limpos.values()):
        return False, "o conteúdo parece sensível"
    if not isinstance(evidencias, (list, tuple)) or not 1 <= len(evidencias) <= 10 or any(not isinstance(e, str) or not _ID_X.fullmatch(e) for e in evidencias):
        return False, "uma proposta precisa de experiências reais como evidência"
    reais = [X.obter(e) for e in evidencias]
    if any(r is None for r in reais):
        return False, "a evidência cita uma experiência que não existe"
    if not isinstance(vinculo, str) or not _ID_T.fullmatch(vinculo):
        return False, "uma proposta precisa estar ligada a uma tarefa do dono"
    t = T.obter(vinculo)
    if not t or t["contexto"]["origem"] not in ("usuario", "meta", "ia"):
        return False, "o vínculo precisa ser uma tarefa que veio do dono (pedido, meta ou conversa)"
    if not isinstance(justificativa, str) or not justificativa.strip():
        return False, "falta a justificativa"
    chave = _s(chave, 160)
    with _trava:
        est = ARQ.get()
        mesmas = [p for p in est["propostas"].values() if p["chave"] == chave]
        if any(p["estado"] in ABERTAS for p in mesmas):
            return False, "já existe uma proposta aberta sobre isso"
        if any(p["estado"] == "cancelado" for p in mesmas):
            return False, "o dono já recusou uma proposta sobre isso"
        if any(p["estado"] in ("concluido", "falhou") and falhas_na_epoca < p["falhas_na_epoca"] + 2 for p in mesmas):
            return False, "nada de novo desde a última proposta sobre isso"
        if sum(1 for p in est["propostas"].values() if p["estado"] in ("proposto", "pausado")) >= MAX_ABERTAS:
            return False, "já há propostas demais esperando o dono"
        oid = f"o{est['proximo']:02d}"
        est["proximo"] += 1
        p = {"id": oid, "estado": "proposto", "tipo": tipo, "params": limpos, "titulo": _s(titulo, 100), "justificativa": _s(justificativa, 400), "evidencias": list(evidencias),
             "vinculo": {"tarefa": vinculo, "origem": t["contexto"]["origem"]}, "chave": chave, "falhas_na_epoca": int(falhas_na_epoca), "limites": dict(LIMITES),
             "criada": _agora(), "decidida": None, "decidida_por": None, "resultado": None, "historico": []}
        _mudar(p, "proposto", "proposta criada a partir de experiências")
        est["propostas"][oid] = p
        ARQ.salvar()
        return True, copy.deepcopy(p)


def _texto_condicoes(c):
    return X._texto_condicoes(c)


def propor_a_partir_das_experiencias():
    """Procura padrões (a mesma estratégia falhando, sem nenhum acerto, nas mesmas condições) e propõe ao dono anotar a observação. Devolve as propostas novas.
    Só vira proposta o que veio de uma tarefa do dono; o que ela fez por conta própria não alimenta novas propostas (evita laço)."""
    novas = []
    for g in X.padroes(MIN_OBSERVACOES):
        if g["sucessos"] or g["falhas"] < MIN_OBSERVACOES:
            continue
        donas = [(x, t) for x, t in zip(g["experiencias"], g["tarefas"]) if (T.obter(t) or {}).get("contexto", {}).get("origem") in ("usuario", "meta", "ia")]
        if not donas:
            continue
        cond = _texto_condicoes(g["condicoes"])
        texto = (f"Observação de execução em {time.strftime('%d/%m/%Y', time.localtime(_agora()))}: «{g['estrategia']}» falhou nas {g['falhas']} vezes em que o desfecho ficou conhecido, "
                 f"nas condições {cond}, e não teve nenhum acerto nelas. São poucas observações: é indício, não regra.")
        ok, p = propor("registrar_informacao", {"texto": texto, "titulo": f"Observações de execução: {g['estrategia']}"}, titulo=f"anotar que «{g['estrategia']}» falhou {g['falhas']}x ({cond})",
                       justificativa=f"«{g['estrategia']}» falhou {g['falhas']} vezes seguidas, sem nenhum acerto, nas mesmas condições ({cond}), em tarefas que o dono pediu.",
                       evidencias=[x for x, _ in donas][:10], vinculo=donas[-1][1], chave=f"padrao-falha|{g['estrategia']}|{cond}", falhas_na_epoca=g["falhas"])
        if ok:
            novas.append(p)
    return novas


def _ao_terminar_tarefa(t):
    """Gancho de `tarefas`: depois de registrar a experiência, vê se surgiu algo a propor. Nunca atrapalha a tarefa; falha fica contada."""
    try:
        if t["contexto"]["origem"] != "propria" and X.da_tarefa(t["id"], t.get("plano_v", 0)):      # só depois que a experiência desta tentativa foi gravada
            propor_a_partir_das_experiencias()
        conciliar()
    except Exception as e:
        _ERROS["n"] += 1
        _ERROS["ultimo"] = f"{type(e).__name__}: {e}"[:200]


def _registrar_gancho():
    T.GANCHOS_FIM[:] = [g for g in T.GANCHOS_FIM if not getattr(g, "_friday_objetivos", False)]
    _ao_terminar_tarefa._friday_objetivos = True
    T.GANCHOS_FIM.append(_ao_terminar_tarefa)


_registrar_gancho()


# ---------------------------------------------------------------- decidir (só o dono)
def aprovar(oid, turno=None):
    """O DONO autoriza. Roda o planejador com os limites da proposta. Devolve (ok, mensagem)."""
    with _trava:
        p = ARQ.get()["propostas"].get(oid) if isinstance(oid, str) else None
        if not p:
            return False, "não achei esse objetivo"
        if p["estado"] != "proposto":
            return False, f"esse objetivo está {p['estado']}" + (": retome antes" if p["estado"] == "pausado" else "")
        _mudar(p, "executando", "aprovado pelo dono", por="dono")
        ARQ.salvar()
        _EM_EXECUCAO.add(oid)
        tipo, params, lim = p["tipo"], dict(p["params"]), dict(p["limites"])
    try:
        r = PL.executar_objetivo(tipo, params, origem="propria", autorizado_por="dono", proposta=oid, nivel_max=lim["nivel_max"], max_tentativas=lim["max_tentativas"], turno=turno)
    finally:
        _EM_EXECUCAO.discard(oid)
    with _trava:
        p = ARQ.get()["propostas"].get(oid)
        if p["estado"] == "cancelado":                                   # o dono cancelou no meio: vale o cancelamento
            return True, "O objetivo foi cancelado enquanto eu executava."
        novo = "concluido" if r["decisao"] == "concluir" else "esperando" if r["decisao"] == "esperar_dono" else "falhou"
        p["resultado"] = {"tarefa": r["tarefa"], "decisao": r["decisao"], "mensagem": _s(r["mensagem"], 300)}
        _mudar(p, novo, r["decisao"])
        ARQ.salvar()
    return True, r["mensagem"]


def _tarefa_da_proposta(oid):
    """A tarefa que nasceu da aprovação desta proposta (o planejador a marca nas restrições). Sobrevive a reinício: é como se descobre o que já foi começado."""
    marca = f"proposta {oid} aprovada pelo dono"
    achadas = [t for t in T.listar() if t["contexto"]["origem"] == "propria" and marca in t["contexto"]["restricoes"]]
    return achadas[-1] if achadas else None


_DA_TAREFA = {T.CONCLUIDA: ("concluido", "a tarefa terminou com o efeito conferido"), T.CANCELADA: ("cancelado", "a tarefa foi cancelada"), T.FALHOU: ("falhou", "a tarefa falhou"),
              T.EXECUTADA_SEM_VERIFICACAO: ("esperando", "executada, mas sem como conferir: só o dono conclui"), T.PRECISA_INTERVENCAO: ("esperando", "a tarefa precisa do dono")}


def conciliar():
    """Põe cada proposta em andamento de acordo com a tarefa que ela criou (a verdade está na tarefa, não numa lembrança). Cobre reinício no meio da execução:
    com tarefa → segue o estado dela; sem tarefa (nada foi começado) → volta a esperar a aprovação do dono, sem repetir nada. Devolve quantas mudaram."""
    em_andamento = [p for p in listar(("executando", "esperando")) if p["id"] not in _EM_EXECUCAO]
    if not em_andamento:
        return 0
    achadas = {p["id"]: _tarefa_da_proposta(p["id"]) for p in em_andamento}
    mudou = 0
    with _trava:
        for p in em_andamento:
            vivo = ARQ.get()["propostas"].get(p["id"])
            if not vivo or vivo["estado"] not in ("executando", "esperando") or vivo["id"] in _EM_EXECUCAO:
                continue
            t = achadas[p["id"]]
            if t is None:
                novo, motivo = ("proposto", "reinício antes de começar: nada foi feito, volta a esperar o dono") if vivo["estado"] == "executando" else (None, "")
            else:
                novo, motivo = _DA_TAREFA.get(t["estado"], ("esperando", f"a tarefa está {T.ROTULO[t['estado']]}"))
                vivo["resultado"] = {"tarefa": t["id"], "decisao": (vivo["resultado"] or {}).get("decisao") or "", "mensagem": _s(t["causa"], 300)}
            if novo and novo != vivo["estado"]:
                _mudar(vivo, novo, motivo)
                mudou += 1
        if mudou:
            ARQ.salvar()
    return mudou


def pausar(oid):
    with _trava:
        p = ARQ.get()["propostas"].get(oid) if isinstance(oid, str) else None
        if not p or p["estado"] != "proposto":
            return False
        _mudar(p, "pausado", "pausado pelo dono", por="dono")
        ARQ.salvar()
        return True


def retomar(oid):
    with _trava:
        p = ARQ.get()["propostas"].get(oid) if isinstance(oid, str) else None
        if not p or p["estado"] != "pausado":
            return False
        _mudar(p, "proposto", "retomado pelo dono", por="dono")
        ARQ.salvar()
        return True


def cancelar(oid):
    """O dono recusa/cancela. Se a proposta já criou uma tarefa que ainda está aberta, cancela só essa tarefa."""
    with _trava:
        p = ARQ.get()["propostas"].get(oid) if isinstance(oid, str) else None
        if not p or p["estado"] in FINAIS:
            return False
        _mudar(p, "cancelado", "cancelado pelo dono", por="dono")
        ARQ.salvar()
    t = _tarefa_da_proposta(oid)
    if t and t["estado"] not in T.FINAIS:                      # só a tarefa que esta proposta criou; nunca a de outra origem
        T.cancelar(t["id"], "objetivo cancelado pelo dono")
    return True


# ---------------------------------------------------------------- painel e voz
def resumo():
    conciliar()
    ps = listar()
    return {"propostas": sum(1 for p in ps if p["estado"] in ("proposto", "pausado")), "executando": sum(1 for p in ps if p["estado"] in ("executando", "esperando")),
            "concluidos": sum(1 for p in ps if p["estado"] == "concluido"), "recusados": sum(1 for p in ps if p["estado"] == "cancelado"), "erros": _ERROS["n"]}


def falar():
    conciliar()
    ps = listar(("proposto", "pausado", "esperando"))
    if not ps:
        return "Não tenho nenhum objetivo proposto esperando você."
    linhas = []
    for p in ps[:5]:
        linhas.append(f"{int(p['id'][1:])}: {p['titulo']} ({p['estado']}) — porque {p['justificativa']}")
    return ("Objetivos que eu proponho, nenhum executado sem o seu «aprova o objetivo N»: " + " | ".join(linhas))[:1200]


_NUM = r"(?:o |um |numero |n )?(?P<n>\d{1,3})"
_LISTA = re.compile(r"(quais (sao )?(os )?objetivos (que )?(voce )?propoe|o que (voce )?propoe|objetivos propostos|meus objetivos propostos|quais sao as suas propostas)")
_APROVA = re.compile(rf"(aprovo|aprova|aprovar) (o )?objetivo {_NUM}")
_PAUSA = re.compile(rf"(pausa|pausar) (o )?objetivo {_NUM}")
_RETOMA = re.compile(rf"(retoma|retomar) (o )?objetivo {_NUM}")
_CANCELA = re.compile(rf"(cancela|cancelar|recusa|recusar|nao quero) (o )?objetivo {_NUM}")


def tratar(texto):
    """Voz do dono. Só estas frases aprovam, pausam ou cancelam; «sim», «pode», «faz» não. Devolve a fala ou None."""
    if not isinstance(texto, str) or len(texto) > 200:
        return None
    f = M._fold(" ".join(texto.split()).rstrip(".!? "))
    if _LISTA.fullmatch(f):
        return falar()
    for rx, acao in ((_APROVA, "aprovar"), (_PAUSA, "pausar"), (_RETOMA, "retomar"), (_CANCELA, "cancelar")):
        m = rx.fullmatch(f)
        if not m:
            continue
        n = int(m.group("n"))
        oid = f"o{n:02d}"
        if acao == "aprovar":
            try:
                ok, msg = aprovar(oid)
            except Exception as e:                                    # não esconde: fica contado no painel e dito ao dono; a proposta se acerta com a tarefa (se houver)
                _ERROS["n"] += 1
                _ERROS["ultimo"] = f"{type(e).__name__}: {e}"[:200]
                conciliar()
                atual = (obter(oid) or {}).get("estado", "?")
                return (f"Deu erro ({type(e).__name__}) ao executar o objetivo {n}. Nada foi dado como feito sem conferir; "
                        + ("ele continua esperando a sua aprovação." if atual == "proposto" else f"ele está {atual}."))
            return f"Objetivo {n}: {msg}" if ok else f"Não aprovei: {msg}."
        ok = {"pausar": pausar, "retomar": retomar, "cancelar": cancelar}[acao](oid)
        verbo = {"pausar": "Pausei", "retomar": "Retomei", "cancelar": "Cancelei"}[acao]
        return f"{verbo} o objetivo {n}." if ok else "Não mudei nada: esse objetivo não está num estado que permita isso."
    return None
