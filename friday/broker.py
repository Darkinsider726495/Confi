"""Corretor de ferramentas (tool broker): o LLM PROPÕE, o corretor AUTORIZA.
Níveis: 0 leitura | 1 baixo risco | 2 confirmação falada | 3 PIN no HUD/celular | 4 proibido.
Contaminação: depois que o turno leu dado externo (ex.: leads), todo nível >= 1 sobe um degrau."""
import os, re, json, math, time, copy, hashlib, hmac, secrets, threading, unicodedata, datetime as dt
import privacidade as P

BASE = os.path.dirname(os.path.abspath(__file__))
AUDITORIA = os.environ.get("FRIDAY_AUDITORIA") or os.path.join(BASE, "auditoria.jsonl")
LOCK = threading.RLock()
FERRAMENTAS, PEND, NOTIFICAR, NOTIFICAR_PEDIDO = {}, None, None, None   # NOTIFICAR_PEDIDO(pendência pública): notificação com botão preso ao id (quem liga é o main)
_falhas, _bloq = [], 0.0

# Quem acompanha o FIM de cada ação (hoje: tarefas.py). Cada observador recebe uma cópia do evento:
#   {tipo: executada | cancelada | expirada | substituida, ferramenta, pendencia (id ou None), nivel, decisao, ...}
# «executada» também leva args, resultado, erro e codigo CRUS, só em memória: quem ouve não pode gravá-los sem minimizar (a trilha de auditoria não tem conteúdo).
# Observador que quebra ou demora não pode atrapalhar o corretor; ele também não pode chamar o corretor de dentro do evento (o evento sai com a trava do corretor presa).
OBSERVADORES = []


def _emitir(**ev):
    for f in list(OBSERVADORES):
        try:
            f(copy.deepcopy(ev))
        except Exception:
            pass

# Confirmação de nível 2 (ver docs/ARQUITETURA.md, «Níveis de risco e confirmação»). Tudo comparado sem acento e sem pontuação.
#   CONSENTE:  palavra de consentimento EXPLÍCITO. Sozinha ("confirmo"), só vale logo depois de a pendência ser anunciada.
#   VAGAS:     respostas de conversa comum. NUNCA executam sozinhas; só valem junto do nome da ação ("pode mandar o aviso").
#   NEGA:      qualquer negativa junto de um consentimento ou do nome da ação cancela.
CONSENTE = {"confirmo", "confirmado", "autorizo"}
VAGAS = {"sim", "pode", "pode fazer", "isso", "isso mesmo"}
NAO = {"cancela", "cancelar", "nao", "esquece", "deixa pra la"}
NEGA = {"nao", "nunca", "cancela", "cancelar", "pare", "desiste", "desisto"}
_T = {"string": str, "number": (int, float), "integer": int, "boolean": bool}


class Turno:
    """Estado de uma conversa de um pedido. Fica 'contaminado' ao ler dados de terceiros."""
    def __init__(self):
        self.contaminado = False


def registrar(nome, desc, props, req, fn, nivel=0, externo=False, externo_dyn=None, rotulo=None, audit_args=(), interno=False):
    """externo_dyn(resultado) -> bool: a ferramenta só contamina o turno quando o RESULTADO traz dado de terceiros (ex.: lembrar um estudo da internet).
    rotulo: como o usuário NOMEIA a ação ao confirmar («confirmo enviar sms»). Texto, ou função(args) -> texto. Padrão: o nome sem sublinhados.
    audit_args: nomes de argumentos de TEXTO que são identificadores curtos (relé, alias do contato) e podem ficar em claro na trilha; os demais textos viram só o tamanho.
    props aceita, além de type: minimum, maximum (números), maxLength e enum (textos) e ao_exceder="limitar" (ajusta ao limite e AVISA; o padrão é recusar).
    interno=True: a ferramenta NÃO vai para a IA (fora de definicoes()) e o corretor a recusa, a menos que o pedido venha de código
    da própria FRIDAY dentro de `with uso_interno():` (hoje: só o ciclo do MAE). Continua passando por validação, nível, coordenador e auditoria."""
    FERRAMENTAS[nome] = dict(fn=fn, desc=desc, props=props, req=req, nivel=nivel, externo=externo, externo_dyn=externo_dyn, rotulo=rotulo,
                             audit_args=tuple(audit_args), interno=bool(interno))


