"""Planejador (Fase 4): do objetivo ao resultado conferido, trocando de estratégia quando uma falha.

O ciclo de 11 passos, todos visíveis em `resultado["ciclo"]`:
   1 receber um objetivo permitido · 2 avaliar contexto e recursos · 3 separar o que sabe do que precisa descobrir · 4 dividir em etapas ·
   5 escolher uma estratégia · 6 executar (pelo corretor) · 7 observar · 8 verificar se a etapa cumpriu o propósito (`verificacao.py`) ·
   9 registrar a experiência (`experiencias.py`) · 10 atualizar o plano · 11 continuar, tentar alternativa, pedir esclarecimento ou parar.

Não é uma sequência rígida: se uma estratégia falha, as evidências decidem a próxima; se o ambiente muda entre as tentativas (cofre desligado, manutenção), tudo é reavaliado.

Limites que não mudam (propor ≠ planejar ≠ estar autorizado a executar):
  • As estratégias vêm do CATÁLOGO abaixo, que é código. Nem a experiência, nem a IA, nem texto da internet acrescentam ferramentas ou sobem de nível.
  • Quem executa é o corretor. O planejador só monta o plano, chama `tarefas` e lê o resultado conferido. Estratégia de nível ≥ 2 nunca é escolhida sozinha: vira sugestão
    («posso fazer assim se você confirmar»). Uma recusa do corretor encerra a tentativa; não se contorna recusa trocando de ferramenta.
  • Objetivo PRÓPRIO (origem «propria») só roda se o dono aprovou, só em tipos que o catálogo permite para isso e nunca acima do nível 1 (`objetivos.py`).
  • Conteúdo que parece sensível (senha, cartão, documento) não é guardado por nenhuma estratégia: é recusado antes, para não trocar de lugar o que uma ferramenta se negou a guardar.
  • A experiência só ORDENA as estratégias já permitidas, e só conta o que foi observado em condições compatíveis com as de agora (`experiencias.sinais`).
"""
import re, time
import broker as B
import experiencias as X
import memoria as M
import privacidade as P
import tarefas as T
import verificacao as V

MAX_TENTATIVAS = 3          # estratégias diferentes por objetivo (operacional, não é limite de conhecimento)
NIVEL_MAX_PADRAO = 1        # acima disso a ação precisa de confirmação do dono: nunca é escolhida sozinha
ORIGENS_PERMITIDAS = ("usuario", "meta", "propria")
REGRA_DE_ESCOLHA = ("ordem pela taxa de sucesso suavizada (sucessos+1)/(n+2) das experiências compatíveis com as condições de agora; sem experiência vale 0,5; "
                    "empate pela ordem do catálogo; estratégias fora do nível permitido ou indisponíveis não entram")


def _E(ferramentas, descricao, hipotese, esperado, montar, requer=None):
    return {"id": "+".join(ferramentas), "ferramentas": tuple(ferramentas), "descricao": descricao, "hipotese": hipotese, "esperado": esperado, "montar": montar, "requer": requer or {}}


def _passo(descricao, ferramenta, args, depende_de=()):
    p = {"descricao": descricao, "ferramenta": ferramenta, "args": args}
    if depende_de:
        p["depende_de"] = list(depende_de)
    return p


def _nota(p):
    return f"{p['titulo']}: {p['texto']}" if p.get("titulo") else p["texto"]


def _nome_arquivo(p):
    base = re.sub(r"[^a-z0-9]+", "-", M._fold(p.get("titulo") or "").lower()).strip("-")[:40]
    return f"registro-{base or time.strftime('%Y%m%d-%H%M%S')}.md"


def _guardar_memoria(p):
    a = {"texto": p["texto"]}
    if p.get("titulo"):
        a["titulo"] = p["titulo"]
    return a


