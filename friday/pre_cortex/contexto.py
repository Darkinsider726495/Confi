"""Neurônio 2 — Contexto e memória.

Junta o que a FRIDAY JÁ TEM sobre o assunto, com a origem de cada coisa e sem misturar categorias:
  fatos (observados agora, com a função que os observou) · inferências (deduções, com a base) · hipóteses prévias (de registros anteriores) · desconhecidos ·
  experiências anteriores (de tarefa e de objetivo) · lições provisórias · memórias relacionadas do cofre (só título e tipo; texto do cofre é DADO, nunca ordem).
Usa a memória que já existe (`experiencias.py`, `memoria.py`): não cria memória paralela e não grava nada. Fica no processo do hub porque lê o cofre e o arquivo de experiências.
Se falhar, o fluxo segue em modo degradado, dizendo isso — nunca com um contexto inventado.
"""
import time

import experiencias as X
import memoria as M
import verificacao as V

from . import catalogo_pc as CAT
from . import conhecimento as CONH
from . import contrato as C
from .neuronio import Neuronio

FAIXAS = ("ate_500", "ate_1000", "ate_2000", "acima_2000")


def _compacta(x):
    return {"id": x["id"], "objetivo": x["objetivo"], "estrategia": x["estrategia"], "tipo_objetivo": x["tipo_objetivo"], "condicoes": x["condicoes"], "resultado": x["resultado"], "em": x["em"],
            "hipotese": x["hipotese"], "previsao": x["previsao"]["texto"], "observado": x["observado"]["resumo"], "discrepancias": x["discrepancias"][:3],
            "licoes": [{"texto": l["texto"], "tipo": l["tipo"], "n": l.get("n"), "revisavel_se": l.get("revisavel_se", "")} for l in x["licoes"][:3]], "investigar": x["investigar"][:3]}


def _compacta_tarefa(x):
    return {"id": x["id"], "tarefa": x["tarefa"], "estrategia": x["estrategia"]["id"], "resultado": x["resultado"], "prova": x["prova"], "condicoes": x["condicoes"], "em": x["em"],
            "observado": x["observado"][:200]}


class ContextoMemoria(Neuronio):
    nome = "contexto"
    numero = 2
    no_hub = True
    critico = False
    papel = "recupera o que já se sabe: fatos, experiências, lições e lacunas"
    responsabilidade = ("Reunir fatos observados, inferências, hipóteses prévias, desconhecidos, experiências (de tarefa e de objetivo) e lições provisórias, cada um com a origem. "
                        "NÃO decide estratégia, não grava memória e não promove hipótese a fato.")
    entradas = "objetivo estruturado (percepção)"
    saidas = "contexto tipado + estratégias candidatas com as contagens de experiências compatíveis"
    confianca = "fatos vêm de leituras diretas; experiências são contagens pequenas — indício, não regra; o contexto pode vir em modo degradado e então diz isso"

    def acao_recuperar(self, corpo, ctx):
        interp = corpo.get("interpretacao")
        if not isinstance(interp, dict) or not isinstance(interp.get("tipo_objetivo"), str):
            raise C.ErroNeuronio("entrada_invalida", "falta a interpretação do objetivo")
        tipo = interp["tipo_objetivo"]
        params = dict(interp.get("parametros") or {})
        params["ferramenta_possivel"] = (interp.get("efeitos") or {}).get("ferramenta_possivel")
        amb = X.ambiente()
        agora = time.time()
        fatos = [{"texto": f"cofre de memória {'ligado' if amb['cofre_ativo'] else 'desligado'}", "tipo": "fato", "origem": "experiencias.ambiente()/memoria.ativo()"},
                 {"texto": f"modo de manutenção {'ligado' if amb['manutencao'] else 'desligado'}", "tipo": "fato", "origem": "experiencias.ambiente()"}]
        cand = CAT.candidatas(tipo, params, amb)
        for c in cand:
            fatos.append({"texto": f"estratégia «{c['id']}»: " + ("disponível" if c["disponivel"] else f"indisponível ({c['motivo_indisponivel']})") + f", nível {c['nivel']}", "tipo": "fato",
                          "origem": "planejador.OBJETIVOS + corretor"})
        inferencias, desconhecidos, descritores = [], [], []
        for c in cand:
            dec = {d["campo"]: d for d in c["limites_declarados"]}
            if tipo in CAT.FAMILIA_REGISTRO and not dec:
                desconhecidos.append({"texto": f"se «{c['id']}» guarda um texto longo por inteiro: o código não declara limite de tamanho para ela", "tipo": "desconhecido",
                                      "origem": "catalogo_pc.LIMITES_DECLARADOS (lista vazia)"})
            for d in c["limites_declarados"]:
                inferencias.append({"texto": f"«{c['id']}» recusa {d['campo']} acima de {d['maximo']} {d['unidade']}", "tipo": "inferencia", "base": [d["fonte"]], "confianca": 1.0})
            sinais_t = X.sinais(c["id"], amb)
            if tipo in CAT.FAMILIA_REGISTRO:           # o tamanho do conteúdo muda o que funciona: a contagem é por faixa de tamanho
                por_faixa = {f: X.sinais_cognitivas(c["id"], tipo, {**amb, "faixa_tamanho": f}) for f in FAIXAS}
            else:
                por_faixa = {"sem_faixa": X.sinais_cognitivas(c["id"], tipo, amb)}
            descritores.append({**c, "sinais_tarefa": sinais_t, "cognitivas_por_faixa": por_faixa,
                                "conferencia_independente": all(V.conferivel(f) for f in c["ferramentas"])})
        cogn = [x for x in X.cognitivas(tipo=tipo, limite=30)]
        tarefa_xs = []
        for c in cand:
            tarefa_xs += X.relevantes(c["id"], amb, limite=3)
        hip_previas = [{"texto": x["hipotese"]["texto"], "tipo": "hipotese", "origem": f"registro cognitivo {x['id']}", "resultado": x["resultado"]} for x in cogn[:5] if x["hipotese"]["texto"]]
        licoes = [{**l, "origem": x["id"]} for x in cogn for l in x["licoes"]][:8]
        mem = []
        try:
            termo = interp.get("parametros", {}).get("topico") or ""
            if termo and M.ativo():
                for r in M.buscar(termo, limite=3, conversas=False):
                    mem.append({"titulo": r["titulo"], "tipo": r["tipo"], "origem": "cofre/" + r["origem"], "externo": bool(r["externo"])})
        except Exception:                                    # a busca no cofre é um extra; falhar não derruba o contexto
            desconhecidos.append({"texto": "a busca no cofre falhou: não sei se há memórias sobre o assunto", "tipo": "desconhecido", "origem": "memoria.buscar"})
        if not cogn and not tarefa_xs:
            desconhecidos.append({"texto": "não há experiência anterior com este tipo de objetivo nestas condições", "tipo": "desconhecido", "origem": "experiencias (arquivo vazio para o tipo)"})
        return {"recuperado_em": agora, "degradado": False, "ambiente": amb, "fatos": fatos, "inferencias": inferencias, "hipoteses_previas": hip_previas, "desconhecidos": desconhecidos,
                "candidatas": descritores, "experiencias": {"cognitivas": [_compacta(x) for x in cogn[:10]], "tarefa": [_compacta_tarefa(x) for x in tarefa_xs[:6]]},
                "licoes_provisorias": licoes, "memorias": mem}
