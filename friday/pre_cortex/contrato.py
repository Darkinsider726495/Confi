"""Contrato das mensagens entre neurônios (versão «precortex/1»).

Toda comunicação entre módulos — dentro do mesmo processo (modo local) ou entre processos (modo distribuído) — usa o MESMO envelope JSON. O modo local
também serializa e desserializa cada mensagem, para que um objeto que não cabe em JSON falhe nos testes locais e não só no modo distribuído.

Pedido:
  contrato        «precortex/1»
  id              único (a mesma mensagem reenviada depois de uma falha mantém o MESMO id: é assim que o destinatário reconhece duplicata)
  tipo            pedido | resposta | cancelar | evento
  correlacao      id do objetivo (pcNNNN): junta tudo o que pertence a ele
  plano           {id, versao} do plano a que a mensagem se refere (ou null)
  de, para        emissor e destinatário (nome do neurônio ou do hub)
  acao            o que o destinatário deve fazer (ex.: «interpretar»)
  criada_em       relógio de quem criou (segundos, época Unix)
  expira_em       prazo de validade: depois dele o destinatário NÃO processa mais (resposta «expirada»)
  timeout_s       quanto o emissor espera por resposta em cada tentativa
  tentativa       1, 2, 3… (informativo; não muda o id)
  em_resposta_a   (respostas) id do pedido
  estado          criada | enviada | recebida | processando | concluida | falhou | expirada | cancelada | duplicada
  corpo           o conteúdo (objeto JSON)
Resposta: os mesmos campos mais ok, erro {codigo, mensagem}, processado_por {worker, pid, neuronio}, tempos {recebida_em, iniciada_em, concluida_em, duracao_ms}, duplicada.

Entrega «ao menos uma vez»: o emissor pode reenviar (mesmo id) e o destinatário pode receber duas vezes; por isso os neurônios cognitivos são idempotentes e o
destinatário guarda as respostas já dadas (dedupe). Ações que não podem repetir (executar pelo corretor) NÃO dependem disso: o hub registra antes de executar.
"""
import hashlib
import json
import re
import time
import uuid

VERSAO = "precortex/1"
TAMANHO_MAX = 256 * 1024
TIPOS = ("pedido", "resposta", "cancelar", "evento")
ESTADOS = ("criada", "enviada", "recebida", "processando", "concluida", "falhou", "expirada", "cancelada", "duplicada")
FINAIS = ("concluida", "falhou", "expirada", "cancelada")
CODIGOS = ("contrato_invalido", "expirada", "neuronio_desconhecido", "acao_desconhecida", "cancelada", "timeout", "indisponivel", "erro_interno",
           "entrada_invalida", "recusada", "dependencia_ausente")
RECUPERAVEIS = ("timeout", "indisponivel")          # vale tentar de novo com o mesmo id
_ID = re.compile(r"[a-z]{1,6}-[0-9a-f]{8,32}")
_NOME = re.compile(r"[a-z][a-z0-9_]{0,31}")
_CORR = re.compile(r"[a-z0-9][a-z0-9_.\-]{0,39}")
_ACAO = re.compile(r"[a-z][a-z0-9_]{0,40}")


def novo_id(prefixo="m"):
    return f"{prefixo}-{uuid.uuid4().hex[:16]}"


