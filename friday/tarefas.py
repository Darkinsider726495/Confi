"""Tarefas (Fase 2): o registro mínimo do que a FRIDAY está tentando fazer, passo a passo, e se de fato deu certo.

Por que existe: o corretor decide e executa UMA ação; o pré-córtex guarda METAS (o que ela quer); nada guardava o caminho entre os dois — o plano, em que
passo está, o que já aconteceu, o que a conferência achou. Aqui isso fica gravado em `.cerebro/tarefas.json` (estado vivo) e `.cerebro/tarefas_historico.jsonl`
(só acrescenta; nada é apagado).

O que este módulo NÃO faz: não executa nada por conta própria. Cada passo vai ao corretor (`broker.executar_estruturado`), que continua decidindo: nível, validação,
confirmação clara presa à ação, PIN, manutenção, auditoria. Uma tarefa não tem como pular a confirmação, e a IA não tem ferramenta para criar ou mexer em tarefas.

Máquina de estados (TRANSICOES é a única regra; fora dela `TransicaoInvalida`):
  CRIADA → PLANEJANDO → PRONTA → EXECUTANDO → VERIFICANDO → CONCLUIDA
  e os desvios: BLOQUEADA (espera a confirmação do dono, outra tarefa ou o fim da manutenção), FALHOU, PRECISA_INTERVENCAO, CANCELADA,
  EXECUTADA_SEM_VERIFICACAO (rodou, mas não há como conferir daqui: nunca vira CONCLUIDA sozinha).
«A ferramenta respondeu que fez» NÃO é objetivo cumprido: o passo só vira `verificado` quando `verificacao.py` olha o estado real e acha o efeito.

Gravação antes de executar: antes de chamar o corretor o passo é marcado `executando`, com a marca de `verificacao.antes()`, e isso vai para o disco. Se o processo
cair no meio, o disco diz exatamente o que estava em andamento e a marca permite conferir depois se a ação chegou a acontecer (Fase 6).

Privacidade: o registro guarda o objetivo (redigido), o plano e, só para passos de nível ≤ 1 sem dado sensível, os argumentos (para poder retomar) — que saem do registro
quando a tarefa termina (CONCLUIDA/CANCELADA). Passos de nível ≥ 2
ou com conteúdo sensível guardam só o resumo («‹texto: 40 caracteres›»); os argumentos ficam na memória do processo e, se ele reiniciar, a tarefa pede ao dono que repita.
A resposta da ferramenta nunca é guardada, só o código e o tamanho; a evidência da conferência é uma frase sem o conteúdo. A trilha de auditoria continua sendo só do corretor.

Trava: `_trava` (a mesma do arquivo de estado) NUNCA fica presa durante uma chamada ao corretor (o corretor avisa os observadores com a trava dele presa; se as duas se
esperassem haveria impasse). Quem ouve os eventos do corretor (`_ouvir`) só mexe no registro e na conferência — nunca chama o corretor.
"""
import copy, json, re, threading, time
import broker as B
import verificacao as V
import estado as ES
import memoria as M
import privacidade as P

CRIADA, PLANEJANDO, PRONTA, EXECUTANDO, VERIFICANDO = "CRIADA", "PLANEJANDO", "PRONTA", "EXECUTANDO", "VERIFICANDO"
CONCLUIDA, EXECUTADA_SEM_VERIFICACAO, FALHOU = "CONCLUIDA", "EXECUTADA_SEM_VERIFICACAO", "FALHOU"
BLOQUEADA, CANCELADA, PRECISA_INTERVENCAO = "BLOQUEADA", "CANCELADA", "PRECISA_INTERVENCAO"
ESTADOS = (CRIADA, PLANEJANDO, PRONTA, EXECUTANDO, VERIFICANDO, CONCLUIDA, EXECUTADA_SEM_VERIFICACAO, FALHOU, BLOQUEADA, CANCELADA, PRECISA_INTERVENCAO)
TRANSICOES = {
    CRIADA: {PLANEJANDO, CANCELADA},
    PLANEJANDO: {PRONTA, FALHOU, CANCELADA},
    PRONTA: {EXECUTANDO, PLANEJANDO, BLOQUEADA, PRECISA_INTERVENCAO, CANCELADA},
    EXECUTANDO: {VERIFICANDO, BLOQUEADA, FALHOU, PRECISA_INTERVENCAO, CANCELADA},
    VERIFICANDO: {PRONTA, CONCLUIDA, EXECUTADA_SEM_VERIFICACAO, FALHOU, PRECISA_INTERVENCAO, CANCELADA},
    BLOQUEADA: {PRONTA, EXECUTANDO, PRECISA_INTERVENCAO, FALHOU, CANCELADA},
    FALHOU: {PLANEJANDO, PRONTA, CANCELADA},
    EXECUTADA_SEM_VERIFICACAO: {VERIFICANDO, CANCELADA},
    PRECISA_INTERVENCAO: {PRONTA, PLANEJANDO, VERIFICANDO, FALHOU, CANCELADA},
    CONCLUIDA: set(),
    CANCELADA: set(),
}
FINAIS = (CONCLUIDA, CANCELADA)
AVISAM_FIM = (CONCLUIDA, EXECUTADA_SEM_VERIFICACAO, FALHOU, PRECISA_INTERVENCAO, CANCELADA)   # quem se inscreve em GANCHOS_FIM é avisado ao entrar nestes
PASSO_ESTADOS = ("pendente", "executando", "aguardando", "verificado", "refutado", "sem_verificacao", "falhou", "cancelado", "intervencao")
ORIGENS = ("usuario", "meta", "propria", "ia")
ROTULO = {CRIADA: "criada", PLANEJANDO: "planejando", PRONTA: "pronta para executar", EXECUTANDO: "executando", VERIFICANDO: "conferindo", CONCLUIDA: "concluída",
          EXECUTADA_SEM_VERIFICACAO: "executada, mas não consegui conferir", FALHOU: "falhou", BLOQUEADA: "esperando", CANCELADA: "cancelada",
          PRECISA_INTERVENCAO: "precisa de você"}

MAX_PASSOS = 12
MAX_HIST = 40          # entradas de histórico guardadas na própria tarefa (o arquivo .jsonl guarda todas)
MAX_ABERTAS = 200      # tarefas não finais ao mesmo tempo (operacional, não é teto de conhecimento)
MAX_FINAIS = 100       # concluídas/canceladas mantidas no estado vivo; as mais antigas saem dele e ficam só no histórico
MAX_VIVOS = 200        # argumentos mantidos só na memória do processo
_ID_TAREFA = re.compile(r"t\d{4,6}")
_ID_PASSO = re.compile(r"p\d{1,2}")
_ID_META = re.compile(r"m\d{1,6}")
_ID_PEND = re.compile(r"[0-9a-f]{6}")
_FERR = re.compile(r"[a-z_][a-z0-9_]{0,40}")

