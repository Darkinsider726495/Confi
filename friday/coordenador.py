"""Coordenador (Fase 5): o mínimo para vários pedidos não se pisarem, e para cada escolha ter explicação.

Duas coisas, e só estas:
  1. RESERVA DE RECURSOS. Duas ações que mexem no MESMO recurso ao mesmo tempo (o mesmo relé, o mesmo contato, o mesmo arquivo, o cofre inteiro durante uma
     consolidação) não rodam juntas: a segunda espera a primeira. Ações em recursos diferentes, ou que só se somam (duas notas, dois lembretes), continuam em
     paralelo. Isto foi medido antes de existir (`reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py`: sem reserva, duas tarefas no mesmo recurso
     ficam juntas dentro da ferramenta). `tarefas.py` chama a reserva antes de cada passo e libera depois; ele não importa este módulo (a ligação é por `RESERVAS`).
  2. AVALIAÇÃO DE PROPOSTAS. Dado um conjunto de coisas que módulos querem fazer (tarefas a retomar, objetivos), diz para cada uma: `executar_agora`, `esperar`
     (dependência, recurso ocupado ou conflito com outra mais importante), `pedir_dono` (nível ≥ 2, ou algo que só o dono autoriza) ou `recusar` (proposta mal formada),
     com os componentes da nota (relevância, urgência, custo, risco, incerteza) e o motivo. Cada decisão vai para `.cerebro/coordenacao.jsonl` (só acrescenta; ids,
     módulo, nota e motivo; nomes de recurso viram um código curto, sem conteúdo).

O que NÃO faz, de propósito:
  • Não serializa nada que não precise. A decisão do dono («se ela quiser fazer tudo ao mesmo tempo, ela que decide») vale: propostas sem conflito saem juntas.
    O `nucleo.py` é uma camada observacional e não participa do escalonamento (docs/NUCLEO.md).
  • Não executa nada e não tem ferramenta da IA: quem executa é o corretor, pelas tarefas. Não cria agentes concorrentes: não há fila, thread nem laço aqui.
  • Não altera regra de segurança: a nota só ORDENA o que já é permitido; `pedir_dono` e `recusar` não saem de lá por nota alta.
  • Os pesos da nota são escolhas de projeto, escritas aqui; não são aprendidos nem se ajustam sozinhos.
Cobertura honesta: a reserva vale para o que passa por `tarefas.py` (IA, planejador, objetivos, retomada). Protocolos, rotinas da autonomia e atalhos de voz da memória chamam o
corretor direto e ficam fora (docs/PLANEJADOR.md)."""
import copy, hashlib, json, threading, time
import memoria as M
import privacidade as P
import tarefas as T

PESOS = {"relevancia": 0.40, "urgencia": 0.30, "custo": -0.10, "risco": -0.15, "incerteza": -0.05}
DECISOES = ("executar_agora", "esperar", "pedir_dono", "recusar")
MODOS = ("excl", "comp")                  # exclusivo: ninguém mais usa; compartilhado: só convive com outro compartilhado
RELEVANCIA_POR_ORIGEM = {"usuario": 1.0, "meta": 0.8, "ia": 0.6, "propria": 0.3}
_trava = threading.RLock()
_reservas = {}                            # dono -> {"ferramenta", "recursos": [(recurso, modo)], "desde"}
_ERROS = {"n": 0, "ultimo": ""}
_agora = time.time


# ---------------------------------------------------------------- recursos de cada ferramenta
def _nome(v):
    s = " ".join(M._fold(v).split())[:60] if isinstance(v, str) else ""
    return s or "?"                       # nome que não deu para ler: tratado como «algum», que conflita com outro «algum» (na dúvida, espera)


def _um(prefixo, campo, modo="excl"):
    return lambda a: [(f"{prefixo}:{_nome((a or {}).get(campo))}", modo)]