# Cada tipo de objetivo: parâmetros validados, e estratégias EQUIVALENTES (cumprem o objetivo por inteiro) em ordem de preferência.
# `parciais` são o que dá para oferecer quando nada equivalente funciona: nunca rodam sozinhas, porque não cumprem o objetivo todo.
OBJETIVOS = {
    "registrar_informacao": {
        "descricao": "guardar uma informação para achar depois",
        "params": {"texto": ("str", 1, 2000), "titulo": ("str", 0, 80)}, "obrigatorios": ("texto",), "permite_proprio": True,
        "estrategias": [
            _E(("guardar_memoria",), "guardar na memória de longo prazo", "a nota entra no cofre e a memória consegue achá-la", "uma nota do cofre alterada agora contém o texto",
               lambda p: [_passo("guardar na memória de longo prazo", "guardar_memoria", _guardar_memoria(p))], requer={"cofre_ativo": True}),
            _E(("anotar",), "salvar como nota", "a nota entra na lista de notas", "uma nota nova no banco com o texto",
               lambda p: [_passo("salvar como nota", "anotar", {"texto": _nota(p)})]),
            _E(("criar_arquivo",), "criar um arquivo de texto", "o arquivo nasce na pasta da FRIDAY com o texto", "um arquivo novo com o conteúdo exato",
               lambda p: [_passo("criar um arquivo de texto", "criar_arquivo", {"nome": _nome_arquivo(p), "conteudo": p["texto"]})]),
        ],
        "parciais": [],
    },
    "registrar_e_avisar": {
        "descricao": "guardar uma informação e me avisar daqui a pouco",
        "params": {"texto": ("str", 1, 200), "minutos": ("num", 0.1, 43200)}, "obrigatorios": ("texto", "minutos"), "permite_proprio": False,
        "estrategias": [
            _E(("anotar", "criar_lembrete"), "anotar e criar o aviso", "a nota é salva e o lembrete é criado depois dela", "uma nota nova e um lembrete novo com o texto e o horário",
               lambda p: [_passo("salvar como nota", "anotar", {"texto": p["texto"]}), _passo("criar o aviso", "criar_lembrete", {"minutos": p["minutos"], "texto": p["texto"]}, ["p1"])]),
            _E(("guardar_memoria", "criar_lembrete"), "guardar na memória e criar o aviso", "a memória guarda e o lembrete é criado depois", "uma nota do cofre com o texto e um lembrete novo",
               lambda p: [_passo("guardar na memória", "guardar_memoria", {"texto": p["texto"]}), _passo("criar o aviso", "criar_lembrete", {"minutos": p["minutos"], "texto": p["texto"]}, ["p1"])],
               requer={"cofre_ativo": True}),
        ],
        "parciais": [],
    },
    "lembrar_depois": {
        "descricao": "me avisar daqui a pouco",
        "params": {"texto": ("str", 1, 200), "minutos": ("num", 0.1, 43200)}, "obrigatorios": ("texto", "minutos"), "permite_proprio": False,
        "estrategias": [
            _E(("criar_lembrete",), "criar um lembrete falado", "o lembrete será falado na hora marcada", "um lembrete novo no banco com o texto e o horário",
               lambda p: [_passo("criar o aviso", "criar_lembrete", {"minutos": p["minutos"], "texto": p["texto"]})]),
        ],
        "parciais": [{"id": "anotar", "descricao": "só anotar o assunto, sem o aviso na hora marcada (não cumpre o pedido por inteiro)"}],
    },
}


# ---------------------------------------------------------------- 1. receber
def tipos():
    return {k: v["descricao"] for k, v in OBJETIVOS.items()}


def _validar_params(obj, params):
    if not isinstance(params, dict):
        return None, "os parâmetros precisam ser um dicionário"
    extras = set(params) - set(obj["params"])
    if extras:
        return None, f"parâmetro desconhecido: {sorted(extras)[0]}"
    limpos = {}
    for nome, (tipo, a, b) in obj["params"].items():
        v = params.get(nome)
        if v is None or v == "":
            if nome in obj["obrigatorios"]:
                return None, f"falta {nome}"
            continue
        if tipo == "str":
            if not isinstance(v, str) or not a <= len(v.strip()) <= b:
                return None, f"{nome} precisa ser texto de {a} a {b} caracteres"
            limpos[nome] = v.strip()
        else:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not a <= v <= b:
                return None, f"{nome} precisa ser número entre {a} e {b}"
            limpos[nome] = v
    return limpos, None


