"""Registro dos neurônios e onde cada um roda por padrão.

Adicionar um neurônio: crie a classe (herde de `Neuronio`), liste-a em `CLASSES` e, se ela mora no hub, em `NO_HUB` (precisa do corretor, das tarefas ou do cofre)
ou em algum trabalhador. O hub descobre as ações, a criticidade e o trabalhador por aqui (docs/PRE_CORTEX.md, «Como adicionar um neurônio»).
"""
import importlib

from .neuronio import Neuronio



class Coordenacao(Neuronio):
    """Neurônio 6: é o motor do hub. Não recebe mensagens; decide a ordem das fases, o paralelismo, as tentativas e a autorização, e é o ÚNICO que alcança o corretor."""
    nome = "coordenacao"
    numero = 6
    no_hub = True
    por_mensagem = False
    papel = "coordena as fases, pede autorização e executa pelo corretor sem repetir o que não pode repetir"
    responsabilidade = ("Ordenar as fases e o que roda em paralelo; reenviar mensagens com o mesmo id; aplicar os limites (tentativas, tempo, nós, replanejamentos); parar quando um módulo crítico "
                        "falha; exigir a autorização presa ao hash do plano; registrar a execução ANTES de agir e executar só pelo corretor (tarefas). NÃO decide sozinha o que é seguro "
                        "(isso é da crítica), NÃO prova o efeito (isso é do verificador) e NÃO tem permissão própria (a do corretor vale).")
    entradas = "respostas dos outros neurônios + decisões do dono (autorizar, negar, cancelar, aceitar)"
    saidas = "mensagens, execução pelo corretor, eventos e o dossiê do objetivo"
    confianca = "determinística; as garantias (sem duplicar, sem pular a crítica) são testadas, não prometidas"


# nome do neurônio -> (módulo, classe). A carga é PREGUIÇOSA de propósito: um processo trabalhador só importa os neurônios que hospeda, e os que usam o corretor, as tarefas
# ou o cofre (contexto, aprendizagem) nunca entram nele.
CLASSES = {"percepcao": ("percepcao", "Percepcao"), "contexto": ("contexto", "ContextoMemoria"), "hipoteses": ("hipoteses", "Hipoteses"), "planejamento": ("planejamento", "Planejamento"),
           "critica": ("critica", "Critica"), "verificador": ("verificador", "Verificador"), "aprendizagem": ("aprendizagem", "Aprendizagem"), "monitor": ("monitor", "Monitor")}
# trabalhadores padrão do modo local e do distribuído (a coordenação/execução, o nono «neurônio» de execução, é do hub e não aparece aqui: ela não é uma mensagem, é o corretor)
GRUPOS_PADRAO = {"cognicao": ("percepcao", "hipoteses", "planejamento"), "revisao": ("critica", "verificador")}
NO_HUB = ("contexto", "aprendizagem", "monitor")


def classe(nome):
    mod, cls = CLASSES[nome]
    return getattr(importlib.import_module("." + mod, __package__), cls)


def novos(nomes=None):
    """Instâncias novas dos neurônios que falam por mensagem (uma por classe), filtradas por nome se `nomes` vier. Só importa o que foi pedido."""
    return [classe(n)() for n in CLASSES if nomes is None or n in nomes]


def descricoes():
    """Os nove da missão, em ordem (a coordenação aparece como o sexto, mesmo sem falar por mensagem)."""
    return [n.descricao() for n in sorted(novos() + [Coordenacao()], key=lambda x: x.numero)]


def criticos():
    return {n.nome: n.critico for n in novos()}
