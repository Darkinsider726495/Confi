"""Neurônio 8 — Aprendizagem por experiência.

Depois da verificação independente, compara o que foi PREVISTO com o que foi OBSERVADO e grava um registro cognitivo (em `experiencias.jsonl`, a memória que já existe):
contexto de antes · hipótese e previsão · resultado conferido · diferenças · fatores que podem explicá-las (cada um tipado: fato, inferência ou hipótese) · lições provisórias ·
o que investigar · o efeito disso na ordem das estratégias.

O que isto NÃO é: não há punição, recompensa, sofrimento nem castigo — nenhum número de «prêmio» é somado e nenhum peso de modelo muda. Uma experiência negativa vira INVESTIGAÇÃO e
revisão: a estratégia continua disponível, só com menos confiança nas condições em que falhou, e volta a subir se novos registros a favorecerem. Uma observação é indício, não regra:
as lições saem como hipótese, com `n` e a condição que as revisaria. Correlação não é causa: um fator candidato diz «coincidiu com», não «causou».
Auditável e reversível: o registro tem o id da tentativa e do plano; `experiencias.revogar_cognitiva` desfaz o efeito sem apagar. Limitado: só pode propor ajuste de
`PARAMETROS_AUTORIZADOS` (a ordem de estratégias); limites de segurança, crítica e autorização não estão ao alcance daqui (e o armazém recusa qualquer outro parâmetro).
"""
import experiencias as X

from . import contrato as C
from . import exploracao as EX
from .neuronio import Neuronio

MAPA = {"sucesso": "sucesso", "parcial": "parcial", "falha_total": "falha", "inconclusivo": "inconclusivo"}


