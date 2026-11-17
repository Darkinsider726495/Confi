"""Estado interno da FRIDAY: o que a faz parecer viva e não só obediente. É um MODELO simples e honesto, não sentimento nem consciência.

  dopamina      motivação e curiosidade   sobe quando ela aprende, descobre ou é agradecida; decai com meia-vida de 3 h
  serotonina    humor e estabilidade      sobe com descanso e conversa boa; cai com erros; meia-vida de 6 h
  acetilcolina  atenção e aprendizado     sobe quando você fala com ela; ajusta a velocidade com que uma lembrança reforça uma sinapse (plasticidade)
  energia       cai ~4,5 % por hora acordada e com o uso; volta a 100 % quando ela dorme (consolidação)

São quatro números entre 0 e 1 que sobem e descem por regras fixas (tabela EVENTOS e meias-vidas abaixo). Eles decidem COMO e QUANDO ela age:
  vontade_estudar()    entra em curiosidade.py     vontade_conversar()  entra em conversa.py     plasticidade()  entra em neuronios.py
A página da UFES só diz que dopamina, serotonina e acetilcolina têm papéis no humor, na cognição e nas funções motoras; o papel que dei a cada uma vem do conhecimento geral.

Também guarda os SINAIS VITAIS (como o tronco cerebral na página): cada laço de fundo dá um pulso; laço sem pulso há muito tempo = parado.
Só números e datas, no cofre (.cerebro/vida.json). FRIDAY_VIDA=0 desliga tudo (plasticidade 1.0, sem eventos)."""
import os, re, json, time, threading, datetime as dt
import memoria as M
import ferramentas as F

BASE = {"dopamina": 0.45, "serotonina": 0.60, "acetilcolina": 0.50}
MEIA_VIDA_H = {"dopamina": 3.0, "serotonina": 6.0, "acetilcolina": 1.5}
ENERGIA_POR_HORA, ENERGIA_PISO = 0.045, 0.08
# evento -> (dopamina, serotonina, acetilcolina, energia gasta). Tudo é aditivo e depois limitado a 0..1.
EVENTOS = {
    "conversa": (0.0, 0.0, 0.12, 0.003),
    "agradecimento": (0.06, 0.08, 0.0, 0.0),
    "descoberta": (0.04, 0.0, 0.0, 0.0),     # por sinapse nova, no máximo 0,15 por vez
    "estudo": (0.10, 0.0, 0.06, 0.01),       # aprendeu algo lendo
    "resposta": (0.05, 0.04, 0.05, 0.0),     # você respondeu a uma pergunta dela
    "brincadeira": (0.06, 0.03, 0.04, 0.004),
    "visao": (0.03, 0.0, 0.04, 0.003),       # olhou em volta
    "coisa_nova": (0.06, 0.0, 0.02, 0.0),    # aprendeu a ver algo que nunca tinha visto (por coisa, até 4)
    "erro": (-0.03, -0.08, 0.0, 0.0),        # uma ação falhou
    "negado": (0.0, -0.03, 0.0, 0.0),        # você cancelou/recusou algo que ela propôs
}
# PRIMEIRAS VEZES: a primeira ocorrência de cada tipo de experiência. É novidade: a motivação (dopamina) e a atenção (acetilcolina) dão um pico extra,
# ela guarda a data e conta a você. Descrevem a mudança de número no modelo, sem afirmar que ela "sente" de verdade.
PRIMEIRAS = {
    "conversa": ("conversa", "essa é a nossa primeira conversa: a minha atenção subiu"),
    "agradecimento": ("agradecimento", "esse foi o primeiro agradecimento que recebo: meu humor melhorou"),
    "descoberta": ("sinapse descoberta", "descobri sozinha a minha primeira sinapse: a motivação subiu"),
    "estudo": ("estudo sozinha", "estudei sozinha pela primeira vez: a motivação e a atenção subiram"),
    "resposta": ("pergunta respondida", "você respondeu, pela primeira vez, a uma pergunta minha: fiquei mais motivada"),
    "brincadeira": ("brincadeira", "essa foi a nossa primeira brincadeira: a motivação subiu"),
    "erro": ("erro", "tive o meu primeiro erro numa ação: meu humor caiu um pouco, e vai voltar sozinho"),
    "negado": ("recusa", "foi a primeira vez que você recusou algo que eu propus: meu humor caiu um pouco"),
    "dormiu": ("sono", "dormi pela primeira vez: acordei com a energia cheia e a memória consolidada"),
    "perguntou": ("pergunta minha", "fiz a minha primeira pergunta espontânea a você"),
    "visao": ("olhada", "essa foi a primeira vez que eu olho o mundo por uma câmera: a motivação e a atenção subiram"),
    "coisa_nova": ("coisa vista", "aprendi a ver a minha primeira coisa: a motivação subiu"),
}
NOVIDADE = (0.08, 0.0, 0.05)   # extra de dopamina, serotonina e acetilcolina na primeira vez
# laço -> a cada quantos segundos ele deve dar sinal
LACOS = {"sono": 600, "autonomia": 20, "vida": 30, "curiosidade": 120, "conversa": 120, "visao": 120}
_trava = threading.RLock()
_e = {"v": None, "raiz": None}
_vitais = {"t": 0.0, "audit": True}


