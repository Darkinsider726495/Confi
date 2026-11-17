"""Neurônio 3 — Hipóteses.

Para cada estratégia candidata monta uma HIPÓTESE ({estratégia} cumpre o objetivo), com: de onde veio, evidências a favor e contra (cada uma com a fonte), incertezas, a PREVISÃO
que dá para conferir depois, as condições em que ela deve ser revista e uma confiança estimada. A confiança NÃO é calibrada: é (sucessos+1)/(n+2) dos registros compatíveis
com a faixa de tamanho do conteúdo; sem registro vale 0,5 e o texto diz «sem experiência». O que o código não declara aparece como incerteza, nunca como fato.
Compara as hipóteses (ordem por confiança, depois menor impacto, depois a ordem do catálogo) e devolve a escolha com as contagens que a sustentam — o hub consegue refazer a conta.
Não inventa fatos, não executa e não promove hipótese a fato: o resultado só muda de status depois da verificação independente.
"""
import time

from . import conhecimento as CONH
from . import contrato as C
from .neuronio import Neuronio

REGRA = ("ordem pela confiança estimada p=(sucessos+1)/(n+2) dos registros do mesmo tipo de objetivo e da mesma faixa de tamanho do conteúdo; sem registro p=0,5; "
         "empate: menor impacto, depois menor custo, depois a ordem do catálogo; estratégia inviável pelo limite declarado ou já tentada neste objetivo não entra na fila")


def _tam_bytes(texto):
    return len(texto.encode("utf-8"))


