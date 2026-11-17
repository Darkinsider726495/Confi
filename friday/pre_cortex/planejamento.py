"""Neurônio 4 — Planejamento e previsão.

Duas ações:
  gerar_conteudo   produz o CONTEÚDO do objetivo (o plano de estudo, por regra determinística) — não depende das experiências, por isso roda em paralelo com o contexto.
  montar_plano     escolhe a estratégia que as hipóteses colocaram na frente e monta o PLANO com os dez campos: objetivo, estado inicial conhecido, etapas, justificativa de cada
                   etapa, resultado esperado, critérios de sucesso, riscos e incertezas, alternativas, condições para interromper ou pedir ajuda e critérios de verificação.
O plano só PROPÕE: nomeia uma estratégia do catálogo (o hub é quem traduz isso em passos e o corretor quem executa), traz a previsão do que a releitura independente deve encontrar
e assina o conteúdo com um hash (a crítica confere). Pode existir e não ser executado. Replanejar = montar outra versão com as evidências novas, sem repetir o que já falhou.
"""
import time

from . import conhecimento as CONH
from . import contrato as C
from .neuronio import Neuronio

TIPOS_ETAPA = ("verificacao_previa", "revisao", "autorizacao", "execucao", "verificacao", "aprendizagem", "entrega")


assinar = C.hash_plano


