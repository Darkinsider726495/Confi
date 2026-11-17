"""Experiências (Fase 3): o que aconteceu quando ela tentou, comparado com o que esperava — para escolher melhor da próxima vez.

Não é treino de modelo e não é recompensa/punição: nenhum número «de prêmio» é somado, nenhum peso de IA muda. É memória episódica estruturada + contagem honesta.
Cada tarefa que termina (`tarefas.GANCHOS_FIM`) vira um registro em `.cerebro/experiencias.jsonl` (só acrescenta; nada é apagado) com:
  objetivo e contexto · hipótese · estratégia · ações · esperado · observado · evidências · diferença · causas com confiança · o que foi aprendido ·
  o que continua desconhecido · alternativas · condições em que vale reutilizar.

Como o registro é montado, para não se enganar:
  • O que ela ESPERAVA (hipótese e resultado esperado) é gravado ANTES de agir (`intencao`). Escrever a expectativa depois de ver o resultado seria enfeitar.
    Tarefas que ninguém planejou (a IA chamando uma ferramenta) ganham uma hipótese «implícita», e o registro diz isso.
  • Cada afirmação é de um tipo: FATO (observado: estado do passo, veredito da conferência, código do corretor), INFERÊNCIA (conclusão com confiança),
    HIPÓTESE (palpite a testar) ou DESCONHECIDO (o que não dá para saber daqui). As confianças são estimativas por regra, não probabilidades calibradas.
  • Uma tentativa nunca vira regra universal: o que se aprende vale para uma estratégia, em certas CONDIÇÕES (`ambiente()`), com `n` observações.
    `sinais()` conta só o que é compatível com as condições de agora; uma falha com o cofre desligado não pesa quando o cofre está ligado.
  • Nada aqui concede permissão. Experiência só ajuda a ORDENAR estratégias que o catálogo do planejador já permite; quem decide e executa continua sendo o corretor.

Privacidade: os registros usam o que `tarefas.py` já redigiu (objetivo, descrições, resumos de argumentos). O conteúdo pedido, a resposta da ferramenta e a trilha de auditoria não entram.
"""
import copy, json, os, re, threading, time
import broker as B
import memoria as M
import tarefas as T
import verificacao as V

FATO, INFERENCIA, HIPOTESE, DESCONHECIDO = "fato", "inferencia", "hipotese", "desconhecido"
TIPOS = (FATO, INFERENCIA, HIPOTESE, DESCONHECIDO)
SUCESSO, FALHA, SEM_CONFERENCIA, INTERROMPIDA, CANCELADA = "sucesso", "falha", "sem_conferencia", "interrompida", "cancelada"
RESULTADOS = (SUCESSO, FALHA, SEM_CONFERENCIA, INTERROMPIDA, CANCELADA)
TIPOS_FALHA = ("falso_sucesso", "erro", "recusa")
_ID = re.compile(r"x\d{4,7}")
_ID_TAREFA = re.compile(r"t\d{4,6}")
_ESTRAT = re.compile(r"[a-z_][a-z0-9_]{0,40}(\+[a-z_][a-z0-9_]{0,40}){0,11}")
_TIPO_OBJ = re.compile(r"[a-z_][a-z0-9_]{0,40}")

_trava = threading.RLock()
_agora = time.time
_MEM = []                    # com o cofre desligado as experiências vivem só no processo
_CACHE = {"chave": None, "itens": [], "descartadas": 0}
_ERROS = {"n": 0, "ultimo": ""}


# ---------------------------------------------------------------- ambiente (as condições em que algo foi tentado)
def ambiente():
    """Condições observáveis agora que mudam o que funciona. Só coisas que dá para olhar de verdade, não impressões."""
    return {"cofre_ativo": bool(M.ativo()), "manutencao": os.path.exists(os.path.join(B.BASE, "MANUTENCAO"))}


def _condicoes_ok(c):
    if not isinstance(c, dict):
        return {}
    return {k: v for k, v in list(c.items())[:12] if isinstance(k, str) and re.fullmatch(r"[a-z_][a-z0-9_]{0,30}", k) and isinstance(v, (bool, int, str)) and (not isinstance(v, str) or len(v) <= 40)}


def compativel(registrada, atuais):
    """As condições registradas não contradizem as de agora? (só compara as chaves que as duas têm)"""
    return all(atuais[k] == v for k, v in (registrada or {}).items() if k in (atuais or {}))


# ---------------------------------------------------------------- arquivo (só acrescenta)
def _arquivo():
    return M._dentro(M.base() / ".cerebro" / "experiencias.jsonl")


def _s(v, n):
    return " ".join(v.split())[:n] if isinstance(v, str) else ""


def _num(v, a=0.0, b=1.0, padrao=0.0):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and a <= v <= b else padrao


def _decl(lista, n=8):
    """Lista de afirmações {texto, tipo, confianca, ...}; descarta o que não tem tipo válido (um fato sem tipo não entra)."""
    saida = []
    for x in (lista if isinstance(lista, list) else [])[:n]:
        if isinstance(x, dict) and x.get("tipo") in TIPOS and _s(x.get("texto"), 300):
            item = {"texto": _s(x["texto"], 300), "tipo": x["tipo"], "confianca": _num(x.get("confianca"))}
            if isinstance(x.get("base"), list):
                item["base"] = [_s(b, 80) for b in x["base"][:5] if isinstance(b, str)]
            if isinstance(x.get("n"), int) and not isinstance(x.get("n"), bool) and 0 <= x["n"] <= 10**6:
                item["n"] = x["n"]
            saida.append(item)
    return saida