def canonico(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_de(obj):
    """Impressão digital estável de um objeto JSON (a mesma entrada dá sempre o mesmo valor)."""
    return hashlib.sha256(canonico(obj).encode("utf-8")).hexdigest()[:32]


def hash_plano(plano):
    """Hash do plano sem o próprio hash e sem o instante de geração: qualquer mudança no resto muda o valor. A crítica e a autorização se prendem a ele."""
    p = {k: v for k, v in plano.items() if k not in ("hash", "gerado_em")}
    return hash_de(p)


def ida_e_volta(obj):
    """Passa pelo JSON como passaria pela rede. Levanta ValueError se o objeto não é JSON puro."""
    try:
        return json.loads(json.dumps(obj, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as e:
        raise ValueError(f"conteúdo não serializável em JSON: {e}") from None


def criar(de, para, acao, corpo, *, correlacao, plano=None, timeout_s=10.0, validade_s=None, tentativa=1, tipo="pedido", em_resposta_a=None, id=None, agora=None):
    t = time.time() if agora is None else agora
    validade = float(validade_s) if validade_s is not None else float(timeout_s) * 3 + 5.0
    return {"contrato": VERSAO, "id": id or novo_id("m"), "tipo": tipo, "correlacao": correlacao, "plano": plano, "de": de, "para": para, "acao": acao,
            "criada_em": t, "expira_em": t + validade, "timeout_s": float(timeout_s), "tentativa": int(tentativa), "em_resposta_a": em_resposta_a,
            "estado": "criada", "corpo": corpo if corpo is not None else {}}


def _num(v, a, b):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and a <= v <= b


def validar(msg):
    """(ok, motivo). Confere forma, tipos e tamanho; não confere se o destinatário existe."""
    if not isinstance(msg, dict):
        return False, "a mensagem não é um objeto JSON"
    if msg.get("contrato") != VERSAO:
        return False, f"contrato {str(msg.get('contrato'))[:20]!r} não é {VERSAO!r}"
    if msg.get("tipo") not in TIPOS:
        return False, "tipo inválido"
    if not isinstance(msg.get("id"), str) or not _ID.fullmatch(msg["id"]):
        return False, "id inválido"
    if not isinstance(msg.get("correlacao"), str) or not _CORR.fullmatch(msg["correlacao"]):
        return False, "correlacao inválida"
    for campo in ("de", "para"):
        if not isinstance(msg.get(campo), str) or not _NOME.fullmatch(msg[campo]):
            return False, f"{campo} inválido"
    if not isinstance(msg.get("acao"), str) or not _ACAO.fullmatch(msg["acao"]):
        return False, "acao inválida"
    if not _num(msg.get("criada_em"), 0, 1e12) or not _num(msg.get("expira_em"), 0, 1e12):
        return False, "horários inválidos"
    if msg["expira_em"] < msg["criada_em"]:
        return False, "prazo de validade anterior à criação"
    if not _num(msg.get("timeout_s"), 0.01, 3600):
        return False, "timeout_s inválido"
    if not isinstance(msg.get("tentativa"), int) or isinstance(msg.get("tentativa"), bool) or not 1 <= msg["tentativa"] <= 100:
        return False, "tentativa inválida"
    pl = msg.get("plano")
    if pl is not None and not (isinstance(pl, dict) and isinstance(pl.get("id"), str) and isinstance(pl.get("versao"), int) and not isinstance(pl.get("versao"), bool)):
        return False, "plano inválido (precisa de id e versao)"
    if not isinstance(msg.get("corpo"), dict):
        return False, "corpo precisa ser um objeto"
    try:
        n = len(json.dumps(msg, ensure_ascii=False))
    except (TypeError, ValueError):
        return False, "a mensagem não é JSON puro"
    if n > TAMANHO_MAX:
        return False, f"mensagem grande demais ({n} bytes; máximo {TAMANHO_MAX})"
    return True, ""


def resposta(pedido, *, de, ok, corpo=None, erro=None, estado=None, processado_por=None, tempos=None, duplicada=False, agora=None):
    """Monta a resposta a um pedido. `erro` = (codigo, mensagem) quando ok é falso."""
    t = time.time() if agora is None else agora
    if estado is None:
        estado = "concluida" if ok else "falhou"
    return {"contrato": VERSAO, "id": novo_id("r"), "tipo": "resposta", "correlacao": pedido.get("correlacao"), "plano": pedido.get("plano"), "de": de,
            "para": pedido.get("de"), "acao": pedido.get("acao"), "criada_em": t, "expira_em": t + 60.0, "timeout_s": float(pedido.get("timeout_s") or 1.0),
            "tentativa": int(pedido.get("tentativa") or 1), "em_resposta_a": pedido.get("id"), "estado": estado, "ok": bool(ok),
            "corpo": corpo if ok and corpo is not None else {}, "erro": None if ok else {"codigo": erro[0], "mensagem": str(erro[1])[:300]},
            "processado_por": processado_por or {}, "tempos": tempos or {}, "duplicada": bool(duplicada)}


class ErroNeuronio(Exception):
    """Um neurônio recusou ou não conseguiu a ação, de um jeito esperado (entrada inválida, dependência ausente…). Vira resposta de erro, não queda."""

    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        assert codigo in CODIGOS, codigo
        self.codigo, self.mensagem = codigo, str(mensagem)
