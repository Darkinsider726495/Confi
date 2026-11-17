"""Registro estruturado de um objetivo (o «dossiê»): o estado compartilhado entre os neurônios.

Campos pedidos pela missão: identificador, descrição, origem, resultado esperado, prioridade, restrições, recursos, estado, próxima etapa, dependências, histórico de decisões e critérios
de conclusão. Mais: a fase, o grafo de etapas com estado de cada uma, os resultados de cada neurônio (interpretação, contexto, hipóteses, planos, críticas, verificações, aprendizado), os usos
(tentativas, tempo, mensagens) e o bloqueio, quando houver.

Não há dois sistemas de objetivos: o dossiê é o registro rico dos objetivos COMPOSTOS do pré-córtex; ele se liga às peças que já existem (tarefas para executar, experiências para lembrar,
coordenador para recursos, retomada para recuperar, metas do pré-frontal por id, `objetivos.py` para as propostas de ferramenta da própria IA) e não as substitui (docs/PRE_CORTEX.md).
"""
import re

ORIGENS = ("pedido_do_dono", "sugerido_pelo_sistema", "aceito_para_execucao")
PRIORIDADES = ("baixa", "normal", "alta")
ESTADOS = ("recebido", "aguardando_aceite", "em_andamento", "aguardando_autorizacao", "aguardando_confirmacao_do_corretor", "aguardando_execucao", "plano_pronto",
           "precisa_do_dono", "concluido", "bloqueado", "cancelado")
FINAIS = ("concluido", "cancelado")
PARADOS = ("aguardando_aceite", "aguardando_autorizacao", "aguardando_confirmacao_do_corretor", "aguardando_execucao", "plano_pronto", "precisa_do_dono", "bloqueado")
FASES = ("interpretacao", "conhecimento", "hipoteses", "plano", "revisao", "autorizacao", "execucao", "verificacao", "aprendizagem", "decisao", "fim")
ID_OBJETIVO = re.compile(r"pc\d{4,6}")
ROTULO_ESTADO = {"recebido": "recebido", "aguardando_aceite": "esperando o dono aceitar", "em_andamento": "em andamento", "aguardando_autorizacao": "esperando a autorização do dono",
                 "aguardando_confirmacao_do_corretor": "esperando a confirmação do corretor", "aguardando_execucao": "esperando a execução terminar", "plano_pronto": "plano pronto (não executado)",
                 "precisa_do_dono": "precisa do dono", "concluido": "concluído", "bloqueado": "bloqueado", "cancelado": "cancelado"}


def novo(pcid, descricao, *, agora, origem="pedido_do_dono", prioridade="normal", so_planejar=False, meta=None, limites=None):
    if origem not in ORIGENS:
        raise ValueError("origem inválida")
    if prioridade not in PRIORIDADES:
        prioridade = "normal"
    return {"id": pcid, "descricao": " ".join(str(descricao).split())[:1000], "origem": origem, "origem_aceita": origem != "sugerido_pelo_sistema", "prioridade": prioridade,
            "criado_em": agora, "atualizado_em": agora, "so_planejar": bool(so_planejar), "meta": meta, "estado": "recebido", "fase": "interpretacao", "proxima_etapa": "interpretar o pedido",
            "restricoes": [], "recursos": [], "resultado_esperado": "", "criterios_de_conclusao": [], "dependencias": [], "historico_decisoes": [], "limites": dict(limites or {}),
            "uso": {"mensagens": 0, "nos": 0, "replanos": 0, "revisoes_critica": 0, "inicio": agora, "pausas_s": 0.0, "pausa_desde": None}, "grafo": [], "ciclo": 0,
            "interpretacao": None, "contexto": None, "conteudo": None, "hipoteses": None, "coerencia": None, "planos": [], "plano_atual": None, "tentativas_anteriores": [],
            "execucoes": {}, "verificacoes": [], "aprendizados": [], "no_interpretacao": None, "motivo_revisao": None, "autorizacao": None, "autorizacao_concedida": None, "resultado_final": None, "bloqueio": None, "cancelado": False,
            "degradado": [], "ritmo_pausas": 0}


def decisao(d, quem, texto, motivo, agora, dados=None):
    """Acrescenta ao histórico de decisões (limitado a 80 entradas no dossiê vivo; o arquivo de eventos guarda tudo)."""
    d["historico_decisoes"].append({"em": agora, "quem": quem, "decisao": texto, "motivo": motivo, **({"dados": dados} if dados else {})})
    del d["historico_decisoes"][:-80]
    d["atualizado_em"] = agora


def plano_atual(d):
    for p in d["planos"]:
        if p["versao"] == d["plano_atual"]:
            return p
    return None


def resumo(d):
    """Versão curta (listas e painel)."""
    pa = plano_atual(d)
    return {"id": d["id"], "descricao": d["descricao"][:160], "origem": d["origem"], "estado": d["estado"], "rotulo": ROTULO_ESTADO.get(d["estado"], d["estado"]), "fase": d["fase"], "prioridade": d["prioridade"],
            "proxima_etapa": d["proxima_etapa"], "plano": {"versao": pa["versao"], "estrategia": pa["plano"].get("estrategia"), "hash": pa["hash"]} if pa else None,
            "criado_em": d["criado_em"], "atualizado_em": d["atualizado_em"], "so_planejar": d["so_planejar"], "bloqueio": d["bloqueio"], "replanos": d["uso"]["replanos"]}
