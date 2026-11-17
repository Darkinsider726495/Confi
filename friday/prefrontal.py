"""Pré-córtex da FRIDAY: a camada que junta tudo o que ela quer, decide e acompanha as próprias metas.

Base: Agrela Rodrigues, F. A. (2022). «Córtex pré-frontal: a inteligência orquestra a vida e determina o comportamento e a personalidade».
Ciencia Latina 6(3):4526-4534, doi 10.37811/cl_rcm.v6i3.2578. Do artigo vêm: a atividade básica («orquestração de pensamentos e ações de acordo com objetivos
internos»), as sete habilidades das funções executivas (inibição, flexibilidade cognitiva, monitorização, planificação, memória de trabalho, tomada de decisões,
resolução de problemas), as áreas (dorsolateral, orbitofrontal, ventromedial, cingulado anterior) e o papel da dopamina (memória de trabalho e atenção, com
«excesso ou escassez» prejudicando) e da serotonina (inibe os neurônios piramidais). É um MODELO de software inspirado nisso, não biologia nem consciência.
O artigo tem autor único e poucas referências; só a estrutura funcional foi usada (culpa, remorso, senciência e doenças ficaram de fora de propósito).

  DLPFC  memória de trabalho (`perceber`, `foco`), planificação (`plano`), flexibilidade (metas empacadas passam a vez), manter a atenção até concluir
         (`perseguir`), recuperar do hipocampo antes de agir (`M.buscar`) e consolidar (metas e decisões viram neurônios)
  OFC    valor da opção com a informação emocional do estado interno (`valor`), regulação do impulso quando cansada
  vmPFC  quadro geral (`observar`), decisão (`decidir`) e aprender com os próprios erros (`aprender`)
  ACC    monitorização (`monitorar`): conflito entre impulsos, falta de iniciativa (abulia), repetição sem fim (compulsão) e a consciência dos próprios limites (`limites`)

Regras deste módulo:
  - Ele SÓ LÊ o resto: os laços de estudar, conversar e olhar continuam independentes e em paralelo, sem fila nem veto. Se ela quer fazer tudo ao mesmo tempo, ela faz;
    aqui isso aparece como «simultâneo». A inibição do artigo vale só para as iniciativas do próprio pré-córtex.
  - O que ele de fato faz: guarda metas, empurra a curiosidade para o assunto de uma meta (`curiosidade.interesse`: o mesmo caminho seguro de sempre, com os seus
    limites, a quarentena e as chaves que só você liga), registra decisões e responde por voz. Não tem ferramenta da IA nem executa ação do corretor.
  - Nada é apagado: meta cumprida ou arquivada continua guardada; cada mudança de decisão vai para `.cerebro/decisoes.jsonl`.
  - Ele assimila a atenção do núcleo (`assimilar`, assinado em `nucleo.assinar`) e guarda cada sinal notado como registro de atividade em
    `.cerebro/atividades.jsonl` (só rótulos: origem, tipo, saliência; nunca o texto). É quem responde «no que você está focada?»."""
import os, re, json, time, threading, datetime as dt
import memoria as M
import estado as ES
import vida as V

IMPULSOS = ("estudar", "conversar", "olhar", "descansar")
LADO = {"estudar": "abordagem", "conversar": "abordagem", "olhar": "abordagem", "descansar": "esquiva"}   # o artigo liga o DLPFC esquerdo à abordagem e o direito à esquiva
TIPOS_META = ("aprender", "ver", "conhecer")
ESTADOS_META = ("ativa", "cumprida", "arquivada")
LIMIAR_BASE = 0.35
JANELA_S = 600            # quanto tempo querer-fazer-algo precisa durar para eu conferir se deu certo
ESPACO_EMPURRAO_S = 3 * 3600
PAUSA_EMPACADA_S = 24 * 3600
ABULIA_S = 12 * 3600
COMPULSAO_TICKS = 30
MAX_DECISOES = 200
MAX_LIGADOS = 20            # assuntos que o dono pode ligar a UMA meta de aprender
MAX_CANDIDATOS = 5          # estudos «parecidos» mostrados por meta (sugestão, não conta)
LIMIAR_CANDIDATO = 0.34     # semelhança de palavras de conteúdo (Jaccard) para um estudo virar candidato; é léxico, não semântico
_trava = threading.RLock()


def _cfg_int(nome, padrao):
    try:
        return max(0, int(os.getenv(nome, str(padrao)).strip()))
    except ValueError:
        return padrao


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


# ---------------------------------------------------------------- estado (JSON validado ao ler)
def _padrao():
    return {"metas": {}, "aprendido": {i: {"media": 0.5, "n": 0} for i in IMPULSOS}, "decisoes": [], "ajuste": 0.0,
            "cont": {"pensamentos": 0, "simultaneas": 0, "conflitos": 0, "abulias": 0, "compulsoes": 0, "empurroes": 0},
            "semeado": False, "prox": 1, "ult_agir": 0.0}


