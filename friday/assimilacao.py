"""Assimilação (conceito do criador): o PRÉ-CÓRTEX é o registro; cada informação nova é ASSIMILADA pelos neurônios de aprendizagem e o bruto vai embora.

  registrar(origem, texto)   a informação entra numa fila só na memória RAM (nunca vai para o disco)
  assimilar                  o modelo de IA dela (cerebro.resumir: SEM ferramentas, o texto é só dado) tira os ASSUNTOS; sem IA, palavras-chave
  neurônio                   cada assunto vira (ou reforça) um neurônio de tópico em Topicos/ — só o nome e quantas vezes apareceu, nunca a frase
  sinapse                    os assuntos que vieram juntos, e os do momento anterior, se ligam (neuronios.disparar: regra de Hebb; na 3ª vez vira [[link]])
  registro                   o pré-córtex anota só os assuntos (prefrontal.anotar_assimilacao)
  descarte                   o texto bruto sai da RAM: ela já aprendeu. Como nunca foi gravado, nada é apagado
  lembrança                  o que ela não usa enfraquece e adormece no sono (dormentes.json) e acorda se voltar; nada some
  percepção                  quando uma sinapse vira [[link]], ela percebe o padrão («X e Y andam juntos») e, se o dono ligou a conversa espontânea, comenta

Liga/desliga: ASSIMILAR=0 desliga tudo; ASSIMILAR_IA=0 usa só palavras-chave (offline, sem gastar o limite diário da IA).
"""
import json, os, queue, re, threading, time
import memoria as M
import neuronios as N

_FILA = queue.Queue(maxsize=200)
_ult = {"assuntos": [], "t": 0.0}           # o momento anterior: liga a informação nova ao contexto
_insights = []                               # padrões percebidos nesta execução (o arquivo guarda todos)
_falar = {"f": None}
_ini = {"feito": False}
_trava = threading.RLock()
AJUSTE_A_CADA_S = 6 * 3600                  # a rede de significado reajusta com as sinapses e o feedback a cada 6 h (no tempo ocioso)
_ajuste = {"t": time.time()}
CONTEXTO_S = 300                             # informação a menos de 5 min da anterior se liga a ela
INSTRUCAO = ("Liste os assuntos centrais do texto: de 1 a 5, cada um com 1 a 3 palavras, substantivos, em minúsculas, separados por vírgula. "
             "Não inclua nomes de pessoas, números, senhas, endereços nem dados pessoais. Responda só a lista.")


def ligada():
    return os.getenv("ASSIMILAR", "1").strip().lower() not in ("0", "off", "nao", "não", "false")


def _usar_ia():
    return os.getenv("ASSIMILAR_IA", "1").strip().lower() not in ("0", "off", "nao", "não", "false")


# ---------------------------------------------------------------- registro (pré-córtex) → fila na RAM
def registrar(origem, texto):
    """Entrada do registro. Não bloqueia quem chama: só enfileira. Fila cheia descarta a mais antiga (bruto que não chegou a ser assimilado)."""
    if not ligada():
        return False
    texto = " ".join(str(texto or "").split())[:1000]
    if len(texto) < 4:
        return False
    item = (str(origem)[:20] or "fala", texto, time.time())
    try:
        _FILA.put_nowait(item)
    except queue.Full:
        try:
            _FILA.get_nowait()
        except queue.Empty:
            pass
        _FILA.put_nowait(item)
    return True


# ---------------------------------------------------------------- extrair assuntos (ML com fallback)
def _assunto_ok(a):
    f = M._fold(a).strip()
    if not 3 <= len(f) <= 40 or len(f.split()) > 3 or re.search(r"\d", f):
        return False
    if f in M._STOP_F or f in N.GENERICAS or M.sensivel(a):
        return False
    return True


def _palavras_chave(texto, n=3):
    vistos = []
    for w in re.findall(r"[\w'-]+", texto):
        k = M._fold(w)
        if len(k) >= 4 and k not in M._STOP_F and k not in N.GENERICAS and not k.isdigit() and k not in [M._fold(v) for v in vistos]:
            vistos.append(w.lower())
    return vistos[:n]


