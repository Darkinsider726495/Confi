"""Protocolos: sequências nomeadas que você dispara falando ("protocolo foco", "bom dia") ou tocando no painel.
Só quem fala é você: a IA não dispara protocolos. Cada passo de ferramenta passa pelo corretor (níveis, confirmação, auditoria).
Personalize em protocolos.json (mesma forma de PADRAO); entradas com o mesmo nome substituem as padrão."""
import os, re, json, unicodedata
import broker as B
import ferramentas as F
import telemetria as T

BASE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.environ.get("FRIDAY_PROTOCOLOS") or os.path.join(BASE, "..", "protocolos.json")
PADRAO = {
    "briefing": {"desc": "Hora, clima, agenda, leads e saúde dos sistemas.", "apelidos": ["bom dia", "resumo do dia", "relatorio do dia"],
                 "passos": [{"falar": "@briefing"}]},
    "relatorio": {"desc": "Relatório de sistemas.", "apelidos": ["relatorio de sistemas", "status dos sistemas", "diagnostico", "como estao os sistemas"],
                  "passos": [{"falar": "@relatorio"}]},
    "foco": {"desc": "Avisos só por notificação durante 1 hora.", "apelidos": ["modo foco", "nao me perturbe"],
             "passos": [{"ferramenta": "silenciar", "args": {"minutos": 60}},
                        {"falar": "Modo foco ativo por uma hora, @tratamento. Os avisos vão só para a notificação."}]},
    "noite": {"desc": "Avisos só por notificação por 8 horas.", "apelidos": ["boa noite"],
              "passos": [{"ferramenta": "silenciar", "args": {"minutos": 480}},
                         {"falar": "Boa noite, @tratamento. Silêncio por oito horas, só notificações. Sigo em vigília."}]},
    "retomar": {"desc": "Volta a falar normalmente.", "apelidos": ["pode falar", "voltar a falar", "fim do foco"],
                "passos": [{"ferramenta": "voltar_a_falar", "args": {}}, {"falar": "Voltei a falar normalmente, @tratamento."}]},
}


def _norm(t):
    t = "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def _valido(p):
    if not isinstance(p, dict) or not isinstance(p.get("passos"), list) or not 0 < len(p["passos"]) <= 12:
        return False
    for s in p["passos"]:
        if not isinstance(s, dict):
            return False
        if "falar" in s:
            if not isinstance(s["falar"], str) or len(s["falar"]) > 600:
                return False
        elif not (isinstance(s.get("ferramenta"), str) and isinstance(s.get("args", {}), dict)):
            return False
    return True


def carregar():
    r = dict(PADRAO)
    try:
        with open(ARQ, encoding="utf-8") as f:
            for nome, p in json.load(f).items():
                if _valido(p):
                    r[_norm(nome)] = {"desc": str(p.get("desc", ""))[:120], "apelidos": [str(a) for a in p.get("apelidos", [])][:8], "passos": p["passos"]}
    except (OSError, ValueError, AttributeError):
        pass
    return r


def resumo():
    return [{"nome": n, "desc": p.get("desc", "")} for n, p in carregar().items()]


def achar(texto):
    t = re.sub(r"^(friday|jarvis|fraide) ", "", _norm(texto))
    m = re.match(r"^(?:ativar |ative |iniciar |inicie |executar |execute |rodar |rode )?protocolo (.+)$", t)
    alvo = _norm(m.group(1)) if m else t
    for nome, p in carregar().items():
        if alvo == _norm(nome) or alvo in {_norm(a) for a in p.get("apelidos", [])}:
            return nome
    return "?" if m else None  # "?" = pediu um protocolo que não existe


def listar():
    return "Protocolos disponíveis: " + "; ".join(f"{n}, {p['desc'].rstrip('.').lower()}" for n, p in carregar().items() if p.get("desc")) + "."


def _macro(txt):
    return (txt.replace("@briefing", T.briefing()).replace("@relatorio", T.relatorio()).replace("@tratamento", F.tratamento()))


def executar(nome, turno=None):
    p = carregar().get(nome)
    if not p:
        return f"Não tenho o protocolo {nome}. " + listar()
    turno = turno or B.Turno()
    B._audit(ferramenta="protocolo:" + nome, decisao="iniciado")
    falas, saidas = [], []
    for passo in p["passos"]:
        if "falar" in passo:
            falas.append(_macro(passo["falar"]))
            continue
        r = B.executar(passo["ferramenta"], passo.get("args") or {}, turno)
        saidas.append(r)
        if r.startswith("AÇÃO PENDENTE"):
            pend = B.pendente_publico() or {}
            B._audit(ferramenta="protocolo:" + nome, decisao="pausado")
            return f"Protocolo {nome} pausado em {passo['ferramenta']}: preciso da sua confirmação, {F.tratamento()}. {pend.get('desc', '')}".strip()
    B._audit(ferramenta="protocolo:" + nome, decisao="executado")
    return " ".join(falas) or " ".join(saidas) or "Protocolo executado."


def tratar(texto):
    """Se o texto é um pedido de protocolo, executa e devolve a resposta; senão devolve None (segue para a IA)."""
    t = _norm(texto)
    if t in ("protocolos", "quais protocolos", "lista de protocolos", "quais sao os protocolos", "listar protocolos"):
        return listar()
    nome = achar(texto)
    if nome is None:
        return None
    return executar(nome) if nome != "?" else "Não tenho esse protocolo. " + listar()