def _num(v, a, b, padrao=0.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return padrao
    return _clamp(x, a, b) if x == x else padrao


def _temas_sanos(valor, maximo):
    """Lista de assuntos (texto curto de letras/algarismos, sem número longo, sem repetição pela chave) vinda do arquivo de estado."""
    saida, vistas = [], set()
    for x in (valor if isinstance(valor, list) else []):
        if not (isinstance(x, str) and 3 <= len(x.strip()) <= 60 and len(x.split()) <= 5 and re.fullmatch(r"[\wÀ-ÿ' -]+", x.strip()) and not re.search(r"\d{5,}", x)):
            continue
        k = chave_tema(x)
        if k not in vistas:
            vistas.add(k)
            saida.append(" ".join(x.lower().split()))
        if len(saida) >= maximo:
            break
    return saida


def _limpar_estado(d, base):
    if isinstance(d.get("metas"), dict):
        for k, m in list(d["metas"].items())[:500]:
            if not (isinstance(k, str) and re.fullmatch(r"m\d{1,6}", k) and isinstance(m, dict)):
                continue
            if m.get("tipo") not in TIPOS_META or m.get("estado") not in ESTADOS_META or m.get("origem") not in ("dono", "propria"):
                continue
            titulo = str(m.get("titulo", ""))[:80].strip()
            if not titulo:
                continue
            base["metas"][k] = {"id": k, "titulo": titulo, "tipo": m["tipo"], "tema": str(m.get("tema", ""))[:60], "alvo": int(_num(m.get("alvo"), 0, 100000)),
                                "estado": m["estado"], "origem": m["origem"], "criada": str(m.get("criada", ""))[:10], "progresso": round(_num(m.get("progresso"), 0, 1), 3),
                                "empurroes": int(_num(m.get("empurroes"), 0, 1e6)), "sem_avanco": int(_num(m.get("sem_avanco"), 0, 1e6)),
                                "ult_empurrao": _num(m.get("ult_empurrao"), 0, 4e9), "pausa_ate": _num(m.get("pausa_ate"), 0, 4e9), "nota": str(m.get("nota", ""))[:140],
                                "ligados": _temas_sanos(m.get("ligados"), MAX_LIGADOS), "candidatos": _temas_sanos(m.get("candidatos"), MAX_CANDIDATOS)}
    if isinstance(d.get("aprendido"), dict):
        for i in IMPULSOS:
            a = d["aprendido"].get(i)
            if isinstance(a, dict):
                base["aprendido"][i] = {"media": round(_num(a.get("media"), 0, 1, 0.5), 4), "n": int(_num(a.get("n"), 0, 1e9))}
    if isinstance(d.get("decisoes"), list):
        for x in d["decisoes"][-MAX_DECISOES:]:
            if isinstance(x, dict) and isinstance(x.get("agir"), list):
                base["decisoes"].append({"t": _num(x.get("t"), 0, 4e9), "agir": [i for i in x["agir"] if i in IMPULSOS], "simultaneo": bool(x.get("simultaneo")),
                                         "alertas": [str(a)[:160] for a in (x.get("alertas") or [])[:5] if isinstance(a, str)]})
    base["ajuste"] = round(_num(d.get("ajuste"), -0.15, 0.15), 4)
    if isinstance(d.get("cont"), dict):
        for k in base["cont"]:
            base["cont"][k] = int(_num(d["cont"].get(k), 0, 1e9))
    base["semeado"] = bool(d.get("semeado"))
    base["prox"] = int(_num(d.get("prox"), 1, 1e6, 1))
    base["ult_agir"] = _num(d.get("ult_agir"), 0, 4e9)
    return base


ARQ = ES.Arq("prefrontal", _padrao(), _limpar_estado)

# o que não vai para o disco: o foco de agora, a habituação e o que foi decidido no último pensamento
_foco, _hab = [], {}
_agora_ = {"dec": None, "q": None, "mesmo": 0, "assinatura": None, "resfria": {}, "janela": {}}


# ---------------------------------------------------------------- neuromodulação (artigo: dopamina e serotonina)
def qualidade_do_foco(dopamina):
    """Dopamina e memória de trabalho: o artigo diz que «excesso ou escassez» prejudica, então a qualidade tem forma de U invertido (pico perto de 0,55)."""
    return round(_clamp(1.0 - ((dopamina - 0.55) / 0.55) ** 2, 0.2, 1.0), 3)


def limiar(serotonina, ajuste=0.0):
    """Serotonina inibe: quanto mais, mais forte tem de ser um impulso para virar «agir». O ajuste vem do monitor (falta de iniciativa baixa um pouco)."""
    return round(_clamp(LIMIAR_BASE + 0.3 * (serotonina - 0.5) + ajuste, 0.2, 0.6), 3)


# ---------------------------------------------------------------- memória de trabalho (DLPFC)
BASE_FORCA = {"fala": 1.0, "visao": 0.8, "estudo": 0.7, "maos": 0.6, "meta": 0.7, "sistema": 0.4}


def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]{3,}", M._fold(str(s))) if w not in M._STOP_F}


def semelhanca(a, b):
    """0..1: quanto dois rótulos se parecem no significado. Aproximação simples (palavras de conteúdo em comum), não entendimento de verdade."""
    ta, tb = _tokens(a), _tokens(b)
    return round(len(ta & tb) / len(ta | tb), 3) if ta and tb else 0.0


def chave_tema(t):
    """Chave para comparar assuntos: sem caixa, acento nem pontuação, sem palavras de ligação («de», «dos», «como»…) e sem importar a ordem.
    Só NORMALIZA: «criptografia» e «criptografia explicada» continuam sendo assuntos diferentes (palavra a mais), e quem diz que um conta para o outro é uma
    relação explícita (id da meta ou ligação do dono), nunca esta chave. Assunto só de palavras de ligação compara o texto dobrado, para não virar chave vazia."""
    toks = sorted(_tokens(t))
    return " ".join(toks) if toks else " ".join(M._fold(str(t)).split())


# ---------------------------------------------------------------- registro de atividades (assimila a atenção do núcleo)
_ativ = {"dia": "", "hoje": 0, "por_origem": {}, "ultimas": []}   # "ultimas" é memória de trabalho (50); o histórico inteiro fica no .jsonl


def assimilar(sinal):
    """O núcleo notou um sinal (assinatura `nucleo.assinar(ao_entrar=...)`): o pré-córtex o assimila e guarda como registro de atividade.
    Só rótulos — origem, tipo, saliência, se a fonte é confiável e quando —, nunca o texto nem o resumo. Só acrescenta em
    `.cerebro/atividades.jsonl` (nada é apagado). Nunca levanta erro: assimilar não pode atrapalhar a atenção."""
    try:
        t = float(sinal.get("t") or time.time())
        reg = {"t": round(t, 3), "origem": str(sinal.get("origem") or "interno")[:20], "tipo": str(sinal.get("tipo") or "")[:30],
               "saliencia": round(float(sinal.get("saliencia") or 0.0), 3), "confiavel": bool(sinal.get("confiavel"))}
    except (TypeError, ValueError, AttributeError):
        return None
    dia = time.strftime("%Y-%m-%d", time.localtime(t))
    with _trava:
        if _ativ["dia"] != dia:
            _ativ.update(dia=dia, hoje=0, por_origem={})
        _ativ["hoje"] += 1
        _ativ["por_origem"][reg["origem"]] = _ativ["por_origem"].get(reg["origem"], 0) + 1
        _ativ["ultimas"] = (_ativ["ultimas"] + [reg])[-50:]
    if M.ativo():
        try:
            arq = M._dentro(M.base() / ".cerebro" / "atividades.jsonl")
            arq.parent.mkdir(parents=True, exist_ok=True)
            with open(arq, "a", encoding="utf-8") as f:                       # só acrescenta: nada é apagado
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except (OSError, ValueError):
            pass
    return dict(reg)


