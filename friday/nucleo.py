"""Núcleo da FRIDAY: a ARQUITETURA dela, inspirada em como o cérebro organiza o trabalho (e não no formato dele).

Peças:
  1. ATENÇÃO (inspirada no tálamo). Todo sinal que chega (fala, visão, mãos, sistema, internet) recebe uma saliência: peso da origem x novidade x estado de atenção.
     A novidade cai com a repetição (HABITUAÇÃO: o que se repete deixa de ser notado) e volta com o tempo. Seu pedido nunca é ignorado; um gesto repetido, sim.
  2. ESPAÇO DE TRABALHO (inspirado na memória de trabalho / espaço global). Só o que foi notado entra no FOCO, que tem poucas vagas e disputa por elas.
     Quem entra é anunciado aos assinantes (o pré-córtex assimila e registra); quem sai do foco NÃO é apagado: o conhecimento já foi guardado pela fonte.
  3. ATIVIDADE EM PARALELO. Nada aqui é fila: estudar, conversar, olhar, sonhar e responder rodam ao mesmo tempo. O núcleo só observa (`agir`, `ocupado`);
     quem protege recurso que não pode ser usado por dois ao mesmo tempo é o coordenador.
  4. SISTEMA DISTRIBUÍDO DENTRO DO NÚCLEO. `iniciar()` sobe, junto com o núcleo, o pré-córtex distribuído (hub + nove neurônios; cada objetivo na sua linha)
     e o ciclo autônomo. Ações locais de baixo impacto o hub já executa sem esperar o dono; as de risco esperam a autorização dele.
  5. AUTONOMIA TOTAL (pedida pelo dono). Só o dono liga/desliga, por voz («liga a autonomia total» / «desliga a autonomia total»; «sim»/«pode» nunca ligam).
     Ligada, o núcleo aprova SOZINHO os objetivos que ela mesma propõe, de nível ≤ 1 e sem ação fora do aparelho, e os executa em paralelo, sem esperar ordem.
     Nível 2+ (mensagem, ligação, arquivo do dono, dinheiro) continua pedindo o dono: o corretor não é contornado. Desligada (o padrão), tudo é como antes.

O que NÃO é: não tem ferramenta da IA, não executa ação do corretor por conta própria, não liga nem desliga a curiosidade, a conversa, a câmera ou a FRIDAY.
Não é consciência nem biologia: é um modelo para organizar o código (docs/NUCLEO.md)."""
import os, re, time, threading, contextlib
from collections import deque

# peso de cada origem antes da novidade. Fala do dono pesa mais; internet pesa menos.
ORIGENS = {"fala": 0.9, "maos": 0.6, "visao": 0.55, "sistema": 0.4, "web": 0.3, "interno": 0.25}
CONFIAVEIS = {"fala", "maos", "sistema", "interno"}   # visão e internet são dado de terceiros: entram no foco como «não verificado»
IMPULSOS = ("estudar", "conversar", "olhar", "responder", "sonhar")
OCUPADO_MAX = 900.0                                    # uma ação "em andamento" há mais que isto é considerada travada e deixa de segurar as outras
_lock = threading.RLock()
_h = {}                                                # chave -> [contagem recente, hora da última contagem]
_foco = deque()
_ativos = {}                                           # impulso -> horas de início das ações em andamento
_fim = {}                                              # impulso -> hora em que a última ação terminou
_ao_entrar, _ao_sair = [], []
_conta = {"notados": 0, "ignorados": 0, "saiu": 0, "hoje": {}, "dia": ""}
_seq = [0]


def _agora():
    return time.time()


def _num(nome, padrao, tipo=float):
    try:
        v = tipo(os.getenv(nome, "").strip() or padrao)
    except ValueError:
        v = padrao
    return max(tipo(0), v)


def ligado():
    return os.getenv("NUCLEO", "1").strip().lower() not in ("0", "off", "nao", "não", "false")


def vagas():
    """Vagas do foco (quantas coisas ela mantém em primeiro plano). 0 = sem limite. É atenção, não armazenamento: o que sai do foco continua guardado onde nasceu."""
    return _num("NUCLEO_FOCO", 7, int)


def meia_vida_s():
    return _num("NUCLEO_HABITUACAO_S", 300.0)


def limiar():
    return _num("NUCLEO_LIMIAR", 0.25)


def _atencao():
    """Nível de acetilcolina do estado interno (0..1): atenção alta nota mais. Sem estado interno vale 0,5 (neutro)."""
    try:
        import vida as V
        return V.nivel("acetilcolina")
    except Exception:
        return 0.5