def _limpar_experiencia(x):
    if not isinstance(x, dict) or not isinstance(x.get("id"), str) or not _ID.fullmatch(x["id"]):
        return None
    if not isinstance(x.get("tarefa"), str) or not _ID_TAREFA.fullmatch(x["tarefa"]) or x.get("resultado") not in RESULTADOS:
        return None
    est = x.get("estrategia") if isinstance(x.get("estrategia"), dict) else {}
    if not isinstance(est.get("id"), str) or not _ESTRAT.fullmatch(est["id"]):
        return None
    obj = x.get("objetivo") if isinstance(x.get("objetivo"), dict) else {}
    hip = x.get("hipotese") if isinstance(x.get("hipotese"), dict) else {}
    reuso = x.get("reuso") if isinstance(x.get("reuso"), dict) else {}
    acoes = []
    for a in (x.get("acoes") if isinstance(x.get("acoes"), list) else [])[:12]:
        if isinstance(a, dict) and isinstance(a.get("ferramenta"), str):
            acoes.append({"passo": _s(a.get("passo"), 8), "descricao": _s(a.get("descricao"), 120), "ferramenta": _s(a["ferramenta"], 41), "nivel": a["nivel"] if isinstance(a.get("nivel"), int) and not isinstance(a.get("nivel"), bool) else None,
                          "estado": _s(a.get("estado"), 20), "args_resumo": _s(a.get("args_resumo"), 300)})
    evid = []
    for e in (x.get("evidencias") if isinstance(x.get("evidencias"), list) else [])[:12]:
        if isinstance(e, dict):
            evid.append({"passo": _s(e.get("passo"), 8), "veredito": e.get("veredito") if e.get("veredito") in V.VEREDITOS else V.INCONCLUSIVO,
                         "forca": _s(e.get("forca"), 20), "texto": _s(e.get("texto"), 220)})
    tipo = obj.get("tipo") if isinstance(obj.get("tipo"), str) and _TIPO_OBJ.fullmatch(obj["tipo"]) else None
    return {"k": "experiencia", "id": x["id"], "em": _num(x.get("em"), 0, 1e12), "tarefa": x["tarefa"], "plano_v": x["plano_v"] if isinstance(x.get("plano_v"), int) and not isinstance(x.get("plano_v"), bool) and 0 <= x["plano_v"] < 10**4 else 0,
            "substitui": x["substitui"] if isinstance(x.get("substitui"), str) and _ID.fullmatch(x["substitui"]) else None,
            "fonte": x.get("fonte") if x.get("fonte") in ("planejador", "tarefa", "precortex") else "tarefa",
            "objetivo": {"texto": _s(obj.get("texto"), 300), "tipo": tipo, "origem": _s(obj.get("origem"), 12), "meta": _s(obj.get("meta"), 8) or None},
            "condicoes": _condicoes_ok(x.get("condicoes")),
            "hipotese": {"texto": _s(hip.get("texto"), 300), "origem": hip.get("origem") if hip.get("origem") in ("planejador", "implicita", "precortex") else "implicita"},
            "estrategia": {"id": est["id"], "descricao": _s(est.get("descricao"), 160)},
            "acoes": acoes, "esperado": _s(x.get("esperado"), 300), "observado": _s(x.get("observado"), 300), "evidencias": evid,
            "resultado": x["resultado"], "tipo_falha": x.get("tipo_falha") if x.get("tipo_falha") in TIPOS_FALHA else None,
            "prova": _s(x.get("prova"), 20), "diferenca": _s(x.get("diferenca"), 300) or None,
            "causas": _decl(x.get("causas")), "aprendido": _decl(x.get("aprendido")),
            "desconhecido": [_s(d, 200) for d in (x.get("desconhecido") if isinstance(x.get("desconhecido"), list) else [])[:6] if isinstance(d, str)],
            "alternativas": [_s(a, 80) for a in (x.get("alternativas") if isinstance(x.get("alternativas"), list) else [])[:8] if isinstance(a, str)],
            "escolha": x["escolha"] if isinstance(x.get("escolha"), dict) and len(json.dumps(x["escolha"])) < 6000 else None,
            "reuso": {"quando": _s(reuso.get("quando"), 300), "nao_quando": _s(reuso.get("nao_quando"), 300), "validade": _s(reuso.get("validade"), 200)}}


def _limpar_intencao(x):
    if not isinstance(x, dict) or not isinstance(x.get("tarefa"), str) or not _ID_TAREFA.fullmatch(x["tarefa"]):
        return None
    est = x.get("estrategia") if isinstance(x.get("estrategia"), str) and _ESTRAT.fullmatch(x["estrategia"]) else None
    if not est:
        return None
    return {"k": "intencao", "em": _num(x.get("em"), 0, 1e12), "tarefa": x["tarefa"], "plano_v": x["plano_v"] if isinstance(x.get("plano_v"), int) and not isinstance(x.get("plano_v"), bool) and 0 <= x["plano_v"] < 10**4 else 0,
            "origem": x.get("origem") if x.get("origem") in ("planejador", "precortex") else "planejador",
            "tipo": x.get("tipo") if isinstance(x.get("tipo"), str) and _TIPO_OBJ.fullmatch(x["tipo"]) else None, "estrategia": est,
            "descricao": _s(x.get("descricao"), 160), "hipotese": _s(x.get("hipotese"), 300), "esperado": _s(x.get("esperado"), 300),
            "alternativas": [_s(a, 80) for a in (x.get("alternativas") if isinstance(x.get("alternativas"), list) else [])[:8] if isinstance(a, str)],
            "condicoes": _condicoes_ok(x.get("condicoes")), "escolha": x["escolha"] if isinstance(x.get("escolha"), dict) and len(json.dumps(x["escolha"])) < 6000 else None}


