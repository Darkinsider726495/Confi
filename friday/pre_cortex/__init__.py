"""Pré-córtex cognitivo distribuído da FRIDAY (Fase 7).

Um conjunto de «neurônios» de software (módulos com responsabilidade, contrato de mensagens e estado próprios) que colaboram para analisar um objetivo,
levantar hipóteses, planejar, ser criticado por um módulo independente, executar pelo corretor, conferir o resultado por fora e aprender com a diferença
entre o previsto e o observado. É engenharia, não consciência: nada aqui sente, quer ou sofre; «aprender» é registrar o que aconteceu, com condições e
contagem, e usar isso para ORDENAR estratégias que o catálogo (código) já permite. Quem executa continua sendo o corretor (docs/PRE_CORTEX.md).

Este arquivo é leve de propósito: um trabalhador (processo separado) importa o pacote sem trazer o corretor, as tarefas nem o cofre.
O que o app usa (hub, voz, painel) fica em `fachada.py`, que só é carregado por quem o importa (`import pre_cortex.fachada`).
"""
import os
import sys

_FRIDAY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FRIDAY not in sys.path:          # os módulos da FRIDAY (broker, tarefas…) são «de topo»: `python -m friday.pre_cortex.x` precisa enxergá-los
    sys.path.append(_FRIDAY)

VERSAO_PACOTE = "1.0"
