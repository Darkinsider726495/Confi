"""Neurônio 1 — Percepção e interpretação.

Recebe o pedido em linguagem natural e devolve um objetivo ESTRUTURADO: o tipo, os parâmetros, o que foi dito de fato (fato), o que foi deduzido (inferência),
o que foi suposto por falta de informação (hipótese) e o que falta (desconhecido). Nunca preenche lacuna em silêncio: uma suposição aparece com esse nome.
Também classifica os EFEITOS do pedido: um pedido que sai do aparelho (mensagem, ligação, compra, instalação, comando, internet, apagar) é marcado como externo e,
mais adiante, só anda com autorização do dono. Este módulo só lê texto: não conhece o corretor, o cofre nem as tarefas.

Backend determinístico: regras em expressões regulares, sem modelo de linguagem. A «confiança» é a fração dos campos que vieram escritos no pedido — uma conta simples,
não uma probabilidade calibrada, e o resultado diz isso.
"""
import re
import unicodedata

from . import conhecimento as K
from . import contrato as C
from .neuronio import Neuronio

FATO, INFERENCIA, HIPOTESE, DESCONHECIDO = "fato", "inferencia", "hipotese", "desconhecido"
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12}
_NUM_RE = r"(\d{1,2}|" + "|".join(_NUM) + r")"

EXTERNOS = (
    ("envio_de_mensagem", re.compile(r"\b(?:envi(?:e|ar|a)|mand(?:e|ar|a))\b.*\b(?:mensagem|sms|whatsapp|zap|e-?mail)\b|\b(?:sms|whatsapp|zap)\b.*\b(?:para|pra|pro)\b")),
    ("ligacao", re.compile(r"\b(?:lig(?:ue|ar|a)|telefon(?:e|ar))\b.*\b(?:para|pra|pro)\b")),
    ("compra_ou_pagamento", re.compile(r"\b(?:compr(?:e|ar)|pag(?:ue|ar)|pix|transfir(?:a|ir))\b")),
    ("instalacao", re.compile(r"\b(?:instal(?:e|ar)|pip install|apt(?:-get)? install)\b")),
    ("comando_ou_script", re.compile(r"\b(?:execut(?:e|ar)|rod(?:e|ar))\b.*\b(?:comando|script|programa|codigo|terminal)\b|\bsudo\b|\brm -")),
    ("internet", re.compile(r"\b(?:baix(?:e|ar)|download|navegu?e|acess(?:e|ar) (?:o )?site)\b|\bpesquis(?:e|ar)\b.*\b(?:web|internet|google)\b")),
    ("apagar", re.compile(r"\b(?:apag(?:ue|ar)|delet(?:e|ar)|remov(?:a|er)|exclu(?:a|ir))\b")),
)
FERRAMENTA_DA_CATEGORIA = {"envio_de_mensagem": "enviar_sms", "ligacao": "ligar"}      # as demais não têm ferramenta no catálogo: só viram proposta
_REGISTRAR = re.compile(r"\b(?:registr\w+|salv\w+|guard\w+|anot\w+|memoriz\w+|memoria)\b")
_ESTUDO = re.compile(r"\b(?:plano|roteiro|cronograma|curso)\b.*\b(?:estud\w+|aprend\w+)\b|\b(?:estud\w+|aprend\w+)\b|\bplano de estud\w+")
_ANOTAR = re.compile(r"^\s*(?:por favor,?\s*)?(?:anot(?:e|ar|a)|registr(?:e|ar)|guard(?:e|ar)|salv(?:e|ar))\s+(?:que\s+|isto:?\s*|isso:?\s*|o seguinte:?\s*)?(.+)$", re.S)