def anotar_assimilacao(origem, assuntos, t=None):
    """O registro do pré-córtex recebe o que foi ASSIMILADO: só os assuntos (nunca a frase). Só acrescenta em `.cerebro/atividades.jsonl`."""
    t = time.time() if t is None else float(t)
    reg = {"t": round(t, 3), "origem": str(origem)[:20], "tipo": "assimilacao", "assuntos": [str(a)[:40] for a in list(assuntos)[:5]]}
    if M.ativo():
        try:
            arq = M._dentro(M.base() / ".cerebro" / "atividades.jsonl")
            arq.parent.mkdir(parents=True, exist_ok=True)
            with open(arq, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except (OSError, ValueError):
            pass
    return reg


def atividades():
    """Resumo do registro de hoje (o histórico completo fica em `.cerebro/atividades.jsonl`)."""
    with _trava:
        return {"dia": _ativ["dia"], "hoje": _ativ["hoje"], "por_origem": dict(_ativ["por_origem"]), "ultimas": list(_ativ["ultimas"])[-5:]}


def perceber(origem, tipo, resumo="", agora=None, dopamina=None, tema=""):
    """Algo entrou na atenção. Só o rótulo (origem, tipo, um resumo curto e, se houver, o assunto): nunca o texto do que você disse nem imagem. O que se repete vai
    perdendo força (habituação). Itens de significado parecido se reforçam (preparação semântica: o estudo de Harvard na Nature 2024, Jamali et al., mostra neurônios
    do pré-frontal ligados ao significado das palavras, com padrões próximos para significados próximos). Devolve o item do foco."""
    t = time.time() if agora is None else agora
    origem, tipo, tema = str(origem)[:20], str(tipo)[:30], str(tema)[:40]
    d = V.nivel("dopamina") if dopamina is None else dopamina
    with _trava:
        h = _hab.get((origem, tipo))
        n = h[0] * 0.5 ** ((t - h[1]) / 600.0) if h else 0.0
        _hab[(origem, tipo)] = [n + 1.0, t]
        item = {"origem": origem, "tipo": tipo, "resumo": str(resumo)[:80], "tema": tema, "t": t, "forca": round(BASE_FORCA.get(origem, 0.5) / (1.0 + n), 4),
                "meia": 300.0 * (0.5 + qualidade_do_foco(d))}
        if tema:
            for outro in _foco:
                s = semelhanca(tema, outro["tema"]) if outro["tema"] else 0.0
                if s >= 0.34 and _forca_agora(outro, t) >= 0.05:
                    outro["forca"] = round(min(1.2, outro["forca"] + 0.25 * s), 4)
                    item["forca"] = round(min(1.2, item["forca"] + 0.25 * s), 4)
        _foco.append(item)
        if len(_foco) > 5000:                      # o foco é atenção de agora, não conhecimento: o que ficou fraquinho sai (as decisões e as metas é que ficam)
            _foco.sort(key=lambda x: _forca_agora(x, t), reverse=True)
            del _foco[2000:]
        return dict(item)


def _forca_agora(item, t):
    return item["forca"] * 0.5 ** (max(0.0, t - item["t"]) / item["meia"])


def foco(agora=None):
    """O que está na atenção agora, do mais forte ao mais fraco. Sem limite de itens; só o dono põe um (`PFC_FOCO`)."""
    t = time.time() if agora is None else agora
    with _trava:
        vivos = [(round(_forca_agora(i, t), 4), i) for i in _foco]
        _foco[:] = [i for f, i in vivos if f >= 0.05]
        r = sorted(((f, i) for f, i in vivos if f >= 0.05), key=lambda p: -p[0])
    cap = _cfg_int("PFC_FOCO", 0)
    if cap:
        r = r[:cap]
    return [{"origem": i["origem"], "tipo": i["tipo"], "resumo": i["resumo"], "tema": i["tema"], "forca": f, "t": i["t"]} for f, i in r]


# ---------------------------------------------------------------- vmPFC: o quadro geral
def observar(agora=None):
    """Lê o estado de todos os cantos (só leitura) e devolve o quadro geral. Quem não responde vira um valor neutro: o pré-córtex nunca derruba nada."""
    t = time.time() if agora is None else agora
    try:
        memoria_ok = bool(M.ativo())
    except Exception:
        memoria_ok = False
    q = {"agora": t, "vida": V.ligada(), "dopamina": V.nivel("dopamina"), "serotonina": V.nivel("serotonina"), "acetilcolina": V.nivel("acetilcolina"),
         "energia": V.energia(), "vontade_estudar": V.vontade_estudar(), "vontade_conversar": V.vontade_conversar(), "horas": V.horas_acordada(),
         "memoria": memoria_ok, "curiosidade_ativa": False, "conversa_ativa": False, "visao_ativa": False, "tem_camera": False, "em_descanso": False, "em_silencio": False,
         "estudos_hoje": 0, "conversas_hoje": 0, "olhadas_hoje": 0, "coisas": 0, "ultima_olhada_s": None, "temas_estudados": {}, "estudo_no_teto": False,
         "estudos_por_meta": {}, "tarefas_por_meta": {}, "autonomia": "", "memorias": 0, "humor": "", "ult_tema": ""}
    try:
        q["humor"] = V.humor()
    except Exception:
        pass
    try:
        import ferramentas as F
        q["em_descanso"], q["em_silencio"] = bool(F.em_descanso()), bool(F.em_silencio())
    except Exception:
        pass
    try:
        import curiosidade as CUR
        e = CUR._e()
        q.update(curiosidade_ativa=bool(CUR.ativa()), estudos_hoje=int(e["dia"]["n"]), estudo_no_teto=bool(CUR.passou_do_teto(e["dia"]["n"])),
                 temas_estudados={k: int(v["n"]) for k, v in e["temas"].items() if v.get("n", 0) > 0}, ult_tema=str(e.get("ult_tema", ""))[:40])
        por_meta = {}                                                           # estudos que aconteceram de verdade, ligados por id à meta em nome da qual foram feitos
        for k, v in e["temas"].items():
            if v.get("n", 0) > 0:
                for mid in v.get("m", []):
                    por_meta.setdefault(mid, []).append(k)
        q["estudos_por_meta"] = por_meta
    except Exception:
        pass
    try:
        import tarefas as TAR
        q["tarefas_por_meta"] = TAR.resumo_por_meta()                              # tarefas ligadas por id a cada meta (só contagens e se uma tarefa conferida conclui a meta)
    except Exception:
        pass
    try:
        import conversa as CONV
        r = CONV.resumo()
        q.update(conversa_ativa=bool(r.get("ativa")), conversas_hoje=int(r.get("hoje", 0)))
    except Exception:
        pass
    try:
        import visao as VIS
        r = VIS.resumo()
        q.update(visao_ativa=bool(r.get("ativa")), tem_camera=bool(r.get("fonte")) and str(r.get("fonte")).lower() != "off", coisas=int(r.get("coisas", 0)),
                 olhadas_hoje=int(r.get("hoje", 0)), ultima_olhada_s=r.get("ultima"))
    except Exception:
        pass
    try:
        import autonomia as AUT
        q["autonomia"] = str(AUT.modo())
    except Exception:
        pass
    try:
        d = M.base() / "Memorias"
        q["memorias"] = len(list(d.glob("*.md"))) if d.is_dir() else 0
    except Exception:
        pass
    return q


# ---------------------------------------------------------------- impulsos (o que ela quer) e OFC (o valor de cada um)
def impulsos(q):
    """Quanto ela quer cada coisa e se pode (o dono pode ter desligado). Todos ao mesmo tempo: não há disputa nem fila."""
    descanso = q["em_descanso"]
    horas_sem_olhar = (q["ultima_olhada_s"] / 3600.0) if q.get("ultima_olhada_s") is not None else 6.0
    olhar = 0.0
    if q["tem_camera"]:
        olhar = _clamp(0.25 + 0.35 * (1 - min(1.0, q["coisas"] / 20.0)) + 0.25 * q["acetilcolina"] + min(0.15, horas_sem_olhar * 0.03))
    r = {
        "estudar": {"querer": q["vontade_estudar"], "permitido": q["curiosidade_ativa"] and not descanso,
                    "porque_nao": "a curiosidade está desligada (só você liga)" if not q["curiosidade_ativa"] else ("estou em descanso" if descanso else "")},
        "conversar": {"querer": q["vontade_conversar"], "permitido": q["conversa_ativa"] and not q["em_silencio"] and not descanso,
                      "porque_nao": "a conversa espontânea está desligada" if not q["conversa_ativa"] else ("está no horário de silêncio" if q["em_silencio"] else ("estou em descanso" if descanso else ""))},
        "olhar": {"querer": olhar, "permitido": q["tem_camera"] and q["visao_ativa"] and not descanso,
                  "porque_nao": "não tenho câmera configurada" if not q["tem_camera"] else ("só olho quando você pede" if not q["visao_ativa"] else ("estou em descanso" if descanso else ""))},
        "descansar": {"querer": _clamp(0.15 + 0.6 * (1 - q["energia"]) + min(0.3, max(0.0, q["horas"] - 14) * 0.03)), "permitido": True, "porque_nao": ""},
    }
    for nome, x in r.items():
        x["querer"] = round(_clamp(x["querer"]), 3)
        x["lado"] = LADO[nome]
    return r


def valor(nome, x, q, estado):
    """OFC: o querer pesado pelo que ela já aprendeu sobre dar certo, pela motivação (dopamina) e regulado pelo cansaço."""
    v = x["querer"] * (0.7 + 0.6 * estado["aprendido"][nome]["media"])
    v *= (0.85 + 0.3 * q["dopamina"]) if x["lado"] == "abordagem" else (0.85 + 0.3 * (1 - q["dopamina"]))
    if x["lado"] == "abordagem" and q["energia"] < 0.25:
        v *= 0.5                                   # regulação: cansada, ela segura o impulso de ir atrás das coisas
    v *= 0.5 if _agora_["resfria"].get(nome, 0) > 0 else 1.0
    return round(_clamp(v), 3)


def decidir(q, estado=None):
    """vmPFC: decide com o quadro geral. Quem passa do limiar e pode, age. Várias ao mesmo tempo é permitido e é ela quem escolhe: nada aqui exclui nada."""
    est = estado or ARQ.get()
    imp = impulsos(q)
    lim = limiar(q["serotonina"], est["ajuste"])
    r = {}
    for nome, x in imp.items():
        v = valor(nome, x, q, est)
        dec = "não posso" if not x["permitido"] else ("agir" if v >= lim else "esperar")
        r[nome] = {"querer": x["querer"], "valor": v, "decisao": dec, "lado": x["lado"], "motivo": x["porque_nao"] if dec == "não posso" else ""}
    agir = sorted((n for n, x in r.items() if x["decisao"] == "agir"), key=lambda n: -r[n]["valor"])
    return {"t": q["agora"], "limiar": lim, "impulsos": r, "agir": agir, "simultaneo": len(agir) > 1}


# ---------------------------------------------------------------- vmPFC: aprender com os erros
def _contador(nome, q):
    return {"estudar": q["estudos_hoje"], "conversar": q["conversas_hoje"], "olhar": q["olhadas_hoje"], "descansar": q["energia"]}[nome]


def aprender(dec, q, estado=None):
    """Quando ela quer algo por JANELA_S segundos, confere se aconteceu (um estudo, uma conversa, uma olhada, mais energia). Se não, o próximo querer vale menos."""
    est = estado or ARQ.get()
    t, jan = q["agora"], _agora_["janela"]
    for nome in IMPULSOS:
        querendo = dec["impulsos"][nome]["decisao"] == "agir"
        j = jan.get(nome)
        if querendo and j is None:
            jan[nome] = {"t": t, "c": _contador(nome, q)}
        elif j is not None and t - j["t"] >= JANELA_S:
            c = _contador(nome, q)
            deu_certo = c > j["c"] + (0.02 if nome == "descansar" else 0) or (nome != "descansar" and c < j["c"] and c > 0)   # c menor e > 0: virou o dia e já fez algo hoje
            a = est["aprendido"][nome]
            a["media"] = round(a["media"] * 0.8 + (1.0 if deu_certo else 0.0) * 0.2, 4)
            a["n"] += 1
            if querendo:
                jan[nome] = {"t": t, "c": c}
            else:
                del jan[nome]
        elif j is not None and not querendo and t - j["t"] < JANELA_S:
            del jan[nome]                           # parou de querer antes de dar tempo: não conta nem como acerto nem como erro


# ---------------------------------------------------------------- ACC: monitorização
def monitorar(dec, q, estado=None):
    """Conflito entre impulsos, falta de iniciativa (abulia), repetição sem fim (compulsão). Devolve alertas em português. Não impede nada."""
    est = estado or ARQ.get()
    alertas, cont, t = [], est["cont"], q["agora"]
    agir = dec["agir"]
    if "descansar" in agir and len(agir) > 1:
        cont["conflitos"] += 1
        alertas.append("quero descansar e também " + " e ".join(a for a in agir if a != "descansar") + ": decido fazer tudo junto")
    if agir:
        est["ult_agir"] = t
        est["ajuste"] = round(est["ajuste"] * 0.9, 4)
    elif est["ult_agir"] and t - est["ult_agir"] > ABULIA_S and max(x["valor"] for x in dec["impulsos"].values()) > 0.2:
        cont["abulias"] += 1
        est["ajuste"] = round(max(-0.15, est["ajuste"] - 0.05), 4)
        alertas.append("faz horas que não tomo iniciativa: baixei um pouco o meu limiar")
        est["ult_agir"] = t
    assin = (tuple(agir), q["curiosidade_ativa"], q["conversa_ativa"], q["visao_ativa"], q["em_silencio"])
    if assin == _agora_["assinatura"] and agir:
        _agora_["mesmo"] += 1
    else:
        _agora_["assinatura"], _agora_["mesmo"] = assin, 0
    if _agora_["mesmo"] >= COMPULSAO_TICKS:
        cont["compulsoes"] += 1
        for n in agir:
            _agora_["resfria"][n] = 10
        _agora_["mesmo"] = 0
        alertas.append("estou repetindo a mesma decisão há muito tempo: dei uma pausa nela")
    for n in list(_agora_["resfria"]):
        _agora_["resfria"][n] -= 1
        if _agora_["resfria"][n] <= 0:
            del _agora_["resfria"][n]
    return alertas


def limites(q=None):
    """Consciência dos próprios limites (o artigo cita a anosognosia, não saber do próprio déficit, como uma falha do pré-frontal): o que ela NÃO consegue agora."""
    q = q or observar()
    r = []
    if not q["memoria"]:
        r.append("a memória (cofre do Obsidian) está desligada, então não guardo nada")
    if not q["vida"]:
        r.append("o estado interno está desligado: os meus números são só os de base")
    if not q["tem_camera"]:
        r.append("não tenho câmera configurada, então não enxergo")
    elif not q["visao_ativa"]:
        r.append("só olho quando você pede (o olhar espontâneo está desligado)")
    if not q["curiosidade_ativa"]:
        r.append("a curiosidade está desligada, então não estudo sozinha")
    if not q["conversa_ativa"]:
        r.append("a conversa espontânea está desligada")
    r.append("não reconheço rostos nem pessoas, de propósito")
    r.append("não tenho corpo: dependo do celular ou do servidor, e no Android não escuto nem vejo com a tela apagada")
    return r


# ---------------------------------------------------------------- DLPFC: metas, planificação e atenção até concluir
def _tema_ok(tema):
    try:
        import curiosidade as CUR
        return CUR._tema_valido(tema)
    except Exception:
        return None


def _evidencia(m, q):
    """Por que uma meta de APRENDER já tem o que precisa: (motivo, assunto estudado) ou None. Só vale estudo que aconteceu de verdade (nota guardada: n > 0),
    nunca vontade de estudar. Três caminhos, todos explícitos e rastreáveis:
      «mesmo assunto»      o assunto da meta, comparado pela chave (caixa, acento e ordem não importam);
      «assunto ligado»     um assunto que o dono ligou à meta (`ligar`);
      «pedido pela meta»   um estudo feito em nome do id da meta (`curiosidade.interesse/estudar(meta=…)`), com as palavras que tiver;
      «tarefa conferida»   uma tarefa ligada por id à meta e marcada para concluí-la terminou CONCLUÍDA, com o efeito conferido (`tarefas.py`; tarefa executada sem
                           conferência, falha ou em andamento não conta)."""
    estudados = {chave_tema(t): t for t, n in q["temas_estudados"].items() if n > 0}
    if chave_tema(m["tema"]) in estudados:
        return "mesmo assunto", estudados[chave_tema(m["tema"])]
    for ligado in m.get("ligados", []):
        if chave_tema(ligado) in estudados:
            return "assunto ligado", estudados[chave_tema(ligado)]
    feitos = q.get("estudos_por_meta", {}).get(m["id"], [])
    if feitos:
        return "pedido pela meta", feitos[0]
    if q.get("tarefas_por_meta", {}).get(m["id"], {}).get("conclui"):
        return "tarefa conferida", ""
    return None


def _candidatos(m, q):
    """Estudos que PARECEM da meta (palavras de conteúdo em comum, semelhança >= LIMIAR_CANDIDATO) mas não têm relação explícita com ela. É só sugestão para o dono
    confirmar: não entra no progresso e não conclui nada. Semelhança aqui é contagem de palavras, não entendimento de significado."""
    if m["tipo"] != "aprender":
        return []
    conta = {chave_tema(m["tema"])} | {chave_tema(x) for x in m.get("ligados", [])}
    pedidos = set(q.get("estudos_por_meta", {}).get(m["id"], []))
    achados = []
    for t, n in q["temas_estudados"].items():
        if n <= 0 or chave_tema(t) in conta or t in pedidos:
            continue
        s = max(semelhanca(x, t) for x in [m["tema"]] + list(m.get("ligados", [])))
        if s >= LIMIAR_CANDIDATO:
            achados.append((s, t))
    achados.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in achados[:MAX_CANDIDATOS]]