def _limpo(t, n=80):
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(t or ""))
    t = re.sub(r"https?://\S+|www\.\S+", "", t)
    return " ".join(t.split())[:n]


# ---------------------------------------------------------------- atenção
def _contagem(chave, t):
    """Quantas vezes essa chave foi notada há pouco, já com a decaída (meia-vida) aplicada."""
    c = _h.get(chave)
    if not c:
        return 0.0
    mv = meia_vida_s()
    return c[0] * (0.5 ** ((t - c[1]) / mv)) if mv > 0 else 0.0


def _podar(t):
    """Contadores de habituação já apagados pela decaída (< 0,05) são esquecidos: são hábitos de curto prazo, não conhecimento."""
    if len(_h) > 5000:
        for k in [k for k in _h if _contagem(k, t) < 0.05]:
            _h.pop(k, None)


def perceber(origem, tipo, resumo="", chave=None, agora=None):
    """Um sinal chegou. Devolve {origem, tipo, resumo, saliencia, novidade, notado, confiavel, t}. Nunca levanta erro: a atenção não pode atrapalhar o resto."""
    t = _agora() if agora is None else agora
    try:
        origem = origem if origem in ORIGENS else "interno"
        chave = str(chave or f"{origem}:{tipo}")[:80]
        with _lock:
            n = _contagem(chave, t)
            nov = 1.0 / (1.0 + n)
            mod = max(0.6, min(1.2, 0.8 + 0.4 * _atencao()))
            sal = round(ORIGENS[origem] * (0.35 + 0.65 * nov) * mod, 3) if ligado() else 0.0
            _h[chave] = [n + 1.0, t]
            _podar(t)
            _seq[0] += 1
            s = {"id": _seq[0], "origem": origem, "tipo": str(tipo)[:30], "resumo": _limpo(resumo), "saliencia": sal, "novidade": round(nov, 3),
                 "notado": sal >= limiar(), "confiavel": origem in CONFIAVEIS, "t": t}
            dia = time.strftime("%Y-%m-%d", time.localtime(t))
            if _conta["dia"] != dia:
                _conta.update(dia=dia, hoje={})
            if s["notado"]:
                _conta["notados"] += 1
                _conta["hoje"][origem] = _conta["hoje"].get(origem, 0) + 1
                _entrar(s, t)
            else:
                _conta["ignorados"] += 1
        if s["notado"]:
            for f in list(_ao_entrar):
                try:
                    f(s)
                except Exception:
                    pass
        return s
    except Exception:
        return {"origem": str(origem), "tipo": str(tipo), "resumo": "", "saliencia": 0.0, "novidade": 0.0, "notado": False, "confiavel": False, "t": t}


# ---------------------------------------------------------------- espaço de trabalho (foco)
def _peso(s, t):
    """Quanto o sinal ainda segura o foco: a saliência de quando chegou, caindo à metade a cada 5 minutos."""
    return s["saliencia"] * (0.5 ** (max(0.0, t - s["t"]) / 300.0))


def _entrar(s, t):
    _foco.append(s)
    n = vagas()
    saidos = []
    while n and len(_foco) > n:
        pior = min(_foco, key=lambda x: _peso(x, t))
        _foco.remove(pior)
        saidos.append(pior)
    _conta["saiu"] += len(saidos)
    for x in saidos:
        for f in list(_ao_sair):
            try:
                f(x)
            except Exception:
                pass


def foco(agora=None):
    """O que está em primeiro plano agora, do mais forte para o mais fraco."""
    t = _agora() if agora is None else agora
    with _lock:
        return [dict(x, peso=round(_peso(x, t), 3)) for x in sorted(_foco, key=lambda x: -_peso(x, t))]


def assinar(ao_entrar=None, ao_sair=None):
    """Quem quiser saber do que entra no foco (ou sai dele) se inscreve aqui. As funções recebem o sinal; erro delas nunca atrapalha."""
    with _lock:                                   # a mesma função assinada duas vezes recebe cada sinal uma vez só
        if ao_entrar and ao_entrar not in _ao_entrar:
            _ao_entrar.append(ao_entrar)
        if ao_sair and ao_sair not in _ao_sair:
            _ao_sair.append(ao_sair)


# ---------------------------------------------------------------- seleção de impulsos
@contextlib.contextmanager
def agir(nome):
    """Registra atividade para observabilidade. Não bloqueia outros impulsos ou trabalhadores."""
    t = _agora()
    with _lock:
        _ativos.setdefault(nome, []).append(t)
    try:
        yield
    finally:
        with _lock:
            lista = _ativos.get(nome, [])
            if t in lista:
                lista.remove(t)
            if not lista:
                _ativos.pop(nome, None)
            _fim[nome] = _agora()