GANCHOS_FIM = []       # funções(tarefa_copia) chamadas fora da trava quando uma tarefa entra em AVISAM_FIM; não podem chamar o corretor
RESERVAS = {"reservar": None, "liberar": None}   # preenchido por coordenador.py (tarefas não importa o coordenador): reservar(dono, ferramenta, args) -> (ok, quem); liberar(dono)
ESPERA_RECURSO_S = 3.0  # quanto um passo espera outro que usa o mesmo recurso, antes de deixar a tarefa PRONTA com o motivo (operacional)
MAX_QUEDAS = 2         # um passo já interrompido por queda/reinício esta quantidade de vezes não é repetido sozinho (evita laço de queda: cai, volta, repete, cai…)
ATIVAS = {}            # tarefa -> vezes que ESTE processo a está executando agora (a retomada depois de reinício nunca mexe nelas)
DICAS = []             # funções(ferramenta, args) -> texto|None; quando uma ação da IA falha ou o efeito não é encontrado, o texto vai junto para a IA (ela só propõe; o corretor decide)


class TransicaoInvalida(ValueError):
    pass


# ---------------------------------------------------------------- estado em disco (validado ao ler)
def _txt(v, n):
    return P.redigir(" ".join(v.split()), n)[:n] if isinstance(v, str) else ""


def _num(v, padrao=0.0):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e12 else padrao


def _inteiro(v, a, b, padrao=0):
    return v if isinstance(v, int) and not isinstance(v, bool) and a <= v <= b else padrao


def _prim(v):
    return isinstance(v, (bool, int, float, str)) and (not isinstance(v, str) or len(v) <= 2000)


def _args_ok(a):
    return isinstance(a, dict) and len(a) <= 8 and all(isinstance(k, str) and len(k) <= 40 and _prim(v) for k, v in a.items())


def _marca_ok(m):
    if not isinstance(m, dict) or len(m) > 12:
        return None
    saida = {}
    for k, v in m.items():
        if not isinstance(k, str) or len(k) > 30:
            continue
        if isinstance(v, (bool, int, float)) and not isinstance(v, str):
            saida[k] = v
        elif isinstance(v, str) and len(v) <= 80:
            saida[k] = v
        elif isinstance(v, list) and len(v) <= 30 and all(isinstance(x, str) and len(x) <= 80 for x in v):
            saida[k] = list(v)
    return saida


def _verificacao_ok(v):
    if not isinstance(v, dict) or v.get("veredito") not in V.VEREDITOS:
        return None
    return {"veredito": v["veredito"], "forca": v.get("forca") if v.get("forca") in (V.INDEPENDENTE, V.DA_RESPOSTA, V.NENHUMA, "dono") else V.NENHUMA,
            "evidencia": _txt(v.get("evidencia"), 200), "em": _num(v.get("em"))}


def _limpar_passo(p, ids_antes):
    if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not _ID_PASSO.fullmatch(p["id"]) or p["id"] in ids_antes:
        return None
    ferr = p.get("ferramenta")
    if not isinstance(ferr, str) or not _FERR.fullmatch(ferr):
        return None
    nivel = p.get("nivel")
    return {"id": p["id"], "descricao": _txt(p.get("descricao"), 120) or ferr, "ferramenta": ferr,
            "args": dict(p["args"]) if _args_ok(p.get("args")) else None, "args_resumo": _txt(p.get("args_resumo"), 300),
            "nivel": nivel if isinstance(nivel, int) and not isinstance(nivel, bool) and 0 <= nivel <= 4 else None,
            "depende_de": [d for d in (p.get("depende_de") or []) if isinstance(d, str) and d in ids_antes][:MAX_PASSOS] if isinstance(p.get("depende_de"), list) else [],
            "estado": p.get("estado") if p.get("estado") in PASSO_ESTADOS else "intervencao",
            "tentativas": _inteiro(p.get("tentativas"), 0, 99),
            "pendencia": p["pendencia"] if isinstance(p.get("pendencia"), str) and _ID_PEND.fullmatch(p["pendencia"]) else None,
            "marca": _marca_ok(p.get("marca")), "codigo": _txt(p.get("codigo"), 60) or None, "tam": _inteiro(p.get("tam"), 0, 10**9, None) if p.get("tam") is not None else None,
            "verificacao": _verificacao_ok(p.get("verificacao"))}


def _limpar_tarefa(tid, x):
    if not isinstance(tid, str) or not _ID_TAREFA.fullmatch(tid) or not isinstance(x, dict) or x.get("id") != tid:
        return None
    passos, ids = [], []
    if isinstance(x.get("passos"), list):
        for p in x["passos"][:MAX_PASSOS]:
            q = _limpar_passo(p, ids)
            if q:
                passos.append(q)
                ids.append(q["id"])
    ctx = x.get("contexto") if isinstance(x.get("contexto"), dict) else {}
    estado = x.get("estado") if x.get("estado") in ESTADOS else PRECISA_INTERVENCAO
    if estado in (PRONTA, EXECUTANDO, VERIFICANDO, BLOQUEADA, EXECUTADA_SEM_VERIFICACAO) and not passos:
        estado = PRECISA_INTERVENCAO
    hist = []
    for h in (x.get("historico") if isinstance(x.get("historico"), list) else [])[-MAX_HIST:]:
        if isinstance(h, dict) and h.get("para") in ESTADOS:
            hist.append({"em": _num(h.get("em")), "de": h["de"] if h.get("de") in ESTADOS else None, "para": h["para"], "motivo": _txt(h.get("motivo"), 120)})
    return {"id": tid, "objetivo": _txt(x.get("objetivo"), 300) or "(sem objetivo)",
            "contexto": {"origem": ctx.get("origem") if ctx.get("origem") in ORIGENS else "usuario",
                         "meta": ctx["meta"] if isinstance(ctx.get("meta"), str) and _ID_META.fullmatch(ctx["meta"]) else None,
                         "conclui_meta": ctx.get("conclui_meta") is True,
                         "restricoes": [_txt(r, 120) for r in (ctx.get("restricoes") if isinstance(ctx.get("restricoes"), list) else [])[:8] if isinstance(r, str)]},
            "estado": estado, "passos": passos, "tentativas": _inteiro(x.get("tentativas"), 0, 9999), "plano_v": _inteiro(x.get("plano_v"), 0, 9999),
            "depende_de": [d for d in (x.get("depende_de") if isinstance(x.get("depende_de"), list) else [])[:10] if isinstance(d, str) and _ID_TAREFA.fullmatch(d)],
            "proxima_acao": _txt(x.get("proxima_acao"), 200), "causa": _txt(x.get("causa"), 300), "historico": hist,
            "criada": _num(x.get("criada")), "atualizada": _num(x.get("atualizada"))}