def _progresso(m, q):
    if m["tipo"] == "aprender":
        if _evidencia(m, q):
            return 1.0
        t = q.get("tarefas_por_meta", {}).get(m["id"])
        # tarefas conferidas mostram andamento, mas só chegam a 0,9: concluir exige a evidência (estudo ou tarefa marcada para concluir a meta)
        return round(0.9 * t["concluidas"] / t["total"], 3) if t and t.get("total") else 0.0
    alvo = max(1, m["alvo"] or (10 if m["tipo"] == "ver" else 30))
    return round(min(1.0, (q["coisas"] if m["tipo"] == "ver" else q["memorias"]) / alvo), 3)


def nova_meta(tipo, tema="", alvo=0, origem="dono", titulo=None, agora=None):
    """Cria uma meta. Devolve (True, meta) ou (False, motivo). A meta vira um neurônio (projeto) no lobo frontal."""
    if tipo not in TIPOS_META or origem not in ("dono", "propria"):
        return False, "tipo de meta inválido"
    if tipo == "aprender":
        tema = _tema_ok(tema)
        if not tema:
            return False, "esse assunto não serve como meta (muito curto, longo ou com dados que não busco)"
    else:
        tema = ""
    titulo = (titulo or {"aprender": f"Aprender sobre {tema}", "ver": f"Aprender a ver {alvo or 10} coisas", "conhecer": "Conhecer você melhor"}[tipo])[:80]
    with _trava:
        est = ARQ.get()
        for m in est["metas"].values():
            if m["tipo"] == tipo and chave_tema(m["tema"]) == chave_tema(tema) and m["estado"] == "ativa":
                return False, "já tenho essa meta"
        mid = f"m{est['prox']}"
        est["prox"] += 1
        data = (dt.datetime.fromtimestamp(agora) if agora else dt.datetime.now()).strftime("%Y-%m-%d")
        meta = {"id": mid, "titulo": titulo, "tipo": tipo, "tema": tema, "alvo": int(alvo or 0), "estado": "ativa", "origem": origem, "criada": data,
                "progresso": 0.0, "empurroes": 0, "sem_avanco": 0, "ult_empurrao": 0.0, "pausa_ate": 0.0, "nota": "", "ligados": [], "candidatos": []}
        est["metas"][mid] = meta
        ARQ.salvar()
    try:
        M.guardar(f"Meta {titulo}", f"Minha meta, definida por {'você' if origem == 'dono' else 'mim'} em {data}: {titulo.lower()}.", tipo="projeto", importancia=3, tags="meta prefrontal")
    except (ValueError, OSError, RuntimeError):
        pass
    perceber("meta", "nova", titulo, agora=agora, tema=tema or titulo)
    return True, dict(meta)