RECURSOS = {
    "rele": _um("rele", "nome"),
    "lanterna": lambda a: [("lanterna", "excl")],
    "vibrar": lambda a: [("vibracao", "excl")],
    "enviar_sms": _um("contato", "contato"),
    "ligar": lambda a: _um("contato", "contato")(a) + [("linha_telefonica", "excl")],
    "preparar_whatsapp": _um("contato", "contato"),
    "criar_arquivo": _um("arquivo", "nome"),
    "compartilhar_arquivo": _um("arquivo", "nome"),
    "guardar_memoria": lambda a: [("cofre", "comp")],
    "pedir_evolucao": lambda a: [("cofre", "comp")],
    "consolidar_memoria": lambda a: [("cofre", "excl")],
    "esquecer_memoria": lambda a: [("cofre", "excl")],
    "exportar_cerebro": lambda a: [("cofre", "excl")],
    "silenciar": lambda a: [("silencio", "excl")],
    "voltar_a_falar": lambda a: [("silencio", "excl")],
    # laboratório (MAE): o arquivo do laboratório em jogo e o ciclo de teste são exclusivos (uma modificação por vez)
    "lab_criar": _um("lab:arquivo", "rel"),
    "lab_editar": _um("lab:arquivo", "rel"),
    "lab_excluir": _um("lab:arquivo", "rel"),
    "lab_renomear": lambda a: _um("lab:arquivo", "rel")(a) + _um("lab:arquivo", "novo_rel")(a),
    "lab_restaurar": _um("lab:arquivo", "rel"),
    "lab_testar": lambda a: [("lab:teste", "excl")],
}
# Ferramentas que mudam algo mas cujos efeitos se somam ou só leem: duas ao mesmo tempo não se atrapalham. Toda ferramenta de nível ≥ 1 tem de estar numa das duas listas (teste).
SEM_RECURSO = {
    "anotar": "cada nota é uma linha nova; duas juntas são duas notas",
    "criar_lembrete": "cada lembrete é uma linha nova",
    "notificar": "cada notificação é independente",
    "localizacao": "só lê o sensor",
}


def recursos_de(ferramenta, args):
    """[(recurso, modo)] que esta ação usa. Ferramenta desconhecida ou sem regra: nenhum (o corretor continua decidindo o resto)."""
    fn = RECURSOS.get(ferramenta)
    if not fn:
        return []
    try:
        return [(r, m) for r, m in fn(args if isinstance(args, dict) else {}) if m in MODOS]
    except Exception:
        return [(f"{ferramenta}:?", "excl")]


def _codigo(recurso):
    """Para o disco: tipo do recurso + código curto do nome (dá para ver que dois pedidos bateram no mesmo, sem dizer qual contato ou arquivo)."""
    tipo, _, nome = str(recurso).partition(":")
    return f"{tipo}:{hashlib.sha256(nome.encode()).hexdigest()[:6]}" if nome else tipo


def _conflita(a, b):
    return a[0] == b[0] and "excl" in (a[1], b[1])


# ---------------------------------------------------------------- reserva
def reservar(dono, ferramenta, args):
    """Tudo ou nada, sem esperar. Devolve (True, None) ou (False, {"recurso", "dono", "ferramenta"}) com quem está usando. O mesmo dono pode reservar de novo (substitui)."""
    quer = recursos_de(ferramenta, args)
    with _trava:
        for outro, r in _reservas.items():
            if outro == dono:
                continue
            for q in quer:
                for u in r["recursos"]:
                    if _conflita(q, u):
                        return False, {"recurso": q[0], "dono": outro, "ferramenta": r["ferramenta"]}
        if quer:
            _reservas[dono] = {"ferramenta": ferramenta, "recursos": quer, "desde": _agora()}
        else:
            _reservas.pop(dono, None)
        return True, None


def liberar(dono):
    with _trava:
        return _reservas.pop(dono, None) is not None


def ocupados():
    """Cópia do que está reservado agora: [{dono, ferramenta, recursos, desde}]."""
    with _trava:
        return [{"dono": d, "ferramenta": r["ferramenta"], "recursos": [x[0] for x in r["recursos"]], "desde": r["desde"]} for d, r in sorted(_reservas.items())]


def reiniciar():
    with _trava:
        _reservas.clear()
        _ERROS.update(n=0, ultimo="")


def _ligar():
    T.RESERVAS["reservar"], T.RESERVAS["liberar"] = reservar, liberar


_ligar()


# ---------------------------------------------------------------- avaliação de propostas
def _clamp(x):
    return max(0.0, min(1.0, float(x)))


