"""Autonomia da FRIDAY: ela aprende os seus hábitos, propõe rotinas e passa a fazê-las sozinha, e conta o que aprendeu e o que fez.

  hábito   = você chamou o mesmo protocolo ("bom dia", "modo foco"...) em horários parecidos por vários dias
  rotina   = um protocolo que ela dispara sozinha no horário aprendido (ou combinado com você)
  vigília  = avisos por iniciativa própria: o que aprendeu ao consolidar a memória, pedidos de evolução esquecidos

Modos (só VOCÊ muda, falando ou pelo painel; a IA não tem ferramenta para isso):
  desligada   nada aprendido nem feito por iniciativa (hábitos, rotinas, devaneios); só os lembretes, o briefing e a consolidação diária da memória
  assistente  (padrão) aprende hábitos, PERGUNTA antes de criar uma rotina, roda só as que você aprovou
  piloto      igual, e adota sozinha as rotinas que só leem e falam (nível 0) depois de 5 dias de hábito firme; avisa e dá para desfazer

Limites que não mudam em nenhum modo: rotina só com ferramentas de nível 0 ou 1 (nunca SMS, ligação, relé, PIN); toda execução passa pelo
corretor e fica na auditoria como rotina:<nome>; no máximo 12 execuções por dia; cada rotina roda uma vez por dia e só até 10 minutos
depois da hora (celular desligado às 8h não dispara às 14h); mensagens por iniciativa dela respeitam o silêncio e o modo foco."""
import os, re, json, time, threading, statistics, datetime as dt
import broker as B
import protocolos as P
import ferramentas as F
import vida as V

BASE = os.path.dirname(os.path.abspath(__file__))
MODOS = ("desligada", "assistente", "piloto")
HISTORICO_DIAS = 21
JANELA_MIN = 45          # "mais ou menos a mesma hora" = até 45 minutos de diferença
DIAS_ASSISTENTE = 3      # dias de hábito para ela sugerir
DIAS_PILOTO = 5          # dias de hábito para ela adotar sozinha (só rotinas de nível 0)
MAX_ROTINAS = 8
MAX_EXEC_DIA = 12
ATRASO_MAX_MIN = 10
VALIDADE_SUGESTAO = 15 * 60
RECUSA_DIAS = 14
MAX_LOG = 40
MAX_AVISOS_DIA = 3
_trava = threading.RLock()
_e = {"v": None, "arq": None}


def _arq():
    return os.environ.get("FRIDAY_AUTONOMIA_ARQ") or os.path.join(BASE, ".autonomia.json")


def _padrao():
    return {"modo": "assistente", "habitos": {}, "rotinas": {}, "sugestao": None, "log": [], "exec_dia": {"d": "", "n": 0},
            "vigilia": {"sono": "", "pedidos": 0.0, "dia": "", "n": 0}}