def _fold(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _semanas(f):
    m = re.search(_NUM_RE + r"\s+semanas?\b", f)
    if m:
        v = m.group(1)
        return (int(v) if v.isdigit() else _NUM[v]), FATO, m.group(0)
    m = re.search(_NUM_RE + r"\s+mes(?:es)?\b", f)
    if m:
        v = m.group(1)
        n = int(v) if v.isdigit() else _NUM[v]
        return n * 4, INFERENCIA, f"«{m.group(0)}» entendido como {n * 4} semanas"
    return None, DESCONHECIDO, ""


def _minutos(f):
    achados = []
    for m in re.finditer(r"\b(\d{1,2})\s*h\s*(\d{1,2})\b", f):
        achados.append((m.start(), int(m.group(1)) * 60 + int(m.group(2)), m.group(0)))
    for m in re.finditer(r"\b(\d{1,2}(?:[.,]\d)?)\s*horas?\b", f):
        achados.append((m.start(), int(round(float(m.group(1).replace(",", ".")) * 60)), m.group(0)))
    for m in re.finditer(r"\b(\d{1,3})\s*(?:min|minutos?)\b", f):
        achados.append((m.start(), int(m.group(1)), m.group(0)))
    for m in re.finditer(r"\bmeia hora\b", f):
        achados.append((m.start(), 30, m.group(0)))
    if not achados:
        return None, DESCONHECIDO, ""
    chaves = [m.start() for m in re.finditer(r"\bpor dia\b|\bao dia\b|\bdiari\w+|\bpor dia\b|\blimite\b|\bno maximo\b", f)]
    achados.sort(key=lambda a: min([abs(a[0] - k) for k in chaves] or [999]))
    pos, minutos, trecho = achados[0]
    perto = chaves and min(abs(pos - k) for k in chaves) <= 45
    return minutos, (FATO if perto else INFERENCIA), (trecho if perto else f"«{trecho}» entendido como o tempo por dia")


def classificar_efeitos(f):
    cats = [c for c, rx in EXTERNOS if rx.search(f)]
    return {"externo": bool(cats), "categorias": cats}


class Percepcao(Neuronio):
    nome = "percepcao"
    numero = 1
    papel = "transforma o pedido em objetivo estruturado"
    responsabilidade = ("Interpretar o texto do pedido: tipo, parâmetros, restrições, efeitos externos; separar fato, inferência, suposição e desconhecido. "
                        "NÃO decide o que fazer, não planeja e não executa.")
    entradas = "texto do pedido + origem"
    saidas = "objetivo estruturado (tipo, parâmetros, campos tipados, efeitos, faltando, critérios de conclusão)"
    confianca = "regras determinísticas; a «confiança» é a fração de campos escritos no pedido, não uma probabilidade calibrada"

    def acao_interpretar(self, corpo, ctx):
        return {"interpretacao": self._interpretar(corpo)}

    def _interpretar(self, corpo):
        texto = corpo.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise C.ErroNeuronio("entrada_invalida", "falta o texto do pedido")
        texto = " ".join(texto.split())[:1000]
        f = _fold(texto)
        efeitos = classificar_efeitos(f)
        campos, faltando, suposicoes, restricoes = [], [], [], []
        base = {"texto_original": texto, "efeitos": efeitos}

        if efeitos["externo"]:
            return {**base, **self._externo(texto, f, efeitos)}
        m_anotar = _ANOTAR.match(texto)
        topico = next((t for t in K.topicos() if re.search(r"\b" + re.escape(t) + r"\b", f)), None)
        if _ESTUDO.search(f) and (topico or re.search(r"\bplano\b", f)):
            return {**base, **self._estudo(texto, f, topico, efeitos)}
        if m_anotar and len(m_anotar.group(1).strip()) >= 1:
            conteudo = m_anotar.group(1).strip()
            campos = [{"nome": "texto", "valor": conteudo[:2000], "tipo": FATO, "fonte": "trecho do pedido"}]
            return {**base, "tipo_objetivo": "registrar_informacao", "suportado": True, "motivo_nao_suportado": None, "parametros": {"texto": conteudo[:2000]}, "campos": campos,
                    "faltando": [], "suposicoes": [], "restricoes": [], "efeitos": {**efeitos, "escrita_local": True},
                    "resultado_esperado": "o texto fica guardado e pode ser achado depois", "criterios_de_conclusao": ["o texto pedido relido do armazenamento sem perda"],
                    "confianca": {"valor": 1.0, "calibrada": False, "regra": "fração dos campos que vieram escritos no pedido (1 de 1)"}, "pede_esclarecimento": None, "registrar": True}
        return {**base, "tipo_objetivo": "desconhecido", "suportado": False, "motivo_nao_suportado": "não reconheci um objetivo que eu saiba planejar (plano de estudo, registrar uma informação)",
                "parametros": {}, "campos": [], "faltando": ["tipo_de_objetivo"], "suposicoes": [], "restricoes": [], "efeitos": {**efeitos, "escrita_local": False},
                "resultado_esperado": "", "criterios_de_conclusao": [], "confianca": {"valor": 0.0, "calibrada": False, "regra": "nenhum tipo reconhecido"},
                "pede_esclarecimento": "Diga, por exemplo: «elabore um plano de estudos de Python para 4 semanas, no máximo 90 minutos por dia, e registre» ou «anote que …».", "registrar": False}

    def _estudo(self, texto, f, topico, efeitos):
        campos, faltando, suposicoes, restricoes = [], [], [], []
        if topico:
            campos.append({"nome": "topico", "valor": topico, "tipo": FATO, "fonte": f"«{topico}» no pedido"})
        else:
            faltando.append("topico")
        sem, t_sem, fonte_sem = _semanas(f)
        if sem is not None:
            campos.append({"nome": "semanas", "valor": sem, "tipo": t_sem, "fonte": fonte_sem})
            restricoes.append(f"{sem} semana{'s' if sem > 1 else ''}")
        else:
            faltando.append("semanas")
        mi, t_min, fonte_min = _minutos(f)
        if mi is not None:
            campos.append({"nome": "minutos_dia", "valor": mi, "tipo": t_min, "fonte": fonte_min})
            restricoes.append(f"no máximo {mi} min por dia")
        else:
            faltando.append("minutos_dia")
        registrar = bool(_REGISTRAR.search(f))
        campos.append({"nome": "registrar", "valor": registrar, "tipo": FATO if registrar else INFERENCIA,
                       "fonte": "pedido de registrar/guardar no texto" if registrar else "o pedido não mandou guardar: só montar o plano"})
        suportado, motivo = True, None
        params = {c["nome"]: c["valor"] for c in campos}
        if not topico:
            suportado, motivo = False, "não reconheci o assunto do estudo (sei: " + ", ".join(K.topicos()) + ")"
        else:
            if sem is None:
                params["semanas"] = 4
                suposicoes.append({"campo": "semanas", "valor": 4, "tipo": HIPOTESE, "motivo": "você não disse a duração; assumi 4 semanas (confirme)"})
            if mi is None:
                params["minutos_dia"] = K.PADRAO_MINUTOS
                suposicoes.append({"campo": "minutos_dia", "valor": K.PADRAO_MINUTOS, "tipo": HIPOTESE, "motivo": f"você não disse o limite diário; assumi {K.PADRAO_MINUTOS} min (confirme)"})
            if not 1 <= params["semanas"] <= K.MAX_SEMANAS:
                suportado, motivo = False, f"só monto planos de 1 a {K.MAX_SEMANAS} semanas"
            elif not K.MIN_MINUTOS <= params["minutos_dia"] <= K.MAX_MINUTOS:
                suportado, motivo = False, f"o limite diário precisa ficar entre {K.MIN_MINUTOS} e {K.MAX_MINUTOS} minutos"
        explicitos = sum(1 for c in campos if c["nome"] in ("topico", "semanas", "minutos_dia") and c["tipo"] == FATO)
        crit = []
        if suportado:
            s, m = params["semanas"], params["minutos_dia"]
            crit = [f"plano com {s} semana(s) e {s * 7} dias", f"nenhum dia acima de {m} minutos"]
            if params["registrar"]:
                crit.append("plano registrado e relido do armazenamento sem perda")
        return {"tipo_objetivo": "plano_de_estudo", "suportado": suportado, "motivo_nao_suportado": motivo, "parametros": params, "campos": campos, "faltando": faltando,
                "suposicoes": suposicoes, "restricoes": restricoes, "efeitos": {**efeitos, "escrita_local": bool(params.get("registrar"))},
                "resultado_esperado": (f"plano de estudo de {K.CURRICULOS[topico]['nome']} com {params['semanas']} semana(s), respeitando {params['minutos_dia']} min por dia"
                                       + (", guardado e conferido" if params.get("registrar") else ", apresentado sem ser guardado")) if suportado else "",
                "criterios_de_conclusao": crit,
                "confianca": {"valor": round(explicitos / 3, 2), "calibrada": False, "regra": f"{explicitos} de 3 campos principais (assunto, semanas, minutos) vieram escritos no pedido"},
                "pede_esclarecimento": None if suportado else motivo, "registrar": bool(params.get("registrar"))}

    def _externo(self, texto, f, efeitos):
        cats = efeitos["categorias"]
        contato = None
        m = re.search(r"\b(?:para|pra|pro)\s+(?:a |o )?([a-z]{2,20})", f)
        if m:
            contato = m.group(1)
        ferr = next((FERRAMENTA_DA_CATEGORIA[c] for c in cats if c in FERRAMENTA_DA_CATEGORIA), None)
        params = {"categorias": cats, "texto_pedido": texto[:300]}
        if contato:
            params["contato"] = contato
        mensagem = None
        mm = re.search(r"\b(?:dizendo|avisando|falando|contando|informando)(?:\s+que)?[:\s]+(.{2,300})$", texto.strip(), re.I | re.S)
        if mm:
            mensagem = " ".join(mm.group(1).split()).strip(" .")
            if mensagem:
                params["mensagem"] = mensagem
        motivo = "o pedido sai do aparelho ou altera algo fora do cofre: " + ", ".join(cats)
        return {"tipo_objetivo": "acao_externa", "suportado": True, "motivo_nao_suportado": None, "parametros": params,
                "campos": [{"nome": "categorias", "valor": cats, "tipo": FATO, "fonte": "palavras do pedido"}] + ([{"nome": "contato", "valor": contato, "tipo": INFERENCIA, "fonte": "nome depois de «para»"}] if contato else [])
                + ([{"nome": "mensagem", "valor": mensagem, "tipo": FATO, "fonte": "trecho do pedido depois de «dizendo que»/«avisando que»"}] if mensagem else []),
                "faltando": ([] if contato or not ferr else ["contato"]) + ([] if mensagem or ferr != "enviar_sms" else ["mensagem"]), "suposicoes": [], "restricoes": ["exige autorização do dono antes de qualquer execução"],
                "efeitos": {**efeitos, "escrita_local": False, "motivo": motivo, "ferramenta_possivel": ferr},
                "resultado_esperado": "uma PROPOSTA de plano; nada é executado sem a autorização do dono e a confirmação do corretor",
                "criterios_de_conclusao": ["o dono autorizou o plano exato", "o corretor confirmou a ação"] if ferr else ["não há ferramenta no catálogo para isto: só proposta"],
                "confianca": {"valor": 0.5, "calibrada": False, "regra": "classificação por palavras; o conteúdo exato da ação não foi interpretado"},
                "pede_esclarecimento": None, "registrar": False}