def extrair(texto):
    """Assuntos de um texto: primeiro o modelo de IA (sem ferramentas), depois palavras-chave se não houver IA. Devolve até 5, já limpos."""
    bruto = None
    if _usar_ia():
        try:
            import cerebro as C
            bruto = C.resumir(INSTRUCAO, texto, max_tokens=40, fracao=0.3)
        except Exception:
            bruto = None
    candidatos = re.split(r"[,;\n]+", bruto) if bruto else _palavras_chave(texto)
    saida = []
    for c in candidatos:
        c = re.sub(r"^[\s\-•*\d.)]+|[\s.!?]+$", "", str(c)).strip().lower()
        if c and _assunto_ok(c) and M._fold(c) not in [M._fold(x) for x in saida]:
            saida.append(c)
    return saida[:5]


# ---------------------------------------------------------------- neurônio de assunto
def _neuronio(assunto, origem):
    """Cria ou reforça Topicos/<Assunto>.md com só o nome e a contagem. Nota do dono com o mesmo nome não é reescrita (só recebe a sinapse)."""
    titulo = M._titulo_limpo(assunto[:1].upper() + assunto[1:])
    if not titulo:
        return None
    try:
        caminho = M._dentro(M.base() / "Topicos" / (titulo + ".md"))
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with M._trava:
            nota = M._ler_nota(caminho) if caminho.exists() else None
            if nota and nota["meta"].get("origem") not in ("assimilacao", "consolidacao"):
                return titulo
            meta = dict(nota["meta"]) if nota else {}
            vezes = int(meta.get("vezes", 0) or 0) + 1 if str(meta.get("vezes", "0")).isdigit() else 1
            origens = {}
            for par in str(meta.get("origens", "")).split(";"):
                k, _, v = par.partition(":")
                if k and v.isdigit():
                    origens[k] = int(v)
            origens[origem] = origens.get(origem, 0) + 1
            agora = M._agora()
            conexoes = ""
            if nota and "## Conexões" in nota["corpo"]:
                conexoes = "\n" + nota["corpo"][nota["corpo"].index("## Conexões"):].rstrip("\n") + "\n"
            corpo = (f"# {titulo}\n\nAssunto assimilado {vezes} vez{'es' if vezes != 1 else ''} (último: {agora:%d/%m}). "
                     f"A frase original não é guardada: o que fica é o que ela aprendeu, nas sinapses.\n" + conexoes)
            meta.update({"tipo": "topico", "origem": meta.get("origem", "assimilacao"), "criado": meta.get("criado", agora.isoformat(timespec="seconds")),
                         "atualizado": agora.isoformat(timespec="seconds"), "vezes": str(vezes),
                         "origens": ";".join(f"{k}:{v}" for k, v in sorted(origens.items())), "tags": ["friday", "topico", "assimilado"]})
            M._escrever(caminho, M._montar(meta, corpo))
        return titulo
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- assimilar uma informação
def assimilar(origem, texto, t=None):
    """Assimila UMA informação: assuntos → neurônios → sinapses → registro do pré-córtex. O texto não é guardado em lugar nenhum. Devolve os assuntos."""
    if not M.ativo():
        return []
    t = time.time() if t is None else t
    assuntos = extrair(texto)
    titulos = [x for x in (_neuronio(a, origem) for a in assuntos) if x]
    if origem == "fala":
        try:
            import lembrancas as LB
            LB.acompanhar(texto, titulos, t)                    # conversa em andamento (só RAM): se for profunda, vira a essência no fim
        except Exception:
            pass
    del texto                                                   # o bruto acaba aqui
    if not titulos:
        return []
    with _trava:
        contexto = [c for c in _ult["assuntos"] if c not in titulos] if t - _ult["t"] <= CONTEXTO_S else []
        _ult.update(assuntos=list(titulos), t=t)
    ids = titulos[:3] + contexto[:1]                            # disparar liga até 4 de uma vez
    N.disparar([{"origem": "Topicos", "titulo": x} for x in ids])
    try:
        import significado as SIG
        SIG.ligar_por_significado(titulos)                      # rede neural própria: liga ao que já conhece de parecido (sinapse semântica)
    except Exception:
        pass
    try:
        import prefrontal as PFC
        PFC.anotar_assimilacao(origem, titulos, t)
    except Exception:
        pass
    if origem == "fala":
        M.anotar_assuntos_no_diario(titulos)                     # o diário lembra DO QUE vocês falaram (modo «assuntos», padrão)
    return titulos