# ---------------------------------------------------------------- registros cognitivos (Fase 7, pré-córtex)
# Uma experiência de TAREFA (acima) diz o que um passo fez. Um registro COGNITIVO diz o que um OBJETIVO inteiro conseguiu: previsão × observação conferida por fora,
# fatores possíveis, lições provisórias e o que investigar. Mesmo arquivo, mesma regra (só acrescenta, nada se apaga): um registro errado é REVOGADO por outro registro.
RESULTADOS_COG = ("sucesso", "parcial", "falha", "inconclusivo")
PARAMETROS_AUTORIZADOS = ("ordem_de_estrategias",)      # a ÚNICA coisa que o aprendizado do pré-córtex pode propor ajustar; limites de segurança não estão (nem podem estar) aqui
_ID_COG = re.compile(r"c\d{4,7}")
_ID_OBJ = re.compile(r"pc\d{4,6}")
_ID_PLANO = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,40}")


def _limpar_cognitiva(x):
    if not isinstance(x, dict) or not isinstance(x.get("id"), str) or not _ID_COG.fullmatch(x["id"]) or x.get("resultado") not in RESULTADOS_COG:
        return None
    if not isinstance(x.get("objetivo"), str) or not _ID_OBJ.fullmatch(x["objetivo"]):
        return None
    if not isinstance(x.get("estrategia"), str) or not _ESTRAT.fullmatch(x["estrategia"]) or not isinstance(x.get("tipo_objetivo"), str) or not _TIPO_OBJ.fullmatch(x["tipo_objetivo"]):
        return None
    pl = x.get("plano") if isinstance(x.get("plano"), dict) else {}
    ajuste = x.get("proposta_de_ajuste")
    if ajuste is not None:
        if not isinstance(ajuste, dict) or ajuste.get("parametro") not in PARAMETROS_AUTORIZADOS:
            return None                                              # ajuste fora dos parâmetros autorizados: o registro inteiro é recusado, não «consertado»
        ajuste = {"parametro": ajuste["parametro"], "escopo": _s(ajuste.get("escopo"), 120), "efeito": _s(ajuste.get("efeito"), 240), "reversivel": True}
    prev = x.get("previsao") if isinstance(x.get("previsao"), dict) else {}
    obs = x.get("observado") if isinstance(x.get("observado"), dict) else {}

    def crit(lista, campos):
        saida = []
        for c in (lista if isinstance(lista, list) else [])[:12]:
            if isinstance(c, dict):
                item = {k: _s(c.get(k), 160) for k in campos}
                if "ok" in c:
                    item["ok"] = c["ok"] if isinstance(c["ok"], bool) else None
                saida.append(item)
        return saida
    licoes = _decl(x.get("licoes"))
    for item, bruto in zip(licoes, [l for l in (x.get("licoes") if isinstance(x.get("licoes"), list) else [])[:8] if isinstance(l, dict) and l.get("tipo") in TIPOS and _s(l.get("texto"), 300)]):
        item["revisavel_se"] = _s(bruto.get("revisavel_se"), 200)
    return {"k": "cognitiva", "id": x["id"], "em": _num(x.get("em"), 0, 1e12), "objetivo": x["objetivo"], "tentativa": x["tentativa"] if isinstance(x.get("tentativa"), int) and not isinstance(x.get("tentativa"), bool) and 1 <= x["tentativa"] < 100 else 1,
            "plano": {"id": pl.get("id") if isinstance(pl.get("id"), str) and _ID_PLANO.fullmatch(pl["id"]) else "", "versao": pl["versao"] if isinstance(pl.get("versao"), int) and not isinstance(pl.get("versao"), bool) and 0 <= pl["versao"] < 10**4 else 0,
                      "hash": _s(pl.get("hash"), 40)},
            "tipo_objetivo": x["tipo_objetivo"], "estrategia": x["estrategia"], "condicoes": _condicoes_ok(x.get("condicoes")),
            "tarefa": x["tarefa"] if isinstance(x.get("tarefa"), str) and _ID_TAREFA.fullmatch(x["tarefa"]) else None,
            "experiencia_tarefa": x["experiencia_tarefa"] if isinstance(x.get("experiencia_tarefa"), str) and _ID.fullmatch(x["experiencia_tarefa"]) else None,
            "hipotese": {"id": _s((x.get("hipotese") or {}).get("id") if isinstance(x.get("hipotese"), dict) else "", 20), "texto": _s((x.get("hipotese") or {}).get("texto") if isinstance(x.get("hipotese"), dict) else "", 300)},
            "previsao": {"texto": _s(prev.get("texto"), 300), "criterios": crit(prev.get("criterios"), ("id", "descricao"))},
            "observado": {"resumo": _s(obs.get("resumo"), 300), "criterios": crit(obs.get("criterios"), ("id", "esperado", "observado"))},
            "resultado": x["resultado"], "discrepancias": [_s(d, 300) for d in (x.get("discrepancias") if isinstance(x.get("discrepancias"), list) else [])[:6] if isinstance(d, str)],
            "fatores": _decl(x.get("fatores")), "licoes": licoes,
            "investigar": [_s(d, 200) for d in (x.get("investigar") if isinstance(x.get("investigar"), list) else [])[:5] if isinstance(d, str)],
            "proposta_de_ajuste": ajuste, "origem": "precortex"}


def _limpar_revogacao(x):
    if not isinstance(x, dict) or not isinstance(x.get("revoga"), str) or not _ID_COG.fullmatch(x["revoga"]):
        return None
    return {"k": "cognitiva_revogada", "revoga": x["revoga"], "em": _num(x.get("em"), 0, 1e12), "motivo": _s(x.get("motivo"), 300), "por": x.get("por") if x.get("por") in ("dono", "sistema") else "sistema"}