class Hipoteses(Neuronio):
    nome = "hipoteses"
    numero = 3
    critico = False          # sem ele o hub segue pela ordem do catálogo, em modo degradado (fases._hipoteses_minimas), e a execução passa a exigir o dono
    papel = "levanta e compara hipóteses sobre qual estratégia cumpre o objetivo"
    responsabilidade = ("Formular hipóteses com origem, evidências a favor e contra, incertezas, previsão verificável e condição de revisão; compará-las. "
                        "NÃO afirma fatos, não executa e não decide sozinha: a escolha segue para planejamento e crítica.")
    entradas = "interpretação + contexto (candidatas e contagens) + conteúdo gerado + tentativas anteriores deste objetivo"
    saidas = "hipóteses comparadas + escolha com as contagens que a justificam"
    confianca = "baixa e não calibrada: depende de poucos registros; sem registro vale 0,5"

    def acao_gerar(self, corpo, ctx):
        interp, cont = corpo.get("interpretacao"), corpo.get("conteudo")
        candidatas = corpo.get("candidatas")
        if not isinstance(interp, dict) or not isinstance(candidatas, list):
            raise C.ErroNeuronio("entrada_invalida", "faltam a interpretação ou as candidatas")
        degradado = bool(corpo.get("contexto_degradado"))
        tipo = interp.get("tipo_objetivo")
        amb = corpo.get("ambiente") or {}
        tentadas = {t["estrategia"]: t for t in corpo.get("tentativas_anteriores") or [] if isinstance(t, dict) and t.get("estrategia")}
        registro = tipo in ("plano_de_estudo", "registrar_informacao")
        texto = (cont or {}).get("texto") if registro else None
        tamanho_c = len(texto) if isinstance(texto, str) else None
        tamanho_b = _tam_bytes(texto) if isinstance(texto, str) else None
        faixa = CONH.faixa_de_tamanho(tamanho_c) if registro and tamanho_c is not None else "sem_faixa"
        condicoes = {**amb, **({"faixa_tamanho": faixa} if faixa != "sem_faixa" else {})}
        previsao_generica = (interp.get("resultado_esperado") or "o efeito pedido existe")
        hipoteses, excluidas, ranking_base = [], [], []
        for c in candidatas:
            cid = c["id"]
            if not c.get("disponivel", True):
                excluidas.append({"id": cid, "motivo": c.get("motivo_indisponivel") or "indisponível"})
                continue
            if cid in tentadas:
                t = tentadas[cid]
                excluidas.append({"id": cid, "motivo": f"já tentada neste objetivo (resultado: {t.get('resultado')}); repetir sem mudar nada não traz informação"})
                continue
            inviavel = []
            for d in c.get("limites_declarados") or []:
                if registro and tamanho_c is not None:
                    uso = tamanho_b if d["unidade"] == "bytes" else tamanho_c
                    if uso > d["maximo"]:
                        inviavel.append(f"o conteúdo tem {uso} {d['unidade']} e o limite declarado é {d['maximo']} ({d['fonte']})")
            cog = (c.get("cognitivas_por_faixa") or {}).get(faixa) or {"n": 0, "sucessos": 0, "falhas": 0, "p": 0.5, "ids": [], "inconclusivas": 0, "confianca": 0.0}
            tar = c.get("sinais_tarefa") or {"n": 0, "sucessos": 0, "falhas": 0, "p": 0.5, "ids": []}
            a_favor, contra, incertezas = [], [], []
            if c.get("disponivel", True):
                a_favor.append({"texto": f"a ferramenta existe e está liberada no nível {c.get('nivel')}", "tipo": "fato", "fonte": "corretor/catálogo"})
            if c.get("conferencia_independente"):
                a_favor.append({"texto": "o efeito pode ser conferido por fora da ferramenta", "tipo": "fato", "fonte": "verificacao.conferivel"})
            else:
                incertezas.append("o efeito desta estratégia não pode ser conferido por fora")
            for d in c.get("limites_declarados") or []:
                if not inviavel:
                    a_favor.append({"texto": f"o conteúdo cabe no limite declarado ({d['maximo']} {d['unidade']})", "tipo": "inferencia", "fonte": d["fonte"]})
            if registro and not (c.get("limites_declarados") or []):
                incertezas.append("não há limite de tamanho declarado: o código não diz se um texto desse tamanho é guardado por inteiro")
            for i in inviavel:
                contra.append({"texto": i, "tipo": "fato", "fonte": "catalogo_pc.LIMITES_DECLARADOS"})
            if cog["n"]:
                if cog["sucessos"]:
                    a_favor.append({"texto": f"{cog['sucessos']} de {cog['n']} objetivo(s) parecidos (mesma faixa de tamanho, {faixa}) foram cumpridos com esta estratégia", "tipo": "fato", "fonte": ", ".join(cog["ids"][-3:])})
                if cog["falhas"]:
                    contra.append({"texto": f"{cog['falhas']} de {cog['n']} objetivo(s) parecidos (faixa {faixa}) não foram cumpridos por inteiro com esta estratégia", "tipo": "fato", "fonte": ", ".join(cog["ids"][-3:])})
            else:
                incertezas.append(f"sem experiência com esta estratégia na faixa de tamanho {faixa}")
            if tar["n"]:
                if tar["sucessos"]:
                    a_favor.append({"texto": f"{tar['sucessos']} de {tar['n']} tarefa(s) isoladas com esta ferramenta terminaram conferidas (conferência de TAREFA, mais fraca que a do objetivo)",
                                    "tipo": "fato", "fonte": ", ".join(tar["ids"][-3:])})
                if tar["falhas"]:
                    contra.append({"texto": f"{tar['falhas']} tarefa(s) isoladas com esta ferramenta falharam", "tipo": "fato", "fonte": ", ".join(tar["ids"][-3:])})
            if degradado:
                incertezas.append("o módulo de contexto estava indisponível: nenhuma experiência foi consultada")
            perfil = c.get("perfil") or {}
            impacto = perfil.get("impacto", 1.0)
            custo = perfil.get("custo", 1.0)
            h = {"id": f"h{len(hipoteses) + 1}", "estrategia": cid, "texto": f"«{cid}» cumpre o objetivo por inteiro ({c.get('descricao')})", "origem": "catálogo de estratégias + contexto recuperado",
                 "evidencias_a_favor": [e for e in a_favor if e], "evidencias_contra": contra, "incertezas": incertezas,
                 "previsao": {"texto": f"depois de executar «{cid}», a leitura independente encontra o conteúdo completo: {previsao_generica}",
                              "onde_conferir": c.get("esperado_do_catalogo") or "no armazenamento real", "verificavel": bool(c.get("conferencia_independente"))},
                 "condicoes_de_revisao": ["se a releitura independente achar menos do que o esperado, a hipótese é refutada para esta faixa de tamanho e a diferença vai para investigação",
                                          "uma única observação não confirma nem derruba uma regra geral"],
                 "confianca": {"valor": cog["p"], "calibrada": False, "n": cog["n"], "metodo": "(sucessos+1)/(n+2) dos registros do mesmo tipo e faixa; " + ("sem experiência: 0,5" if not cog["n"] else f"{cog['sucessos']} acerto(s) em {cog['n']}")},
                 "viavel": not inviavel, "status": "nao_testada"}
            hipoteses.append(h)
            ranking_base.append({"id": cid, "n": cog["n"], "sucessos": cog["sucessos"], "falhas": cog["falhas"], "p": cog["p"], "experiencias": cog["ids"], "cognitivas": {k: cog[k] for k in ("n", "sucessos", "falhas", "p", "ids")},
                                 "condicoes_da_contagem": condicoes, "impacto": impacto, "custo": custo, "ordem": c.get("ordem", 99), "viavel": not inviavel, "hipotese": h["id"],
                                 "motivo": (f"p={cog['p']:.2f} ({cog['sucessos']} acerto(s) em {cog['n']}, faixa {faixa})" if cog["n"] else f"p=0,50 (sem experiência na faixa {faixa})")
                                           + ("; INVIÁVEL: " + inviavel[0] if inviavel else "")})
        ranking = sorted(ranking_base, key=lambda r: (not r["viavel"], -r["p"], r["impacto"], r["custo"], r["ordem"]))
        for i, r in enumerate(ranking):
            r["posicao"] = i + 1
            if i > 0:
                ant = ranking[i - 1]
                r["motivo"] += (f"; atrás de «{ant['id']}» " + ("porque a anterior é viável e esta não" if ant["viavel"] and not r["viavel"] else
                                 f"por confiança ({ant['p']:.2f} contra {r['p']:.2f})" if ant["p"] != r["p"] else f"pelo desempate de menor impacto ({ant['impacto']} contra {r['impacto']})" if ant["impacto"] != r["impacto"] else "pela ordem do catálogo"))
        viaveis = [r for r in ranking if r["viavel"]]
        escolha = {"em": float(corpo.get("instante_do_contexto") or time.time()), "tipo": tipo, "condicoes": condicoes, "faixa_tamanho": faixa, "regra": REGRA,
                   "ranking": [{k: v for k, v in r.items() if k not in ("ordem",)} for r in ranking], "excluidas": excluidas, "escolhida": viaveis[0]["id"] if viaveis else None}
        for h in hipoteses:
            h["posicao"] = next(r["posicao"] for r in ranking if r["hipotese"] == h["id"])
        hipoteses.sort(key=lambda h: h["posicao"])
        return {"hipoteses": hipoteses, "comparacao": [{"id": r["id"], "hipotese": r["hipotese"], "p": r["p"], "n": r["n"], "impacto": r["impacto"], "viavel": r["viavel"], "posicao": r["posicao"], "motivo": r["motivo"]} for r in ranking],
                "escolha": escolha, "faixa_tamanho": faixa, "contexto_degradado": degradado,
                "aviso": "a confiança de cada hipótese é uma estimativa por contagem, não uma probabilidade calibrada"}