def _componentes(p):
    c = {}
    for k in PESOS:
        v = p.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            return None
        c[k] = round(_clamp(v), 4)
    return c


def nota(c):
    return round(sum(PESOS[k] * c[k] for k in PESOS), 4)


def proposta_de_tarefa(t, agora=None, concluidas=None):
    """Monta a proposta de retomar/executar uma tarefa a partir do que está registrado nela. Cada componente tem uma regra simples e escrita:
    relevância pela origem (pedido seu 1,0 · meta 0,8 · conversa 0,6 · objetivo dela, aprovado 0,3) · urgência: 0,5 se foi pedido seu, mais até 0,5 conforme espera
    (12 h = máximo) · custo: passos que faltam / máximo de passos · risco: maior nível dos passos que faltam / 3 · incerteza: 1 − confiança da experiência
    com essa estratégia nas condições de agora (sem experiência = 1,0)."""
    import experiencias as X
    agora = _agora() if agora is None else agora
    faltam = [p for p in t["passos"] if p["estado"] in ("pendente", "executando", "aguardando", "intervencao")]
    origem = t["contexto"]["origem"]
    espera_h = max(0.0, (agora - t["criada"]) / 3600)
    estrat = "+".join(p["ferramenta"] for p in t["passos"]) or "?"
    try:
        confianca = X.sinais(estrat, X.ambiente())["confianca"]
    except Exception:
        confianca = 0.0
    nivel = max([p["nivel"] if isinstance(p["nivel"], int) and not isinstance(p["nivel"], bool) else 2 for p in faltam] or [0])   # nível ilegível = tratado como sensível
    recursos = []
    for p in faltam:
        args = T.argumentos_guardados(t["id"], p["id"])
        recursos += recursos_de(p["ferramenta"], args) if args is not None else [(f"{p['ferramenta']}:?", "excl")]
    return {"id": t["id"], "modulo": "tarefas", "descricao": t["objetivo"], "origem": origem, "recursos": recursos,
            "depende_de": list(t["depende_de"]), "precisa_dono": nivel >= 2,
            "relevancia": RELEVANCIA_POR_ORIGEM.get(origem, 0.3), "urgencia": _clamp((0.5 if origem == "usuario" else 0.2) + min(0.5, espera_h / 12 * 0.5)),
            "custo": len(faltam) / T.MAX_PASSOS, "risco": nivel / 3, "incerteza": 1 - confianca}


def avaliar(propostas, concluidas=(), agora=None):
    """Decide o que cada proposta merece AGORA. Devolve as decisões, da mais à menos importante. Não executa nada.
    Ordem das regras (a primeira que vale decide): mal formada → recusar · exige o dono → pedir_dono · depende de algo que não terminou → esperar ·
    recurso ocupado por uma ação em andamento → esperar · conflito com outra proposta de nota maior → esperar · senão executar_agora (várias podem sair juntas)."""
    agora = _agora() if agora is None else agora
    itens = []
    for p in propostas if isinstance(propostas, (list, tuple)) else []:
        c = _componentes(p) if isinstance(p, dict) else None
        if c is None or not isinstance(p.get("id"), str) or not isinstance(p.get("modulo"), str):
            itens.append({"id": p.get("id") if isinstance(p, dict) and isinstance(p.get("id"), str) else "?", "modulo": "?", "proposta": None, "componentes": None, "nota": -9.0})
            continue
        itens.append({"id": p["id"], "modulo": p["modulo"], "proposta": p, "componentes": c, "nota": nota(c)})
    itens.sort(key=lambda i: (-i["nota"], i["id"]))
    usados = []                                          # (recurso, modo, id) de quem já saiu nesta rodada
    em_uso = _copia_reservas()                           # [(dono, ferramenta, [(recurso, modo)])] das ações em andamento
    saida = []
    for i in itens:
        p = i["proposta"]
        d = {"id": i["id"], "modulo": i["modulo"], "decisao": "", "motivo": "", "nota": i["nota"], "componentes": i["componentes"]}
        if p is None:
            d.update(decisao="recusar", motivo="proposta mal formada (faltam componentes numéricos, id ou módulo)")
        elif p.get("precisa_dono"):
            d.update(decisao="pedir_dono", motivo="exige a confirmação do dono (nível 2 ou mais); não é decidida aqui")
        else:
            falta = [x for x in (p.get("depende_de") or []) if x not in set(concluidas)]
            quer = [(r, m) for r, m in (p.get("recursos") or []) if m in MODOS]
            ocupado = next(((q[0], dono) for q in quer for dono, _, recs in em_uso if dono != i["id"] for r in recs if _conflita(q, r)), None)
            choque = next(((q[0], u[2]) for q in quer for u in usados if u[2] != i["id"] and _conflita(q, (u[0], u[1]))), None)
            if falta:
                d.update(decisao="esperar", motivo="depende de " + ", ".join(falta) + ", que ainda não terminou")
            elif ocupado:
                d.update(decisao="esperar", motivo=f"o recurso {ocupado[0].split(':')[0]} está em uso por {ocupado[1]}")
            elif choque:
                d.update(decisao="esperar", motivo=f"usa o mesmo recurso ({choque[0].split(':')[0]}) que {choque[1]}, que vem antes (nota maior)")
            else:
                d.update(decisao="executar_agora", motivo="sem dependência pendente, sem recurso ocupado e sem conflito com outra de nota maior")
                usados += [(r, m, i["id"]) for r, m in quer]
        saida.append(d)
        _registrar(d, [r for r, _ in (p.get("recursos") or [])] if p else [], agora)
    return saida


