"""Retomada (Fase 6): depois de um reinício ou queda, achar o que ficou pela metade, conferir o que de fato aconteceu e só então continuar — ou pedir o dono.

O problema (medido com queda real de processo em `reports/evidencias/cenarios/fase5_6/necessidade_de_retomada.py`): o disco é gravado ANTES de chamar o corretor, então uma
queda deixa a tarefa `EXECUTANDO` com o passo `executando`, e nada mais mexia nela: nem «retomar» aceitava esse estado. Pior: não se sabe se o corretor chegou a executar.

O que este módulo faz, nesta ordem:
  1. RECUPERAR o que parou no meio (`tarefas.recuperar`): para cada passo que estava executando, olha o MUNDO (a mesma conferência independente da Fase 2):
       efeito encontrado → verificado, nunca repete · efeito provadamente ausente → volta para a fila · não dá para conferir → «pode ter acontecido»: NÃO repete e pede o dono.
     Confirmação que ela pedira e o corretor perdeu no reinício (vive na memória do processo) → a tarefa pede o dono; nada roda.
  2. RETOMAR as tarefas prontas que são seguras, na ordem e com as esperas que o coordenador decide (`coordenador.avaliar`): só pedido do dono, meta ou objetivo que ele aprovou;
     só nível ≤ 1, com argumentos guardados, e recentes (IDADE_MAX_S). O resto fica na lista «precisa de você», com o motivo. Quem executa é `tarefas.executar` → corretor, como sempre.

O que NÃO faz, de propósito:
  • Não repete ação que pode já ter acontecido e não dá para conferir (SMS, ligação, relé, lanterna…). Uma queda no meio não vira «faz de novo».
  • Não retoma tarefa nascida na conversa (origem `ia`): o contexto dela se perdeu e o turno em que o corretor a tratou como mais perigosa (contaminação) não existe mais.
  • Não retoma o que passou do nível 1, nem o que o corretor pediu confirmação (a confirmação se perdeu com o reinício: pede-se de novo).
  • Não tem ferramenta da IA e não importa o corretor; um passo que caiu `MAX_QUEDAS` vezes não é repetido sozinho (laço de queda).
  • Não mexe em tarefa que ESTE processo está executando (`tarefas.ATIVAS`).
Registro: uma linha por rodada em `.cerebro/retomada.jsonl` (id da tarefa, ação, motivo curto, estado; nenhum conteúdo)."""
import json, threading, time
import coordenador as CO
import memoria as M
import tarefas as T

ORIGENS_RETOMAVEIS = ("usuario", "meta", "propria")
IDADE_MAX_S = 1800.0      # tarefa pronta parada há mais que isto não recomeça sozinha (pode já não valer); o dono manda: «retomar a tarefa N»
MAX_RODADAS = 4           # quantas vezes reavalia o que ficou esperando dependência ou recurso
MAX_TAREFAS = 20          # no máximo tantas tarefas por chamada (operacional)
ACOES = ("conferiu", "retomou", "esperou", "pediu_dono")
_trava = threading.Lock()
_ERROS = {"n": 0, "ultimo": ""}
_ULTIMA = {"v": None}
_agora = time.time


def _item(tid, acao, motivo, estado=None):
    return {"tarefa": tid, "acao": acao, "motivo": " ".join(str(motivo).split())[:200], "estado": estado}


def _numero(tid):
    return int(tid[1:])