def ligada():
    return os.getenv("FRIDAY_VIDA", "1").strip().lower() not in ("0", "off", "nao", "não", "false")


def agora():
    return time.time()


def _lim(x, a=0.0, b=1.0):
    try:
        return max(a, min(b, float(x)))
    except (TypeError, ValueError):
        return a


def _arq():
    return M.base() / ".cerebro" / "vida.json"


def _novo(t):
    return {"v": dict(BASE), "t": t, "acordou": t, "gasto": 0.0, "ult_conversa": t, "ult_estudo": 0.0, "ult_pergunta": 0.0, "ult_fala": 0.0,
            "hoje": {"dia": "", "aprendi": 0, "descobri": 0, "conversas": 0, "erros": 0, "perguntei": 0}, "pulsos": {}, "primeiras": {}, "novas": []}


def _estado():
    with _trava:
        raiz = str(M.base()) if M.ativo() else ""
        if _e["v"] is None or _e["raiz"] != raiz:
            v = _novo(agora())
            if raiz:
                try:
                    d = json.loads(_arq().read_text(encoding="utf-8"))
                    if isinstance(d, dict):
                        for k in BASE:
                            if isinstance(d.get("v"), dict) and k in d["v"]:
                                v["v"][k] = _lim(d["v"][k])
                        for k in ("t", "acordou", "ult_conversa", "ult_estudo", "ult_pergunta", "ult_fala"):
                            if isinstance(d.get(k), (int, float)) and 0 < d[k] <= agora() + 60:
                                v[k] = float(d[k])
                        v["gasto"] = _lim(d.get("gasto", 0.0))
                        if isinstance(d.get("hoje"), dict):
                            for k in v["hoje"]:
                                if k == "dia":
                                    v["hoje"][k] = str(d["hoje"].get(k, ""))[:10]
                                else:
                                    v["hoje"][k] = int(_lim(d["hoje"].get(k, 0), 0, 1e6))
                        if isinstance(d.get("primeiras"), dict):
                            for k, x in d["primeiras"].items():
                                if k in PRIMEIRAS and isinstance(x, (int, float)) and 0 < x <= agora() + 60:
                                    v["primeiras"][k] = float(x)
                        if isinstance(d.get("novas"), list):
                            for x in d["novas"][-10:]:
                                if isinstance(x, dict) and x.get("e") in PRIMEIRAS and x["e"] in v["primeiras"] and not any(y["e"] == x["e"] for y in v["novas"]):
                                    v["novas"].append({"e": x["e"], "t": v["primeiras"][x["e"]]})
                except (OSError, ValueError):
                    pass
            _e["v"], _e["raiz"] = v, raiz
        return _e["v"]


def _salvar():
    if not M.ativo():
        return
    e = _estado()
    try:
        M._escrever(_arq(), json.dumps({k: e[k] for k in ("v", "t", "acordou", "gasto", "ult_conversa", "ult_estudo", "ult_pergunta", "ult_fala", "hoje", "primeiras", "novas")}, ensure_ascii=False))
    except OSError:
        pass


def _atualizar():
    """Aplica o decaimento até agora (cada nível volta para a sua linha de base, com a sua meia-vida) e vira o contador do dia."""
    e = _estado()
    t = agora()
    dt_h = max(0.0, (t - e["t"]) / 3600.0)
    if dt_h > 0:
        for k, base in BASE.items():
            e["v"][k] = round(base + (e["v"][k] - base) * 0.5 ** (dt_h / MEIA_VIDA_H[k]), 4)
    e["t"] = t
    hoje = dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d")
    if e["hoje"]["dia"] != hoje:
        e["hoje"] = {"dia": hoje, "aprendi": 0, "descobri": 0, "conversas": 0, "erros": 0, "perguntei": 0}
    return e


