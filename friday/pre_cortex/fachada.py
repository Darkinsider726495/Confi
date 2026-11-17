"""Ponte entre o FRIDAY (main.py) e o pré-córtex distribuído.

- `hub()` cria UM hub, só quando alguém precisa (primeira frase, primeira consulta do painel ou objetivo a recuperar na partida). O painel nunca cria o hub só para mostrar o resumo.
- `tratar(texto)` reconhece frases EXPLÍCITAS (nunca «sim»/«pode»):
    «pré-córtex: <objetivo>»                       registra e inicia
    «pré-córtex planejar: <objetivo>»              só planeja (nada é executado)
    «autorizo o plano do objetivo pc3» [versão N]  autoriza o plano pendente (preso ao hash e à versão que estão esperando)
    «nego o plano do objetivo pc3»
    «cancele o objetivo pc3» / «explique o objetivo pc3»
    «como está o pré-córtex?»
- Onde guarda: PRECORTEX_PASTA, ou `.cerebro/precortex` dentro do cofre; sem cofre, só na memória (o painel avisa que não sobrevive a um reinício).
Não há frase, rota nem ferramenta que pare o FRIDAY ou o hub.
"""
import os
import re
import threading

import memoria as M

from . import api as API
from . import config as CF
from . import dossie as D
from . import explicar as EXPL
from . import hub as HB

_TRAVA = threading.RLock()
_E = {"hub": None, "api": None}

_RX_PEDIDO = re.compile(r"\s*pr[eé][\s-]?c[oó]rtex(?P<plan>\s+(?:s[oó]\s+)?planej(?:ar|e))?\s*[:,\-–]\s*(?P<t>\S.*)", re.I | re.S)
_ID = r"pc\s?(?P<n>\d{1,6})"
_RX_AUT = re.compile(rf"(autorizo|autorizar|autoriza) o plano do objetivo {_ID}(?: (?:na )?versao (?P<v>\d{{1,3}}))?")
_RX_NEG = re.compile(rf"(nego|negar|nega|recuso) o plano do objetivo {_ID}")
_RX_CAN = re.compile(rf"(cancele|cancela|cancelar) o objetivo {_ID}")
_RX_EXP = re.compile(rf"(explique|explica|explicar) o objetivo {_ID}")
_RX_STATUS = re.compile(r"(como esta|status|situacao|resumo)( d?o)? pre[ -]?cortex|o que o pre[ -]?cortex esta fazendo")


def pasta():
    p = (os.getenv("PRECORTEX_PASTA") or "").strip()
    if p:
        return os.path.expanduser(p)
    b = M.base()
    return str(b / ".cerebro" / "precortex") if b else None


def criado():
    return _E["hub"] is not None


def hub():
    with _TRAVA:
        if _E["hub"] is None:
            _E["hub"] = HB.Hub(CF.Config.carregar(), pasta(), token=os.getenv("PRECORTEX_TOKEN") or "")
        return _E["hub"]


def api():
    with _TRAVA:
        if _E["api"] is None:
            _E["api"] = API.Api(hub)
        return _E["api"]


def reiniciar():
    """Testes: libera o hub deste processo (o próximo uso cria outro, que recupera o que estava gravado)."""
    with _TRAVA:
        h, _E["hub"], _E["api"] = _E["hub"], None, None
    if h is not None:
        h.encerrar(1.0)


def _pcid(m):
    return f"pc{int(m.group('n')):04d}"


def _explicar(pcid):
    d = hub().dossie(pcid)
    if d is None:
        return f"Não conheço o objetivo {pcid}."
    q = {p["n"]: p for p in EXPL.perguntas(d)}
    partes = [f"Objetivo {pcid} — {D.ROTULO_ESTADO.get(d['estado'], d['estado'])}."]
    for n in (1, 9, 10, 11, 12):
        partes.append(f"{q[n]['pergunta']} {q[n]['resposta']}")
    partes.append("As 12 perguntas completas, com a fonte de cada item, estão na página /precortex.")
    return " ".join(partes)