# Ferramentas internas: quem pede é código da FRIDAY (o ciclo do MAE), nunca a IA. A marca vale só na thread que abriu o bloco,
# então um pedido da conversa (outra thread, ou a mesma fora do bloco) continua recusado.
_interno = threading.local()


class uso_interno:
    """`with B.uso_interno(): B.executar_estruturado("lab_criar", ...)` — só código da FRIDAY abre este bloco; a IA não tem como."""
    def __enter__(self):
        _interno.n = getattr(_interno, "n", 0) + 1
        return self

    def __exit__(self, *exc):
        _interno.n = max(0, getattr(_interno, "n", 0) - 1)
        return False


def _em_uso_interno():
    return getattr(_interno, "n", 0) > 0


def _norm(texto):
    """minúsculas, sem acento, sem pontuação: «Confirmo, enviar SMS!» -> «confirmo enviar sms»."""
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _rotulo(f, nome, args):
    r = f.get("rotulo")
    try:
        r = r(args) if callable(r) else r
    except Exception:
        r = None
    return str(r).strip() if r else nome.replace("_", " ")


def _resumo(rotulo, args):
    """Descrição FEITA PELO CORRETOR do que vai ser executado (a IA pode descrever mal): o nome da ação e os argumentos, truncados."""
    partes = "; ".join(f"{k}: {' '.join(str(v).split())[:80]}" for k, v in args.items())
    return f"{rotulo} ({partes})" if partes else rotulo


def _esquema_publico(props):
    """O esquema que vai para a IA: sem a chave interna ao_exceder, que vira uma frase na descrição do parâmetro."""
    saida = {}
    for k, v in props.items():
        v = dict(v)
        if v.pop("ao_exceder", None) == "limitar":
            v["description"] = (str(v.get("description", "")) + " Valor fora da faixa é ajustado ao limite, e a resposta avisa.").strip()
        saida[k] = v
    return saida


def definicoes():
    """O que a IA recebe: tudo, menos as ferramentas internas."""
    return [{"name": n, "description": f["desc"],
             "input_schema": {"type": "object", "properties": _esquema_publico(f["props"]), "required": f["req"], "additionalProperties": False}}
            for n, f in FERRAMENTAS.items() if not f.get("interno")]


class PedidoInvalido(ValueError):
    """Pedido recusado pelo corretor. A mensagem vai para quem pediu; `codigo` é curto, seguro para a trilha e não repete o que foi recebido."""
    def __init__(self, msg, codigo):
        super().__init__(msg)
        self.codigo = codigo


def _fmt(x):
    return f"{x:g}" if isinstance(x, (int, float)) and not isinstance(x, bool) else str(x)