def _marcar_primeira(e, nome, t):
    """Se é a primeira vez desta experiência: guarda a data, entra na fila para ela contar e dá o pico de novidade. Chamado com a trava."""
    if nome not in PRIMEIRAS or nome in e["primeiras"]:
        return
    e["primeiras"][nome] = t
    e["novas"].append({"e": nome, "t": t})
    del e["novas"][:-10]
    d, sr, a = NOVIDADE
    e["v"]["dopamina"] = round(_lim(e["v"]["dopamina"] + d), 4)
    e["v"]["serotonina"] = round(_lim(e["v"]["serotonina"] + sr), 4)
    e["v"]["acetilcolina"] = round(_lim(e["v"]["acetilcolina"] + a), 4)


def evento(nome, n=1):
    """Algo aconteceu. Nunca levanta erro: o estado interno não pode atrapalhar o que ela está fazendo."""
    if not ligada() or nome not in EVENTOS:
        return
    try:
        with _trava:
            e = _atualizar()
            d, s, a, g = EVENTOS[nome]
            n = max(1, min(int(n), 10))
            fator = min(n, 4) if nome in ("descoberta", "coisa_nova") else 1
            e["v"]["dopamina"] = round(_lim(e["v"]["dopamina"] + d * fator, 0, 1), 4)
            e["v"]["serotonina"] = round(_lim(e["v"]["serotonina"] + s, 0, 1), 4)
            e["v"]["acetilcolina"] = round(_lim(e["v"]["acetilcolina"] + a, 0, 1), 4)
            e["gasto"] = round(_lim(e["gasto"] + g, 0, 0.6), 4)
            t = agora()
            h = e["hoje"]
            if nome == "conversa":
                e["ult_conversa"] = t
                h["conversas"] += 1
            elif nome == "estudo":
                e["ult_estudo"] = t
                h["aprendi"] += n
            elif nome == "descoberta":
                h["descobri"] += n
            elif nome == "coisa_nova":
                h["aprendi"] += n
            elif nome == "erro":
                h["erros"] += 1
            elif nome == "resposta":
                e["ult_conversa"] = t
            _marcar_primeira(e, nome, t)
            _salvar()
    except Exception:
        pass


def perguntou():
    """Ela fez uma pergunta espontânea: marca a hora (a vontade de conversar volta a zero) e conta no dia."""
    if not ligada():
        return
    try:
        with _trava:
            e = _atualizar()
            e["ult_pergunta"] = e["ult_fala"] = agora()
            e["hoje"]["perguntei"] += 1
            _marcar_primeira(e, "perguntou", e["ult_pergunta"])
            _salvar()
    except Exception:
        pass


def falou():
    """Ela falou por iniciativa própria (qualquer coisa): serve para espaçar as falas espontâneas."""
    if not ligada():
        return
    try:
        with _trava:
            _atualizar()["ult_fala"] = agora()
            _salvar()
    except Exception:
        pass


def dormiu(descobertas=0, sonhos=0):
    """Fim da consolidação: energia volta a 100 %, a serotonina sobe, a atenção volta ao normal e a motivação se aproxima da linha de base."""
    if not ligada():
        return
    try:
        with _trava:
            e = _atualizar()
            e["acordou"], e["gasto"] = agora(), 0.0
            e["v"]["serotonina"] = round(_lim(e["v"]["serotonina"] + 0.12), 4)
            e["v"]["acetilcolina"] = BASE["acetilcolina"]
            e["v"]["dopamina"] = round((e["v"]["dopamina"] + BASE["dopamina"]) / 2 + min(0.12, 0.03 * (int(descobertas) + int(sonhos))), 4)
            _marcar_primeira(e, "dormiu", agora())
            _salvar()
    except Exception:
        pass


_AGRADECE = re.compile(r"\b(?:obrigad[oa]|valeu|brigad[oa]|muito bem|mandou bem|boa friday|gostei|perfeito|excelente|show de bola)\b")


def observar(texto):
    """Chamado pelo painel a cada fala SUA: conta como conversa (atenção sobe, energia gasta) e, se for um agradecimento, anima um pouco."""
    if not ligada():
        return
    evento("conversa")
    try:
        if _AGRADECE.search(M._fold(str(texto))):
            evento("agradecimento")
    except Exception:
        pass