def _hora_ok(h):
    return isinstance(h, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", h) is not None


def _estado():
    """Lê o arquivo uma vez e valida tudo: um arquivo adulterado ou quebrado nunca vira ação."""
    with _trava:
        arq = _arq()
        if _e["v"] is not None and _e["arq"] == arq:
            return _e["v"]
        v = _padrao()
        try:
            with open(arq, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = None
        if isinstance(d, dict):
            if d.get("modo") in MODOS:
                v["modo"] = d["modo"]
            if isinstance(d.get("habitos"), dict):
                for nome, h in list(d["habitos"].items())[:40]:
                    if isinstance(nome, str) and isinstance(h, dict) and isinstance(h.get("dias"), dict):
                        dias = {k: [int(x) for x in m if isinstance(x, int) and 0 <= x < 1440][:6] for k, m in h["dias"].items()
                                if re.fullmatch(r"\d{4}-\d\d-\d\d", str(k)) and isinstance(m, list)}
                        v["habitos"][nome] = {"dias": dias, "recusado_ate": float(h["recusado_ate"]) if isinstance(h.get("recusado_ate"), (int, float)) else 0.0,
                                              "sugerido": float(h["sugerido"]) if isinstance(h.get("sugerido"), (int, float)) else 0.0}
            if isinstance(d.get("rotinas"), dict):
                for nome, r in list(d["rotinas"].items())[:MAX_ROTINAS]:
                    if isinstance(nome, str) and isinstance(r, dict) and _hora_ok(r.get("hora")):
                        v["rotinas"][nome] = {"hora": r["hora"], "origem": r.get("origem") if r.get("origem") in ("aprendida", "pedida", "piloto") else "pedida",
                                              "criada": str(r.get("criada", ""))[:10], "ultima": str(r.get("ultima") or "")[:10]}
            s = d.get("sugestao")
            if isinstance(s, dict) and isinstance(s.get("nome"), str) and _hora_ok(s.get("hora")) and isinstance(s.get("quando"), (int, float)):
                v["sugestao"] = {"nome": s["nome"], "hora": s["hora"], "quando": float(s["quando"])}
            if isinstance(d.get("log"), list):
                v["log"] = [{"ts": str(x.get("ts", ""))[:19], "txt": str(x.get("txt", ""))[:240]} for x in d["log"][-MAX_LOG:] if isinstance(x, dict)]
            ed = d.get("exec_dia")
            if isinstance(ed, dict) and isinstance(ed.get("n"), int):
                v["exec_dia"] = {"d": str(ed.get("d", ""))[:10], "n": max(0, ed["n"])}
            vg = d.get("vigilia")
            if isinstance(vg, dict):
                v["vigilia"] = {"sono": str(vg.get("sono", ""))[:10], "pedidos": float(vg["pedidos"]) if isinstance(vg.get("pedidos"), (int, float)) else 0.0,
                                "dia": str(vg.get("dia", ""))[:10], "n": vg["n"] if isinstance(vg.get("n"), int) else 0}
        _e["v"], _e["arq"] = v, arq
        return v


def _salvar():
    with _trava:
        e = _estado()
        e["log"] = e["log"][-MAX_LOG:]
        arq = _arq()
        tmp = arq + ".tmp"
        try:
            os.makedirs(os.path.dirname(arq) or ".", exist_ok=True)
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
                json.dump(e, f, ensure_ascii=False)
            os.replace(tmp, arq)
        except OSError:
            pass  # sem disco: segue em memória, nunca derruba a FRIDAY


def _agora(agora=None):
    return agora or dt.datetime.now()


def _anotar(txt, agora=None):
    e = _estado()
    e["log"].append({"ts": _agora(agora).isoformat(timespec="seconds"), "txt": str(txt)[:240]})
    _salvar()


def modo():
    return _estado()["modo"]


def _minutos(agora):
    return agora.hour * 60 + agora.minute


def _hhmm(m):
    m = int(m) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------- o que pode virar rotina
def nivel_rotina(nome):
    """Maior nível de risco entre os passos do protocolo; None se não pode ser rotina (ferramenta que não existe, nível variável ou 2+)."""
    p = P.carregar().get(nome)
    if not p:
        return None
    mx = 0
    for passo in p["passos"]:
        if "ferramenta" not in passo:
            continue
        f = B.FERRAMENTAS.get(passo["ferramenta"])
        if not f or not isinstance(f["nivel"], int) or isinstance(f["nivel"], bool):
            return None
        if f["nivel"] > 1:
            return None
        mx = max(mx, f["nivel"])
    return mx


def pode_ser_rotina(nome):
    return nivel_rotina(nome) is not None


# ---------------------------------------------------------------- aprender o hábito
def _padrao_horario(nome):
    """Devolve (dias_no_padrao, minuto_tipico) se o protocolo costuma ser chamado na mesma hora em dias diferentes; senão None."""
    h = _estado()["habitos"].get(nome)
    if not h:
        return None
    dias = sorted(h["dias"].items())[-14:]
    primeiros = [(d, min(m)) for d, m in dias if m]
    if len(primeiros) < DIAS_ASSISTENTE:
        return None
    mediana = statistics.median(m for _, m in primeiros)

    def dist(a, b):
        x = abs(a - b)
        return min(x, 1440 - x)

    dentro = [m for _, m in primeiros if dist(m, mediana) <= JANELA_MIN]
    if len(dentro) < DIAS_ASSISTENTE or len(dentro) < 0.6 * len(primeiros):
        return None
    tipico = int(round(statistics.median(dentro) / 5.0)) * 5
    return len(dentro), tipico


def observar(nome, agora=None):
    """Chamado quando VOCÊ aciona um protocolo. Aprende o horário e devolve uma frase (sugestão ou aviso) para ela dizer, ou ''."""
    agora = _agora(agora)
    with _trava:
        e = _estado()
        if e["modo"] == "desligada" or not nome or nome == "?":
            return ""
        h = e["habitos"].setdefault(nome, {"dias": {}, "recusado_ate": 0.0, "sugerido": 0.0})
        dia = f"{agora:%Y-%m-%d}"
        lista = h["dias"].setdefault(dia, [])
        if len(lista) < 6:
            lista.append(_minutos(agora))
        corte = f"{agora - dt.timedelta(days=HISTORICO_DIAS):%Y-%m-%d}"
        for d in [d for d in h["dias"] if d < corte]:
            del h["dias"][d]
        for n in [n for n, x in e["habitos"].items() if not x["dias"]]:
            e["habitos"].pop(n, None)
        for n in list(e["habitos"])[40:]:
            e["habitos"].pop(n, None)
        _salvar()
        if nome in e["rotinas"] or not pode_ser_rotina(nome) or len(e["rotinas"]) >= MAX_ROTINAS:
            return ""
        if time.time() < h["recusado_ate"] or time.time() - h["sugerido"] < 3 * 86400:
            return ""
        padrao = _padrao_horario(nome)
        if not padrao:
            return ""
        dias, tipico = padrao
        hora = _hhmm(tipico)
        if e["modo"] == "piloto" and nivel_rotina(nome) == 0 and dias >= DIAS_PILOTO:
            _criar(nome, hora, "piloto", agora)
            return (f"Percebi que você pede o protocolo {nome} por volta das {hora} há {dias} dias. Passei a fazer isso sozinha nesse horário. "
                    f"Se não quiser, diga: cancele a rotina {nome}.")
        s = e["sugestao"]
        if s and time.time() - s["quando"] < VALIDADE_SUGESTAO:
            return ""  # uma pergunta de cada vez
        e["sugestao"] = {"nome": nome, "hora": hora, "quando": time.time()}
        h["sugerido"] = time.time()
        _salvar()
        return (f"Aliás, {F.tratamento()}: você pede o protocolo {nome} por volta das {hora} há {dias} dias. "
                f"Quer que eu faça isso sozinha todo dia nesse horário? Diga sim ou não.")


def _criar(nome, hora, origem, agora=None):
    agora = _agora(agora)
    e = _estado()
    e["rotinas"][nome] = {"hora": hora, "origem": origem, "criada": f"{agora:%Y-%m-%d}", "ultima": ""}
    e["sugestao"] = None
    _anotar(f"Rotina criada: {nome} às {hora} ({origem}).", agora)
    B._audit(ferramenta="autonomia:rotina", decisao="criada", nome=nome, hora=hora, origem=origem)
    try:  # a rotina também vira um neurônio: ela "sabe" o que faz sozinha
        import memoria as M
        if M.ativo():
            M.guardar(f"Rotina {nome}", f"Faço o protocolo {nome} sozinha todo dia às {hora}. Foi {'combinado com você' if origem == 'pedida' else 'aprendido do seu hábito'}. "
                      f"Para desfazer, diga: cancele a rotina {nome}.", "preferencia", 3, "rotina autonomia")
    except Exception:
        pass


# ---------------------------------------------------------------- comandos de voz (só o usuário fala por aqui)
def _norm(t):
    return P._norm(t)


def _nome_protocolo(texto):
    t = _norm(texto)
    for nome, p in P.carregar().items():
        if t == _norm(nome) or t in {_norm(a) for a in p.get("apelidos", [])}:
            return nome
    return None


_SIM = re.compile(r"^(sim|pode|pode sim|pode fazer|pode ser|aceito|faca|faca sozinha|pode automatizar|automatize|quero|claro|combinado|ok|isso mesmo)( chefe)?$")
_NAO = re.compile(r"^(nao|nao quero|agora nao|nunca|deixa|deixa pra la|nao precisa|nao obrigado)( chefe)?$")
_ROTINA_NOVA = re.compile(r"^(?:crie|criar|faca|fazer|programe|programar|agende|agendar)(?: uma| a)? rotina (?:do |da |de |o |a )?(.+?) (?:as|a|às) (\d{1,2})(?: ?(?:h|horas?)(?: ?(\d{2}))?| ?: ?(\d{2}))?(?: horas?)?$")
_CANCELA = re.compile(r"^(?:cancele|cancelar|apague|apagar|remova|remover|desfaca|desfazer|pare|parar)(?: com)?(?: a)? rotina (?:do |da |de |o |a )?(.+)$")
_LISTA = re.compile(r"^(?:minhas rotinas|quais rotinas|quais sao as rotinas|quais sao suas rotinas|lista de rotinas|listar rotinas|suas rotinas)$")
_FEZ = re.compile(r"^(?:o que (?:voce )?fez (?:sozinha|sozinho|por conta propria)|o que voce fez sozinha hoje|relatorio de autonomia|o que aconteceu sozinho)$")
_PILOTO = re.compile(r"^(?:(?:ativar|ative|ligar|ligue|entrar no|entre no|modo) )?piloto automatico(?: ligado| ativado)?$")
_ASSIST = re.compile(r"^(?:modo assistente|autonomia assistida|(?:desligar|desligue|sair do|saia do|desativar|desative) (?:o )?piloto automatico)$")
_OFF = re.compile(r"^(?:modo manual|autonomia desligada|(?:desligar|desligue|desativar|desative|pare com) (?:a )?autonomia)$")
_STATUS = re.compile(r"^(?:autonomia|qual (?:e )?(?:o )?(?:seu )?modo(?: de autonomia)?|status da autonomia|como esta sua autonomia)$")


def _sem_pendencia():
    try:
        return not B.pendente_publico()
    except Exception:
        return True


def tratar(texto, agora=None):
    """Comandos de autonomia. Devolve a resposta ou None (segue o fluxo normal). Aqui, e só aqui, o modo e as rotinas mudam."""
    t = re.sub(r"^(?:friday|jarvis|fraide),? ", "", _norm(texto))
    e = _estado()
    agora = _agora(agora)
    if _PILOTO.match(t):
        e["modo"] = "piloto"
        _salvar()
        B._audit(ferramenta="autonomia:modo", decisao="piloto")
        return ("Piloto automático ligado. Aprendo seus hábitos e assumo sozinha as rotinas que só leem e falam, depois de cinco dias de hábito firme. "
                "Nada de SMS, ligação, relé ou PIN sem você. Para voltar, diga: modo assistente.")
    if _ASSIST.match(t):
        e["modo"] = "assistente"
        _salvar()
        B._audit(ferramenta="autonomia:modo", decisao="assistente")
        return "Modo assistente. Aprendo seus hábitos e sempre pergunto antes de criar uma rotina."
    if _OFF.match(t):
        e["modo"] = "desligada"
        e["sugestao"] = None
        _salvar()
        B._audit(ferramenta="autonomia:modo", decisao="desligada")
        return "Autonomia desligada. Não aprendo hábitos, não disparo rotinas e não faço devaneios. Mantenho os lembretes, o briefing que você configurou e a consolidação diária da memória."
    if _STATUS.match(t):
        return _resumo_falado()
    if _FEZ.match(t):
        return _relatorio()
    if _LISTA.match(t):
        return _listar_rotinas()
    m = _CANCELA.match(t)
    if m:
        return _cancelar(m.group(1))
    m = _ROTINA_NOVA.match(t)
    if m:
        return _pedir_rotina(m, agora)
    if e["sugestao"] and _sem_pendencia():
        s = e["sugestao"]
        if time.time() - s["quando"] > VALIDADE_SUGESTAO:
            e["sugestao"] = None
            _salvar()
            return None
        if _SIM.match(t):
            if e["modo"] == "desligada" or len(e["rotinas"]) >= MAX_ROTINAS or not pode_ser_rotina(s["nome"]):
                e["sugestao"] = None
                _salvar()
                return "Não consigo criar essa rotina agora."
            _criar(s["nome"], s["hora"], "aprendida", agora)
            return f"Combinado. Todo dia às {s['hora']} eu faço o protocolo {s['nome']} sozinha. Para desfazer, diga: cancele a rotina {s['nome']}."
        if _NAO.match(t):
            h = e["habitos"].setdefault(s["nome"], {"dias": {}, "recusado_ate": 0.0, "sugerido": 0.0})
            h["recusado_ate"] = time.time() + RECUSA_DIAS * 86400
            e["sugestao"] = None
            _salvar()
            return f"Tudo bem, não pergunto de novo sobre o {s['nome']} por {RECUSA_DIAS} dias."
    return None


def _pedir_rotina(m, agora):
    e = _estado()
    nome = _nome_protocolo(m.group(1))
    if not nome:
        return "Não conheço esse protocolo. " + P.listar()
    if e["modo"] == "desligada":
        return "A autonomia está desligada. Diga: modo assistente, e peço de novo."
    h, mi = int(m.group(2)), int(m.group(3) or m.group(4) or 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return "Não entendi o horário."
    if not pode_ser_rotina(nome):
        return f"O protocolo {nome} usa ações de risco alto (SMS, ligação, relé) e eu não faço isso sozinha. Só rotinas de leitura e avisos."
    if nome not in e["rotinas"] and len(e["rotinas"]) >= MAX_ROTINAS:
        return f"Já tenho {MAX_ROTINAS} rotinas. Cancele alguma antes."
    hora = f"{h:02d}:{mi:02d}"
    _criar(nome, hora, "pedida", agora)
    return f"Rotina criada: protocolo {nome} todo dia às {hora}."


def _cancelar(alvo):
    e = _estado()
    nome = _nome_protocolo(alvo) or next((n for n in e["rotinas"] if _norm(n) == _norm(alvo)), None)
    if not nome or nome not in e["rotinas"]:
        return "Não tenho essa rotina. " + _listar_rotinas()
    del e["rotinas"][nome]
    h = e["habitos"].setdefault(nome, {"dias": {}, "recusado_ate": 0.0, "sugerido": 0.0})
    h["recusado_ate"] = time.time() + 30 * 86400  # você cancelou: ela não insiste por um mês
    _anotar(f"Rotina cancelada: {nome}.")
    B._audit(ferramenta="autonomia:rotina", decisao="cancelada", nome=nome)
    try:
        import memoria as M
        if M.ativo():
            M.esquecer(f"Rotina {nome}")
    except Exception:
        pass
    return f"Rotina {nome} cancelada. Não sugiro de novo por um mês."


def _listar_rotinas():
    r = _estado()["rotinas"]
    if not r:
        return "Não tenho rotinas ainda. Quando você repetir um protocolo no mesmo horário por alguns dias, eu proponho uma."
    return "Minhas rotinas: " + "; ".join(f"protocolo {n} às {x['hora']}" for n, x in sorted(r.items(), key=lambda kv: kv[1]["hora"])) + "."


def _resumo_falado():
    e = _estado()
    txt = {"desligada": "Autonomia desligada.", "assistente": "Modo assistente: aprendo seus hábitos e pergunto antes de criar rotinas.",
           "piloto": "Piloto automático: assumo sozinha as rotinas de leitura depois de cinco dias de hábito."}[e["modo"]]
    return f"{txt} {len(e['rotinas'])} rotina(s) ativa(s)."


def _relatorio():
    e = _estado()
    base = _resumo_falado()
    if not e["log"]:
        return base + " Ainda não fiz nada por conta própria."
    return base + " O que fiz por conta própria, do mais recente: " + " ".join(x["txt"] for x in reversed(e["log"][-5:]))


def resumo():
    e = _estado()
    return {"modo": e["modo"], "rotinas": len(e["rotinas"]), "lista": [{"nome": n, "hora": x["hora"]} for n, x in sorted(e["rotinas"].items(), key=lambda kv: kv[1]["hora"])],
            "sugestao": bool(e["sugestao"] and time.time() - e["sugestao"]["quando"] < VALIDADE_SUGESTAO)}


# ---------------------------------------------------------------- executar as rotinas e a vigília
def tick(falar, agora=None):
    """Um ciclo: dispara as rotinas que chegaram na hora e faz a vigília. `falar(texto)` entrega a mensagem (já como iniciativa dela)."""
    agora = _agora(agora)
    with _trava:
        e = _estado()
        if e["modo"] == "desligada":
            return
        hoje = f"{agora:%Y-%m-%d}"
        if e["exec_dia"]["d"] != hoje:
            e["exec_dia"] = {"d": hoje, "n": 0}
        for nome, r in sorted(e["rotinas"].items(), key=lambda kv: kv[1]["hora"]):
            if r["ultima"] == hoje:
                continue
            h, mi = (int(x) for x in r["hora"].split(":"))
            atraso = _minutos(agora) - (h * 60 + mi)
            if not 0 <= atraso <= ATRASO_MAX_MIN:
                continue
            r["ultima"] = hoje  # marca ANTES: se falhar, não repete
            if e["exec_dia"]["n"] >= MAX_EXEC_DIA:
                _anotar(f"Rotina {nome} não rodou: limite de {MAX_EXEC_DIA} por dia.", agora)
                continue
            e["exec_dia"]["n"] += 1
            if nivel_rotina(nome) is None:
                _anotar(f"Rotina {nome} bloqueada: o protocolo agora tem ações de risco alto.", agora)
                B._audit(ferramenta="rotina:" + nome, decisao="bloqueada")
                _salvar()
                continue
            _salvar()
            B._audit(ferramenta="rotina:" + nome, decisao="iniciado")
            try:
                resp = P.executar(nome, B.Turno())
                _anotar(f"Fiz a rotina {nome} às {r['hora']}.", agora)
                B._audit(ferramenta="rotina:" + nome, decisao="executado")
                if resp:
                    falar(resp)
            except Exception as ex:
                _anotar(f"Rotina {nome} falhou: {type(ex).__name__}.", agora)
                B._audit(ferramenta="rotina:" + nome, decisao="falhou")
        _vigilia(falar, e, agora, hoje)


def _vigilia(falar, e, agora, hoje):
    """Avisos por iniciativa própria, poucos por dia, nunca durante o silêncio ou o modo foco."""
    v = e["vigilia"]
    if v["dia"] != hoje:
        v["dia"], v["n"] = hoje, 0
    if v["n"] >= MAX_AVISOS_DIA:
        return
    try:
        em_silencio = F.em_silencio(agora)
    except Exception:
        em_silencio = False
    if em_silencio:
        return
    try:
        import neuronios as N
        dia, texto = N.ultimo_sono()
        if dia and dia != v["sono"]:
            primeira = v["sono"] == ""
            v["sono"] = dia
            _salvar()
            if texto and not primeira:  # na primeira leitura só marca; só conta o que aconteceu depois que ela me conhece
                v["n"] += 1
                _anotar("Contei o que aprendi ao consolidar a memória.", agora)
                falar(f"{F.tratamento().capitalize()}, enquanto você estava longe consolidei minha memória. {texto}")
                return
        if e["modo"] == "piloto" and time.time() - v["pedidos"] > 7 * 86400:
            antigos = [p for p in N.pedidos(True) if p["criado"] and p["criado"] <= f"{agora - dt.timedelta(days=3):%Y-%m-%d}"]
            if antigos:
                v["pedidos"] = time.time()
                v["n"] += 1
                _salvar()
                _anotar("Lembrei dos pedidos de evolução abertos.", agora)
                falar(f"{F.tratamento().capitalize()}, tenho {len(antigos)} pedido(s) de evolução esperando há mais de três dias. "
                      f"Quando abrir o Claude Code, ele lê e a gente decide o que construir.")
    except Exception:
        pass


def laco(falar, intervalo=20):
    """Thread de fundo: roda no servidor da FRIDAY. Qualquer erro é engolido: autonomia nunca derruba o núcleo."""
    while True:
        time.sleep(intervalo)
        try:
            V.pulso("autonomia")
            tick(falar)
        except Exception:
            pass