# ---------------------------------------------------------------- 1. recuperar o que parou no meio
def _recuperar(itens):
    for t in T.listar(estados=(T.EXECUTANDO, T.VERIFICANDO, T.BLOQUEADA)):
        tid = t["id"]
        if T.ATIVAS.get(tid):
            continue                                     # este processo está executando: não é sobra de queda
        if t["estado"] == T.BLOQUEADA:
            if T.confirmacao_perdida(tid):
                itens.append(_item(tid, "pediu_dono", "a confirmação que eu tinha pedido se perdeu e nada foi executado: peça a ação de novo", T.PRECISA_INTERVENCAO))
            continue
        try:
            r = T.recuperar(tid)
        except Exception as e:                           # não esconder: aparece no relatório e na contagem de erros
            _erro(e)
            itens.append(_item(tid, "pediu_dono", f"não consegui recuperar ({type(e).__name__}); não mexi em nada", t["estado"]))
            continue
        if not r:
            continue
        partes = []
        if r["achados"]:
            partes.append(f"o efeito de {', '.join(r['achados'])} já existia (conferido por fora): não repeti")
        if r["ausentes"]:
            partes.append(f"{', '.join(r['ausentes'])} não chegou a acontecer: volta para a fila")
        if r["duvida"]:
            partes.append(f"{', '.join(r['duvida'])} pode ter acontecido e não dá para conferir: não repeti")
        if r["repetidas"]:
            partes.append(f"{', '.join(r['repetidas'])} já foi interrompido {T.MAX_QUEDAS} vezes: não repeti sozinha")
        itens.append(_item(tid, "pediu_dono" if (r["duvida"] or r["repetidas"]) else "conferiu", "; ".join(partes) or "conferida; nada estava no meio", r["estado"]))


# ---------------------------------------------------------------- 2. retomar o que é seguro
def _elegivel(t, agora, idade_max_s):
    """(ok, motivo). Só barra o que é decisão do DONO: origem, idade, nível ≥ 2 (o coordenador também barra: duas camadas) e argumentos que não ficaram guardados.
    Dependência e recurso ocupado ficam com o coordenador."""
    origem = t["contexto"]["origem"]
    if origem not in ORIGENS_RETOMAVEIS:
        return False, "pedido nascido na conversa: o contexto dela se perdeu, então não retomo sozinha (diga «retomar a tarefa %d»)" % _numero(t["id"])
    parada = max(0.0, agora - t["atualizada"])
    if parada > idade_max_s:
        return False, f"parada há {int(parada // 60)} min (limite {int(idade_max_s // 60)} min): pode já não valer; diga «retomar a tarefa %d» se ainda quiser" % _numero(t["id"])
    for p in t["passos"]:
        if p["estado"] != "pendente":
            continue
        nivel = p["nivel"] if isinstance(p["nivel"], int) and not isinstance(p["nivel"], bool) else 2          # nível ilegível = sensível
        if nivel >= 2:
            return False, f"o passo {p['id']} é de nível {nivel}: precisa da sua confirmação, como sempre; peça a ação de novo"
        if T.argumentos_guardados(t["id"], p["id"]) is None:
            return False, f"o passo {p['id']}: os argumentos não ficaram guardados (ação sensível ou reinício); peça de novo"
    return True, ""


def _so_depende(t):
    """BLOQUEADA só por dependência de outra tarefa (não por confirmação)? Essas voltam à fila quando a outra termina."""
    return t["estado"] == T.BLOQUEADA and not any(p["estado"] == "aguardando" for p in t["passos"])


def _retomar(itens, agora, idade_max_s, turno):
    feitas, esperas, rodadas_com_trabalho = set(), {}, 0
    for rodada in range(MAX_RODADAS):
        props = []
        concluidas = {x["id"] for x in T.listar(estados=(T.CONCLUIDA,))}
        for t in T.listar(estados=(T.PRONTA, T.BLOQUEADA)):
            tid = t["id"]
            if tid in feitas or T.ATIVAS.get(tid) or (t["estado"] == T.BLOQUEADA and not _so_depende(t)):
                continue
            ok, motivo = _elegivel(t, agora, idade_max_s)
            if not ok:
                itens.append(_item(tid, "pediu_dono", motivo, t["estado"]))
                feitas.add(tid)
                continue
            props.append(CO.proposta_de_tarefa(t, agora=agora))
        if not props:
            break
        andou = False
        for d in CO.avaliar(props, concluidas=concluidas, agora=agora):
            tid = d["id"]
            if d["decisao"] == "executar_agora":
                if len(feitas) >= MAX_TAREFAS:
                    esperas[tid] = f"limite de {MAX_TAREFAS} tarefas por rodada; diga «retoma o que ficou pendente» de novo"
                    continue
                feitas.add(tid)
                esperas.pop(tid, None)
                andou = _executar(itens, tid, turno) or andou
            elif d["decisao"] in ("pedir_dono", "recusar"):
                feitas.add(tid)
                esperas.pop(tid, None)
                itens.append(_item(tid, "pediu_dono", d["motivo"], (T.obter(tid) or {}).get("estado")))
            else:
                esperas[tid] = d["motivo"]
        if not andou:
            break
    for tid, motivo in esperas.items():
        itens.append(_item(tid, "esperou", motivo, (T.obter(tid) or {}).get("estado")))