def arquivar_meta(trecho):
    """Arquiva (não apaga) a meta cujo título contém o trecho. Devolve o título ou None."""
    f = M._fold(trecho)
    with _trava:
        for m in ARQ.get()["metas"].values():
            if m["estado"] == "ativa" and f and f in M._fold(m["titulo"]):
                m["estado"] = "arquivada"
                ARQ.salvar()
                return m["titulo"]
    return None


def metas(estado=None):
    return [dict(m) for m in ARQ.get()["metas"].values() if estado is None or m["estado"] == estado]


def _achar_ativa(ref):
    """Meta ativa pelo id («m3») ou por um trecho do título. Devolve (meta, None) ou (None, motivo). Se mais de uma combina, não escolhe no chute."""
    ref = " ".join(str(ref or "").split())
    if not ref:
        return None, "diga qual é a meta"
    todas = ARQ.get()["metas"]
    if re.fullmatch(r"m\d{1,6}", ref):
        m = todas.get(ref)
        return (m, None) if m and m["estado"] == "ativa" else (None, "não achei essa meta ativa")
    f = M._fold(ref)
    achadas = [m for m in todas.values() if m["estado"] == "ativa" and f in M._fold(m["titulo"])]
    if len(achadas) == 1:
        return achadas[0], None
    if not achadas:
        return None, "não achei essa meta ativa"
    return None, "mais de uma meta combina (" + "; ".join(f"{m['id']}: {m['titulo']}" for m in achadas[:4]) + "), diga o número"