def _copia_reservas():
    with _trava:
        return [(d, r["ferramenta"], list(r["recursos"])) for d, r in sorted(_reservas.items())]


def _registrar(d, recursos, agora):
    """Uma linha por decisão: quem, o quê, nota, motivo. Recurso só como tipo+código; nada do que foi pedido."""
    if not M.ativo():
        return
    try:
        arq = M._dentro(M.base() / ".cerebro" / "coordenacao.jsonl")
        arq.parent.mkdir(parents=True, exist_ok=True)
        reg = {"em": agora, "alvo": d["id"], "modulo": d["modulo"], "decisao": d["decisao"], "motivo": P.redigir(d["motivo"], 160), "nota": d["nota"],
               "componentes": d["componentes"], "recursos": sorted({_codigo(r) for r in recursos})}
        with open(arq, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    except (OSError, ValueError, TypeError) as e:
        _ERROS["n"] += 1
        _ERROS["ultimo"] = f"{type(e).__name__}"[:80]


def decisoes_recentes(n=5):
    """As últimas decisões registradas (para a voz e o painel). Sem conteúdo."""
    if not M.ativo():
        return []
    try:
        arq = M.base() / ".cerebro" / "coordenacao.jsonl"
        linhas = arq.read_text(encoding="utf-8").splitlines()[-max(1, int(n)):]
    except (OSError, ValueError):
        return []
    saida = []
    for l in linhas:
        try:
            x = json.loads(l)
        except ValueError:
            continue
        if isinstance(x, dict) and x.get("decisao") in DECISOES:
            saida.append({k: x.get(k) for k in ("em", "alvo", "modulo", "decisao", "motivo", "nota")})
    return saida


def resumo():
    return {"reservas": len(ocupados()), "erros": _ERROS["n"]}


def falar():
    r = decisoes_recentes(5)
    oc = ocupados()
    if not r and not oc:
        return "Não coordenei nada ainda: só entro quando há mais de uma coisa para fazer, ou uma que bate em outra."
    partes = []
    if oc:
        partes.append("em uso agora: " + "; ".join(f"{o['ferramenta']} ({o['dono']})" for o in oc[:3]))
    for d in reversed(r):
        partes.append(f"{d['alvo']}: {d['decisao'].replace('_', ' ')} — {d['motivo']}")
    return ("Minhas últimas decisões — " + " | ".join(partes))[:900]


_PERG = ("o que voce esta coordenando", "o que voce coordenou", "por que voce fez isso primeiro", "suas decisoes de coordenacao", "decisoes de coordenacao")


def tratar(texto):
    """Só lê. «o que você está coordenando?»"""
    if not isinstance(texto, str) or len(texto) > 120:
        return None
    f = M._fold(" ".join(texto.split()).rstrip(".!? "))
    return falar() if f in _PERG else None