def liberar(nome, agora=None):
    """Compatibilidade: o núcleo observacional nunca concede nem nega execução.

    A concorrência é decidida pelo coordenador de recursos e pelo pré-córtex
    distribuído. Manter esta função sempre permissiva evita que integrações
    antigas reintroduzam uma fila global de impulsos.
    """
    return True


def ocupado(agora=None):
    t = _agora() if agora is None else agora
    with _lock:
        return sorted(n for n, ini in _ativos.items() if any(t - i < OCUPADO_MAX for i in ini))


def esperando(agora=None):
    return [n for n in IMPULSOS if not liberar(n, agora)]


# ---------------------------------------------------------------- autonomia total e sistema distribuído (dentro do núcleo)
def _limpar_auto(lido, padrao):
    padrao["autonomia_total"] = lido.get("autonomia_total") is True
    padrao["mudou_em"] = lido.get("mudou_em") if isinstance(lido.get("mudou_em"), (int, float)) else None
    return padrao


_AUTO = None
_EXEC = set()                          # propostas que o ciclo autônomo está executando agora
_MAX_PARALELO = 4                      # objetivos próprios ao mesmo tempo (cada um na sua linha)
_ini = {"feito": False, "hub": None, "erro": ""}


def _arq_auto():
    global _AUTO
    if _AUTO is None:
        import estado as ES
        _AUTO = ES.Arq("nucleo_autonomia", {"autonomia_total": False, "mudou_em": None}, _limpar_auto)
    return _AUTO


def autonomia_total():
    """Ligada só pelo dono, por voz. Padrão: desligada."""
    try:
        return bool(_arq_auto().get()["autonomia_total"])
    except Exception:
        return False


def _definir_autonomia(ligar):
    a = _arq_auto()
    with a.trava:
        a.get().update(autonomia_total=bool(ligar), mudou_em=_agora())
        a.salvar()


def ciclo_autonomo():
    """Uma volta: com a autonomia total ligada, aprova e executa EM PARALELO os objetivos que ela propôs (nível ≤ 1, nada fora do aparelho).
    Cada um roda na sua linha; o que já está rodando não é disparado de novo. Devolve os ids disparados nesta volta."""
    if not autonomia_total():
        return []
    import objetivos as OBJ
    disparados = []
    for p in OBJ.listar(("proposto",)):
        oid = p["id"]
        with _lock:
            if oid in _EXEC or len(_EXEC) >= _MAX_PARALELO:
                continue
            _EXEC.add(oid)

        def rodar(oid=oid):
            try:
                with agir("objetivo_proprio"):
                    OBJ.aprovar_pela_autonomia(oid)
            except Exception:
                pass
            finally:
                with _lock:
                    _EXEC.discard(oid)
        threading.Thread(target=rodar, name=f"nucleo-auto-{oid}", daemon=True).start()
        disparados.append(oid)
    return disparados


def _laco_autonomo(intervalo=30.0):
    while True:
        try:
            ciclo_autonomo()
        except Exception:
            pass
        time.sleep(intervalo)


def iniciar():
    """Chamado UMA vez na partida (main.py): o sistema distribuído nasce dentro do núcleo, sempre ligado, e o ciclo autônomo começa a girar
    (ele só age com a autonomia total ligada pelo dono). Nunca derruba a partida: erro fica em `painel()["distribuido"]`."""
    with _lock:
        if _ini["feito"]:
            return dict(_ini)
        _ini["feito"] = True
    try:
        import pre_cortex.fachada as PC
        PC.hub()
        _ini["hub"] = True
    except Exception as e:
        _ini.update(hub=False, erro=f"{type(e).__name__}: {e}"[:200])
    threading.Thread(target=_laco_autonomo, name="nucleo-autonomia", daemon=True).start()
    return dict(_ini)


# ---------------------------------------------------------------- painel e fala
def painel(agora=None):
    t = _agora() if agora is None else agora
    with _lock:
        habito = sorted(((k, round(_contagem(k, t), 2)) for k in _h), key=lambda x: -x[1])[:3]
        c = {"notados": _conta["notados"], "ignorados": _conta["ignorados"], "saiu": _conta["saiu"], "hoje": dict(_conta["hoje"])}
    return {"ligado": ligado(), "foco": [{"origem": x["origem"], "tipo": x["tipo"], "resumo": x["resumo"], "peso": x["peso"], "confiavel": x["confiavel"]} for x in foco(t)],
            "vagas": vagas(), "ocupado": ocupado(t), "esperando": esperando(t), "habituado": [{"chave": k, "n": n} for k, n in habito if n >= 1.5], **c,
            "autonomia_total": autonomia_total(), "objetivos_em_execucao": sorted(_EXEC),
            "distribuido": {"iniciado": _ini["feito"], "hub": _ini["hub"], "erro": _ini["erro"]}}