class Planejamento(Neuronio):
    nome = "planejamento"
    numero = 4
    papel = "produz o conteúdo e monta o plano com previsão, critérios e alternativas"
    responsabilidade = ("Gerar o conteúdo do objetivo e transformá-lo em plano com os dez campos, nomeando uma estratégia do catálogo e prevendo o que a verificação deve achar. "
                        "NÃO executa, NÃO autoriza e NÃO pode dispensar a crítica: o plano é uma proposta assinada por hash.")
    entradas = "interpretação, contexto, hipóteses comparadas, conteúdo, tentativas anteriores"
    saidas = "conteúdo; plano versionado com hash"
    confianca = "o conteúdo vem de um currículo-base interno (sem fonte externa); o plano é uma proposta até a crítica aprovar e a verificação conferir"

    # ------------------------------------------------------------------ conteúdo
    def acao_gerar_conteudo(self, corpo, ctx):
        interp = corpo.get("interpretacao")
        if not isinstance(interp, dict) or not interp.get("suportado"):
            raise C.ErroNeuronio("entrada_invalida", "o objetivo não foi entendido o bastante para gerar conteúdo")
        tipo, p = interp["tipo_objetivo"], interp.get("parametros") or {}
        ctx.conferir_cancelamento()
        if tipo == "plano_de_estudo":
            try:
                g = CONH.gerar_plano_estudo(p["topico"], int(p["semanas"]), int(p["minutos_dia"]))
            except (KeyError, ValueError, TypeError) as e:
                raise C.ErroNeuronio("entrada_invalida", f"não consegui gerar o plano: {e}") from None
            nome = CONH.CURRICULOS[p["topico"]]["nome"]
            return {"conteudo": {"tipo": tipo, "texto": g["texto"], "titulo": f"Plano de estudo {nome} {g['semanas']} semanas", "titulo_do_plano": g["titulo"], "tamanho": g["tamanho"],
                                 "tamanho_bytes": len(g["texto"].encode("utf-8")), "semanas": g["semanas"], "minutos_dia": g["minutos_dia"], "total_minutos": g["total_minutos"],
                                 "dias": len(g["dias"]), "fonte": g["fonte"], "hash": C.hash_de(g["texto"]), "gerado_por": "conhecimento.gerar_plano_estudo (determinístico)"}}
        if tipo == "registrar_informacao":
            return {"conteudo": {"tipo": tipo, "texto": p["texto"], "titulo": p.get("titulo") or "", "tamanho": len(p["texto"]), "tamanho_bytes": len(p["texto"].encode("utf-8")),
                                 "hash": C.hash_de(p["texto"]), "fonte": "texto do próprio pedido", "gerado_por": "cópia do pedido"}}
        if tipo == "acao_externa":
            return {"conteudo": {"tipo": tipo, "texto": p.get("mensagem") or "", "tamanho": len(p.get("mensagem") or ""), "hash": C.hash_de(p.get("mensagem") or ""),
                                 "fonte": "trecho do pedido", "gerado_por": "cópia do pedido"}}
        raise C.ErroNeuronio("entrada_invalida", f"tipo «{tipo}» sem gerador de conteúdo")

    # ------------------------------------------------------------------ plano
    def acao_montar_plano(self, corpo, ctx):
        interp, hip, cont = corpo.get("interpretacao"), corpo.get("hipoteses"), corpo.get("conteudo")
        obj = corpo.get("objetivo") or {}
        if not isinstance(interp, dict) or not isinstance(hip, dict) or not isinstance(cont, dict):
            raise C.ErroNeuronio("entrada_invalida", "faltam interpretação, hipóteses ou conteúdo")
        versao = int(corpo.get("versao") or 1)
        escolha = hip.get("escolha") or {}
        estrategia = escolha.get("escolhida")
        tipo = interp["tipo_objetivo"]
        executavel = bool(interp.get("registrar")) or (tipo == "acao_externa" and bool((interp.get("efeitos") or {}).get("ferramenta_possivel")))
        ctx.conferir_cancelamento()
        if executavel and not estrategia:
            motivos = "; ".join(f"«{x['id']}»: {x['motivo']}" for x in escolha.get("excluidas") or []) or "nenhuma candidata"
            raise C.ErroNeuronio("dependencia_ausente", f"nenhuma estratégia viável e ainda não tentada. {motivos}")
        h = next((x for x in hip.get("hipoteses") or [] if x["estrategia"] == estrategia), None) if estrategia else None
        contexto = corpo.get("contexto") or {}
        degradado = bool(corpo.get("contexto_degradado"))
        p = interp.get("parametros") or {}
        ferramentas = (next((c for c in corpo.get("candidatas") or [] if c["id"] == estrategia), {}) or {}).get("ferramentas") or ([estrategia] if estrategia else [])
        if estrategia == "anotar_em_partes":                                       # uma chamada ao corretor por parte: o plano declara todas, na ordem
            ferramentas = list(ferramentas) * len(CONH.dividir_em_partes(cont.get("texto") or ""))
        resultado_esperado = interp.get("resultado_esperado") or "o objetivo é cumprido"
        crit = []
        if tipo == "plano_de_estudo":
            crit = [{"id": "s1", "tipo": "semanas", "descricao": f"o plano tem {p['semanas']} semana(s) com cabeçalho", "parametros": {"semanas": p["semanas"]}},
                    {"id": "s2", "tipo": "dias", "descricao": f"o plano tem {p['semanas'] * 7} dias ({p['semanas']} × 7)", "parametros": {"dias": p["semanas"] * 7}},
                    {"id": "s3", "tipo": "limite_diario", "descricao": f"nenhum dia passa de {p['minutos_dia']} minutos", "parametros": {"minutos": p["minutos_dia"]}}]
        if executavel and tipo != "acao_externa":
            crit.insert(0, {"id": "s0", "tipo": "completo", "descricao": "o conteúdo relido do armazenamento é igual ao gerado (ignorando espaços e quebras de linha)", "parametros": {"hash_do_conteudo": cont.get("hash"), "tamanho": cont.get("tamanho")}})
        if tipo == "acao_externa" and executavel:
            crit.append({"id": "s0", "tipo": "confirmacao_do_corretor", "descricao": "o corretor confirmou a execução depois da autorização do dono", "parametros": {}})
        if tipo == "acao_externa" and not executavel:
            crit.append({"id": "s0", "tipo": "proposta", "descricao": "a proposta descreve a ação pedida e não executa nada (não há ferramenta liberada para isto)", "parametros": {}})
        etapas = [{"id": "e1", "tipo": "verificacao_previa", "descricao": "conferir a coerência do conteúdo gerado (semanas, dias e limite diário)" if tipo == "plano_de_estudo" else "conferir o conteúdo antes de agir",
                   "feito_por": "verificador", "ferramenta": None, "depende_de": [], "resultado_esperado": "conteúdo coerente com os parâmetros pedidos",
                   "justificativa": "o conteúdo vem de uma regra; conferi-lo por outro módulo antes de gravar evita registrar um plano incoerente"},
                  {"id": "e2", "tipo": "revisao", "descricao": "crítica independente: riscos, lacunas, efeitos e necessidade de autorização", "feito_por": "critica", "ferramenta": None, "depende_de": [],
                   "resultado_esperado": "plano aprovado, devolvido ou rejeitado com motivo", "justificativa": "o planejador não pode se aprovar; a crítica roda em outro processo"}]
        if executavel:
            etapas += [{"id": "e3", "tipo": "autorizacao", "descricao": "decidir se o dono precisa autorizar este plano exato", "feito_por": "coordenacao", "ferramenta": None, "depende_de": ["e1", "e2"],
                        "resultado_esperado": "autorização registrada (ou dispensada pelo escopo do pedido)", "justificativa": "propor não é autorizar; nada executa sem esta etapa"},
                       {"id": "e4", "tipo": "execucao", "descricao": f"{(next((c for c in corpo.get('candidatas') or [] if c['id'] == estrategia), {}) or {}).get('descricao', 'executar')} («{estrategia}»)", "feito_por": "coordenacao", "ferramenta": ferramentas[0] if ferramentas else None,
                        "ferramentas": ferramentas, "depende_de": ["e3"], "resultado_esperado": (f"o armazenamento passa a conter o conteúdo completo ({cont.get('tamanho')} caracteres)" if tipo != "acao_externa" else "o corretor executa a ação e registra na auditoria"),
                        "justificativa": (f"estratégia na frente da comparação: {next((r['motivo'] for r in escolha.get('ranking') or [] if r['id'] == estrategia), '')}")},
                       {"id": "e5", "tipo": "verificacao", "descricao": "reler o armazenamento por fora da execução e comparar com o esperado", "feito_por": "verificador", "ferramenta": None, "depende_de": ["e4"],
                        "resultado_esperado": "todos os critérios de sucesso confirmados pela leitura", "justificativa": "a resposta da ferramenta não prova o efeito; só a leitura independente prova"},
                       {"id": "e6", "tipo": "aprendizagem", "descricao": "registrar previsão × observado, fatores possíveis e lições provisórias", "feito_por": "aprendizagem", "ferramenta": None, "depende_de": ["e5"],
                        "resultado_esperado": "registro cognitivo gravado e disponível para o próximo plano", "justificativa": "sem registrar a diferença, o próximo plano começaria do zero"}]
        else:
            etapas.append({"id": "e3", "tipo": "entrega", "descricao": "apresentar o plano ao dono sem guardar nada", "feito_por": "coordenacao", "ferramenta": None, "depende_de": ["e1", "e2"],
                           "resultado_esperado": "plano visível no painel", "justificativa": "o pedido não mandou guardar: nenhuma escrita é feita"})
        riscos = [{"texto": t, "tipo": "incerteza", "fonte": "hipóteses"} for t in (h or {}).get("incertezas") or []]
        riscos += [{"texto": e["texto"], "tipo": "evidencia_contra", "fonte": e["fonte"]} for e in (h or {}).get("evidencias_contra") or []]
        if executavel:
            riscos += [{"texto": "o armazenamento pode alterar o texto (cortar, normalizar espaços ou quebras de linha)", "tipo": "hipotese", "fonte": "classe de risco geral; a releitura independente decide"},
                       {"texto": "a ferramenta pode responder «feito» sem ter produzido o efeito completo", "tipo": "hipotese", "fonte": "motivo da conferência independente (docs/TAREFAS.md)"}]
        for s in interp.get("suposicoes") or []:
            riscos.append({"texto": f"suposição: {s['motivo']}", "tipo": "hipotese", "fonte": "percepção"})
        if degradado:
            riscos.append({"texto": "plano feito sem consultar experiências (contexto indisponível)", "tipo": "incerteza", "fonte": "coordenação"})
        alternativas = [{"estrategia": r["id"], "motivo": r["motivo"], "posicao": r["posicao"]} for r in escolha.get("ranking") or [] if r["id"] != estrategia]
        alternativas += [{"estrategia": x["id"], "motivo": f"fora da fila: {x['motivo']}", "posicao": None} for x in escolha.get("excluidas") or []]
        limites = corpo.get("limites") or {}
        interromper = ["o dono cancelar o objetivo", f"esgotar {limites.get('max_replanos', 3)} replanejamento(s) ou o tempo/recursos do objetivo", "a crítica rejeitar ou o dono negar a autorização",
                       "a verificação ficar inconclusiva (pedir ajuda ao dono em vez de seguir)", "um módulo crítico ficar indisponível (não avançar sem ele)"]
        verif = [{"id": "v1", "como": "reler o armazenamento real depois da execução (banco de notas, pasta de arquivos ou nota de memória) e comparar com o conteúdo esperado", "fonte_independente": True,
                  "executor": "verificador, em processo separado do que executa"}] if executavel and tipo != "acao_externa" else \
               [{"id": "v1", "como": "perguntar ao corretor/tarefa o estado final e conferir a auditoria", "fonte_independente": True, "executor": "verificador"}] if executavel else \
               [{"id": "v1", "como": "reconferir o conteúdo gerado contra os parâmetros pedidos", "fonte_independente": True, "executor": "verificador"}]
        previsao = {"estrategia": estrategia, "hipotese": (h or {}).get("id"), "texto": (h or {}).get("previsao", {}).get("texto") or resultado_esperado,
                    "criterios": [{"id": c["id"], "descricao": c["descricao"]} for c in crit]}
        ant = corpo.get("plano_anterior")
        revisao = None
        if ant:
            revisao = {"de_versao": ant.get("versao"), "para_versao": versao, "mudou": [{"campo": "estrategia", "de": ant.get("estrategia"), "para": estrategia,
                       "motivo": corpo.get("motivo_da_revisao") or "evidências novas depois da tentativa anterior"}]}
        plano = {"id": f"pl-{obj.get('id') or ctx.correlacao}", "versao": versao, "objetivo": resultado_esperado, "descricao_original": (obj.get("descricao") or interp.get("texto_original") or "")[:300],
                 "estado_inicial": {"fatos": [f for f in contexto.get("fatos") or [] if f.get("tipo") == "fato"][:12], "desconhecidos": (contexto.get("desconhecidos") or [])[:8],
                                    "suposicoes": interp.get("suposicoes") or [], "conteudo": {"tipo": cont.get("tipo"), "tamanho": cont.get("tamanho"), "hash": cont.get("hash"), "fonte": cont.get("fonte")}},
                 "etapas": etapas, "resultado_esperado": resultado_esperado, "criterios_de_sucesso": crit, "riscos_e_incertezas": riscos, "alternativas": alternativas,
                 "condicoes_para_interromper": interromper, "criterios_de_verificacao": verif, "estrategia": estrategia, "hipotese_testada": (h or {}).get("id"), "previsao": previsao,
                 "executavel": executavel, "tipo_objetivo": tipo, "escolha": escolha, "revisao": revisao, "parametros_da_estrategia": ({"texto": cont.get("texto"), "titulo": cont.get("titulo") or ""} if tipo != "acao_externa" else
                                                  {"texto": cont.get("texto"), "titulo": "", "contato": p.get("contato"), "mensagem": cont.get("texto")}),
                 "autorizacao_sugerida": bool(tipo == "acao_externa" or (interp.get("efeitos") or {}).get("externo")), "gerado_por": "planejamento (determinístico)", "gerado_em": time.time()}
        plano["hash"] = assinar(plano)
        return {"plano": plano}