def _validar(f, args):
    """Confere o pedido com o esquema da ferramenta. Devolve (argumentos, ajustes). Fora da faixa: RECUSA (PedidoInvalido) — nunca muda o valor em silêncio.
    Só ajusta ao limite onde o parâmetro declara ao_exceder="limitar"; então `ajustes` = {nome: (pedido, usado)} e quem executa avisa."""
    if not isinstance(args, dict):
        raise PedidoInvalido("argumentos inválidos", "args")
    saida, ajustes = dict(args), {}
    for k, v in args.items():
        esq = f["props"].get(k)
        if esq is None:
            raise PedidoInvalido(f"argumento desconhecido: {str(k)[:40]}", "desconhecido")
        t = esq["type"]
        if (isinstance(v, bool) and t != "boolean") or not isinstance(v, _T[t]):
            raise PedidoInvalido(f"{k} deve ser {t}", f"tipo:{k}")
        if t in ("number", "integer") and not isinstance(v, bool):
            if not math.isfinite(v):
                raise PedidoInvalido(f"{k} deve ser um número finito", f"faixa:{k}")
            lo, hi = esq.get("minimum"), esq.get("maximum")
            novo = v if lo is None or v >= lo else lo
            novo = novo if hi is None or novo <= hi else hi
            if novo != v:
                if esq.get("ao_exceder") == "limitar":
                    saida[k], ajustes[k] = novo, (v, novo)
                else:
                    faixa = (f"estar entre {_fmt(lo)} e {_fmt(hi)}" if lo is not None and hi is not None
                             else f"ser no mínimo {_fmt(lo)}" if lo is not None else f"ser no máximo {_fmt(hi)}")
                    raise PedidoInvalido(f"{k} deve {faixa} (recebi {_fmt(v)})", f"faixa:{k}")
        if t == "string":
            if len(v) > esq.get("maxLength", 1000):
                raise PedidoInvalido(f"{k} longo demais (máximo {esq.get('maxLength', 1000)} caracteres, recebi {len(v)})", f"tamanho:{k}")
            if "enum" in esq and v not in esq["enum"]:
                raise PedidoInvalido(f"{k} deve ser um destes: {', '.join(map(str, esq['enum']))}", f"enum:{k}")
    for k in f["req"]:
        if k not in args:
            raise PedidoInvalido(f"falta o argumento {k}", f"falta:{k}")
    return saida, ajustes


def _aviso_ajustes(ajustes):
    return " (Ajustei " + "; ".join(f"{k} de {_fmt(a)} para {_fmt(b)}" for k, (a, b) in ajustes.items()) + ".)" if ajustes else ""