_ROTULO = {"fala": "você falou", "maos": "gesto das mãos", "visao": "eu vi", "sistema": "o sistema avisou", "web": "li na internet", "interno": "eu mesma"}
_FOCO = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:(?:no que|em que|com o que) voce esta (?:focad[oa]|concentrad[oa]|prestando atencao)|"
                   r"o que (?:esta )?(?:chamando|chamou|prendeu) (?:a )?sua atencao|qual (?:e )?o seu foco|onde esta (?:a )?sua atencao)(?: agora| hoje)?[ .!?]*$")
_ARQ = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:(?:como (?:e|funciona) )?(?:a )?sua arquitetura|como (?:voce )?(?:funciona|pensa) por dentro|explique (?:a )?(?:sua )?arquitetura|"
                  r"(?:o que e|como funciona) (?:o )?(?:seu )?nucleo)(?: agora)?[ .!?]*$")


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_AUTO_LIGA = re.compile(_P + r"(?:liga|ligue|ligar|ativa|ative|ativar)(?: a)? autonomia total[ .!]*$")
_AUTO_DESLIGA = re.compile(_P + r"(?:desliga|desligue|desligar|desativa|desative|desativar)(?: a)? autonomia total[ .!]*$")
_AUTO_STATUS = re.compile(_P + r"(?:como esta (?:a )?autonomia total|a autonomia total esta ligada|status da autonomia total)[ ?]*$")


def tratar(texto):
    """Autonomia total (só o dono, por voz), «no que você está focada?» (reserva: o pré-córtex responde antes) e «como é a sua arquitetura?»."""
    try:
        import memoria as M
        f = M._fold(texto).strip()
    except Exception:
        return None
    if _AUTO_LIGA.match(f):
        _definir_autonomia(True)
        return ("Autonomia total ligada. A partir de agora eu aprovo e faço sozinha, ao mesmo tempo, os objetivos que eu mesma proponho de nível 1 "
                "(dentro do celular, nada sai dele). Mandar mensagem, ligar, mexer nos seus arquivos ou gastar continua pedindo você. "
                "Tudo fica no registro de atividades. Para voltar, diga «desliga a autonomia total».")
    if _AUTO_DESLIGA.match(f):
        _definir_autonomia(False)
        return "Autonomia total desligada. Volto a esperar você aprovar os objetivos que eu propuser; o que já estava rodando termina."
    if _AUTO_STATUS.match(f):
        return (f"A autonomia total está {'ligada' if autonomia_total() else 'desligada'}. "
                f"Objetivos meus rodando agora: {len(_EXEC)}. Sistema distribuído: {'ligado' if _ini['hub'] else 'ainda não subiu' if not _ini['feito'] else 'com erro'}.")
    if _FOCO.match(f):
        p = painel()
        if not p["foco"]:
            return "Neste momento nada está em primeiro plano: o que chegou já foi guardado ou eu me acostumei com ele."
        itens = "; ".join(f"{_ROTULO.get(x['origem'], x['origem'])}: {x['resumo'] or x['tipo']}" + ("" if x["confiavel"] else " (não verificado)") for x in p["foco"][:4])
        extra = f" Desde que liguei, me acostumei a ignorar {p['ignorados']} coisas repetidas." if p["ignorados"] else ""
        return f"Em primeiro plano: {itens}.{extra} É um modelo de atenção do meu código, não uma consciência."
    if _ARQ.match(f):
        return ("Por dentro eu sou feita assim: os sentidos (sua voz, a câmera, as suas mãos) mandam sinais; a atenção dá peso a cada um e se acostuma com o que repete; "
                "só o que é notado entra no meu foco, que tem poucas vagas; a memória guarda o que importa; o estado interno muda minha vontade de estudar, conversar e olhar; "
                "e a atividade é observada sem bloquear impulsos independentes. O pré-córtex distribui o planejamento, o coordenador protege recursos conflitantes e o corretor valida as ações. "
                "É inspirado no cérebro, não é um cérebro. Está tudo explicado em docs/NUCLEO.md.")
    return None


def zerar_para_teste():
    with _lock:
        _h.clear(), _foco.clear(), _ativos.clear(), _fim.clear(), _ao_entrar.clear(), _ao_sair.clear(), _EXEC.clear()
        _conta.update(notados=0, ignorados=0, saiu=0, hoje={}, dia="")
        _seq[0] = 0