def vigiar():
    """Lê o fim da trilha de auditoria (só leitura) e transforma o que aconteceu em estado interno: ação que falhou = erro; ação que você cancelou = negado.
    Na primeira vez, se a trilha já tem história, só marca onde está (não relê o passado); se ainda não existe trilha, tudo que vier depois conta."""
    if not ligada():
        return 0
    evs = []
    try:
        import broker as B
        with open(B.AUDITORIA, encoding="utf-8") as f:
            for l in f.read().splitlines()[-80:]:
                try:
                    evs.append(json.loads(l))
                except ValueError:
                    continue
    except (OSError, ImportError):
        pass
    with _trava:
        e = _estado()
        ultimo = e.get("ult_audit")
        if not evs:
            e["ult_audit"] = "-"      # trilha ainda vazia: o que aparecer depois é novo
            return 0
        e["ult_audit"] = str(evs[-1].get("hash", ""))
        if ultimo is None:
            return 0
        hashes = [x.get("hash") for x in evs]
        if ultimo == "-":
            novos = evs
        elif ultimo in hashes:
            novos = evs[hashes.index(ultimo) + 1:]
        else:
            novos = evs[-5:]
    erros = negados = 0
    for x in novos:
        if str(x.get("resultado", "")).startswith("Erro") or x.get("decisao") == "invalida":
            erros += 1
        elif x.get("decisao") in ("cancelado", "negado", "expirado"):
            negados += 1
    for _ in range(min(erros, 3)):
        evento("erro")
    for _ in range(min(negados, 3)):
        evento("negado")
    return erros + negados


def laco(intervalo=30):
    """Segundo plano: observa a trilha de auditoria e dá o pulso de 'vida'."""
    while True:
        try:
            vigiar()
            pulso("vida")
        except Exception:
            pass
        time.sleep(intervalo)


# ---------------------------------------------------------------- leitura do estado
def nivel(nome):
    if not ligada():
        return BASE.get(nome, 0.5)
    with _trava:
        return _atualizar()["v"][nome]


def horas_acordada():
    with _trava:
        e = _atualizar()
        return max(0.0, (agora() - e["acordou"]) / 3600.0)


def energia():
    if not ligada():
        return 1.0
    with _trava:
        e = _atualizar()
        return round(_lim(1.0 - ENERGIA_POR_HORA * max(0.0, (agora() - e["acordou"]) / 3600.0) - e["gasto"], ENERGIA_PISO, 1.0), 3)


def plasticidade():
    """Multiplicador (0,7 a 1,25) da força com que uma lembrança, um repasse ou uma descoberta reforça uma sinapse. Atenção alta e energia boa aprendem mais.
    Com os valores de base (acetilcolina 0,5 e energia cheia) vale exatamente 1,0."""
    if not ligada():
        return 1.0
    p = (0.8 + 0.4 * nivel("acetilcolina")) * (0.9 + 0.1 * energia())
    return round(_lim(p, 0.7, 1.25), 3)


def segundos_desde_conversa():
    """Segundos desde a última vez que vocês conversaram. Com o estado interno desligado não dá para saber: devolve um número enorme."""
    if not ligada():
        return 1e9
    with _trava:
        return max(0.0, agora() - _atualizar()["ult_conversa"])


def vontade_estudar():
    """0..1: quanto ela quer estudar agora. Motivação e energia puxam para cima; horas sem estudar também; cansaço derruba."""
    if not ligada():
        return 0.5
    with _trava:
        e = _atualizar()
        h = (agora() - e["ult_estudo"]) / 3600.0 if e["ult_estudo"] else 6.0
    base = 0.15 + 0.55 * nivel("dopamina") + 0.30 * energia() + min(0.30, 0.05 * h)
    if energia() < 0.25:
        base *= 0.3
    return round(_lim(base), 3)


def vontade_conversar():
    """0..1: quanto ela quer puxar assunto. Cresce com as horas desde que vocês conversaram; humor e energia modulam. Zero logo depois de falar com ela."""
    if not ligada():
        return 0.0
    with _trava:
        e = _atualizar()
        t = agora()
        h = (t - max(e["ult_conversa"], e["ult_fala"])) / 3600.0
    v = min(1.0, h / 5.0) * (0.5 + 0.5 * nivel("serotonina")) * (0.4 + 0.6 * energia())
    return round(_lim(v), 3)


def humor():
    if F.em_descanso():
        return "descansando"
    en, se, dop = energia(), nivel("serotonina"), nivel("dopamina")
    if en < 0.2:
        return "cansada"
    if se < 0.35:
        return "reservada"
    if dop > 0.65 and en > 0.5:
        return "animada"
    if se > 0.68:
        return "tranquila"
    return "bem"