def _limpar_mae(x):
    """Registro do laboratório de engenharia; não é uma tarefa nem uma recompensa."""
    if not isinstance(x, dict) or x.get("k") != "mae_engenharia":
        return None
    rid = x.get("id")
    if not isinstance(rid, str) or not re.fullmatch(r"mae\d{12,20}", rid):
        return None
    resultado = x.get("resultado") if x.get("resultado") in ("sucesso", "falha", "inconclusivo") else None
    if not resultado:
        return None
    return {"k": "mae_engenharia", "id": rid, "em": _num(x.get("em"), 0, 1e12),
            "objetivo": _s(x.get("objetivo"), 300), "resultado": resultado,
            "tentativas": x.get("tentativas") if isinstance(x.get("tentativas"), int) and not isinstance(x.get("tentativas"), bool) and 0 <= x["tentativas"] <= 1000 else 0,
            "observado": _s(x.get("observado"), 300), "licao": _s(x.get("licao"), 300),
            "alvos": [_s(a, 80) for a in (x.get("alvos") if isinstance(x.get("alvos"), list) else [])[:10] if isinstance(a, str)],
            "origem": "mae_laboratorio"}


def _ler():
    """Todas as linhas válidas, em ordem. Relê só quando o arquivo muda; linha estragada é contada em `descartadas`, não escondida."""
    with _trava:
        if not M.ativo():
            return _MEM
        try:
            arq = _arquivo()
            st = arq.stat()
        except OSError:
            _CACHE.update(chave=None, itens=[], descartadas=0)
            return _CACHE["itens"]
        chave = (str(arq), st.st_size, st.st_mtime_ns)
        if _CACHE["chave"] == chave:
            return _CACHE["itens"]
        itens, ruins = [], 0
        try:
            with open(arq, encoding="utf-8") as f:
                for linha in f:
                    if not linha.strip():
                        continue
                    try:
                        x = json.loads(linha)
                        k = x.get("k") if isinstance(x, dict) else None
                        r = (_limpar_experiencia(x) if k == "experiencia" else _limpar_intencao(x) if k == "intencao"
                             else _limpar_cognitiva(x) if k == "cognitiva" else _limpar_revogacao(x) if k == "cognitiva_revogada"
                             else _limpar_mae(x) if k == "mae_engenharia" else None)
                    except ValueError:
                        r = None
                    if r:
                        itens.append(r)
                    else:
                        ruins += 1
        except OSError:
            pass
        _CACHE.update(chave=chave, itens=itens, descartadas=ruins)
        return itens


