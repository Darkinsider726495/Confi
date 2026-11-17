"""Base de um neurônio: uma responsabilidade, ações nomeadas, entradas e saídas em JSON.

Um neurônio NÃO sabe onde roda. Quem o hospeda é um `Worker` (transporte.py), que pode estar no mesmo processo do hub (modo local) ou em outro processo
(modo distribuído). Por isso um neurônio só recebe e devolve JSON puro e nunca chama outro neurônio diretamente: pedir algo a outro módulo é papel do hub.

Para criar um neurônio novo: herde de `Neuronio`, preencha os textos de descrição, escreva métodos `acao_<nome>(self, corpo, ctx)` que devolvem um dict e registre a
classe em `catalogo_neuronios.py` (docs/PRE_CORTEX.md, «Como adicionar um neurônio»).
"""
from . import contrato as C


class Contexto:
    """O que um tratador pode consultar sobre a mensagem que está processando."""
    __slots__ = ("mensagem", "correlacao", "plano", "_cancelado", "worker", "neuronio")

    def __init__(self, mensagem, cancelado, worker, neuronio):
        self.mensagem, self.correlacao, self.plano = mensagem, mensagem.get("correlacao"), mensagem.get("plano")
        self._cancelado, self.worker, self.neuronio = cancelado, worker, neuronio

    def cancelado(self):
        """Verdadeiro se o objetivo foi cancelado: tratadores longos conferem isto entre as etapas e param."""
        return bool(self._cancelado())

    def conferir_cancelamento(self):
        if self.cancelado():
            raise C.ErroNeuronio("cancelada", "o objetivo foi cancelado; parei antes de terminar")


class Neuronio:
    nome = ""
    papel = ""             # uma frase: o que este neurônio faz
    responsabilidade = ""  # o que é dele e o que NÃO é
    entradas = ""
    saidas = ""
    confianca = ""         # quanto e por que se pode confiar no que ele devolve
    critico = True         # False = o fluxo pode seguir em modo degradado, de forma segura, sem ele
    no_hub = False         # True = precisa ficar no processo do hub (usa corretor, tarefas ou cofre)
    numero = 0             # ordem na lista dos nove da missão (só para exibir)
    por_mensagem = True    # False = o neurônio é o próprio motor do hub (só a coordenação/execução): não recebe mensagens, mas aparece no mapa e na documentação

    def acoes(self):
        return sorted(n[5:] for n in dir(self) if n.startswith("acao_") and callable(getattr(self, n)))

    def receber_evento(self, evento, ctx):
        """Gancho opcional de pub/sub. Eventos são metadados; não autorizam ações nem substituem pedidos.

        A implementação padrão mantém uma janela curta de metadados compartilhados.
        Neurônios interessados podem sobrescrever este método, chamar super() e
        enriquecer seu contexto local. Nunca recebe texto bruto do usuário.
        """
        import copy
        from collections import deque
        if not hasattr(self, "_eventos_contexto"):
            self._eventos_contexto = deque(maxlen=32)
        if isinstance(evento, dict):
            self._eventos_contexto.append(copy.deepcopy(evento))

    def eventos_recentes(self, limite=10):
        """Cópia dos últimos metadados de eventos recebidos por este neurônio."""
        import copy
        eventos = list(getattr(self, "_eventos_contexto", ()))
        try:
            n = max(0, min(32, int(limite)))
        except (TypeError, ValueError):
            n = 10
        return copy.deepcopy(eventos[-n:]) if n else []

    def tratar(self, acao, corpo, ctx):
        f = getattr(self, "acao_" + acao, None) if isinstance(acao, str) and acao.isidentifier() else None
        if f is None or not callable(f):
            raise C.ErroNeuronio("acao_desconhecida", f"o neurônio «{self.nome}» não tem a ação «{str(acao)[:40]}»")
        saida = f(corpo, ctx)
        if not isinstance(saida, dict):
            raise C.ErroNeuronio("erro_interno", f"a ação «{acao}» devolveu {type(saida).__name__}, não um objeto")
        return saida

    def descricao(self):
        return {"nome": self.nome, "numero": self.numero, "papel": self.papel, "responsabilidade": self.responsabilidade, "entradas": self.entradas,
                "saidas": self.saidas, "confianca": self.confianca, "critico": self.critico, "no_hub": self.no_hub, "por_mensagem": self.por_mensagem, "acoes": self.acoes()}