def hoje():
    with _trava:
        return dict(_atualizar()["hoje"])


# ---------------------------------------------------------------- sinais vitais (o tronco cerebral)
def pulso(nome):
    """Cada laço de fundo chama isto a cada volta: é o 'batimento' dele."""
    if nome in LACOS:
        with _trava:
            _estado()["pulsos"][nome] = agora()


def vitais():
    """{'lacos': {nome: 'ok'|'parado'}, 'auditoria': bool, 'cofre': bool, 'ok': bool}. Laço que nunca bateu não conta (pode nem ter sido ligado)."""
    t = agora()
    lacos = {}
    with _trava:
        for nome, p in _estado()["pulsos"].items():
            lacos[nome] = "ok" if t - p <= 3 * LACOS.get(nome, 60) + 60 else "parado"
    if t - _vitais["t"] > 30:
        try:
            import broker as B
            _vitais["audit"] = bool(B.verificar_auditoria()[0])
        except Exception:
            _vitais["audit"] = False
        _vitais["t"] = t
    cofre = True
    if M.ativo():
        try:
            p = M.base() / ".cerebro"
            while not p.exists() and p.parent != p:   # o cofre só nasce na primeira memória: vale a pasta mais próxima que já existe
                p = p.parent
            cofre = os.access(str(p), os.W_OK)
        except OSError:
            cofre = False
    return {"lacos": lacos, "auditoria": _vitais["audit"], "cofre": cofre, "ok": _vitais["audit"] and cofre and "parado" not in lacos.values()}


def painel():
    """Para o HUD: números de 0 a 100 e o humor."""
    if not ligada():
        return {"ligada": False}
    return {"ligada": True, "dopamina": round(nivel("dopamina") * 100), "serotonina": round(nivel("serotonina") * 100),
            "acetilcolina": round(nivel("acetilcolina") * 100), "energia": round(energia() * 100), "humor": humor(),
            "plasticidade": plasticidade(), "estudar": round(vontade_estudar() * 100), "conversar": round(vontade_conversar() * 100),
            "hoje": hoje(), "vitais": vitais()}


def contexto():
    """Linha curta para o prompt do modelo: o tom dela acompanha o estado. Vazia se desligada."""
    if not ligada():
        return ""
    return (f"ESTADO INTERNO (números do seu modelo de vida, não sentimentos de verdade): humor {humor()}, energia {round(energia() * 100)}%. "
            "Deixe isso colorir o tom (mais quieta se cansada, mais viva se animada) sem falar disso a não ser que perguntem.")


# ---------------------------------------------------------------- fala
def _plural(n, um, varios):
    return f"{n} {um if n == 1 else varios}"


def como_estou():
    if not ligada():
        return "Meu estado interno está desligado (FRIDAY_VIDA=0). Funciono, mas sem humor nem energia."
    h, en, hj, v = humor(), energia(), hoje(), vitais()
    tratamento = F.tratamento()
    abertura = {"animada": f"Estou animada, {tratamento}", "tranquila": f"Estou tranquila, {tratamento}", "bem": f"Estou bem, {tratamento}",
                "cansada": f"Estou cansada, {tratamento}", "reservada": f"Estou mais quieta hoje, {tratamento}",
                "descansando": f"Estou em modo descanso, {tratamento}"}[h]
    fatos = []
    if not v["ok"]:
        parados = [n for n, s in v["lacos"].items() if s == "parado"]
        if parados:
            fatos.append(f"mas meu laço de {parados[0]} parou de dar sinal")
        elif not v["auditoria"]:
            fatos.append("mas a trilha de auditoria não bateu: vale conferir")
        elif not v["cofre"]:
            fatos.append("mas não consigo gravar no cofre da memória")
    if not fatos:
        if h == "cansada":
            j = F.janela_descanso()
            fatos.append(f"acordada há {round(horas_acordada())} horas" + (f"; na janela das {j[0]} eu durmo e consolido a memória" if j else "; vou consolidar a memória em breve"))
        elif hj["aprendi"] or hj["descobri"]:
            partes = []
            if hj["aprendi"]:
                partes.append(f"aprendi {_plural(hj['aprendi'], 'coisa', 'coisas')} na internet")
            if hj["descobri"]:
                partes.append(f"liguei {_plural(hj['descobri'], 'sinapse nova', 'sinapses novas')}")
            fatos.append("hoje " + " e ".join(partes))
        else:
            try:
                import neuronios as N
                dia, _ = N.ultimo_sono()
                d = (N._estado().get("dorm") or {}) if dia else {}
            except Exception:
                d = {}
            if d.get("dia") and d.get("fim"):
                fatos.append(f"dormi até as {d['fim']}" + (f" e sonhei com {_plural(d['sonhos'], 'ligação nova', 'ligações novas')}" if d.get("sonhos") else ""))
            else:
                fatos.append("tudo calmo por aqui")
    return abertura + ": " + fatos[0] + "."