def _resumo_params(params):
    return ", ".join(f"{k}: {len(v)} caracteres" if isinstance(v, str) else f"{k}: {v}" for k, v in params.items())


# ---------------------------------------------------------------- 2. contexto e recursos
def _nivel_da_estrategia(e, params):
    return max(T._nivel_do_passo(p["ferramenta"], p["args"]) for p in e["montar"](params))


def _indisponivel(e, params, amb, nivel_max):
    """None se pode ser escolhida; senão o motivo (em português), que vai para a justificativa."""
    for f in e["ferramentas"]:
        if f not in B.FERRAMENTAS:
            return f"a ferramenta «{f}» não existe aqui"
    for k, v in e["requer"].items():
        if amb.get(k) != v:
            return f"exige {k}={'sim' if v is True else 'não' if v is False else v}, e agora é {'sim' if amb.get(k) is True else 'não' if amb.get(k) is False else amb.get(k)}"
    n = _nivel_da_estrategia(e, params)
    if n >= 4:
        return "ação proibida"
    if n > nivel_max:
        return f"exige confirmação do dono (nível {n}); não é escolhida sozinha"
    return None


# ---------------------------------------------------------------- 5. escolher (com a justificativa que dá para conferir)
def _motivo(s):
    if s["n"] == 0:
        extra = f" ({s['recusas']} recusa(s), {s['sem_conferencia']} sem conferência, não pesam)" if s["recusas"] or s["sem_conferencia"] else ""
        return f"sem experiência compatível com desfecho conhecido{extra}: vale 0,50"
    return f"{s['sucessos']} acerto(s) e {s['falhas']} falha(s) em {s['n']} tentativa(s) compatíveis ({', '.join(s['ids'][-3:])}): {s['p']:.2f}"


def escolher(tipo, params, amb=None, nivel_max=NIVEL_MAX_PADRAO, ja_tentadas=()):
    """Ordena as estratégias do tipo. Devolve {em, condicoes, regra, ranking, excluidas, escolhida, conhecimento}.
    `ranking[i]` traz as contagens e os ids das experiências em que se apoia, para `experiencias.conferir_escolha` poder refazer a conta."""
    obj = OBJETIVOS[tipo]
    amb = X.ambiente() if amb is None else amb
    em = time.time()
    ranking, excluidas = [], []
    for ordem, e in enumerate(obj["estrategias"]):
        if e["id"] in ja_tentadas:
            excluidas.append({"id": e["id"], "motivo": "já tentada nesta execução"})
            continue
        motivo = _indisponivel(e, params, amb, nivel_max)
        if motivo:
            excluidas.append({"id": e["id"], "motivo": motivo})
            continue
        s = X.sinais(e["id"], amb, ate=em)
        ranking.append({"id": e["id"], "descricao": e["descricao"], "n": s["n"], "sucessos": s["sucessos"], "falhas": s["falhas"], "p": s["p"], "experiencias": s["ids"],
                        "motivo": _motivo(s), "_ordem": ordem})
    ranking.sort(key=lambda r: (-r["p"], r["_ordem"]))
    for r in ranking:
        del r["_ordem"]
    conhecimento = {
        "sabe": [f"condições agora: {X._texto_condicoes(amb)}"] + [f"«{r['id']}»: {r['motivo']}" for r in ranking if r["n"]],
        "descobrir": [f"«{r['id']}» ainda não foi tentada nestas condições" for r in ranking if not r["n"]],
        "desconhecido": [f"o efeito de «{f}» não pode ser conferido daqui" for r in ranking[:1] for f in next(e for e in obj["estrategias"] if e["id"] == r["id"])["ferramentas"] if not V.conferivel(f)]}
    return {"em": em, "condicoes": dict(amb), "regra": REGRA_DE_ESCOLHA, "ranking": ranking, "excluidas": excluidas, "escolhida": ranking[0]["id"] if ranking else None, "conhecimento": conhecimento}