# ---------- auditoria em cadeia de hashes (adulterar uma linha quebra todas as seguintes) ----------
def _hash(prev, ev):
    return hashlib.sha256((prev + json.dumps(ev, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def _ultimo_hash():
    try:
        with open(AUDITORIA, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            ls = f.read().splitlines()
        return json.loads(ls[-1])["hash"] if ls else "0" * 64
    except (FileNotFoundError, ValueError, KeyError):
        return "0" * 64


_CONTROLE = {"ts", "prev", "hash", "ferramenta", "decisao"}      # campos que o corretor controla: não passam pela redação


def _audit(**ev):
    """Uma linha na trilha. Todo texto livre que qualquer módulo mande passa antes pela redação (privacidade.redigir): a trilha guarda o fato, não o conteúdo."""
    with LOCK:
        ev = {k: (P.redigir(v, 500) if isinstance(v, str) and k not in _CONTROLE else v) for k, v in ev.items()}
        ev["ts"] = dt.datetime.now().isoformat(timespec="seconds")
        ev["prev"] = _ultimo_hash()
        ev["hash"] = _hash(ev["prev"], ev)
        with open(AUDITORIA, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def verificar_auditoria():
    """Confere a cadeia de hashes. Retorna (ok, nº de eventos válidos)."""
    prev, n = "0" * 64, 0
    try:
        with open(AUDITORIA, encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except FileNotFoundError:
        return True, 0
    for l in linhas:
        try:
            e = json.loads(l)
            h = e.pop("hash")
        except (ValueError, KeyError):
            return False, n
        if e.get("prev") != prev or _hash(prev, e) != h:
            return False, n
        prev, n = h, n + 1
    return True, n


def ultimos(n=6):
    try:
        with open(AUDITORIA, encoding="utf-8") as f:
            ls = f.read().splitlines()[-n:]
        return [{k: e[k] for k in ("ts", "ferramenta", "decisao", "nivel") if k in e} for e in map(json.loads, ls)]
    except (FileNotFoundError, ValueError):
        return []


# ---------- decisão ----------
def _nivel(f, args, turno):
    n = f["nivel"](args) if callable(f["nivel"]) else f["nivel"]
    return n if n >= 4 else min(n + (1 if turno.contaminado and n >= 1 else 0), 3)


def _dyn(fn, r):
    try:
        return bool(fn(r))
    except Exception:
        return True  # na dúvida, trata como dado de terceiros


def _rodar(nome, f, args, n, decisao, turno=None, ajustes=None, pendencia=None, saida=None):
    """Executa e registra o FATO na trilha: argumentos resumidos (sem o texto), código do resultado e tamanho. O texto do resultado volta só para quem pediu."""
    erro = None
    try:
        r = str(f["fn"](**args))
    except Exception as e:
        erro, r = type(e).__name__, f"Erro: {e}"
    if turno and (f["externo"] or (f.get("externo_dyn") and _dyn(f["externo_dyn"], r))):
        turno.contaminado = True
    codigo = f"Erro: {erro}" if erro else ("Erro" if r.startswith("Erro") else "ok")
    if saida is not None:
        saida["codigo"] = codigo                              # quem pediu o estado estruturado recebe o mesmo código que a trilha guardou
    extra = {"ajustes": sorted(ajustes)} if ajustes else {}
    _audit(ferramenta=nome, args=P.resumir_args(args, f.get("audit_args", ())), nivel=n, decisao=decisao, resultado=codigo, tam=len(r), **extra)
    _emitir(tipo="executada", ferramenta=nome, args=args, resultado=r, erro=bool(erro or r.startswith("Erro")), codigo=codigo, decisao=decisao, pendencia=pendencia, nivel=n)
    return r + _aviso_ajustes(ajustes)


def _res(estado, texto, codigo, nivel=None, pendencia=None, ajustes=None):
    return {"estado": estado, "texto": texto, "codigo": codigo, "nivel": nivel, "pendencia": pendencia, "erro": codigo.startswith("Erro"), "ajustes": ajustes or {}}


def executar_estruturado(nome, args, turno=None):
    """Como `executar`, mas diz o que aconteceu sem precisar adivinhar pelo começo da frase. Devolve
    {estado: executada | pendente | recusada | negada, texto (o mesmo que `executar` devolve), codigo, nivel, pendencia (id, se ficou pendente), erro, ajustes}.
    «executada» NÃO quer dizer que o objetivo foi atingido: só que o corretor rodou a ferramenta (quem precisa saber do efeito confere por fora, ver verificacao.py)."""
    turno = turno or Turno()
    f = FERRAMENTAS.get(nome)
    if not f:
        _audit(ferramenta=nome, decisao="desconhecida")
        return _res("recusada", "Ferramenta desconhecida.", "desconhecida")
    if f.get("interno") and not _em_uso_interno():
        _audit(ferramenta=nome, decisao="negado_interno")
        return _res("negada", "Ação proibida: esta ferramenta é interna do laboratório e só o ciclo do modo experimental a usa.", "interno", f.get("nivel"))
    try:
        args, ajustes = _validar(f, args or {})
    except ValueError as e:
        codigo = getattr(e, "codigo", "invalido")
        _audit(ferramenta=nome, decisao="invalida", resultado=codigo)
        return _res("recusada", f"Pedido inválido: {e}", codigo)
    n = _nivel(f, args, turno)
    if n >= 4:
        _audit(ferramenta=nome, nivel=n, decisao="negado")
        return _res("negada", "Ação proibida.", "nivel4", n)
    if n >= 2 and os.path.exists(os.path.join(BASE, "MANUTENCAO")):
        _audit(ferramenta=nome, nivel=n, decisao="negado_manutencao")
        return _res("negada", "Modo manutenção ativo: ações de nível 2 ou mais estão desligadas.", "manutencao", n)
    if n >= 2:
        texto, pid = _pedir(nome, args, n, ajustes)
        return _res("pendente", texto, "pendente", n, pid, ajustes)
    saida = {}
    r = _rodar(nome, f, args, n, "automatico", turno, ajustes, saida=saida)
    return _res("executada", r, saida.get("codigo", "ok"), n, None, ajustes)


def executar(nome, args, turno=None):
    return executar_estruturado(nome, args, turno)["texto"]


def _pedir(nome, args, n, ajustes=None):
    global PEND
    desc = f"{nome} {json.dumps(args, ensure_ascii=False)}"
    f = FERRAMENTAS[nome]
    rotulo = _rotulo(f, nome, args)
    with LOCK:
        if _pend_valida():                                   # a IA propôs outra coisa por cima: a antiga NUNCA roda, e fica registrado
            _audit(ferramenta=PEND["nome"], decisao="substituido")
            _emitir(tipo="substituida", ferramenta=PEND["nome"], pendencia=PEND["id"], nivel=PEND["nivel"], decisao="substituido")
        PEND = dict(nome=nome, args=args, nivel=n, tipo="voz" if n == 2 else "pin",
                    expira=time.time() + (45 if n == 2 else 120), desc=desc, ajustes=ajustes or {},
                    id=secrets.token_hex(3), rotulo=rotulo, chave=tuple(_norm(rotulo).split()), resumo=_resumo(rotulo, args), falas=0)
        publica = _publica(PEND)
    _audit(ferramenta=nome, args=P.resumir_args(args, f.get("audit_args", ())), nivel=n, decisao="pendente")
    if n >= 3 and NOTIFICAR:
        try:
            NOTIFICAR(f"FRIDAY pede confirmação (nível 3): {desc}. Abra o HUD e digite o PIN.")
        except Exception:
            pass
    if n == 2 and NOTIFICAR_PEDIDO:
        try:
            NOTIFICAR_PEDIDO(publica)
        except Exception:
            pass                                             # sem notificação o painel e a voz continuam valendo
    como = (f'dizendo "confirmo" logo em seguida (ou "confirmo {rotulo}" mais tarde). Um "sim", "pode" ou "isso" solto NÃO vale'
            if n == 2 else "no HUD ou no celular, com o PIN")
    return (f"AÇÃO PENDENTE ({desc}). O usuário precisa confirmar {como}. "
            "Descreva a ação a ele em uma frase e não tente repetir."), publica["id"]


def _publica(p):
    return {"id": p["id"], "desc": p["desc"], "resumo": p["resumo"], "rotulo": p["rotulo"], "nivel": p["nivel"], "tipo": p["tipo"],
            "expira_em": int(p["expira"] - time.time())}


def frase_pendente():
    """O que o CORRETOR diz ao usuário sobre a pendência (None se não há). Não depende da IA: é o que realmente será executado."""
    with LOCK:
        p = _pend_valida()
        if not p:
            return None
        if p["tipo"] == "voz":
            return f"Aguardo sua confirmação para: {p['resumo']}. Diga «confirmo» para executar ou «cancela» para desistir."
        return f"Aguardo o PIN, no painel ou no celular, para: {p['resumo']}."


def _pend_valida():
    global PEND
    if PEND and time.time() > PEND["expira"]:
        _audit(ferramenta=PEND["nome"], decisao="expirado")
        _emitir(tipo="expirada", ferramenta=PEND["nome"], pendencia=PEND["id"], nivel=PEND["nivel"], decisao="expirado")
        PEND = None
    return PEND


def confirmar_voz(texto):
    """Chamado ANTES do LLM em toda fala do usuário. Retorna (tratado, resposta)."""
    global PEND
    with LOCK:
        p = _pend_valida()
        if not p:
            return False, ""
        t = _norm(texto)
        palavras = set(t.split())
        cita = bool(p["chave"]) and all(w in palavras for w in p["chave"])      # «mandar aviso» aparece na fala
        forte = bool(palavras & CONSENTE)                                        # confirmo / confirmado / autorizo
        if t in NAO or (palavras & NEGA and (cita or forte) and len(t.split()) <= 8):
            PEND = None
            _audit(ferramenta=p["nome"], decisao="cancelado")
            _emitir(tipo="cancelada", ferramenta=p["nome"], pendencia=p["id"], nivel=p["nivel"], decisao="cancelado")
            return True, "Cancelado."
        imediata = p["falas"] == 0                       # nenhuma outra fala desde que a pendência foi anunciada
        forte_sozinho = forte and palavras <= (CONSENTE | {"eu"})                # «confirmo», sem dizer qual ação
        vaga = (t in VAGAS and imediata) or (cita and bool(palavras & {"sim", "pode", "isso"}) and not forte)   # «sim», «pode», «pode mandar o aviso»
        if forte and cita or (forte_sozinho and imediata):
            executar = True                              # consentimento explícito preso à ação (a qualquer hora enquanto vale) ou logo após o anúncio
        elif forte_sozinho or vaga:
            executar = False                             # «confirmo» depois de outra conversa, ou resposta vaga: não executa, pede a frase inteira
        else:
            p["falas"] += 1                              # conversa comum (inclui «sim» respondendo a outra pergunta): segue para a IA
            return False, ""
        if p["tipo"] != "voz":
            return True, "Essa ação crítica exige o PIN no HUD ou no celular."
        if not executar:
            _audit(ferramenta=p["nome"], decisao="confirmacao_vaga")
            return True, (f"Preciso de uma confirmação clara para: {p['resumo']}. "
                          f"Diga «confirmo {p['rotulo']}» para executar, ou «cancela».")
        PEND = None
        return True, _rodar(p["nome"], FERRAMENTAS[p["nome"]], p["args"], p["nivel"], "confirmado_voz", ajustes=p.get("ajustes"), pendencia=p["id"])


def confirmar_botao(id_pendencia):
    """Botão «Confirmo» do painel ou da notificação. Só vale para a pendência cujo id estava na tela: se a IA propôs outra coisa
    depois, o id mudou e o toque não executa nada. Nível 3 continua só com PIN."""
    global PEND
    with LOCK:
        p = _pend_valida()
        if not p:
            return False, "Nada pendente."
        if not isinstance(id_pendencia, str) or not hmac.compare_digest(id_pendencia, p["id"]):
            _audit(ferramenta=p["nome"], decisao="botao_id_diferente")
            return False, "A ação pendente mudou. Confira o painel e confirme de novo."
        if p["tipo"] != "voz":
            return True, "Essa ação crítica exige o PIN no HUD ou no celular."
        PEND = None
        return True, _rodar(p["nome"], FERRAMENTAS[p["nome"]], p["args"], p["nivel"], "confirmado_botao", ajustes=p.get("ajustes"), pendencia=p["id"])


def confirmar_pin(pin):
    global PEND, _bloq
    esperado = os.getenv("FRIDAY_PIN", "")
    with LOCK:
        agora = time.time()
        if agora < _bloq:
            return False, "Muitas tentativas. Aguarde um minuto."
        p = _pend_valida()
        if not p:
            return False, "Nenhuma ação pendente."
        if not esperado or not hmac.compare_digest(str(pin), esperado):
            _falhas.append(agora)
            _falhas[:] = [x for x in _falhas if agora - x < 300]
            if len(_falhas) >= 5:
                _bloq = agora + 60
                _falhas.clear()
            _audit(ferramenta=p["nome"], decisao="pin_errado")
            return False, "PIN incorreto."
        PEND = None
        return True, _rodar(p["nome"], FERRAMENTAS[p["nome"]], p["args"], p["nivel"], "confirmado_pin", ajustes=p.get("ajustes"), pendencia=p["id"])


def cancelar():
    global PEND
    with LOCK:
        if PEND:
            _audit(ferramenta=PEND["nome"], decisao="cancelado")
            _emitir(tipo="cancelada", ferramenta=PEND["nome"], pendencia=PEND["id"], nivel=PEND["nivel"], decisao="cancelado")
        PEND = None


def pendente_publico():
    with LOCK:
        p = _pend_valida()
        return None if not p else _publica(p)