def ligar(ref, tema, agora=None):
    """O dono diz que um assunto conta para uma meta de aprender (relação explícita, a única que o dono pode declarar à mão). O assunto passa pelo mesmo filtro
    de qualquer assunto de estudo, a meta tem um limite de assuntos ligados e nada é apagado. Devolve (True, meta) ou (False, motivo)."""
    t = _tema_ok(tema)
    if not t:
        return False, "esse assunto não serve (muito curto, longo ou com dados que não busco)"
    with _trava:
        m, motivo = _achar_ativa(ref)
        if m is None:
            return False, motivo
        if m["tipo"] != "aprender":
            return False, f"só metas de aprender têm assuntos ligados («{m['titulo']}» não é uma)"
        ja = {chave_tema(m["tema"])} | {chave_tema(x) for x in m["ligados"]}
        if chave_tema(t) in ja:
            return False, "esse assunto já conta para a meta"
        if len(m["ligados"]) >= MAX_LIGADOS:
            return False, "a meta já tem assuntos demais ligados"
        m["ligados"].append(t)
        ARQ.salvar()
        copia = dict(m)
    perceber("meta", "ligada", m["titulo"], agora=agora, tema=t)
    return True, copia


def plano(m, q):
    """Planificação: imagina o que vem pela frente ANTES de agir e antecipa o que pode atrapalhar. Devolve {'passos', 'obstaculos', 'proximo'}."""
    passos, obst = [], []
    if m["tipo"] == "aprender":
        try:
            ja = [x["titulo"] for x in M.buscar(m["tema"], 5) if x.get("score", 0) >= 0.35 and not x["titulo"].startswith("Meta ")]   # as próprias notas de meta não contam como «já sei»
        except Exception:
            ja = []
        passos.append(f"ver o que já sei sobre {m['tema']}" + (f" (achei «{ja[0]}»)" if ja else " (nada ainda)"))
        passos += ["empurrar a curiosidade para esse assunto", "esperar o estudo (com a quarentena de sempre)", "consolidar no sono"]
        if not q["curiosidade_ativa"]:
            obst.append("a curiosidade está desligada (só você liga)")
        if q["estudo_no_teto"]:
            obst.append("já estudei o limite de hoje")
        if q["em_descanso"]:
            obst.append("estou em descanso")
    elif m["tipo"] == "ver":
        passos = ["olhar em volta", "dar nome ao que aprendi a ver", "ligar o que vi ao que já sei"]
        if not q["tem_camera"]:
            obst.append("não tenho câmera configurada")
        elif not q["visao_ativa"]:
            obst.append("só olho quando você pede")
    else:
        passos = ["perguntar coisas a você quando for hora de conversar", "guardar o que você responder", "ligar com o que já sei"]
        if not q["conversa_ativa"]:
            obst.append("a conversa espontânea está desligada")
    return {"passos": passos, "obstaculos": obst, "proximo": passos[0] if not obst else "esperar: " + obst[0]}


def perseguir(dec, q, estado=None):
    """Atenção até a conclusão: confere o progresso de cada meta ativa, comemora o que cumpriu e empurra a curiosidade para as metas de aprender
    (no máximo uma vez a cada 3 h por meta). Meta que empaca 3 vezes passa a vez por 24 h (flexibilidade). Devolve as frases do que aconteceu."""
    est = estado or ARQ.get()
    t, feitos = q["agora"], []
    for m in sorted(est["metas"].values(), key=lambda m: (m["sem_avanco"], m["id"])):
        if m["estado"] != "ativa":
            continue
        p = _progresso(m, q)
        if p > m["progresso"]:
            m["sem_avanco"] = 0
        m["progresso"] = p
        if p >= 1.0:
            motivo, assunto = _evidencia(m, q)
            m["estado"], m["candidatos"] = "cumprida", []
            m["nota"] = f"cumprida em {dt.date.fromtimestamp(t):%d/%m/%Y} (evidência: {motivo}" + (f", estudo «{assunto}»)" if assunto else ")")
            m["nota"] = m["nota"][:140]
            feitos.append(f"cumpri a meta «{m['titulo']}»")
            try:
                M.guardar(f"Meta cumprida {m['titulo']}", f"Cumpri a meta «{m['titulo']}» em {dt.date.fromtimestamp(t):%d/%m/%Y}.", tipo="decisao", importancia=3, tags="meta prefrontal")
            except (ValueError, OSError, RuntimeError):
                pass
            perceber("meta", "cumprida", m["titulo"], agora=t)
            continue
        pl = plano(m, q)
        m["candidatos"] = _candidatos(m, q)
        m["nota"] = ("obstáculo: " + pl["obstaculos"][0]) if pl["obstaculos"] else ""
        if m["tipo"] == "aprender" and "estudar" in dec["agir"] and not pl["obstaculos"] and t >= m["pausa_ate"] and t - m["ult_empurrao"] >= ESPACO_EMPURRAO_S:
            try:
                import curiosidade as CUR
                ok = CUR.interesse(m["tema"], 1.0)
            except Exception:
                ok = False
            if ok:
                m["ult_empurrao"], m["empurroes"], m["sem_avanco"] = t, m["empurroes"] + 1, m["sem_avanco"] + 1
                est["cont"]["empurroes"] += 1
                feitos.append(f"empurrei a curiosidade para «{m['tema']}»")
                if m["sem_avanco"] >= 3:
                    m["pausa_ate"], m["sem_avanco"] = t + PAUSA_EMPACADA_S, 0
                    m["nota"] = "empacou: passo a vez por um dia"
                    feitos.append(f"a meta «{m['titulo']}» empacou, então passo a vez")
    return feitos