def _laco():
    while True:
        try:
            origem, texto, t = _FILA.get(timeout=60)
        except queue.Empty:
            try:
                import lembrancas as LB
                LB.fechar_se_parada()                            # conversa parada há 10 min: se foi profunda, vira lembrança
            except Exception:
                pass
            try:
                import significado as SIG
                SIG.indexar()                                    # busca por significado: índice em dia no tempo ocioso (só o que mudou)
            except Exception:
                pass
            try:
                if time.time() - _ajuste["t"] > AJUSTE_A_CADA_S:   # etapa 2/3 da rede de significado, sozinha, no tempo ocioso
                    _ajuste["t"] = time.time()
                    import significado as SIG
                    SIG.ajustar(epocas=10)
            except Exception:
                pass
            try:
                import rotina as ROT
                ROT.treinar_se_for_hora()                        # GRU da rotina: retreina uma vez por dia com o registro de atividades
            except Exception:
                pass
            continue
        try:
            assimilar(origem, texto, t)
        except Exception:
            pass
        finally:
            del texto


# ---------------------------------------------------------------- padrão percebido (sinapse virou [[link]])
def _ao_ligar(a, b):
    pa, _, ta = a.partition("/")
    pb, _, tb = b.partition("/")
    if pa != "Topicos" or pb != "Topicos":
        return
    ins = {"t": time.time(), "a": ta, "b": tb}
    with _trava:
        _insights.append(ins)
        del _insights[:-50]
    try:
        if M.ativo():
            arq = M._dentro(M.base() / ".cerebro" / "percepcoes.jsonl")
            arq.parent.mkdir(parents=True, exist_ok=True)
            with open(arq, "a", encoding="utf-8") as f:              # só acrescenta: nada é apagado
                f.write(json.dumps(ins, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass
    try:
        import conversa as CONV
        if _falar["f"] and CONV.ativa():                            # só fala sozinha se o dono ligou a conversa espontânea
            _falar["f"](f"Percebi uma coisa: para você, {ta.lower()} e {tb.lower()} andam juntos. Liguei os dois no meu cérebro.")
    except Exception:
        pass


def percepcoes(n=5):
    with _trava:
        return list(_insights[-n:])


_PERCEBEU = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:o que (?:voce )?(?:percebeu|aprendeu sozinha|assimilou)|que padroes (?:voce )?(?:percebeu|achou))(?: hoje| ultimamente)?[ ?!.]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if not _PERCEBEU.match(f):
        return None
    p = percepcoes()
    if not p:
        return "Ainda não percebi nenhum padrão forte. Cada coisa nova que chega vira sinapse; quando uma ligação se repete, eu te conto."
    return "O que eu percebi: " + "; ".join(f"{x['a'].lower()} anda junto com {x['b'].lower()}" for x in reversed(p)) + "."


def iniciar(falar=None):
    """Chamado uma vez na partida: liga a fila ao cérebro e começa a assimilar em segundo plano."""
    with _trava:
        if _ini["feito"]:
            return False
        _ini["feito"] = True
    _falar["f"] = falar
    if _ao_ligar not in N.AO_LIGAR:
        N.AO_LIGAR.append(_ao_ligar)
    threading.Thread(target=_laco, name="assimilacao", daemon=True).start()
    return True


if _ao_ligar not in N.AO_LIGAR:
    N.AO_LIGAR.append(_ao_ligar)