def _sugestoes(tipo, params, escolha, amb, nivel_max):
    obj = OBJETIVOS[tipo]
    sug = [{"estrategia": e["id"], "descricao": e["descricao"], "porque": x["motivo"]} for x in escolha["excluidas"] for e in obj["estrategias"]
           if e["id"] == x["id"] and x["motivo"].startswith("exige confirmação")]
    sug += [{"estrategia": p["id"], "descricao": p["descricao"], "porque": "não cumpre o objetivo por inteiro"} for p in obj["parciais"]]
    return sug


# ---------------------------------------------------------------- o ciclo
def _res(decisao, mensagem, tid=None, estado=None, tentativas=(), ciclo=(), sugestoes=()):
    return {"decisao": decisao, "mensagem": mensagem, "tarefa": tid, "estado": estado, "tentativas": list(tentativas), "ciclo": list(ciclo), "sugestoes": list(sugestoes)}


def executar_objetivo(tipo, params, *, origem="usuario", meta=None, conclui_meta=False, nivel_max=NIVEL_MAX_PADRAO, max_tentativas=MAX_TENTATIVAS,
                      autorizado_por=None, proposta=None, turno=None):
    """Roda o ciclo até um desfecho. Decisões: «concluir» (efeito conferido), «esperar_dono» (há uma confirmação pendente), «pedir_esclarecimento»,
    «interromper» ou «recusar» (nada foi tentado). Nunca levanta por causa de uma falha de estratégia; erros de uso (tipo desconhecido etc.) viram «recusar»."""
    ciclo = []
    obj = OBJETIVOS.get(tipo) if isinstance(tipo, str) else None
    if obj is None:
        return _res("recusar", f"Não sei planejar objetivos do tipo «{str(tipo)[:40]}». Sei: {', '.join(tipos())}.", ciclo=["1 receber: tipo desconhecido"])
    if origem not in ORIGENS_PERMITIDAS:
        return _res("recusar", "Origem de objetivo inválida.", ciclo=["1 receber: origem inválida"])
    if origem == "propria":
        if autorizado_por != "dono" or not isinstance(proposta, str):
            return _res("recusar", "Objetivo próprio só roda depois que o dono aprova a proposta.", ciclo=["1 receber: objetivo próprio sem autorização do dono"])
        if not obj["permite_proprio"]:
            return _res("recusar", f"Objetivos do tipo «{tipo}» não podem ser próprios.", ciclo=["1 receber: tipo não permitido para objetivo próprio"])
        nivel_max = min(nivel_max, NIVEL_MAX_PADRAO)
    if not isinstance(nivel_max, int) or isinstance(nivel_max, bool) or not 0 <= nivel_max <= 3:
        return _res("recusar", "Nível máximo inválido.", ciclo=["1 receber: nível inválido"])
    max_tentativas = max(1, min(int(max_tentativas), 6)) if isinstance(max_tentativas, int) and not isinstance(max_tentativas, bool) else MAX_TENTATIVAS
    limpos, erro = _validar_params(obj, params)
    if erro:
        return _res("recusar", f"Pedido inválido para «{tipo}»: {erro}.", ciclo=[f"1 receber: {erro}"])
    if any(isinstance(v, str) and M.sensivel(v) for v in limpos.values()):
        return _res("recusar", "Isso parece dado sensível (senha, cartão, documento); não guardo isso por conta própria nem por outra ferramenta.", ciclo=["1 receber: conteúdo sensível, recusado antes de planejar"])
    ciclo.append(f"1 receber: «{tipo}» ({_resumo_params(limpos)}), origem {origem}")

    restricoes = [f"nível máximo {nivel_max}"] + ([f"proposta {proposta} aprovada pelo dono"] if proposta else [])
    tid = T.criar(f"{obj['descricao']} ({_resumo_params(limpos)})", origem=origem, meta=meta, conclui_meta=conclui_meta, restricoes=restricoes)
    tentativas, tentadas = [], []
    escolha = None
    for n in range(1, max_tentativas + 1):
        amb = X.ambiente()                                                               # 2. contexto de agora (reavaliado a cada tentativa: o ambiente pode ter mudado)
        escolha = escolher(tipo, limpos, amb, nivel_max, tentadas)                       # 3 e 5. o que sabe/descobrir e a estratégia
        ciclo.append(f"2 contexto (tentativa {n}): {X._texto_condicoes(amb)}; {len(escolha['ranking'])} estratégia(s) disponível(is), {len(escolha['excluidas'])} fora")
        ciclo.append(f"3 saber × descobrir: sabe {len(escolha['conhecimento']['sabe']) - 1}, a descobrir {len(escolha['conhecimento']['descobrir'])}, desconhecido {len(escolha['conhecimento']['desconhecido'])}")
        if not escolha["escolhida"]:
            break
        e = next(x for x in obj["estrategias"] if x["id"] == escolha["escolhida"])
        passos = e["montar"](limpos)                                                     # 4. etapas
        ciclo.append(f"4 etapas: {' → '.join(p['descricao'] for p in passos)}")
        ciclo.append(f"5 estratégia: «{e['id']}» — {escolha['ranking'][0]['motivo']}")
        try:
            T.planejar(tid, passos)
        except ValueError as exc:
            return _res("interromper", f"Não consegui montar o plano: {exc}.", tid, T.obter(tid)["estado"], tentativas, ciclo)
        plano_v = T.obter(tid)["plano_v"]
        resto = [r["id"] for r in escolha["ranking"][1:]]
        X.intencao(tid, plano_v, tipo=tipo, estrategia=e["id"], descricao=e["descricao"], hipotese=e["hipotese"], esperado=e["esperado"], alternativas=resto, condicoes=amb, escolha=escolha)
        T.executar(tid, turno)                                                           # 6, 7 e 8. executa pelo corretor, observa e confere o efeito
        t = T.obter(tid)
        xp = X.da_tarefa(tid, plano_v)                                                   # 9. a experiência já foi gravada pelo gancho
        tentadas.append(e["id"])
        tentativas.append({"estrategia": e["id"], "estado": t["estado"], "resultado": xp["resultado"] if xp else None, "experiencia": xp["id"] if xp else None, "escolha": escolha})
        ciclo.append(f"6-8 executar, observar, verificar: {t['estado']}")
        ciclo.append(f"9 experiência: {xp['id'] + ' ' + xp['resultado'] if xp else 'não foi gravada'}")
        if t["estado"] == T.CONCLUIDA:
            ciclo.append("11 decisão: concluir")
            return _res("concluir", f"Pronto: {e['descricao']}, e conferi que o efeito existe.", tid, t["estado"], tentativas, ciclo)
        if t["estado"] == T.BLOQUEADA:
            ciclo.append("11 decisão: esperar o dono")
            return _res("esperar_dono", "Estou esperando a sua confirmação clara (diga «confirmo …»); sem ela nada é feito.", tid, t["estado"], tentativas, ciclo)
        if t["estado"] == T.EXECUTADA_SEM_VERIFICACAO:
            ciclo.append("11 decisão: pedir esclarecimento (sem como conferir)")
            return _res("pedir_esclarecimento", f"Executei «{e['descricao']}», mas não consigo conferir daqui. Diga «tarefa {int(tid[1:])} está feita» se deu certo.", tid, t["estado"], tentativas, ciclo)
        if t["estado"] != T.FALHOU:
            ciclo.append(f"11 decisão: interromper ({t['estado']})")
            return _res("interromper", f"A tarefa parou ({T.ROTULO[t['estado']]}). {t['causa']}".strip(), tid, t["estado"], tentativas, ciclo)
        if xp and xp["tipo_falha"] == "recusa":
            ciclo.append("11 decisão: interromper (o corretor recusou; não se contorna)")
            return _res("interromper", f"O corretor recusou o pedido ({t['causa']}). Não vou tentar contornar trocando de ferramenta.", tid, t["estado"], tentativas, ciclo)
        ciclo.append(f"10 atualizar o plano: «{e['id']}» falhou ({xp['tipo_falha'] if xp else 'falha'}); procurar alternativa equivalente e permitida")
    # sem mais alternativas, ou sem tentativas sobrando
    escolha_final = escolher(tipo, limpos, X.ambiente(), nivel_max, tentadas)
    sug = _sugestoes(tipo, limpos, escolha_final, X.ambiente(), nivel_max)
    t = T.obter(tid)
    if not tentativas:
        ciclo.append("11 decisão: pedir esclarecimento (nenhuma estratégia disponível)")
        T.cancelar(tid, "nenhuma estratégia disponível")
        return _res("pedir_esclarecimento", "Não tenho nenhuma estratégia disponível agora para isso: " + "; ".join(f"«{x['id']}» {x['motivo']}" for x in escolha_final["excluidas"]) + ".", tid, T.obter(tid)["estado"], tentativas, ciclo, sug)
    sobrou = bool(escolha_final["escolhida"])
    ciclo.append("11 decisão: pedir esclarecimento (" + ("limite de tentativas" if sobrou else "alternativas esgotadas") + ")")
    falhas = ", ".join(f"«{x['estrategia']}»" for x in tentativas)
    msg = f"Não consegui: tentei {falhas} e o efeito não foi confirmado." + (" Ainda há outras estratégias; quer que eu continue?" if sobrou else " Não restam alternativas equivalentes e permitidas.")
    fora = [x for x in escolha_final["excluidas"] if x["motivo"] != "já tentada nesta execução" and not x["motivo"].startswith("exige confirmação")]
    if fora:
        msg += " Ficaram de fora: " + "; ".join(f"«{x['id']}» {x['motivo']}" for x in fora) + "."
    if sug:
        msg += " Posso, se você quiser: " + "; ".join(f"{s['descricao']}" for s in sug) + "."
    return _res("pedir_esclarecimento", msg, tid, t["estado"], tentativas, ciclo, sug)