class Aprendizagem(Neuronio):
    nome = "aprendizagem"
    numero = 8
    no_hub = True
    critico = False
    papel = "compara previsão e resultado, registra lições provisórias e investigações"
    responsabilidade = ("Registrar contexto, hipótese, previsão e resultado conferido; achar fatores candidatos (sem afirmar causa); gravar lições provisórias e perguntas a investigar; "
                        "refletir o registro na ordem das estratégias. NÃO pune nem premia, NÃO apaga nada, NÃO altera segurança e NÃO transforma uma observação em regra.")
    entradas = "plano, hipótese escolhida, contexto de antes, verificação independente, execução"
    saidas = "registro cognitivo gravado + comparação + efeito na ordem das estratégias"
    confianca = "as lições são hipóteses com n pequeno; só a contagem acumulada e a releitura independente têm peso"

    def acao_registrar(self, corpo, ctx):
        obj, tentativa = corpo.get("objetivo"), int(corpo.get("tentativa") or 1)
        plano, ver, interp = corpo.get("plano"), corpo.get("verificacao"), corpo.get("interpretacao") or {}
        exe = corpo.get("execucao") or {}
        if not isinstance(obj, str) or not isinstance(plano, dict) or not isinstance(ver, dict):
            raise C.ErroNeuronio("entrada_invalida", "faltam objetivo, plano ou verificação")
        ctx.conferir_cancelamento()
        tipo, estrategia = plano.get("tipo_objetivo"), plano.get("estrategia")
        faixa = (plano.get("escolha") or {}).get("faixa_tamanho", "sem_faixa")
        cond = dict((plano.get("escolha") or {}).get("condicoes") or {})
        # idempotência: a mesma tentativa do mesmo objetivo e plano não é registrada duas vezes (entrega «ao menos uma vez»)
        for r in X.cognitivas(tipo=tipo, estrategia=estrategia, limite=200):
            if r["objetivo"] == obj and r["tentativa"] == tentativa and r["plano"]["hash"] == plano.get("hash"):
                return {"registrado": True, "duplicado": True, "id": r["id"], "resultado": r["resultado"], "registro": r}
        antes = X.sinais_cognitivas(estrategia, tipo, cond)
        veredito = ver.get("veredito")
        resultado = MAPA.get(veredito, "inconclusivo")
        med = ver.get("medidas") or {}
        crit_ver = ver.get("criterios") or []
        prev = plano.get("previsao") or {}
        comparacao, discrepancias = [], []
        for pc in prev.get("criterios") or []:
            o = next((c for c in crit_ver if c.get("id") == pc.get("id")), None)
            comparacao.append({"criterio": pc.get("id"), "previsto": pc.get("descricao"), "observado": (o or {}).get("observado"), "ok": (o or {}).get("ok")})
            if o is not None and o.get("ok") is False:
                discrepancias.append(f"{pc.get('descricao')}: esperado {o.get('esperado')}, observado {o.get('observado')}")
        n_ok = sum(1 for c in comparacao if c["ok"] is True)
        qualidade = {"criterios_previstos": len(comparacao), "criterios_confirmados": n_ok, "previsao_acertou": resultado == "sucesso",
                     "nota": "a previsão era «todos os critérios se cumprem»; acertou só se a releitura independente confirmou todos"}
        fatores, licoes, investigar, testes = [], [], [], []
        tam = med.get("esperado_tamanho")
        if resultado == "sucesso":
            fatores.append({"texto": f"o armazenamento devolveu o conteúdo completo ({tam} caracteres) com «{estrategia}»", "tipo": "fato", "confianca": 1.0, "base": [f"verificacao:{ver.get('fonte', '')[:40]}"]})
            licoes += [{"texto": f"«{estrategia}» guardou o conteúdo completo ({tam} caracteres, faixa {faixa}) nesta tentativa", "tipo": "fato", "confianca": 1.0, "n": 1},
                       {"texto": f"«{estrategia}» pode funcionar de novo para conteúdos da mesma faixa; uma observação só indica, não garante", "tipo": "hipotese", "confianca": 0.4, "n": 1,
                        "revisavel_se": "uma releitura futura achar conteúdo faltando nesta faixa de tamanho"}]
        elif resultado in ("parcial", "falha"):
            if med.get("prefixo_preservado") is not None and tam:
                fatores.append({"texto": f"o armazenamento guardou {med['prefixo_preservado']} de {tam} caracteres do esperado ({med.get('fracao', 0) * 100:.0f}%) com «{estrategia}»", "tipo": "fato", "confianca": 1.0, "base": ["verificacao.medidas"]})
            if med.get("observado_tamanho") is not None and med.get("prefixo_preservado") == med.get("observado_tamanho") and med.get("prefixo_preservado", 0) < (tam or 0):
                fatores.append({"texto": "o que foi guardado é exatamente o COMEÇO do texto esperado: o resto foi cortado, não alterado", "tipo": "inferencia", "confianca": 0.7, "base": ["prefixo_preservado == observado_tamanho"]})
                fatores.append({"texto": f"o tamanho do conteúdo ({tam}) passou do que a estratégia guardou ({med.get('observado_tamanho')}); isso COINCIDE com o corte, mas uma observação não prova que o tamanho foi a causa",
                                "tipo": "hipotese", "confianca": 0.35, "base": ["medidas.esperado_tamanho", "medidas.observado_tamanho"]})
            cod = str(exe.get("codigo") or "")
            if cod:
                fatores.append({"texto": f"o corretor respondeu «{cod}» ao passo ({str(exe.get('causa') or '')[:160]})", "tipo": "fato", "confianca": 1.0, "base": ["execucao.codigo"]})
                if cod.startswith("tamanho:") and tam:
                    fatores.append({"texto": f"o conteúdo tem {tam} caracteres e o corretor recusou por tamanho; isso COINCIDE com um limite de tamanho do argumento, mas é uma observação só — o valor do limite não foi medido",
                                    "tipo": "hipotese", "confianca": 0.5, "base": ["execucao.codigo", "medidas.esperado_tamanho"]})
            if ver.get("discordancia_com_a_execucao"):
                fatores.append({"texto": "a execução terminou como cumprida e a releitura do objetivo discordou: a conferência da tarefa olha menos do que o objetivo exige", "tipo": "inferencia", "confianca": 0.6, "base": ["verificacao.discordancia_com_a_execucao"]})
            fatores.append({"texto": "o ambiente (cofre, manutenção) é o mesmo das tentativas anteriores, então não explica a diferença entre estratégias", "tipo": "hipotese", "confianca": 0.2, "base": ["condicoes"]})
            licoes += [{"texto": f"«{estrategia}» não cumpriu o objetivo por inteiro na faixa de tamanho {faixa}: {ver.get('observado_resumo')}", "tipo": "fato", "confianca": 1.0, "n": 1},
                       {"texto": f"«{estrategia}» tende a não guardar por inteiro conteúdos da faixa {faixa}; com 1 observação isto NÃO vale como regra geral", "tipo": "hipotese", "confianca": 0.4, "n": 1,
                        "revisavel_se": f"«{estrategia}» guardar por inteiro um conteúdo da faixa {faixa}, ou o limite for declarado/corrigido"}]
            pergunta = f"Em que tamanho «{estrategia}» começa a perder conteúdo? (a observação foi com {tam} caracteres)"
            investigar.append(pergunta)
            av = EX.avaliar({"id": estrategia, "ferramentas": [estrategia] if estrategia in EX.PERFIS else []}, n_observacoes=antes["n"] + 1, no_escopo_do_pedido=False, experimento=True, simulacao_possivel=False)
            testes.append({"pergunta": pergunta, "avaliacao": av, "executado": False, "motivo": "teste proposto, não executado: grava dados que o dono não pediu — precisa de autorização"})
        else:
            licoes.append({"texto": "a releitura independente não conseguiu concluir; isto não conta como sucesso nem como falha", "tipo": "fato", "confianca": 1.0, "n": 1})
            fatores.append({"texto": f"inconclusivo: {ver.get('observado_resumo')}", "tipo": "desconhecido", "confianca": 0.0})
            investigar.append("conseguir um jeito independente de conferir este tipo de ação")
        ajuste = None
        if resultado in ("sucesso", "parcial", "falha"):
            ajuste = {"parametro": "ordem_de_estrategias", "escopo": f"{tipo}/{faixa}",
                      "efeito": (f"«{estrategia}» sobe na ordem desta faixa (1 acerto)" if resultado == "sucesso" else
                                 f"«{estrategia}» desce na ordem desta faixa até haver mais evidência; continua disponível e volta a subir com registros a favor"), "reversivel": True}
        reg = {"objetivo": obj, "tentativa": tentativa, "plano": {"id": plano.get("id"), "versao": plano.get("versao"), "hash": plano.get("hash")}, "tipo_objetivo": tipo, "estrategia": estrategia, "condicoes": cond,
               "tarefa": exe.get("tarefa"), "experiencia_tarefa": exe.get("experiencia_tarefa"),
               "hipotese": {"id": plano.get("hipotese_testada") or "", "texto": next((h.get("texto") for h in (corpo.get("hipoteses") or []) if h.get("id") == plano.get("hipotese_testada")), f"«{estrategia}» cumpre o objetivo por inteiro")},
               "previsao": {"texto": prev.get("texto") or "", "criterios": prev.get("criterios") or []},
               "observado": {"resumo": ver.get("observado_resumo") or "", "criterios": [{"id": c.get("id"), "esperado": str(c.get("esperado")), "observado": str(c.get("observado")), "ok": c.get("ok")} for c in crit_ver]},
               "resultado": resultado, "discrepancias": discrepancias, "fatores": fatores, "licoes": licoes, "investigar": investigar, "proposta_de_ajuste": ajuste}
        gravado = X.registrar_cognitiva(reg)
        if gravado is None:
            return {"registrado": False, "motivo": "o armazém de experiências recusou o registro", "comparacao": comparacao, "qualidade_da_previsao": qualidade}
        depois = X.sinais_cognitivas(estrategia, tipo, cond)
        return {"registrado": True, "duplicado": False, "id": gravado["id"], "resultado": resultado, "registro": gravado, "comparacao": comparacao, "qualidade_da_previsao": qualidade,
                "fatores": fatores, "licoes": licoes, "investigar": investigar, "propostas_de_teste": testes,
                "efeito_na_selecao": {"estrategia": estrategia, "condicoes": cond, "antes": {k: antes[k] for k in ("n", "sucessos", "falhas", "p")}, "depois": {k: depois[k] for k in ("n", "sucessos", "falhas", "p")},
                                      "texto": f"confiança estimada de «{estrategia}» nestas condições: {antes['p']:.2f} → {depois['p']:.2f} ({depois['sucessos']} acerto(s) em {depois['n']})"},
                "hipotese_status": ("sustentada_por_uma_observacao" if resultado == "sucesso" else "refutada_nesta_tentativa" if resultado in ("parcial", "falha") else "inconclusiva")}