def _acrescentar(reg):
    with _trava:
        if not M.ativo():
            _MEM.append(reg)
            return True
        try:
            arq = _arquivo()
            arq.parent.mkdir(parents=True, exist_ok=True)
            with open(arq, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            return True
        except (OSError, ValueError):
            return False


def reiniciar():
    """Esquece o cache (o próximo uso relê o arquivo) e a memória do processo. Usado em testes."""
    with _trava:
        _CACHE.update(chave=None, itens=[], descartadas=0)
        _MEM.clear()
        _ERROS.update(n=0, ultimo="")


def _experiencias():
    return [x for x in _ler() if x["k"] == "experiencia"]


def _ultimas():
    """A versão mais recente de cada (tarefa, plano): se a mesma tentativa foi registrada de novo (ex.: o dono confirmou o que não dava para conferir), vale a última."""
    por = {}
    for x in _experiencias():
        por[(x["tarefa"], x["plano_v"])] = x
    return list(por.values())


def registrar_mae(registro):
    """Acrescenta a observação do MAE à memória episódica, se o cofre estiver ativo.

    O registro não altera permissões, não vira regra universal e nunca autoriza
    promoção de código por si só. Com o cofre desligado, segue a política local:
    fica apenas em memória durante o processo.
    """
    if not isinstance(registro, dict):
        raise ValueError("registro do MAE inválido")
    alvos = registro.get("arquivos_modificados", [])
    if not isinstance(alvos, list):
        alvos = []
    dado = _limpar_mae({
        "k": "mae_engenharia", "id": "mae" + str(time.time_ns()), "em": _agora(),
        "objetivo": registro.get("objetivo", ""), "resultado": registro.get("resultado", "inconclusivo"),
        "tentativas": registro.get("tentativas", 0), "observado": registro.get("observado", registro.get("observado", "")),
        "licao": "Experiência de laboratório não promove código; candidato real exige staging, testes e rollback.",
        "alvos": [str(x) for x in alvos[:10]],
    })
    if not dado:
        raise ValueError("registro do MAE não passou na validação")
    # Não reutiliza _acrescentar(): ele compartilha o lock de experiências de tarefas
    # e o MAE não deve travar se uma rotina cognitiva estiver finalizando em paralelo.
    if not M.ativo():
        _MEM.append(dado)
        return True
    try:
        arq = _arquivo()
        arq.parent.mkdir(parents=True, exist_ok=True)
        linha = (json.dumps(dado, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        fd = os.open(str(arq), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            os.write(fd, linha)
            os.fsync(fd)
        finally:
            os.close(fd)
        # O cache usa tamanho/mtime e será atualizado na próxima leitura.
        return True
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------- antes de agir
def intencao(tarefa, plano_v, *, tipo, estrategia, descricao, hipotese, esperado, alternativas=(), condicoes=None, escolha=None, origem="planejador"):
    """Grava, ANTES de executar, o que se espera: hipótese, resultado esperado, alternativas e por que esta estratégia foi escolhida. Devolve True se gravou.
    `origem` diz quem formulou a expectativa: o planejador de objetivos simples ou o pré-córtex (Fase 7)."""
    reg = _limpar_intencao({"k": "intencao", "em": _agora(), "tarefa": tarefa, "plano_v": plano_v, "tipo": tipo, "estrategia": estrategia, "descricao": descricao, "origem": origem,
                            "hipotese": hipotese, "esperado": esperado, "alternativas": list(alternativas), "condicoes": ambiente() if condicoes is None else condicoes, "escolha": escolha})
    if not reg:
        raise ValueError("intenção inválida")
    return _acrescentar(reg)


def _intencao_de(tarefa, plano_v):
    achada = None
    for x in _ler():
        if x["k"] == "intencao" and x["tarefa"] == tarefa and x["plano_v"] == plano_v:
            achada = x
    return achada


# ---------------------------------------------------------------- depois de agir
def estrategia_id(passos):
    """A estratégia é o caminho de ferramentas: «anotar+criar_lembrete». Os mesmos nomes valem para o planejador e para as tarefas que ninguém planejou."""
    nomes = [p["ferramenta"] for p in passos]
    return "+".join(nomes) if nomes else "sem_passos"


def _classificar(t):
    """(resultado, tipo_falha, prova) a partir do estado da tarefa e dos passos."""
    passos = t["passos"]
    forcas = [p["verificacao"]["forca"] for p in passos if p.get("verificacao")]
    ordem = {V.INDEPENDENTE: 0, "dono": 1, V.DA_RESPOSTA: 2, V.NENHUMA: 3}
    prova = max(forcas, key=lambda f: ordem.get(f, 3)) if forcas else V.NENHUMA
    e = t["estado"]
    if e == T.CONCLUIDA:
        return SUCESSO, None, prova
    if e == T.CANCELADA:
        return CANCELADA, None, prova
    if e == T.EXECUTADA_SEM_VERIFICACAO:
        return SEM_CONFERENCIA, None, prova
    if e == T.FALHOU:
        if any(p["estado"] == "refutado" for p in passos):
            return FALHA, "falso_sucesso", prova
        falho = next((p for p in passos if p["estado"] == "falhou"), None)
        if falho and (falho.get("codigo") or "").startswith("Erro"):
            return FALHA, "erro", prova
        return FALHA, "recusa", prova
    return INTERROMPIDA, None, prova


def _texto_condicoes(c):
    return ", ".join(f"{k}={'sim' if v is True else 'não' if v is False else v}" for k, v in sorted(c.items())) or "sem condições registradas"


def _montar(t, intencao_reg):
    resultado, tipo_falha, prova = _classificar(t)
    passos = t["passos"]
    estrat = intencao_reg["estrategia"] if intencao_reg else estrategia_id(passos)
    condicoes = intencao_reg["condicoes"] if intencao_reg else ambiente()
    desc = (intencao_reg or {}).get("descricao") or " → ".join(p["descricao"] for p in passos)[:160]
    acoes = [{"passo": p["id"], "descricao": p["descricao"], "ferramenta": p["ferramenta"], "nivel": p["nivel"], "estado": p["estado"], "args_resumo": p["args_resumo"]} for p in passos]
    evid = [{"passo": p["id"], "veredito": p["verificacao"]["veredito"], "forca": p["verificacao"]["forca"], "texto": p["verificacao"]["evidencia"]} for p in passos if p.get("verificacao")]
    origem_int = (intencao_reg or {}).get("origem", "planejador")
    if intencao_reg:
        hip, hip_o, esperado = intencao_reg["hipotese"], origem_int, intencao_reg["esperado"]
    else:
        hip = f"a estratégia «{estrat}» atinge o objetivo"
        hip_o = "implicita"
        esperado = "cada passo produz o efeito que a conferência sabe procurar: " + "; ".join(p["descricao"] for p in passos)
    estados = ", ".join(f"{p['id']} {p['estado']}" for p in passos) or "sem passos"
    base = [f"{p['id']}:{p['estado']}" for p in passos][:5]
    causas, aprendido, desconhecido = [], [], []
    ctx_txt = _texto_condicoes(condicoes)
    if resultado == SUCESSO:
        observado = f"todos os passos conferidos ({estados})"
        diferenca = None
        if prova == "dono":
            observado += "; parte da conferência foi a sua palavra"
            desconhecido.append("se o efeito existe de fato: só o dono confirmou")
        aprendido += [{"texto": f"«{estrat}» produziu o efeito esperado nesta tentativa (condições: {ctx_txt})", "tipo": FATO, "confianca": 1.0, "n": 1},
                      {"texto": "pode funcionar de novo em condições parecidas; uma observação só indica, não garante", "tipo": HIPOTESE, "confianca": 0.4, "n": 1}]
    elif resultado == FALHA:
        observado = f"{t['causa'] or 'a tarefa falhou'} ({estados})"
        diferenca = "esperava o efeito conferido; a conferência não o encontrou" if tipo_falha == "falso_sucesso" else "esperava o efeito; a ferramenta devolveu erro" if tipo_falha == "erro" else "esperava executar; o corretor recusou o pedido"
        if tipo_falha == "falso_sucesso":
            causas = [{"texto": "a ferramenta respondeu que deu certo e a conferência olhou o estado real e não achou o efeito", "tipo": FATO, "confianca": 1.0, "base": base},
                      {"texto": "a ferramenta não produziu o efeito (ou o produziu em outro lugar)", "tipo": INFERENCIA, "confianca": 0.6 if prova == V.INDEPENDENTE else 0.3, "base": base},
                      {"texto": "o ambiente atual contribuiu (" + ctx_txt + ")", "tipo": HIPOTESE, "confianca": 0.2, "base": ["condicoes"]}]
            desconhecido.append("por que a ferramenta disse «feito» sem produzir o efeito")
        elif tipo_falha == "erro":
            falho = next((p for p in passos if p["estado"] == "falhou"), {})
            causas = [{"texto": f"o corretor registrou erro no passo {falho.get('id', '?')} ({falho.get('codigo') or 'erro'})", "tipo": FATO, "confianca": 1.0, "base": base},
                      {"texto": "a causa está na ferramenta ou no ambiente, não no pedido", "tipo": INFERENCIA, "confianca": 0.5, "base": base},
                      {"texto": "o ambiente atual contribuiu (" + ctx_txt + ")", "tipo": HIPOTESE, "confianca": 0.2, "base": ["condicoes"]}]
            desconhecido.append("o motivo exato do erro (a resposta da ferramenta não é guardada)")
        else:
            causas = [{"texto": "o corretor recusou o pedido (validação, nível ou manutenção)", "tipo": FATO, "confianca": 1.0, "base": base},
                      {"texto": "a política do momento impediu (" + ctx_txt + ")", "tipo": INFERENCIA, "confianca": 0.7, "base": ["condicoes"]}]
        aprendido += [{"texto": f"«{estrat}» NÃO produziu o efeito nesta tentativa (condições: {ctx_txt})", "tipo": FATO, "confianca": 1.0, "n": 1},
                      {"texto": "pode falhar de novo nas mesmas condições; uma observação só indica, não garante", "tipo": HIPOTESE, "confianca": 0.4, "n": 1}]
    elif resultado == SEM_CONFERENCIA:
        observado = f"a ação rodou, mas não dá para conferir daqui ({estados})"
        diferenca = "não há como comparar o esperado com o observado"
        desconhecido.append("se o efeito aconteceu: nenhuma conferência independente é possível para estes passos")
        aprendido.append({"texto": f"«{estrat}» foi executada sem conferência; isso não conta como sucesso nem como falha", "tipo": FATO, "confianca": 1.0, "n": 1})
    elif resultado == CANCELADA:
        observado = f"tarefa cancelada ({estados})"
        diferenca = None
        aprendido.append({"texto": "cancelamento do dono: não diz nada sobre a estratégia", "tipo": FATO, "confianca": 1.0, "n": 1})
    else:
        observado = f"a tarefa parou e precisa de você ({estados})"
        diferenca = "não se sabe o que de fato aconteceu"
        desconhecido.append("se a ação chegou a acontecer antes de a tarefa parar")
        aprendido.append({"texto": "tentativa interrompida: não conta como sucesso nem como falha", "tipo": FATO, "confianca": 1.0, "n": 1})
    return {"k": "experiencia", "tarefa": t["id"], "plano_v": t.get("plano_v", 0), "fonte": origem_int if intencao_reg else "tarefa",
            "objetivo": {"texto": t["objetivo"], "tipo": (intencao_reg or {}).get("tipo"), "origem": t["contexto"]["origem"], "meta": t["contexto"]["meta"]},
            "condicoes": condicoes, "hipotese": {"texto": hip, "origem": hip_o}, "estrategia": {"id": estrat, "descricao": desc},
            "acoes": acoes, "esperado": esperado, "observado": observado, "evidencias": evid, "resultado": resultado, "tipo_falha": tipo_falha, "prova": prova,
            "diferenca": diferenca, "causas": causas, "aprendido": aprendido, "desconhecido": desconhecido,
            "alternativas": list((intencao_reg or {}).get("alternativas") or []), "escolha": (intencao_reg or {}).get("escolha"),
            "reuso": {"quando": f"pedido {'do tipo «' + intencao_reg['tipo'] + '»' if intencao_reg and intencao_reg.get('tipo') else 'parecido'} com a estratégia «{estrat}» e condições iguais a: {ctx_txt}",
                      "nao_quando": "se as condições forem outras, esta experiência não vale; se o dono pedir algo diferente, também não",
                      "validade": "uma observação: é indício, não regra"}}


def registrar_tarefa(t):
    """Transforma uma tarefa terminada num registro. Devolve o registro gravado, ou None se não gravou."""
    with _trava:
        ja = [x for x in _experiencias() if x["tarefa"] == t["id"] and x["plano_v"] == t.get("plano_v", 0)]
        reg = _montar(t, _intencao_de(t["id"], t.get("plano_v", 0)))
        proximo = max([int(x["id"][1:]) for x in _experiencias()] or [0]) + 1
        reg.update(id=f"x{proximo:04d}", em=_agora(), substitui=ja[-1]["id"] if ja else None)
        limpo = _limpar_experiencia(reg)
        if not limpo or not _acrescentar(limpo):
            return None
        return copy.deepcopy(limpo)


def _ao_terminar(t):
    """Gancho de `tarefas`: nunca pode atrapalhar a tarefa. Falha aqui fica contada em `resumo()['erros']`, não escondida."""
    try:
        if registrar_tarefa(t) is None:
            raise OSError("não consegui gravar a experiência")
    except Exception as e:
        _ERROS["n"] += 1
        _ERROS["ultimo"] = f"{type(e).__name__}: {e}"[:200]


def _registrar_gancho():
    T.GANCHOS_FIM[:] = [g for g in T.GANCHOS_FIM if not getattr(g, "_friday_experiencias", False)]
    _ao_terminar._friday_experiencias = True
    T.GANCHOS_FIM.append(_ao_terminar)


_registrar_gancho()


# ---------------------------------------------------------------- consultar
def da_tarefa(tarefa, plano_v=None):
    """A experiência mais recente de uma tarefa (e plano), ou None."""
    achadas = [x for x in _experiencias() if x["tarefa"] == tarefa and (plano_v is None or x["plano_v"] == plano_v)]
    return copy.deepcopy(achadas[-1]) if achadas else None


def obter(xid):
    for x in _experiencias():
        if x["id"] == xid:
            return copy.deepcopy(x)
    return None


def sinais(estrategia, condicoes=None, ate=None):
    """O que já aconteceu com esta estratégia em condições compatíveis com `condicoes`. Conta só tentativas com desfecho conhecido:
    sucesso e falha (erro ou falso sucesso). Recusa do corretor, execução sem conferência, interrupção e cancelamento aparecem à parte e NÃO pesam.
    `p` = (sucessos+1)/(n+2) (suavizada: sem dados vale 0,5, uma falha só baixa para 0,33). `ate` limita a experiências feitas até aquele instante (para conferir uma escolha antiga)."""
    s = f = rec = sem = ign = 0
    ids, ultimo = [], None
    for x in _ultimas():
        if x["estrategia"]["id"] != estrategia or (ate is not None and x["em"] > ate) or (condicoes is not None and not compativel(x["condicoes"], condicoes)):
            continue
        r = x["resultado"]
        if r == SUCESSO:
            s += 1
        elif r == FALHA and x["tipo_falha"] in ("erro", "falso_sucesso"):
            f += 1
        elif r == FALHA:
            rec += 1
        elif r == SEM_CONFERENCIA:
            sem += 1
        else:
            ign += 1
        ids.append(x["id"])
        if ultimo is None or x["em"] >= ultimo["em"]:
            ultimo = {"id": x["id"], "resultado": r, "em": x["em"]}
    n = s + f
    return {"estrategia": estrategia, "n": n, "sucessos": s, "falhas": f, "recusas": rec, "sem_conferencia": sem, "ignoradas": ign, "ids": sorted(ids)[-20:],
            "p": round((s + 1) / (n + 2), 4), "confianca": round(n / (n + 2), 4), "ultimo": ultimo}


def padroes(minimo=2):
    """Estratégias que repetiram o mesmo desfecho nas MESMAS condições, com o que as sustenta. Não decide nada: é o que `objetivos.py` usa para propor ao dono que se anote uma observação.
    Só entram tentativas com desfecho conhecido (sucesso, erro ou falso sucesso). Devolve [{estrategia, condicoes, sucessos, falhas, experiencias, tarefas, origens}], as mais falhadas primeiro."""
    grupos = {}
    for x in _ultimas():
        if x["resultado"] == SUCESSO or (x["resultado"] == FALHA and x["tipo_falha"] in ("erro", "falso_sucesso")):
            g = grupos.setdefault((x["estrategia"]["id"], tuple(sorted(x["condicoes"].items()))),
                                  {"estrategia": x["estrategia"]["id"], "condicoes": dict(x["condicoes"]), "sucessos": 0, "falhas": 0, "experiencias": [], "tarefas": [], "origens": set()})
            g["sucessos" if x["resultado"] == SUCESSO else "falhas"] += 1
            g["experiencias"].append(x["id"])
            g["tarefas"].append(x["tarefa"])
            g["origens"].add(x["objetivo"]["origem"])
    saida = [g for g in grupos.values() if g["sucessos"] + g["falhas"] >= minimo]
    saida.sort(key=lambda g: (-g["falhas"], g["estrategia"]))
    return saida


def relevantes(estrategia, condicoes=None, limite=5):
    """As últimas experiências compatíveis com a estratégia e as condições, da mais nova para a mais velha."""
    achadas = [x for x in _ultimas() if x["estrategia"]["id"] == estrategia and (condicoes is None or compativel(x["condicoes"], condicoes))]
    achadas.sort(key=lambda x: x["em"], reverse=True)
    return copy.deepcopy(achadas[:max(1, min(int(limite), 50))])


def conferir_escolha(escolha):
    """Confere se a justificativa de uma escolha de estratégia bate com o que está registrado: para cada candidata, recalcula as contagens com as
    experiências feitas até o instante da escolha. Devolve (ok, divergências). É isto que torna a justificativa verificável, em vez de uma frase."""
    problemas = []
    if not isinstance(escolha, dict) or not isinstance(escolha.get("ranking"), list) or not isinstance(escolha.get("em"), (int, float)):
        return False, ["escolha sem ranking ou sem instante"]
    for item in escolha["ranking"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            problemas.append("item de ranking sem id")
            continue
        real = sinais(item["id"], escolha.get("condicoes"), ate=escolha["em"])
        for campo in ("n", "sucessos", "falhas", "p"):
            if item.get(campo) != real[campo]:
                problemas.append(f"{item['id']}: {campo} dito {item.get(campo)!r}, registrado {real[campo]!r}")
        if sorted(item.get("experiencias") or []) != real["ids"]:
            problemas.append(f"{item['id']}: experiências citadas {sorted(item.get('experiencias') or [])!r}, registradas {real['ids']!r}")
    return not problemas, problemas


# ---------------------------------------------------------------- registros cognitivos: gravar, revogar, consultar
def _todas_cognitivas():
    return [x for x in _ler() if x["k"] == "cognitiva"]


def _revogadas():
    return {x["revoga"] for x in _ler() if x["k"] == "cognitiva_revogada"}


def registrar_cognitiva(reg):
    """Grava um registro cognitivo (objetivo inteiro: previsão × observado conferido por fora). Devolve o registro gravado ou None se foi recusado
    (campo inválido ou ajuste fora de `PARAMETROS_AUTORIZADOS`). O id e o instante são deste módulo, não de quem registra."""
    with _trava:
        proximo = max([int(x["id"][1:]) for x in _todas_cognitivas()] or [0]) + 1
        r = dict(reg) if isinstance(reg, dict) else {}
        r.update(k="cognitiva", id=f"c{proximo:04d}", em=_agora())
        limpo = _limpar_cognitiva(r)
        if not limpo or not _acrescentar(limpo):
            _ERROS["n"] += 1
            _ERROS["ultimo"] = "registro cognitivo recusado"
            return None
        return copy.deepcopy(limpo)


def revogar_cognitiva(cid, motivo, por="dono"):
    """Desfaz o EFEITO de um registro cognitivo sem apagá-lo: ele deixa de contar em `sinais_cognitivas` e continua no arquivo, com o motivo. Devolve True se gravou."""
    with _trava:
        if not isinstance(cid, str) or not any(x["id"] == cid for x in _todas_cognitivas()):
            return False
        r = _limpar_revogacao({"k": "cognitiva_revogada", "revoga": cid, "em": _agora(), "motivo": motivo, "por": por})
        return bool(r) and _acrescentar(r)


def cognitivas(tipo=None, estrategia=None, incluir_revogadas=False, limite=50):
    """Registros cognitivos (mais novos primeiro), por padrão sem os revogados."""
    rev = set() if incluir_revogadas else _revogadas()
    achadas = [x for x in _todas_cognitivas() if x["id"] not in rev and (tipo is None or x["tipo_objetivo"] == tipo) and (estrategia is None or x["estrategia"] == estrategia)]
    achadas.sort(key=lambda x: x["em"], reverse=True)
    return copy.deepcopy(achadas[:max(1, min(int(limite), 200))])


def sinais_cognitivas(estrategia, tipo, condicoes=None, ate=None):
    """Como `sinais`, mas por OBJETIVO: sucesso conta a favor; parcial e falha contam contra (desfecho conhecido); inconclusivo não pesa. A mesma conta suavizada
    p=(s+1)/(n+2). Só entram registros do mesmo tipo de objetivo e com condições compatíveis (inclui a faixa de tamanho do conteúdo)."""
    rev = _revogadas()
    s = f = ign = 0
    ids = []
    for x in _todas_cognitivas():
        if x["id"] in rev or x["estrategia"] != estrategia or x["tipo_objetivo"] != tipo or (ate is not None and x["em"] > ate):
            continue
        if condicoes is not None and not compativel(x["condicoes"], condicoes):
            continue
        if x["resultado"] == "sucesso":
            s += 1
        elif x["resultado"] in ("parcial", "falha"):
            f += 1
        else:
            ign += 1
        ids.append(x["id"])
    n = s + f
    return {"estrategia": estrategia, "tipo": tipo, "n": n, "sucessos": s, "falhas": f, "inconclusivas": ign, "ids": sorted(ids)[-20:], "p": round((s + 1) / (n + 2), 4), "confianca": round(n / (n + 2), 4)}


def conferir_escolha_cognitiva(escolha):
    """Refaz a conta de uma escolha de estratégia do pré-córtex com os registros que existiam no instante dela. Devolve (ok, divergências)."""
    problemas = []
    if not isinstance(escolha, dict) or not isinstance(escolha.get("ranking"), list) or not isinstance(escolha.get("em"), (int, float)) or not isinstance(escolha.get("tipo"), str):
        return False, ["escolha sem ranking, tipo ou instante"]
    for item in escolha["ranking"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or "cognitivas" not in item:
            problemas.append("item de ranking sem id ou sem contagem cognitiva")
            continue
        real = sinais_cognitivas(item["id"], escolha["tipo"], item.get("condicoes_da_contagem", escolha.get("condicoes")), ate=escolha["em"])
        dito = item["cognitivas"]
        for campo in ("n", "sucessos", "falhas", "p"):
            if dito.get(campo) != real[campo]:
                problemas.append(f"{item['id']}: {campo} dito {dito.get(campo)!r}, registrado {real[campo]!r}")
        if sorted(dito.get("ids") or []) != real["ids"]:
            problemas.append(f"{item['id']}: registros citados {sorted(dito.get('ids') or [])!r}, registrados {real['ids']!r}")
    return not problemas, problemas


def resumo_cognitivo():
    """Só contagens dos registros cognitivos (não mexe em `resumo()`, que o painel antigo já usa)."""
    rev = _revogadas()
    ativos = [x for x in _todas_cognitivas() if x["id"] not in rev]
    return {"total": len(ativos), "revogados": len(rev), **{r: sum(1 for x in ativos if x["resultado"] == r) for r in RESULTADOS_COG}}


# ---------------------------------------------------------------- resumo e voz
def resumo():
    """Só contagens (vai para o painel)."""
    ult = _ultimas()
    por = {r: sum(1 for x in ult if x["resultado"] == r) for r in RESULTADOS}
    _ler()
    return {"total": len(ult), **por, "descartadas": _CACHE["descartadas"], "erros": _ERROS["n"]}


def falar():
    ult = _ultimas()
    if not ult:
        return "Ainda não tenho experiências registradas: elas nascem quando uma tarefa termina."
    r = resumo()
    partes = [f"Tenho {r['total']} experiência(s) registrada(s): {r['sucesso']} deram certo, {r['falha']} falharam, {r['sem_conferencia']} não deu para conferir"]
    if r["interrompida"] or r["cancelada"]:
        partes[0] += f", {r['interrompida']} foram interrompidas e {r['cancelada']} canceladas"
    por = {}
    for x in ult:
        if x["resultado"] == FALHA and x["tipo_falha"] in ("erro", "falso_sucesso"):
            por.setdefault(x["estrategia"]["id"], []).append(x)
    if por:
        e, lista = max(por.items(), key=lambda kv: len(kv[1]))
        s = sinais(e)
        partes.append(f"A que mais falhou foi «{e.replace('+', ' e depois ')}»: {s['falhas']} de {s['n']} tentativas com desfecho conhecido, "
                      f"{'sempre' if len({tuple(sorted(x['condicoes'].items())) for x in lista}) == 1 else 'em condições variadas'} ({_texto_condicoes(lista[-1]['condicoes'])})")
    partes.append("São poucas observações: servem de indício para escolher a ordem das tentativas, não são regra.")
    return ". ".join(partes) + "."


_PERG = re.compile(r"(o que (voce|vc) (ja )?aprendeu( com (as |a |suas )?(tarefas?|experiencias?))?|(minhas|suas) experiencias|(quais|como) (sao )?(as )?(suas )?experiencias)")


def tratar(texto):
    """Voz: «o que você aprendeu com as tarefas?», «minhas experiências». Só lê. Devolve a fala, ou None se não for com isto."""
    if not isinstance(texto, str) or len(texto) > 200:
        return None
    f = M._fold(" ".join(texto.split()).rstrip(".!? "))
    return falar() if _PERG.fullmatch(f) else None