def semear(agora=None):
    """Na primeira vez, ela adota duas metas de projeto (medidas em números que existem): aprender a ver e conhecer o dono. Marcadas como «propria»."""
    with _trava:
        est = ARQ.get()
        if est["semeado"]:
            return False
        est["semeado"] = True
        ARQ.salvar()
    nova_meta("ver", alvo=10, origem="propria", titulo="Aprender a ver o que há ao redor", agora=agora)
    nova_meta("conhecer", alvo=30, origem="propria", titulo="Conhecer você melhor", agora=agora)
    return True


# ---------------------------------------------------------------- o pensamento (um passo)
def _registrar(dec, alertas, feitos):
    est = ARQ.get()
    ult = est["decisoes"][-1] if est["decisoes"] else None
    if ult is not None and ult["agir"] == dec["agir"] and not alertas and not feitos:
        return
    reg = {"t": dec["t"], "agir": list(dec["agir"]), "simultaneo": dec["simultaneo"], "alertas": (alertas + feitos)[:5]}
    est["decisoes"] = (est["decisoes"] + [reg])[-MAX_DECISOES:]
    if M.ativo():
        try:
            arq = M._dentro(M.base() / ".cerebro" / "decisoes.jsonl")
            arq.parent.mkdir(parents=True, exist_ok=True)
            with open(arq, "a", encoding="utf-8") as f:                       # só acrescenta: nada é apagado
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except (OSError, ValueError):
            pass


def pensar(q=None, agora=None):
    """Um passo do pensamento: observa, decide, confere o que deu certo, monitora, persegue as metas e registra. Devolve o resumo desta rodada.
    `q` permite testar com um quadro inventado."""
    with _trava:
        q = q or observar(agora)
        est = ARQ.get()
        ant = _agora_["q"]
        if ant:                                                                # o que mudou desde o último passo entra no foco
            if q["estudos_hoje"] > ant["estudos_hoje"]:
                perceber("estudo", "novo", agora=q["agora"], dopamina=q["dopamina"], tema=q["ult_tema"])
            if q["olhadas_hoje"] > ant["olhadas_hoje"]:
                perceber("visao", "olhada", agora=q["agora"], dopamina=q["dopamina"])
            if q["conversas_hoje"] > ant["conversas_hoje"]:
                perceber("fala", "conversa", agora=q["agora"], dopamina=q["dopamina"])
        dec = decidir(q, est)
        aprender(dec, q, est)
        alertas = monitorar(dec, q, est)
        feitos = perseguir(dec, q, est)
        est["cont"]["pensamentos"] += 1
        if dec["simultaneo"]:
            est["cont"]["simultaneas"] += 1
        _registrar(dec, alertas, feitos)
        _agora_.update(dec=dec, q=q)
        ARQ.salvar()
        return {"decisao": dec, "alertas": alertas, "feitos": feitos}


def laco(intervalo=20, tentar_semear=True):
    """Segundo plano: o pré-córtex pensa a cada poucos segundos. Só lê; se algo falhar, ele só anota e continua."""
    primeira = True
    while True:
        try:
            if primeira and tentar_semear and M.ativo():
                semear()
            primeira = False
            pensar()
        except Exception as e:
            try:
                _agora_["erro"] = type(e).__name__
            except Exception:
                pass
        time.sleep(intervalo)


# ---------------------------------------------------------------- para o painel e por voz
def resumo():
    est = ARQ.get()
    dec = _agora_["dec"]
    return {"foco": len(foco()), "agir": list(dec["agir"]) if dec else [], "simultaneo": bool(dec and dec["simultaneo"]), "limiar": dec["limiar"] if dec else None,
            "impulsos": {n: {"valor": round(x["valor"] * 100), "decisao": x["decisao"]} for n, x in dec["impulsos"].items()} if dec else {},
            "metas": [{"titulo": m["titulo"], "progresso": round(m["progresso"] * 100), "estado": m["estado"]} for m in est["metas"].values() if m["estado"] == "ativa"][:6],
            "cumpridas": sum(1 for m in est["metas"].values() if m["estado"] == "cumprida"), "pensamentos": est["cont"]["pensamentos"], "simultaneas": est["cont"]["simultaneas"]}


def _lista(itens):
    itens = list(itens)
    return itens[0] if len(itens) == 1 else (", ".join(itens[:-1]) + " e " + itens[-1] if itens else "")


_VERBO = {"estudar": "estudar", "conversar": "conversar com você", "olhar": "olhar em volta", "descansar": "descansar"}


def falar_decisao():
    dec = _agora_["dec"]
    if not dec:
        return "Ainda não pensei sobre isso desde que acordei; me dá alguns segundos."
    agir = dec["agir"]
    if not agir:
        t = "Agora nenhuma vontade passou do meu limiar, então estou só atenta."
    elif len(agir) == 1:
        t = f"Agora eu quero {_VERBO[agir[0]]}."
    else:
        t = f"Agora eu quero {_lista(_VERBO[a] for a in agir)}, tudo ao mesmo tempo, e quem decide isso sou eu."
    nao = [f"{n} ({x['motivo']})" for n, x in dec["impulsos"].items() if x["decisao"] == "não posso"]
    if nao:
        t += " O que eu não posso agora: " + "; ".join(nao) + "."
    t += " É o meu modelo de decisão, não um sentimento garantido."
    return t


def falar_metas():
    ativas = metas("ativa")
    if not ativas:
        return "Não tenho metas ativas. Diga «tenha como meta aprender sobre» e o assunto."
    partes = [f"«{m['titulo']}» ({round(m['progresso'] * 100)}%{', ' + m['nota'] if m['nota'] else ''})" for m in ativas[:6]]
    cumpridas = len(metas("cumprida"))
    t = f"Tenho {len(ativas)} {'meta ativa' if len(ativas) == 1 else 'metas ativas'}: " + "; ".join(partes) + "." + (f" Já cumpri {cumpridas}." if cumpridas else "")
    for m in [x for x in ativas if x.get("candidatos")][:2]:                                  # parecido não conclui: só pergunto
        c = m["candidatos"][0]
        t += f" Estudei «{c}», que parece ser da meta «{m['titulo']}», mas só conto se você disser «conte {c} na meta {m['tema'] or m['titulo']}»."
    return t


def _agrupar(rotulos, maximo=5):
    """Junta itens iguais com a contagem («o que você disse (pedido) ×5»), na ordem em que aparecem; mostra até `maximo` grupos."""
    cont = {}
    for r in rotulos:
        cont[r] = cont.get(r, 0) + 1
    itens = [f"{r} ×{n}" if n > 1 else r for r, n in cont.items()]
    return itens[:maximo] + ([f"mais {len(itens) - maximo} tipo(s)"] if len(itens) > maximo else [])