def _limpar(lido, padrao):
    tarefas = {}
    bruto = lido.get("tarefas") if isinstance(lido.get("tarefas"), dict) else {}
    for tid, x in list(bruto.items())[:MAX_ABERTAS + MAX_FINAIS + 50]:
        t = _limpar_tarefa(tid, x)
        if t:
            tarefas[tid] = t
    maior = max([int(i[1:]) for i in tarefas] or [0])
    padrao["tarefas"] = tarefas
    padrao["proximo"] = max(_inteiro(lido.get("proximo"), 1, 10**6, 1), maior + 1)
    return padrao


ARQ = ES.Arq("tarefas", {"v": 1, "proximo": 1, "tarefas": {}}, _limpar)
_trava = ARQ.trava
_VIVOS = {}              # (tarefa, passo) -> argumentos; só na memória do processo (nunca no disco quando são sensíveis)
_ganchos_pendentes = []
_trava_ganchos = threading.Lock()
_agora = time.time


def reiniciar():
    """Esquece o que está na memória do processo (o próximo acesso relê o disco). Usado em testes."""
    with _trava:
        ARQ.reiniciar()
        _VIVOS.clear()
    with _trava_ganchos:
        _ganchos_pendentes.clear()


# ---------------------------------------------------------------- histórico em arquivo (só acrescenta)
def _historico(reg):
    if not M.ativo():
        return
    try:
        arq = M._dentro(M.base() / ".cerebro" / "tarefas_historico.jsonl")
        arq.parent.mkdir(parents=True, exist_ok=True)
        with open(arq, "a", encoding="utf-8") as f:
            f.write(json.dumps({"em": _agora(), **reg}, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass


def _sem_args(t):
    c = copy.deepcopy(t)
    for p in c["passos"]:
        p["args"] = None
    return c


def _despachar():
    """Avisa os GANCHOS_FIM, fora da trava das tarefas. Chamado no fim de cada função pública que pode ter terminado uma tarefa."""
    with _trava_ganchos:
        fila, _ganchos_pendentes[:] = list(_ganchos_pendentes), []
    for t in fila:
        for g in list(GANCHOS_FIM):
            try:
                g(copy.deepcopy(t))
            except Exception:
                pass


# ---------------------------------------------------------------- núcleo (tudo abaixo roda com _trava, exceto onde dito)
def _vivo(tid):
    return ARQ.get()["tarefas"].get(tid) if isinstance(tid, str) else None


def _mudar(t, novo, motivo=""):
    antigo = t["estado"]
    if novo not in TRANSICOES.get(antigo, ()):
        raise TransicaoInvalida(f"{antigo} → {novo} não é permitido")
    reg = {"em": _agora(), "de": antigo, "para": novo, "motivo": P.redigir(motivo, 120)}
    t["estado"], t["atualizada"] = novo, reg["em"]
    t["historico"] = (t["historico"] + [reg])[-MAX_HIST:]
    _historico({"tarefa": t["id"], **reg})
    if novo in AVISAM_FIM:
        with _trava_ganchos:
            _ganchos_pendentes.append(copy.deepcopy(t))
    if novo in FINAIS:
        _historico({"tarefa": t["id"], "snapshot": _sem_args(t)})
        for p in t["passos"]:
            _VIVOS.pop((t["id"], p["id"]), None)
            p["args"] = None                                # terminou: o conteúdo não é mais necessário (o resumo e a conferência ficam)
        _podar()


def _mudar_id(tid, novo, motivo=""):
    """Para testes e para quem só tem o id."""
    with _trava:
        t = _vivo(tid)
        if t is None:
            raise ValueError("tarefa desconhecida")
        try:
            _mudar(t, novo, motivo)
        finally:
            ARQ.salvar()
    _despachar()


def _podar():
    est = ARQ.get()
    finais = sorted((t for t in est["tarefas"].values() if t["estado"] in FINAIS), key=lambda t: t["atualizada"])
    for t in finais[:max(0, len(finais) - MAX_FINAIS)]:
        est["tarefas"].pop(t["id"], None)               # sai do estado vivo; o histórico em arquivo já tem tudo


def _passo(t, pid):
    return next((p for p in t["passos"] if p["id"] == pid), None)


def _nivel_do_passo(ferr, args):
    n = B.FERRAMENTAS[ferr]["nivel"]
    try:
        return int(n(args) if callable(n) else n)
    except Exception:
        return 2                                         # na dúvida, trata como sensível


def _args_guardaveis(args, nivel):
    if nivel > 1 or not _args_ok(args):
        return False
    return not any(isinstance(v, str) and M.sensivel(v) for v in args.values())


def _validar_plano(passos):
    if not isinstance(passos, (list, tuple)) or not 1 <= len(passos) <= MAX_PASSOS:
        raise ValueError(f"o plano precisa ter de 1 a {MAX_PASSOS} passos")
    saida = []
    for i, p in enumerate(passos, 1):
        if not isinstance(p, dict):
            raise ValueError("passo inválido")
        ferr = p.get("ferramenta")
        if not isinstance(ferr, str) or ferr not in B.FERRAMENTAS:
            raise ValueError("ferramenta desconhecida no plano")
        args = p.get("args") or {}
        if not _args_ok(args):
            raise ValueError("argumentos do passo inválidos")
        nivel = _nivel_do_passo(ferr, args)
        if nivel >= 4:
            raise ValueError("ação proibida não entra em plano")
        dep = p.get("depende_de") or []
        antes = {f"p{j}" for j in range(1, i)}
        if not isinstance(dep, (list, tuple)) or any(d not in antes for d in dep):
            raise ValueError("um passo só pode depender de passos anteriores")
        saida.append({"id": f"p{i}", "descricao": _txt(p.get("descricao"), 120) or ferr, "ferramenta": ferr, "args": dict(args), "nivel": nivel, "depende_de": list(dep)})
    return saida


def criar(objetivo, passos=None, origem="usuario", meta=None, conclui_meta=False, restricoes=(), depende_de=()):
    """Registra uma tarefa e, se vier `passos`, já a planeja. Devolve o id («t0001»). O objetivo é redigido (dado pessoal e segredo saem)."""
    if origem not in ORIGENS:
        raise ValueError("origem inválida")
    if meta is not None and not (isinstance(meta, str) and _ID_META.fullmatch(meta)):
        raise ValueError("meta inválida")
    if not isinstance(depende_de, (list, tuple)) or any(not (isinstance(d, str) and _ID_TAREFA.fullmatch(d)) for d in depende_de):
        raise ValueError("dependência inválida")
    obj = _txt(objetivo, 300)
    if not obj:
        raise ValueError("a tarefa precisa de um objetivo")
    with _trava:
        est = ARQ.get()
        if sum(1 for t in est["tarefas"].values() if t["estado"] not in FINAIS) >= MAX_ABERTAS:
            raise ValueError("tarefas demais em aberto: conclua ou cancele algumas")
        tid = f"t{est['proximo']:04d}"
        est["proximo"] += 1
        agora = _agora()
        est["tarefas"][tid] = {
            "id": tid, "objetivo": obj, "contexto": {"origem": origem, "meta": meta, "conclui_meta": bool(conclui_meta), "restricoes": [_txt(r, 120) for r in list(restricoes)[:8]]},
            "estado": CRIADA, "passos": [], "tentativas": 0, "plano_v": 0, "depende_de": list(depende_de), "proxima_acao": "montar o plano", "causa": "",
            "historico": [{"em": agora, "de": None, "para": CRIADA, "motivo": "tarefa registrada"}], "criada": agora, "atualizada": agora}
        _historico({"tarefa": tid, "de": None, "para": CRIADA, "motivo": "tarefa registrada", "objetivo": obj, "origem": origem})
        ARQ.salvar()
    if passos is not None:
        planejar(tid, passos)
    return tid


def planejar(tid, passos):
    """Monta (ou refaz) o plano: valida tudo ANTES de mexer no estado. CRIADA/FALHOU/PRECISA_INTERVENCAO/PRONTA → PLANEJANDO → PRONTA."""
    plano = _validar_plano(passos)
    with _trava:
        t = _vivo(tid)
        if t is None:
            raise ValueError("tarefa desconhecida")
        if t["estado"] not in (CRIADA, PRONTA, FALHOU, PRECISA_INTERVENCAO):
            raise ValueError(f"não dá para planejar uma tarefa {ROTULO[t['estado']]}")
        _mudar(t, PLANEJANDO, "montando o plano" if not t["passos"] else "refazendo o plano")
        if t["passos"]:
            _historico({"tarefa": tid, "plano_anterior": [{k: p[k] for k in ("id", "descricao", "ferramenta", "args_resumo", "estado", "tentativas")} for p in t["passos"]]})
            for p in t["passos"]:
                _VIVOS.pop((tid, p["id"]), None)
        novos = []
        for p in plano:
            guardar = t["contexto"]["origem"] != "ia" and _args_guardaveis(p["args"], p["nivel"])
            f = B.FERRAMENTAS[p["ferramenta"]]
            novos.append({"id": p["id"], "descricao": p["descricao"], "ferramenta": p["ferramenta"], "args": dict(p["args"]) if guardar else None,
                          "args_resumo": P.resumir_args(p["args"], f.get("audit_args", ())), "nivel": p["nivel"], "depende_de": p["depende_de"], "estado": "pendente",
                          "tentativas": 0, "pendencia": None, "marca": None, "codigo": None, "tam": None, "verificacao": None})
            if len(_VIVOS) >= MAX_VIVOS:
                _VIVOS.pop(next(iter(_VIVOS)))
            _VIVOS[(tid, p["id"])] = dict(p["args"])
        t["passos"] = novos
        t["plano_v"] += 1                                    # versão do plano: cada plano novo é uma tentativa nova (o registro de experiências usa isto)
        t["causa"] = ""
        t["proxima_acao"] = f"executar o passo p1 ({novos[0]['descricao']})"
        _mudar(t, PRONTA, f"plano com {len(novos)} passo(s)")
        ARQ.salvar()
    _despachar()


def obter(tid):
    with _trava:
        t = _vivo(tid)
        return copy.deepcopy(t) if t else None


def listar(estados=None):
    with _trava:
        return [copy.deepcopy(t) for t in sorted(ARQ.get()["tarefas"].values(), key=lambda t: t["id"]) if estados is None or t["estado"] in estados]


def argumentos_guardados(tid, pid):
    """Cópia dos argumentos de um passo (no estado, ou só na memória do processo), ou None se não estão guardados (ação sensível, conversa, ou o programa reiniciou)."""
    with _trava:
        t = _vivo(tid)
        p = _passo(t, pid) if t else None
        if p is None:
            return None
        a = p["args"] if p["args"] is not None else _VIVOS.get((tid, pid))
        return copy.deepcopy(a) if a is not None else None


def _deps_prontas(t, p):
    return all(_passo(t, d) and _passo(t, d)["estado"] == "verificado" for d in p["depende_de"])


def _fechar_passo(p, r, ver):
    """Anota no passo o que aconteceu. Regra: se a ferramenta relatou erro e a conferência não achou o efeito, falhou; se disse que deu certo e a conferência
    não achou, REFUTADO (falso sucesso); se não há como conferir, sem_verificacao — nunca verificado."""
    p["codigo"], p["tam"] = P.redigir(str(r.get("codigo", "")), 60), len(str(r.get("texto", "")))
    p["verificacao"] = ver
    v = ver["veredito"] if ver else V.INCONCLUSIVO
    if v == V.CONFIRMADO:
        p["estado"] = "verificado"
    elif r.get("erro"):
        p["estado"] = "falhou"
    elif v == V.REFUTADO:
        p["estado"] = "refutado"
    else:
        p["estado"] = "sem_verificacao"


def _resolver(t):
    """De VERIFICANDO para onde a tarefa vai, olhando todos os passos."""
    falhos = [p for p in t["passos"] if p["estado"] in ("refutado", "falhou")]
    if falhos:
        p = falhos[0]
        if p["estado"] == "refutado":
            t["causa"] = f"passo {p['id']} ({p['descricao']}): a ferramenta respondeu que deu certo, mas o efeito não foi encontrado"
            t["proxima_acao"] = "descobrir por que o efeito não apareceu antes de tentar de novo, ou escolher outra estratégia"
        else:
            t["causa"] = f"passo {p['id']} ({p['descricao']}): falhou ({p['codigo'] or 'erro'})"
            t["proxima_acao"] = "ver o motivo da falha e tentar outra estratégia, se for permitida"
        _mudar(t, FALHOU, t["causa"])
        return
    if any(p["estado"] == "intervencao" for p in t["passos"]):
        _mudar(t, PRECISA_INTERVENCAO, t["causa"] or "um passo precisa de você")
        return
    pendentes = [p for p in t["passos"] if p["estado"] == "pendente"]
    if pendentes:
        prontos = [p for p in pendentes if _deps_prontas(t, p)]
        if prontos:
            t["proxima_acao"] = f"executar o passo {prontos[0]['id']} ({prontos[0]['descricao']})"
            _mudar(t, PRONTA, f"próximo: {prontos[0]['id']}")
        else:
            cego = next((p for p in t["passos"] if p["estado"] == "sem_verificacao"), None)
            t["causa"] = f"o passo {cego['id']} rodou, mas não dá para conferir daqui, e o próximo depende dele" if cego else "passos dependem de algo que não vai acontecer"
            t["proxima_acao"] = f"confirmar com você se o passo {cego['id']} deu certo (diga «tarefa {int(t['id'][1:])} está feita») ou cancelar" if cego else "refazer o plano"
            _mudar(t, PRECISA_INTERVENCAO, t["causa"])
        return
    if all(p["estado"] == "verificado" for p in t["passos"]):
        t["causa"], t["proxima_acao"] = "", "nada: concluída e conferida"
        _mudar(t, CONCLUIDA, "todos os passos conferidos")
    else:
        t["causa"] = "executada, mas parte do efeito não dá para conferir daqui"
        t["proxima_acao"] = "só você pode dizer se deu certo (diga «tarefa %d está feita»)" % int(t["id"][1:])
        _mudar(t, EXECUTADA_SEM_VERIFICACAO, t["causa"])


def _preparar(tid):
    """Escolhe o próximo passo e GRAVA antes de executar. Devolve {"fim": resultado} se não há o que executar agora."""
    with _trava:
        t = _vivo(tid)
        if t is None:
            return {"fim": {"tarefa": tid, "passo": None, "estado": None, "broker": None, "motivo": "tarefa desconhecida"}}

        def fim(motivo):
            return {"fim": {"tarefa": tid, "passo": None, "estado": t["estado"], "broker": None, "motivo": motivo}}
        if t["estado"] == EXECUTANDO:
            return fim("já está em execução")
        if t["estado"] == BLOQUEADA and any(p["estado"] == "aguardando" for p in t["passos"]):
            return fim("esperando a sua confirmação")
        if t["estado"] == BLOQUEADA:
            _mudar(t, PRONTA, "desbloqueada")
        if t["estado"] != PRONTA:
            return fim(f"a tarefa está {ROTULO[t['estado']]}")
        esperando = [d for d in t["depende_de"] if (_vivo(d) or {}).get("estado") != CONCLUIDA]
        if esperando:
            t["proxima_acao"] = "esperar as tarefas " + ", ".join(esperando)
            _mudar(t, BLOQUEADA, "depende de " + ", ".join(esperando))
            ARQ.salvar()
            return fim("depende de outra tarefa")
        p = next((q for q in t["passos"] if q["estado"] == "pendente" and _deps_prontas(t, q)), None)
        if p is None:
            _mudar(t, EXECUTANDO, "conferindo o que falta")
            _mudar(t, VERIFICANDO, "nenhum passo para executar")
            _resolver(t)
            ARQ.salvar()
            return fim("nada a executar")
        args = copy.deepcopy(p["args"]) if p["args"] is not None else copy.deepcopy(_VIVOS.get((tid, p["id"])))
        if args is None:
            p["estado"] = "intervencao"
            t["causa"] = f"passo {p['id']}: os argumentos não estão guardados (ação sensível ou o programa reiniciou)"
            t["proxima_acao"] = "pedir ao dono que peça a ação de novo"
            _mudar(t, PRECISA_INTERVENCAO, t["causa"])
            ARQ.salvar()
            return fim("sem os argumentos")
        reservar = RESERVAS["reservar"]
        if reservar:
            ok, quem = reservar(tid, p["ferramenta"], args)
            if not ok:                                    # outra ação usa o mesmo recurso agora: não executa, a tarefa continua PRONTA e diz por quê
                t["proxima_acao"] = f"esperar o recurso «{quem['recurso'].split(':')[0]}», em uso por {quem['dono']}"
                ARQ.salvar()
                return {"ocupado": quem}
        marca = V.antes(p["ferramenta"], args)
        p["estado"], p["tentativas"], p["marca"], p["pendencia"] = "executando", p["tentativas"] + 1, marca, None
        t["tentativas"] += 1
        t["proxima_acao"] = f"conferir o efeito do passo {p['id']}"
        _mudar(t, EXECUTANDO, f"executando {p['id']} (tentativa {p['tentativas']})")
        ARQ.salvar()                                      # gravado ANTES de chamar o corretor
        return {"pid": p["id"], "ferramenta": p["ferramenta"], "args": args, "marca": marca}


def _ativar(tid):
    with _trava:
        ATIVAS[tid] = ATIVAS.get(tid, 0) + 1


def _desativar(tid):
    with _trava:
        n = ATIVAS.get(tid, 0) - 1
        if n > 0:
            ATIVAS[tid] = n
        else:
            ATIVAS.pop(tid, None)


def executar_proximo(tid, turno=None):
    """Executa UM passo pelo corretor e confere o efeito. Devolve {"tarefa", "passo" (None se nada foi executado), "estado", "broker" (resultado estruturado), "motivo"}.
    Se outra ação usa o mesmo recurso (relé, contato, arquivo…), espera um pouco; passando de ESPERA_RECURSO_S a tarefa fica PRONTA com o motivo (nada foi executado)."""
    _ativar(tid)
    try:
        return _executar_proximo(tid, turno)
    finally:
        _desativar(tid)


def _executar_proximo(tid, turno):
    limite = time.monotonic() + ESPERA_RECURSO_S
    while True:
        try:
            pre = _preparar(tid)
        except BaseException:                             # falhou depois de reservar (ex.: ao gravar): a reserva não pode ficar presa
            _liberar_reserva(tid)
            raise
        finally:
            _despachar()
        if "ocupado" not in pre:
            break
        if time.monotonic() >= limite:
            t = obter(tid)
            quem = pre["ocupado"]
            return {"tarefa": tid, "passo": None, "estado": t["estado"] if t else None, "broker": None,
                    "motivo": f"o recurso «{quem['recurso'].split(':')[0]}» está em uso por {quem['dono']}"}
        time.sleep(0.05)
    if "fim" in pre:
        return pre["fim"]
    try:
        pid, ferr, args, marca = pre["pid"], pre["ferramenta"], pre["args"], pre["marca"]
        inesperado = None
        try:
            r = B.executar_estruturado(ferr, args, turno)       # SEM a trava das tarefas
        except Exception as e:
            inesperado, r = type(e).__name__, None
        ver = None
        if r is not None and r["estado"] == "executada":
            ver = V.depois(ferr, args, marca, r["texto"], r["erro"])
        sobra = None
        try:
            with _trava:
                t = _vivo(tid)
                p = _passo(t, pid) if t else None
                if p is not None:
                    _aplicar(t, p, r, ver, inesperado)
                    if t["estado"] == CANCELADA and r is not None and r["estado"] == "pendente":
                        sobra = r["pendencia"]                    # o dono cancelou enquanto o corretor decidia: a confirmação que nasceu não pode ficar solta
                ARQ.salvar()
                estado = t["estado"] if t else None
        except Exception as e:                                  # a ação JÁ foi ao corretor: nunca repetir por causa de falha ao registrar
            estado = None
            _historico({"tarefa": tid, "erro_ao_registrar": type(e).__name__})
        finally:
            _despachar()
        if sobra:
            atual = B.pendente_publico()
            if atual and atual.get("id") == sobra:
                B.cancelar()
        return {"tarefa": tid, "passo": pid, "estado": estado, "broker": r, "motivo": inesperado or ""}
    finally:
        _liberar_reserva(tid)


def _liberar_reserva(tid):
    liberar = RESERVAS["liberar"]
    if liberar:
        liberar(tid)


def _aplicar(t, p, r, ver, inesperado):
    if inesperado:
        p["estado"], p["codigo"] = "intervencao", P.redigir(f"Erro: {inesperado}", 60)
        t["causa"] = f"erro inesperado no corretor ({inesperado}): não sei se o passo {p['id']} chegou a acontecer"
        t["proxima_acao"] = "conferir o que aconteceu antes de repetir"
        destino = PRECISA_INTERVENCAO
    elif r["estado"] == "executada":
        if t["estado"] == CANCELADA:                         # o dono cancelou durante a execução: o passo rodou mesmo assim, o registro diz a verdade
            _fechar_passo(p, r, ver)
            _historico({"tarefa": t["id"], "passo": p["id"], "aviso": "a ação já estava em andamento quando a tarefa foi cancelada", "passo_estado": p["estado"]})
            return
        _fechar_passo(p, r, ver)
        _mudar(t, VERIFICANDO, f"{p['id']}: {p['verificacao']['veredito']}")
        _resolver(t)
        return
    elif r["estado"] == "pendente":
        p["estado"], p["pendencia"], p["codigo"] = "aguardando", r["pendencia"], "pendente"
        t["proxima_acao"] = "esperar a sua confirmação clara (sem ela nada é feito)"
        destino = BLOQUEADA
    elif r["estado"] == "negada" and r["codigo"] == "manutencao":
        p["estado"], p["tentativas"], p["codigo"] = "pendente", max(0, p["tentativas"] - 1), "manutencao"
        t["proxima_acao"] = "esperar o fim do modo manutenção"
        destino = BLOQUEADA
    else:
        p["estado"], p["codigo"] = "falhou", P.redigir(str(r["codigo"]), 60)
        t["causa"] = f"passo {p['id']} ({p['descricao']}): o corretor não executou ({r['codigo']})"
        t["proxima_acao"] = "ajustar o pedido ou escolher outra estratégia"
        destino = FALHOU
    if t["estado"] == CANCELADA:
        return
    _mudar(t, destino, t["causa"] if destino in (FALHOU, PRECISA_INTERVENCAO) else p["codigo"])


def executar(tid, turno=None, max_passos=MAX_PASSOS):
    """Executa os passos em ordem enquanto a tarefa continuar PRONTA. Pára ao pedir confirmação, ao falhar, ao concluir ou ao precisar do dono."""
    feitos = 0
    _ativar(tid)                                          # entre um passo e outro a tarefa fica PRONTA: a retomada não pode achar que é sobra de um reinício
    try:
        for _ in range(max_passos):
            r = executar_proximo(tid, turno)
            if r["passo"] is None:
                break
            feitos += 1
            t = obter(tid)
            if not t or t["estado"] != PRONTA:
                break
    finally:
        _desativar(tid)
    t = obter(tid)
    return {"tarefa": tid, "estado": t["estado"] if t else None, "passos_executados": feitos}


# ---------------------------------------------------------------- o que o corretor avisa (confirmação, cancelamento, expiração)
def _acha_pendencia(pend):
    for t in ARQ.get()["tarefas"].values():
        if t["estado"] == BLOQUEADA:
            for p in t["passos"]:
                if p["estado"] == "aguardando" and p["pendencia"] == pend:
                    return t, p
    return None, None


def _ouvir(ev):
    """Recebe os eventos do corretor. Só cuida dos que têm o id de uma confirmação que ESTA tarefa pediu; o resto (inclusive execuções automáticas, que
    `executar_proximo` já trata) é ignorado. Nunca levanta exceção e nunca chama o corretor."""
    try:
        if not isinstance(ev, dict) or not isinstance(ev.get("pendencia"), str):
            return
        tipo = ev.get("tipo")
        if tipo not in ("executada", "cancelada", "expirada", "substituida"):
            return
        with _trava:
            t, p = _acha_pendencia(ev["pendencia"])
            if t is None:
                return
            tid, pid, ferr, marca = t["id"], p["id"], p["ferramenta"], copy.deepcopy(p["marca"])
        if tipo == "executada":
            args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
            ver = V.depois(ferr, args, marca, str(ev.get("resultado", "")), bool(ev.get("erro")))
            r = {"codigo": ev.get("codigo", ""), "texto": str(ev.get("resultado", "")), "erro": bool(ev.get("erro"))}
        with _trava:
            t, p = _acha_pendencia(ev["pendencia"])
            if t is None or t["id"] != tid or p["id"] != pid:
                return
            if tipo == "executada":
                _mudar(t, EXECUTANDO, "confirmada pelo dono")
                _fechar_passo(p, r, ver)
                _mudar(t, VERIFICANDO, f"{pid}: {p['verificacao']['veredito']}")
                _resolver(t)
            elif tipo == "cancelada":
                p["estado"], t["causa"], t["proxima_acao"] = "cancelado", "o dono cancelou a confirmação", "nada"
                _mudar(t, CANCELADA, "o dono cancelou a confirmação")
            else:
                p["estado"] = "intervencao"
                t["causa"] = "a confirmação expirou sem resposta" if tipo == "expirada" else "outra ação pediu confirmação por cima desta; a antiga nunca roda"
                t["proxima_acao"] = "pedir de novo (diga «retomar a tarefa %d»)" % int(t["id"][1:])
                _mudar(t, PRECISA_INTERVENCAO, t["causa"])
            ARQ.salvar()
    except Exception:
        pass
    finally:
        _despachar()


_ouvir._friday_tarefas = True


def _registrar_observador():
    """Idempotente: nunca deixa duas cópias de `_ouvir` no corretor (nem depois de recarregar o módulo)."""
    B.OBSERVADORES[:] = [f for f in B.OBSERVADORES if not getattr(f, "_friday_tarefas", False)]
    B.OBSERVADORES.append(_ouvir)


_registrar_observador()


# ---------------------------------------------------------------- ações do dono sobre uma tarefa
def cancelar(tid, motivo=""):
    """Cancela a tarefa. Se ela estava esperando uma confirmação do corretor, cancela SÓ essa (nunca a de outra origem)."""
    pend = None
    with _trava:
        t = _vivo(tid)
        if t is None or t["estado"] in FINAIS:
            return False
        for p in t["passos"]:
            if p["estado"] == "aguardando":
                pend = p["pendencia"]
            if p["estado"] in ("pendente", "aguardando", "executando", "intervencao"):
                p["estado"] = "cancelado"
        t["causa"], t["proxima_acao"] = _txt(motivo, 200) or "cancelada pelo dono", "nada"
        _mudar(t, CANCELADA, motivo or "cancelada pelo dono")
        ARQ.salvar()
    if pend:
        atual = B.pendente_publico()
        if atual and atual.get("id") == pend:
            B.cancelar()
    _despachar()
    return True


def _conferir_de_novo(t, p):
    """Antes de repetir um passo cujo resultado não ficou claro, olha se o efeito já existe (a marca de antes está no passo)."""
    if not p.get("marca") or not V.conferivel(p["ferramenta"]) or V.classe(p["ferramenta"]) != "independente":
        return None
    args = p["args"] if p["args"] is not None else _VIVOS.get((t["id"], p["id"]))
    if args is None:
        return None
    return V.depois(p["ferramenta"], args, p["marca"], "", False)


def reabrir(tid):
    """Tenta de novo uma tarefa que falhou, travou ou espera algo. Devolve (ok, mensagem). Um passo já executado só é repetido depois de conferir que o efeito NÃO existe."""
    with _trava:
        t = _vivo(tid)
        if t is None:
            return False, "não achei essa tarefa"
        if t["estado"] not in (FALHOU, PRECISA_INTERVENCAO, BLOQUEADA):
            return False, f"a tarefa está {ROTULO[t['estado']]}; não há o que retomar"
        if any(p["estado"] == "aguardando" for p in t["passos"]):
            return False, "ela está esperando a sua confirmação"
        achados = []
        for p in t["passos"]:
            if p["estado"] in ("refutado", "falhou", "intervencao", "executando", "cancelado"):
                ver = _conferir_de_novo(t, p)
                if ver and ver["veredito"] == V.CONFIRMADO:
                    p["estado"], p["verificacao"] = "verificado", ver
                    achados.append(p["id"])
                else:
                    p["estado"] = "pendente"
        t["causa"] = ""
        _mudar(t, PRONTA, "retomada pelo dono")
        if achados:
            _mudar(t, EXECUTANDO, "conferindo o que já aconteceu")
            _mudar(t, VERIFICANDO, "o efeito de " + ", ".join(achados) + " já existia")
            _resolver(t)
        else:
            nxt = next((p for p in t["passos"] if p["estado"] == "pendente"), None)
            t["proxima_acao"] = f"executar o passo {nxt['id']}" if nxt else "conferir"
        ARQ.salvar()
        msg = "retomei" + (f"; o efeito de {', '.join(achados)} já existia e não repeti" if achados else "")
    _despachar()
    return True, msg


def recuperar(tid):
    """Fase 6. Tarefa que ficou EXECUTANDO ou VERIFICANDO sem que ESTE processo a esteja executando é sobra de uma queda ou reinício: o corretor pode ter executado o
    passo ou não (o disco foi gravado ANTES de chamar o corretor). Para cada passo «executando», olha o mundo, nunca a memória da ferramenta:
      • efeito encontrado por conferência independente → passo verificado, NÃO repete;
      • conferência independente provou que o efeito não existe (ou é só leitura) e ainda não caiu MAX_QUEDAS vezes → volta a «pendente» (pode repetir);
      • qualquer outra coisa (não dá para conferir, conferência inconclusiva, caiu demais) → «intervencao»: pode ter acontecido, NÃO repete, pede o dono.
    Devolve None se não é o caso, ou {"tarefa", "achados", "ausentes", "duvida", "repetidas", "estado"} (ids de passos)."""
    with _trava:
        t = _vivo(tid)
        if t is None or ATIVAS.get(tid) or t["estado"] not in (EXECUTANDO, VERIFICANDO):
            return None
        achados, ausentes, duvida, repetidas = [], [], [], []
        for p in t["passos"]:
            if p["estado"] != "executando":
                continue
            ver = _conferir_de_novo(t, p)
            if ver and ver["veredito"] == V.CONFIRMADO:
                p["estado"], p["verificacao"] = "verificado", ver
                achados.append(p["id"])
            elif (ver and ver["veredito"] == V.REFUTADO) or V.classe(p["ferramenta"]) == "leitura":
                if p["tentativas"] >= MAX_QUEDAS:
                    p["estado"], p["codigo"] = "intervencao", "interrompido"
                    repetidas.append(p["id"])
                else:
                    p["estado"], p["verificacao"] = "pendente", None
                    ausentes.append(p["id"])
            else:
                p["estado"], p["codigo"] = "intervencao", "interrompido"
                duvida.append(p["id"])
        t["causa"], t["proxima_acao"] = "", ""
        if duvida:
            t["causa"] = f"o programa parou durante o passo {', '.join(duvida)} e não dá para conferir daqui se a ação aconteceu; por segurança não repeti"
            t["proxima_acao"] = "veja se a ação aconteceu: diga «tarefa %d está feita» se sim, ou «retomar a tarefa %d» para eu tentar de novo" % (int(tid[1:]), int(tid[1:]))
        elif repetidas:
            t["causa"] = f"o passo {', '.join(repetidas)} foi interrompido {MAX_QUEDAS} vezes sem terminar; não repeti sozinha"
            t["proxima_acao"] = "ver por que o programa cai nesse passo; «retomar a tarefa %d» tenta de novo, se você quiser" % int(tid[1:])
        if t["estado"] == EXECUTANDO:
            _mudar(t, VERIFICANDO, "recuperada depois de queda/reinício")
        _resolver(t)
        _historico({"tarefa": tid, "recuperada": {"achados": achados, "ausentes": ausentes, "duvida": duvida, "repetidas": repetidas}})
        ARQ.salvar()
        saida = {"tarefa": tid, "achados": achados, "ausentes": ausentes, "duvida": duvida, "repetidas": repetidas, "estado": t["estado"]}
    _despachar()
    return saida


def confirmacao_perdida(tid):
    """Tarefa BLOQUEADA esperando uma confirmação que o corretor não tem mais (ela mora na memória do processo: some no reinício, expira, ou outra a substituiu).
    Nada foi executado: o passo vira «intervencao» e o dono pede de novo. Se a confirmação ainda está viva, não mexe. Devolve True se mudou algo."""
    with _trava:
        t = _vivo(tid)
        if t is None or ATIVAS.get(tid) or t["estado"] != BLOQUEADA:
            return False
        esperando = [p for p in t["passos"] if p["estado"] == "aguardando"]
        if not esperando:
            return False
        atual = B.pendente_publico()
        if atual and any(p["pendencia"] == atual.get("id") for p in esperando):
            return False
        for p in esperando:
            p["estado"] = "intervencao"
        t["causa"] = "a confirmação que eu tinha pedido se perdeu (o programa reiniciou ou ela expirou); nada foi executado"
        t["proxima_acao"] = "pedir a ação de novo («retomar a tarefa %d» só serve se eu ainda tiver os dados dela)" % int(tid[1:])
        _mudar(t, PRECISA_INTERVENCAO, t["causa"])
        ARQ.salvar()
    _despachar()
    return True


def confirmar_manual(tid, passo=None):
    """O DONO diz que um passo que ela não consegue conferir deu certo. É a única forma de uma tarefa «sem verificação» virar CONCLUIDA."""
    with _trava:
        t = _vivo(tid)
        if t is None:
            return False, "não achei essa tarefa"
        if t["estado"] not in (EXECUTADA_SEM_VERIFICACAO, PRECISA_INTERVENCAO):
            return False, f"a tarefa está {ROTULO[t['estado']]}; não falta conferir nada"
        alvo = [p for p in t["passos"] if (p["estado"] == "sem_verificacao" or (p["estado"] == "intervencao" and p.get("codigo") == "interrompido"))
                and (passo is None or p["id"] == passo)]            # «interrompido»: o programa caiu no meio e não deu para conferir; só o dono sabe se aconteceu
        if not alvo:
            return False, "não há passo esperando a sua palavra"
        for p in alvo:
            p["estado"] = "verificado"
            p["verificacao"] = {"veredito": V.CONFIRMADO, "forca": "dono", "evidencia": "o dono confirmou que deu certo", "em": _agora()}
        _mudar(t, VERIFICANDO, "o dono confirmou " + ", ".join(p["id"] for p in alvo))
        _resolver(t)
        ARQ.salvar()
    _despachar()
    return True, "anotei que deu certo"


# ---------------------------------------------------------------- pela conversa (a IA propõe; a tarefa registra e confere)
def executar_registrado(nome, args, turno=None):
    """Caminho das chamadas de ferramenta da IA: passa pelo corretor como sempre, mas as que MUDAM algo viram uma tarefa de um passo, para conferir o efeito.
    Devolve o mesmo texto de sempre; só se o efeito NÃO existir acrescenta um aviso para a IA não afirmar ao usuário que foi feito. Se o registro falhar ANTES da
    chamada, cai no caminho antigo; depois da chamada nunca repete."""
    if args is None:
        args = {}
    if not isinstance(args, dict) or not V.tem_efeito(nome):
        return B.executar(nome, args, turno)
    try:
        tid = criar(f"ação pedida na conversa: {nome.replace('_', ' ')}", origem="ia")
        planejar(tid, [{"descricao": nome.replace("_", " "), "ferramenta": nome, "args": args}])
    except Exception:
        return B.executar(nome, args, turno)
    r = executar_proximo(tid, turno)
    b = r.get("broker")
    if b is None:
        if r.get("motivo") and not r.get("passo"):
            return B.executar(nome, args, turno)             # nada foi ao corretor: segue o caminho antigo
        return "Erro: não consegui concluir essa ação; confira antes de afirmar que foi feita."
    texto = b["texto"]
    t = obter(tid)
    p = t["passos"][0] if t and t["passos"] else None
    if p and p["estado"] == "refutado":
        texto += " (Conferi o efeito e NÃO encontrei: não diga ao usuário que foi feito; diga que não consegui confirmar.)"
    if p and (p["estado"] == "refutado" or (p["estado"] == "falhou" and (p.get("codigo") or "").startswith("Erro"))):   # recusa do corretor não ganha dica: a IA deve corrigir o pedido, não trocar de ferramenta
        for d in list(DICAS):
            try:
                dica = d(nome, dict(args))
            except Exception:
                dica = None
            if isinstance(dica, str) and dica.strip():
                texto += " [" + " ".join(dica.split())[:500] + "]"
                break
    return texto


# ---------------------------------------------------------------- por voz e para o pré-córtex
def resumo_por_meta():
    """{meta: {"total", "concluidas", "conclui"}} das tarefas ligadas a metas. `conclui` = uma tarefa marcada para concluir a meta foi CONCLUÍDA e conferida."""
    saida = {}
    with _trava:
        for t in ARQ.get()["tarefas"].values():
            m = t["contexto"]["meta"]
            if not m:
                continue
            r = saida.setdefault(m, {"total": 0, "concluidas": 0, "conclui": False})
            r["total"] += 1
            if t["estado"] == CONCLUIDA:
                r["concluidas"] += 1
                r["conclui"] = r["conclui"] or t["contexto"]["conclui_meta"]
    return saida


def resumo():
    """Para o painel: quantas tarefas em cada estado (sem texto de nenhuma)."""
    with _trava:
        por = {}
        for t in ARQ.get()["tarefas"].values():
            por[t["estado"]] = por.get(t["estado"], 0) + 1
    return {"abertas": sum(n for e, n in por.items() if e not in FINAIS), "por_estado": por}


def falar_tarefas():
    with _trava:
        ativas = sorted((t for t in ARQ.get()["tarefas"].values() if t["estado"] not in FINAIS), key=lambda t: -t["atualizada"])
        partes = [f"tarefa {int(t['id'][1:])}: {t['objetivo']} ({ROTULO[t['estado']]})" for t in ativas[:5]]
        extra = len(ativas) - 5
        dica = ativas[0]["proxima_acao"] if ativas else ""
    if not partes:
        return "Nenhuma tarefa pendente."
    return "; ".join(partes) + (f"; e mais {extra}" if extra > 0 else "") + ". " + (f"Próximo passo da mais recente: {dica}." if dica else "")


_N = r"(?P<n>\d{1,6})"
_LISTA = re.compile(r"(?:quais (?:sao )?(?:as )?(?:minhas )?tarefas|minhas tarefas|tarefas (?:pendentes|abertas|em andamento)|o que (?:voce )?(?:esta|ta) fazendo|o que ficou pendente)")
_CANCELA = re.compile(rf"(?:cancela|cancelar|cancele) (?:a )?tarefa {_N}")
_RETOMA = re.compile(rf"(?:retoma|retomar|retome|continua|continuar|continue) (?:a )?tarefa {_N}")
_FEITA = re.compile(rf"(?:a )?tarefa {_N} (?:esta |ta |foi )?(?:feita|concluida|pronta|resolvida)")
_FEITA_2 = re.compile(rf"marcar (?:a )?tarefa {_N} como (?:feita|concluida)")


def tratar(texto):
    """Comandos de voz das tarefas. None se não for com elas."""
    f = M._fold(" ".join(str(texto).split()).rstrip(".!? "))
    if _LISTA.fullmatch(f):
        return falar_tarefas()
    m = _CANCELA.fullmatch(f)
    if m:
        tid = f"t{int(m.group('n')):04d}"
        return f"Cancelei a tarefa {int(m.group('n'))}." if cancelar(tid, "cancelada por voz") else "Não achei uma tarefa em aberto com esse número."
    m = _RETOMA.fullmatch(f)
    if m:
        tid = f"t{int(m.group('n')):04d}"
        ok, msg = reabrir(tid)
        if not ok:
            return f"Não retomei: {msg}."
        r = executar(tid)
        t = obter(tid)
        return f"Retomei a tarefa {int(m.group('n'))}: agora ela está {ROTULO[t['estado']]}." if t else "Retomei."
    m = _FEITA.fullmatch(f) or _FEITA_2.fullmatch(f)
    if m:
        n = int(m.group("n"))
        ok, msg = confirmar_manual(f"t{n:04d}")
        return ("Anotei que a tarefa %d deu certo." % n) if ok else f"Não mudei nada: {msg}."
    return None