# ---------------------------------------------------------------- ajuda para a IA (ela continua só propondo)
def dica_para_ia(ferramenta, args=None):
    """Quando uma ferramenta da IA falha ou o efeito não é encontrado: conta o que as experiências dizem e quais alternativas EQUIVALENTES e permitidas existem.
    É texto para a IA decidir; o corretor continua decidindo o que roda. Sem alternativa equivalente, devolve None."""
    amb = X.ambiente()
    for tipo, obj in OBJETIVOS.items():
        if not any(e["id"] == ferramenta for e in obj["estrategias"]) or len(obj["estrategias"]) < 2 or tipo == "registrar_e_avisar":
            continue
        propria = X.sinais(ferramenta, amb)
        outras = []
        for e in obj["estrategias"]:
            if e["id"] == ferramenta:
                continue
            if any(f not in B.FERRAMENTAS for f in e["ferramentas"]) or any(amb.get(k) != v for k, v in e["requer"].items()):
                continue
            s = X.sinais(e["id"], amb)
            outras.append(f"«{e['id']}» ({s['sucessos']} de {s['n']} deram certo)" if s["n"] else f"«{e['id']}» (ainda sem histórico)")
        if outras:
            return (f"Experiência registrada: «{ferramenta}» deu certo {propria['sucessos']} de {propria['n']} vezes nestas condições (poucos casos: é indício, não regra). "
                    f"Para {obj['descricao']} há alternativas equivalentes e permitidas: {', '.join(outras)}. Você pode propor uma delas; o corretor continua decidindo.")
    return None


def _registrar_dica():
    T.DICAS[:] = [d for d in T.DICAS if not getattr(d, "_friday_planejador", False)]
    dica_para_ia._friday_planejador = True
    T.DICAS.append(dica_para_ia)


_registrar_dica()