def falar():
    if not criado():
        return "O pré-córtex ainda não recebeu nenhum objetivo nesta execução. Diga «pré-córtex: <objetivo>»."
    h = hub()
    objs = [D.resumo(h.arm.obter(i)) for i in h.arm.ids()]
    if not objs:
        return "O pré-córtex está ocioso: nenhum objetivo registrado."
    espera = [o for o in objs if o["estado"] == "aguardando_autorizacao"]
    andando = [o for o in objs if o["estado"] in HB.ATIVOS]
    mon = h.ultimo_monitor or {}
    txt = f"Pré-córtex em modo {h.cfg['modo']} ({mon.get('modo', 'saúde ainda não avaliada')}): {len(objs)} objetivo(s), {len(andando)} em andamento"
    if espera:
        txt += "; esperando a sua autorização: " + ", ".join(f"{o['id']} (plano v{o['plano']['versao']})" for o in espera if o.get("plano"))
    ult = max(objs, key=lambda o: o["atualizado_em"])
    prox = (ult["proxima_etapa"] or "").strip().rstrip(".")
    return txt + f". O mais recente, {ult['id']}, está «{ult['rotulo']}»" + (f": {prox}." if prox else ".")


def tratar(texto):
    if not isinstance(texto, str) or len(texto) > 1100:
        return None
    m = _RX_PEDIDO.fullmatch(texto.strip())
    if m:
        r = hub().submeter(m.group("t").strip(), so_planejar=bool(m.group("plan")))
        if not r.get("ok"):
            return f"Não registrei: {r.get('erro')}."
        return (f"Registrei o objetivo {r['id']}" + (" só para planejar" if m.group("plan") else "") +
                ". Os neurônios estão trabalhando; acompanhe em /precortex. Nada com efeito fora do aparelho acontece sem a sua autorização.")
    f = M._fold(" ".join(texto.split()).rstrip(".!? "))
    if "cortex" not in f and " pc" not in f and not f.startswith("pc"):
        return None
    if _RX_STATUS.fullmatch(f):
        return falar()
    m = _RX_AUT.fullmatch(f)
    if m:
        r = hub().autorizar(_pcid(m), int(m.group("v")) if m.group("v") else None, None, via="voz")
        return (f"Autorizado só o plano pendente do objetivo {_pcid(m)} (hash {r['plano_hash'][:8]}). O corretor ainda pode pedir a confirmação da ação."
                if r.get("ok") else f"Não autorizei nada: {r.get('erro')}.")
    m = _RX_NEG.fullmatch(f)
    if m:
        r = hub().negar(_pcid(m), "negado pelo dono por voz")
        return f"Neguei: o plano do objetivo {_pcid(m)} não será executado." if r.get("ok") else f"Não mudei nada: {r.get('erro')}."
    m = _RX_CAN.fullmatch(f)
    if m:
        r = hub().cancelar(_pcid(m))
        return f"Pedi o cancelamento do objetivo {_pcid(m)}." if r.get("ok") else f"Não mudei nada: {r.get('erro')}."
    m = _RX_EXP.fullmatch(f)
    if m:
        return _explicar(_pcid(m))
    return None


def resumo():
    """Barato: o painel chama a cada poucos segundos. Não cria o hub."""
    if not criado():
        return {"ativo": False, "pagina": "/precortex"}
    h = _E["hub"]
    objs = [D.resumo(h.arm.obter(i)) for i in h.arm.ids()]
    por = {}
    for o in objs:
        por[o["estado"]] = por.get(o["estado"], 0) + 1
    return {"ativo": True, "pagina": "/precortex", "modo": h.cfg["modo"], "persistente": h.arm.persistente, "objetivos": len(objs), "por_estado": por,
            "aguardando_dono": [o["id"] for o in objs if o["estado"] in ("aguardando_autorizacao", "aguardando_aceite", "precisa_do_dono")],
            "modo_de_operacao": (h.ultimo_monitor or {}).get("modo", "desconhecido")}


def ao_iniciar(falar_cb=None):
    """Na partida: só cria o hub se houver objetivos gravados; retoma o que é seguro e avisa o que espera o dono. Nunca derruba o programa."""
    try:
        p = pasta()
        if not p or not os.path.isfile(os.path.join(p, "objetivos.json")):
            return []
        feitos = hub().recuperar_tudo()
        espera = [pc for pc, o, _ in feitos if o == "esperando_dono"]
        if espera and falar_cb:
            falar_cb("Pré-córtex: " + ", ".join(espera) + " continua(m) esperando a sua autorização do plano. Nada foi executado sem você.")
        return feitos
    except Exception as e:                                                     # noqa: BLE001
        print("pré-córtex: não consegui recuperar na partida:", type(e).__name__, flush=True)
        return []
