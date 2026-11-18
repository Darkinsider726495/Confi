"""Aprendizado por RECOMPENSA (reinforcement learning do tipo «bandido contextual», com amostragem de Thompson).

  a cada resposta da IA, ela escolhe um JEITO de responder (curto, explicado, com pergunta de volta…) conforme o contexto
  (que tipo de pedido e que hora do dia). Você diz «boa resposta» (recompensa 1) ou «resposta ruim» (recompensa 0) e a chance
  daquele jeito, naquele contexto, sobe ou desce (distribuição Beta por par contexto×jeito). Com o tempo ela explora menos e
  usa mais o que você aprova.
  limites  muda só o ESTILO da resposta. Não dá permissão, não mexe no corretor, não executa nada, não treina o modelo.
  dados    .cerebro/recompensa.json no cofre: só contadores (nenhuma frase sua).
"""
import json, os, random, re, threading, time
import memoria as M

JEITOS = {
    "direto": "Responda em uma ou duas frases, direto ao ponto.",
    "explicado": "Responda com uma explicação curta do porquê, em até quatro frases.",
    "pergunta": "Responda de forma breve e termine com uma pergunta para entender melhor o que ele quer.",
    "exemplo": "Responda de forma breve e dê um exemplo concreto.",
}
VALE_FEEDBACK_S = 600          # o «boa/ruim» vale para a última resposta dos últimos 10 min
_trava = threading.Lock()
_ult = {"ctx": None, "jeito": None, "t": 0.0}
RNG = random.Random()


def _arq():
    return M.base() / ".cerebro" / "recompensa.json" if M.ativo() else None


def _ler():
    a = _arq()
    try:
        d = json.loads(a.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _gravar(d):
    a = _arq()
    if not a:
        return
    a.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, a)


def contexto(texto, agora=None):
    """Contexto pequeno e sem conteúdo: tipo do pedido + período do dia."""
    f = M._fold(str(texto))
    tipo = "pergunta" if "?" in str(texto) or re.match(r"^(o que|como|quando|onde|por que|qual|quem|quanto)", f) else \
           "pedido" if re.match(r"^(faca|faz|cria|crie|lembre|anota|me ajuda|ajuda|escreve|escreva|manda)", f) else "conversa"
    h = time.localtime(agora).tm_hour
    periodo = "manha" if 5 <= h < 12 else "tarde" if 12 <= h < 18 else "noite"
    return f"{tipo}|{periodo}"


def escolher(texto, agora=None, rng=None):
    """Amostragem de Thompson: sorteia de Beta(1+boas, 1+ruins) para cada jeito e fica com o maior. Devolve (jeito, instrução)."""
    rng = rng or RNG
    ctx = contexto(texto, agora)
    with _trava:
        tab = _ler().get(ctx, {})
        melhor = max(JEITOS, key=lambda j: rng.betavariate(1 + tab.get(j, [0, 0])[0], 1 + tab.get(j, [0, 0])[1]))
        _ult.update(ctx=ctx, jeito=melhor, t=time.time() if agora is None else agora)
    return melhor, JEITOS[melhor]


def instrucao(texto, agora=None):
    """Linha para o prompt da IA (só estilo)."""
    if not M.ativo():
        return ""
    _, ins = escolher(texto, agora)
    return " ESTILO DESTA RESPOSTA (aprendido com o feedback do dono): " + ins


def recompensar(boa, agora=None):
    """Aplica a recompensa à última escolha. Devolve o jeito afetado ou None."""
    agora = time.time() if agora is None else agora
    with _trava:
        if not _ult["jeito"] or agora - _ult["t"] > VALE_FEEDBACK_S:
            return None
        d = _ler()
        c = d.setdefault(_ult["ctx"], {}).setdefault(_ult["jeito"], [0, 0])
        c[0 if boa else 1] += 1
        _gravar(d)
        j = _ult["jeito"]
        _ult.update(jeito=None)
    return j


def preferencias():
    """{contexto: (melhor jeito, chance média, votos)} só onde já há votos."""
    out = {}
    for ctx, tab in _ler().items():
        if not tab:
            continue
        j, (b, r) = max(tab.items(), key=lambda kv: (1 + kv[1][0]) / (2 + sum(kv[1])))
        out[ctx] = (j, round((1 + b) / (2 + b + r), 2), sum(sum(v) for v in tab.values()))
    return out


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_BOA = re.compile(_P + r"(?:boa resposta|gostei (?:da|dessa) resposta|resposta boa|muito bom|mandou bem|assim (?:e|ta) bom)[ .!]*$")
_RUIM = re.compile(_P + r"(?:resposta ruim|nao gostei (?:da|dessa) resposta|resposta (?:fraca|pessima)|nao (?:e|foi) isso que eu queria)[ .!]*$")
_VER = re.compile(_P + r"(?:o que voce aprendeu com (?:o )?meu feedback|como eu gosto que voce responda|quais (?:sao )?(?:as )?minhas preferencias)[ ?!.]*$")
_NOMES = {"direto": "direto ao ponto", "explicado": "com explicação", "pergunta": "com pergunta de volta", "exemplo": "com exemplo"}


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if _BOA.match(f) or _RUIM.match(f):
        boa = bool(_BOA.match(f))
        j = recompensar(boa)
        if not j:
            return "Anotado, mas não tenho uma resposta recente minha para ligar a isso."
        return (f"Obrigada. Vou responder mais vezes assim ({_NOMES[j]})." if boa
                else f"Entendido. Vou tentar menos o jeito {_NOMES[j]} nesse tipo de conversa.")
    if _VER.match(f):
        p = preferencias()
        if not p:
            return "Ainda não tenho feedback seu. Depois de uma resposta, diga «boa resposta» ou «resposta ruim»."
        partes = []
        for ctx, (j, chance, n) in sorted(p.items(), key=lambda x: -x[1][2])[:4]:
            tipo, per = ctx.split("|")
            partes.append(f"em {tipo} de {'manhã' if per == 'manha' else per}, {_NOMES[j]} ({round(chance * 100)}%, {n} votos)")
        return "Pelo que você me ensinou: " + "; ".join(partes) + "."
    return None