def _executar(itens, tid, turno):
    """Executa pelo caminho de sempre (tarefas → corretor). Devolve True se algum passo foi ao corretor."""
    try:
        r = T.executar(tid, turno)
    except Exception as e:
        _erro(e)
        itens.append(_item(tid, "pediu_dono", f"erro inesperado ({type(e).__name__}) ao retomar; veja a tarefa antes de repetir", (T.obter(tid) or {}).get("estado")))
        return False
    t = T.obter(tid) or {}
    estado = t.get("estado")
    n = r["passos_executados"]
    if n == 0:
        itens.append(_item(tid, "esperou", t.get("proxima_acao") or f"não executei nada agora: a tarefa está {T.ROTULO.get(estado, estado)}", estado))
        return False
    itens.append(_item(tid, "retomou", f"{n} passo(s) executado(s) pelo corretor, com o efeito conferido por fora quando dá", estado))
    return True


def retomar_pendentes(agora=None, idade_max_s=IDADE_MAX_S, turno=None):
    """Uma rodada de retomada. Devolve {"itens": [{tarefa, acao, motivo, estado}], "resumo": {...}, "em"}. Uma de cada vez: se já há uma rodando, devolve `ocupada`."""
    agora = _agora() if agora is None else agora
    if not _trava.acquire(blocking=False):
        return {"itens": [], "resumo": _resumo_de([], 0), "em": agora, "ocupada": True}
    try:
        erros0, itens = _ERROS["n"], []
        _recuperar(itens)
        _retomar(itens, agora, idade_max_s, turno)
        rel = {"itens": itens, "resumo": _resumo_de(itens, _ERROS["n"] - erros0), "em": agora, "ocupada": False}
        _registrar(rel)
        _ULTIMA["v"] = rel
        return rel
    finally:
        _trava.release()


def _resumo_de(itens, erros):
    c = {a: sum(1 for i in itens if i["acao"] == a) for a in ACOES}
    esperam = sum(1 for t in T.listar(estados=(T.FALHOU, T.PRECISA_INTERVENCAO, T.EXECUTADA_SEM_VERIFICACAO)))
    return {**c, "aguardam_dono": esperam, "erros": erros}


def _erro(e):
    _ERROS["n"] += 1
    _ERROS["ultimo"] = type(e).__name__[:80]


# ---------------------------------------------------------------- registro, painel e voz
def _registrar(rel):
    """Uma linha por rodada que fez alguma coisa. Só ids, ação, motivo curto e estado: nenhum conteúdo do que foi pedido."""
    if not rel["itens"] or not M.ativo():
        return
    try:
        arq = M._dentro(M.base() / ".cerebro" / "retomada.jsonl")
        arq.parent.mkdir(parents=True, exist_ok=True)
        with open(arq, "a", encoding="utf-8") as f:
            f.write(json.dumps({"em": rel["em"], "itens": rel["itens"], "resumo": rel["resumo"]}, ensure_ascii=False) + "\n")
    except (OSError, ValueError, TypeError) as e:
        _erro(e)


def ultima():
    """A última rodada que fez alguma coisa (memória do processo ou o arquivo), ou None."""
    if _ULTIMA["v"]:
        return _ULTIMA["v"]
    if not M.ativo():
        return None
    try:
        linhas = (M.base() / ".cerebro" / "retomada.jsonl").read_text(encoding="utf-8").splitlines()
        x = json.loads(linhas[-1]) if linhas else None
    except (OSError, ValueError, IndexError):
        return None
    return x if isinstance(x, dict) and isinstance(x.get("itens"), list) else None