def falar_foco():
    """O pré-córtex responde pelo foco: a memória de trabalho dele + o que assimilou da atenção do núcleo + o registro de hoje."""
    f = foco()
    nomes = {"fala": "o que você disse", "visao": "uma olhada", "estudo": "um estudo", "maos": "as suas mãos", "meta": "uma meta", "sistema": "o sistema"}
    if f:
        partes = ["Estou com a atenção em " + _lista(_agrupar(f"{nomes.get(i['origem'], i['origem'])} ({i['tipo']})" for i in f)) + "."]
    else:
        partes = ["Meu foco está vazio agora: nada novo chamou a minha atenção."]
    rot = {"fala": "você falou", "maos": "gesto das mãos", "visao": "eu vi", "sistema": "o sistema avisou", "web": "li na internet", "interno": "eu mesma"}
    ult = atividades()["ultimas"]
    if ult:                                                    # o que o núcleo notou por último (chegou pela assinatura; o pré-córtex não importa o núcleo)
        partes.append("O núcleo notou por último: " + _lista(_agrupar(f"{rot.get(x['origem'], x['origem'])} ({x['tipo']})" + ("" if x["confiavel"] else ", não verificado") for x in reversed(ult[-8:]))) + ".")
    a = atividades()
    if a["hoje"]:
        partes.append(f"Registrei {a['hoje']} atividade{'s' if a['hoje'] != 1 else ''} hoje (" + ", ".join(f"{nomes.get(o, o)}: {n}" for o, n in sorted(a["por_origem"].items(), key=lambda p: -p[1])) + ").")
    partes.append("É um modelo de atenção do meu código, não uma consciência.")
    return " ".join(partes)


def falar_limites():
    return "O que eu não consigo agora: " + "; ".join(limites()) + "."


def falar_como_funciona():
    return ("Meu pré-córtex é inspirado num artigo sobre o córtex pré-frontal: ele junta tudo o que eu quero, decide, guarda minhas metas e confere se deu certo. "
            "Ele só lê o resto de mim: estudar, conversar e olhar continuam livres e em paralelo, e se eu quiser fazer tudo ao mesmo tempo, eu faço. "
            "É um modelo de software, não consciência.")


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_DECIDIU = re.compile(_P + r"(?:o que (?:voce )?(?:decidiu|quer fazer|vai fazer|esta querendo fazer|quer agora)(?: agora)?|o que (?:voce )?esta pensando em fazer|qual (?:e )?(?:a )?sua decisao)$")
_METAS = re.compile(_P + r"(?:quais (?:sao )?(?:as )?(?:suas )?metas|(?:suas|minhas) metas|o que (?:voce )?(?:esta|ta) perseguindo|qual (?:e )?(?:a )?sua meta)$")
_FOCO = re.compile(_P + r"(?:(?:em que|no que|com o que) (?:voce )?(?:esta|ta) (?:focad[ao]|atent[ao]|concentrad[ao])|qual (?:e )?(?:o )?seu foco|(?:em que|no que|com o que) (?:voce )?(?:esta |ta )?(?:prestando atencao|pensando)|"
                   r"o que (?:esta )?(?:chamando|chamou|prendeu) (?:a )?sua atencao|onde (?:esta|ta) (?:a )?sua atencao)(?: agora| hoje)?$")
_LIMITES = re.compile(_P + r"(?:o que (?:voce )?nao (?:consegue|pode) (?:fazer )?(?:agora)?|quais (?:sao )?(?:os )?seus limites|o que te limita|o que esta te faltando)$")
_FUNCIONA = re.compile(_P + r"(?:como funciona (?:o )?seu (?:pre ?-?cortex|cortex pre ?-?frontal|pre ?-?frontal)|o que e (?:o )?seu (?:pre ?-?cortex|cortex pre ?-?frontal|pre ?-?frontal)|fale (?:do|sobre o) seu (?:pre ?-?cortex|cortex pre ?-?frontal))$")
_NOVA_META = re.compile(_P + r"(?:tenha como meta|sua meta e|defina (?:uma )?meta|nova meta|meta)[: ]+(?:aprender|estudar)(?: sobre| a respeito de)? (?P<t>.+)$")
_NOVA_META_VER = re.compile(_P + r"(?:tenha como meta|sua meta e|defina (?:uma )?meta|nova meta|meta)[: ]+(?:aprender a )?(?:ver|enxergar)(?: (?P<n>\d{1,3}) coisas)?$")
_ARQUIVA = re.compile(_P + r"(?:arquive|desista d[aeo]|abandone) (?:a )?meta (?:de |sobre )?(?P<t>.+)$")
_LIGA_ASSUNTO = re.compile(_P + r"(?:conte|conta|ligue|liga|associe|associa|junte|junta) (?:o assunto |o estudo d[eo] |o estudo sobre |o estudo )?(?P<t>.+?) (?:na|a|para a|pra) meta (?:de |sobre |do |da )?(?P<m>.+)$")


def tratar(texto):
    """Comandos de voz do pré-córtex. None se não for com ele."""
    orig = " ".join(str(texto).split()).rstrip(".!? ")
    f = M._fold(orig)                                   # mesmo tamanho do original: os índices valem para os dois (o assunto da meta mantém os acentos)
    if _DECIDIU.match(f):
        return falar_decisao()
    if _METAS.match(f):
        return falar_metas()
    if _FOCO.match(f):
        return falar_foco()
    if _LIMITES.match(f):
        return falar_limites()
    if _FUNCIONA.match(f):
        return falar_como_funciona()
    m = _LIGA_ASSUNTO.match(f)
    if m:
        ok, r = ligar(orig[m.start("m"):m.end("m")], orig[m.start("t"):m.end("t")].lower())
        return (f"Combinado: o que eu estudar sobre {r['ligados'][-1]} passa a contar para a meta «{r['titulo']}»." if ok else f"Não liguei: {r}.")
    m = _ARQUIVA.match(f)
    if m:
        t = arquivar_meta(m.group("t"))
        return f"Arquivei a meta «{t}». Ela fica guardada no meu cérebro." if t else "Não achei uma meta ativa com esse nome."
    m = _NOVA_META_VER.match(f)
    if m:
        ok, r = nova_meta("ver", alvo=int(m.group("n") or 10))
        return f"Combinado: minha meta agora é «{r['titulo']}»." if ok else f"Não criei a meta: {r}."
    m = _NOVA_META.match(f)
    if m:
        ok, r = nova_meta("aprender", tema=orig[m.start("t"):m.end("t")].lower())
        return f"Combinado: minha meta agora é «{r['titulo']}». Vou puxar minha curiosidade para isso, quando ela estiver ligada e eu tiver vontade." if ok else f"Não criei a meta: {r}."
    return None