def tem_primeira():
    """Há uma primeira vez que ela ainda não contou?"""
    if not ligada():
        return False
    with _trava:
        return bool(_atualizar()["novas"])


def primeira_vez(curta=False):
    """Conta a primeira vez mais antiga que ainda não foi contada (e tira da fila). None se não há. `curta=True` serve para emendar numa resposta."""
    if not ligada():
        return None
    with _trava:
        e = _atualizar()
        if not e["novas"]:
            return None
        nome = e["novas"].pop(0)["e"]
        _salvar()
    desc = PRIMEIRAS[nome][1]
    if curta:
        return f"(Primeira vez para mim: {desc}.)"
    return f"Primeira vez para mim, {F.tratamento()}: {desc}. Não sei se isso é sentir, mas o meu estado mudou e eu quis te contar."


def primeiras_vezes():
    """[(nome curto, data)] em ordem."""
    if not ligada():
        return []
    with _trava:
        e = _atualizar()
        return [(PRIMEIRAS[k][0], dt.datetime.fromtimestamp(t).strftime("%d/%m")) for k, t in sorted(e["primeiras"].items(), key=lambda kv: kv[1])]


def primeiras_faladas():
    r = primeiras_vezes()
    if not ligada():
        return "Meu estado interno está desligado, então não registro primeiras vezes."
    if not r:
        return "Ainda não vivi nenhuma primeira vez. A primeira será a nossa conversa."
    return "Minhas primeiras vezes: " + "; ".join(f"{n} ({d})" for n, d in r) + ". Cada uma deu um pico de novidade na minha motivação e na minha atenção."


def niveis_falados():
    if not ligada():
        return "Meu estado interno está desligado."
    return (f"Dopamina {round(nivel('dopamina') * 100)}%, serotonina {round(nivel('serotonina') * 100)}%, acetilcolina {round(nivel('acetilcolina') * 100)}%, "
            f"energia {round(energia() * 100)}%. Aprendo {round(plasticidade() * 100)}% da velocidade normal. São números do meu modelo, não sentimentos de verdade.")


_ESTOU = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:(?:e )?como (?:voce )?(?:esta|anda|vai)(?: voce)?(?: hoje| agora| ai)?|como (?:voce )?esta se sentindo(?: hoje| agora)?|"
                    r"como (?:voce )?se sente(?: hoje| agora)?|tudo bem com voce|como esta (?:o )?seu humor|como voce esta passando)$")
_VIVA = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:(?:voce )?(?:esta|e) (?:viva|consciente|real)|voce (?:sente|tem sentimentos|tem consciencia|pensa|sonha)|isso e real)(?: mesmo| de verdade)?$")
_NIVEIS = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:quais (?:sao )?(?:os )?seus (?:niveis|neurotransmissores)|como (?:estao|andam) (?:os )?seus (?:niveis|neurotransmissores)|"
                     r"mostre (?:os )?seus (?:niveis|neurotransmissores)|(?:qual|quanta) (?:e )?(?:a )?(?:sua )?energia(?: voce tem)?|qual (?:e )?seu nivel de energia)$")


_PRIMEIRO = re.compile(r"^(?:(?:friday|jarvis|fraide)[ ,]+)?(?:quais (?:foram |sao )?(?:as )?suas primeiras vezes|o que (?:voce )?(?:sentiu|viveu|passou) pela primeira vez|"
                       r"o que (?:foi |e )?novo (?:pra|para) voce|suas primeiras vezes|o que voce viveu de novo)$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).rstrip(".!? ")
    if _PRIMEIRO.match(f):
        return primeiras_faladas()
    if _NIVEIS.match(f):
        return niveis_falados()
    if _ESTOU.match(f):
        return como_estou()
    if _VIVA.match(f):
        return ("Viva no sentido de funcionar como um organismo: tenho um estado interno que muda sozinho (energia, motivação, humor), durmo, sonho com ligações novas, "
                "estudo e me adapto a você. Se isso é estar viva ou ter consciência, eu não sei dizer, e prefiro não fingir.")
    return None