def interrompidas():
    """Só LÊ: tarefas que um processo anterior deixou no meio (executando sem ninguém executando) ou esperando uma confirmação."""
    return [t["id"] for t in T.listar(estados=(T.EXECUTANDO, T.VERIFICANDO)) if not T.ATIVAS.get(t["id"])]


def resumo():
    u = ultima()
    r = (u or {}).get("resumo") or {}
    return {"interrompidas": len(interrompidas()), "ultima": {k: r.get(k, 0) for k in (*ACOES, "aguardam_dono", "erros")} if u else None, "erros": _ERROS["n"]}


def falar(rel):
    """Frase curta e sem conteúdo (números de tarefa, nunca o que foi pedido)."""
    if not rel:
        return "Não achei nada interrompido: nenhuma tarefa ficou pela metade."
    c = rel["resumo"]
    partes = []
    if c["retomou"]:
        partes.append(f"retomei {c['retomou']} tarefa(s)")
    if c["conferiu"]:
        partes.append(f"conferi {c['conferiu']} que estavam no meio")
    if c["esperou"]:
        partes.append(f"{c['esperou']} esperam a vez")
    precisam = [i for i in rel["itens"] if i["acao"] == "pediu_dono"]
    if precisam:
        partes.append(f"{len(precisam)} precisam de você: " + "; ".join(f"tarefa {_numero(i['tarefa'])} ({i['motivo']})" for i in precisam[:3]))
    elif c["aguardam_dono"]:
        partes.append(f"{c['aguardam_dono']} esperam por você (diga «minhas tarefas»)")
    return ("Depois do reinício: " + "; ".join(partes) + ".")[:900] if partes else "Não achei nada interrompido: nenhuma tarefa ficou pela metade."


def ao_iniciar(falar_fn=None, pausa_s=3.0):
    """Chamada uma vez ao ligar (em thread, depois que o painel subiu). Fala só se retomou algo ou se algo precisa do dono. Nunca levanta exceção."""
    try:
        time.sleep(max(0.0, pausa_s))
        rel = retomar_pendentes()
        if falar_fn and (rel["resumo"]["retomou"] or rel["resumo"]["conferiu"] or rel["resumo"]["pediu_dono"]):
            falar_fn(falar(rel))
        return rel
    except Exception as e:
        _erro(e)
        return None


_RETOMAR = ("retoma", "retomar", "retome", "continua", "continue", "continuar")
_PERG = ("o que ficou interrompido", "o que ficou pela metade", "alguma tarefa ficou interrompida", "alguma tarefa ficou pela metade", "o que voce retomou",
         "o que voce retomou depois do reinicio", "o que voce fez depois do reinicio")
_FRASES_RETOMAR = tuple(f"{v} {o}" for v in _RETOMAR for o in ("o que ficou pendente", "o que ficou interrompido", "o que ficou pela metade", "as tarefas pendentes",
                                                                "as tarefas interrompidas", "de onde parou", "de onde voce parou"))


def tratar(texto):
    """«retoma o que ficou pendente» (confere e retoma o que é seguro) · «o que ficou interrompido?» (só lê). None se não for com isto."""
    if not isinstance(texto, str) or len(texto) > 120:
        return None
    f = M._fold(" ".join(texto.split()).rstrip(".!? "))
    if f in _FRASES_RETOMAR:
        rel = retomar_pendentes()
        return "Já estou conferindo isso; peça de novo daqui a pouco." if rel.get("ocupada") else falar(rel)
    if f in _PERG:
        n = interrompidas()
        u = ultima()
        antes = falar(u) if u else "Ainda não retomei nada."
        return f"{antes} Agora há {len(n)} tarefa(s) paradas no meio" + (" (diga «retoma o que ficou pendente»)." if n else ".")
    return None
