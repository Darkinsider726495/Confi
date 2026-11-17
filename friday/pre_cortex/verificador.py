"""Neurônio 7 — Verificação do resultado.

Duas ações:
  coerencia_conteudo   ANTES de gravar: o conteúdo gerado respeita o que foi pedido (semanas, dias, limite diário)? É outra leitura do mesmo texto, feita por outro módulo.
  verificar            DEPOIS de executar: lê o armazenamento real (leitores.py), compara com o esperado e conclui sucesso, falha parcial, falha total ou inconclusivo.
O que a execução disse (a tarefa «concluída», a resposta da ferramenta) NÃO entra no veredito: entra só como comentário, para destacar quando discorda da releitura.
Uma ação que não dá para conferir por fora (SMS, ligação) termina «inconclusiva», nunca «cumprida». Roda em processo separado do que executa, quando a topologia permite.
"""
import re
import time

from . import conhecimento as CONH
from . import contrato as C
from . import leitores as L
from .neuronio import Neuronio


def _norm(t):
    return " ".join(str(t).split())


def maior_prefixo_presente(esperado, observado):
    """Maior k tal que esperado[:k] aparece em observado (busca binária: se um prefixo aparece, os menores também)."""
    lo, hi = 0, len(esperado)
    while lo < hi:
        meio = (lo + hi + 1) // 2
        if esperado[:meio] in observado:
            lo = meio
        else:
            hi = meio - 1
    return lo


class Verificador(Neuronio):
    nome = "verificador"
    numero = 7
    papel = "confere o resultado por evidência independente da execução"
    responsabilidade = ("Comparar o observado (lido do armazenamento real) com o esperado e concluir sucesso, falha parcial, falha total ou inconclusivo; checar a coerência do conteúdo antes de gravar. "
                        "NÃO aceita «terminou sem erro» como prova e NÃO executa nada.")
    entradas = "plano com critérios + passos esperados + marcas tiradas antes da execução + (só como comentário) o que a execução disse"
    saidas = "veredito, critérios com esperado × observado e evidência, medidas numéricas"
    confianca = "alta onde há leitor independente (nota, arquivo, memória); inconclusivo onde não há"
    critico = True

    # ------------------------------------------------------------------ antes de gravar
    def acao_coerencia_conteudo(self, corpo, ctx):
        cont, interp = corpo.get("conteudo"), corpo.get("interpretacao")
        if not isinstance(cont, dict) or not isinstance(interp, dict):
            raise C.ErroNeuronio("entrada_invalida", "faltam conteúdo ou interpretação")
        tipo = interp.get("tipo_objetivo")
        texto = cont.get("texto") or ""
        crit = []
        if tipo == "plano_de_estudo":
            p = interp.get("parametros") or {}
            a = CONH.analisar_texto(texto)
            dias = a["dias"]
            sem, minimo = int(p.get("semanas", 0)), int(p.get("minutos_dia", 0))
            crit.append({"id": "c1", "descricao": f"{sem * 7} dias de estudo", "esperado": sem * 7, "observado": len(dias), "ok": len(dias) == sem * 7})
            crit.append({"id": "c2", "descricao": f"cabeçalho das semanas 1 a {sem}", "esperado": list(range(1, sem + 1)), "observado": a["semanas_com_cabecalho"], "ok": a["semanas_com_cabecalho"] == list(range(1, sem + 1))})
            acima = [d for d in dias if d["minutos"] > minimo]
            crit.append({"id": "c3", "descricao": f"nenhum dia acima de {minimo} min", "esperado": f"≤ {minimo}", "observado": max([d["minutos"] for d in dias] or [0]), "ok": not acima and bool(dias)})
            soma_ruim = [d for d in dias if d["estudo"] + d["pratica"] != d["minutos"]]
            crit.append({"id": "c4", "descricao": "estudo + prática = total do dia", "esperado": 0, "observado": len(soma_ruim), "ok": not soma_ruim})
            ordem = [(d["semana"], CONH.DIAS.index(d["dia"])) for d in dias]
            crit.append({"id": "c5", "descricao": "dias em ordem (semana, dia da semana)", "esperado": "crescente", "observado": "crescente" if ordem == sorted(ordem) else "fora de ordem", "ok": ordem == sorted(ordem)})
        elif tipo == "registrar_informacao":
            crit.append({"id": "c1", "descricao": "o texto a guardar não está vazio", "esperado": ">0", "observado": len(texto), "ok": len(texto) > 0})
        else:
            crit.append({"id": "c1", "descricao": "há o que propor", "esperado": "ação descrita", "observado": "descrita" if interp.get("parametros") else "vazia", "ok": bool(interp.get("parametros"))})
        crit.append({"id": "c9", "descricao": "o hash do conteúdo confere com o texto recebido", "esperado": cont.get("hash"), "observado": C.hash_de(texto), "ok": cont.get("hash") == C.hash_de(texto) if tipo != "acao_externa" else True})
        return {"coerente": all(c["ok"] for c in crit), "criterios": crit, "problemas": [c["descricao"] for c in crit if not c["ok"]], "independente": True,
                "fonte": "releitura do texto gerado por outro módulo (não é a leitura do armazenamento)"}

    # ------------------------------------------------------------------ depois de executar
    def acao_verificar(self, corpo, ctx):
        plano, passos, marcas, interp = corpo.get("plano"), corpo.get("passos_derivados"), corpo.get("marcas"), corpo.get("interpretacao") or {}
        exe = corpo.get("execucao") or {}
        if not isinstance(plano, dict) or not isinstance(passos, list) or not passos:
            raise C.ErroNeuronio("entrada_invalida", "faltam o plano ou os passos esperados")
        ctx.conferir_cancelamento()
        passo = passos[0]
        ferr = passo.get("ferramenta")
        args = passo.get("args") or {}
        lido_em = time.time()
        if ferr not in ("anotar", "criar_arquivo", "guardar_memoria"):
            return {"veredito": "inconclusivo", "independente": False, "fonte": f"não há leitor independente para «{ferr}»", "criterios": [
                {"id": "s0", "tipo": "confirmacao_do_corretor", "descricao": "o corretor confirmou a execução", "esperado": "efeito real", "observado": f"tarefa {exe.get('estado') or 'sem estado'}", "ok": None,
                 "evidencia": "a ação sai do aparelho: só a palavra do corretor existe, e ela não prova o efeito. Executada, mas não consegui conferir; só o dono conclui."}],
                "medidas": {}, "observado_resumo": "sem como conferir de fora", "discordancia_com_a_execucao": None, "lido_em": lido_em}
        esperado = args.get("texto") if ferr in ("anotar", "guardar_memoria") else args.get("conteudo", "")
        if ferr == "anotar" and "texto" in args:
            esperado = args["texto"]
        em_partes = len(passos) > 1 and all(p.get("ferramenta") == "anotar" for p in passos)
        if em_partes:                                                          # várias notas «[parte i/n]»: o esperado é o texto das partes, sem as marcas, em ordem
            esperado = "\n".join(CONH.tirar_marca((p.get("args") or {}).get("texto", ""))[2] for p in passos)
        en = _norm(esperado)
        try:
            achados = L.ler_depois(ferr, (marcas or {}).get(ferr) or marcas)
        except Exception as e:
            return {"veredito": "inconclusivo", "independente": True, "fonte": "tentei reler o armazenamento", "criterios": [], "medidas": {}, "observado_resumo": f"a leitura falhou: {type(e).__name__}: {str(e)[:120]}",
                    "discordancia_com_a_execucao": None, "lido_em": lido_em}
        if em_partes:                                                          # junta as notas novas que têm a marca de parte (na ordem em que apareceram) e as trata como um texto só
            n_total = len(passos)
            vistas = {}
            for t in achados:
                i, n, c = CONH.tirar_marca(t)
                if i is not None and n == n_total and i not in vistas:
                    vistas[i] = c
            achados = [" ".join(vistas[i] for i in sorted(vistas))] if vistas else []
        melhor, k = None, 0
        for t in achados:
            kk = maior_prefixo_presente(en, _norm(t))
            if kk > k or (kk == k and melhor is None and kk > 0):
                melhor, k = t, kk
        MIN = min(20, len(en))
        achou = melhor is not None and k >= MIN
        on = _norm(melhor) if achou else ""
        a = CONH.analisar_texto(on) if achou else {"dias": [], "semanas_com_cabecalho": []}
        crit = []
        for c in plano.get("criterios_de_sucesso") or []:
            t, par = c.get("tipo"), c.get("parametros") or {}
            if t == "completo":
                if not achou:
                    obs, ok, ev = "nada encontrado", False, f"nenhum texto novo no armazenamento começa como o esperado ({len(achados)} item(ns) novo(s) lido(s))"
                else:
                    ok = on == en or en in on
                    obs = f"{k} de {len(en)} caracteres do esperado presentes (em {len(on)} caracteres guardados)"
                    ev = "o texto relido contém o esperado por inteiro" if ok else f"o texto relido tem só os primeiros {k} caracteres do esperado ({k * 100 // max(1, len(en))}%)"
                crit.append({"id": c["id"], "tipo": t, "descricao": c["descricao"], "esperado": f"{len(en)} caracteres", "observado": obs, "ok": ok, "evidencia": ev})
            elif t == "semanas":
                esp = list(range(1, par["semanas"] + 1))
                crit.append({"id": c["id"], "tipo": t, "descricao": c["descricao"], "esperado": esp, "observado": a["semanas_com_cabecalho"], "ok": achou and a["semanas_com_cabecalho"] == esp,
                             "evidencia": f"cabeçalhos achados na releitura: {a['semanas_com_cabecalho'] or 'nenhum'}"})
            elif t == "dias":
                crit.append({"id": c["id"], "tipo": t, "descricao": c["descricao"], "esperado": par["dias"], "observado": len(a["dias"]), "ok": achou and len(a["dias"]) == par["dias"],
                             "evidencia": f"{len(a['dias'])} dia(s) legíveis na releitura"})
            elif t == "limite_diario":
                mx = max([d["minutos"] for d in a["dias"]] or [0])
                crit.append({"id": c["id"], "tipo": t, "descricao": c["descricao"], "esperado": f"≤ {par['minutos']}", "observado": mx, "ok": achou and bool(a["dias"]) and mx <= par["minutos"],
                             "evidencia": "maior dia lido na releitura: %d min" % mx})
        if not crit:
            crit.append({"id": "s0", "tipo": "completo", "descricao": "o conteúdo foi guardado", "esperado": f"{len(en)} caracteres", "observado": f"{k}", "ok": achou and en in on, "evidencia": "releitura do armazenamento"})
        todos = all(c["ok"] for c in crit)
        if not achou:
            veredito = "falha_total"
        elif todos:
            veredito = "sucesso"
        else:
            veredito = "parcial"
        dis = None
        if exe.get("estado") is not None:
            dis = (exe["estado"] in ("concluida", "CONCLUIDA", "concluída")) != (veredito == "sucesso")
        medidas = {"esperado_tamanho": len(en), "observado_tamanho": len(on) if achou else None, "prefixo_preservado": k, "fracao": round(k / max(1, len(en)), 3), "itens_novos_lidos": len(achados),
                   "dias_observados": len(a["dias"]), "semanas_observadas": a["semanas_com_cabecalho"]}
        resumo = ("nada do esperado apareceu no armazenamento" if not achou else f"guardou {k} de {len(en)} caracteres do esperado ({medidas['fracao'] * 100:.0f}%)" if not todos else "o armazenamento contém o esperado por inteiro")
        return {"veredito": veredito, "independente": True, "fonte": {"anotar": "banco de notas (somente leitura, notas depois da marca)", "criar_arquivo": "pasta de arquivos (arquivos novos)",
                                                                       "guardar_memoria": "notas de memória do cofre alteradas depois da marca"}[ferr],
                "criterios": crit, "medidas": medidas, "observado_resumo": resumo, "discordancia_com_a_execucao": dis, "lido_em": lido_em, "ferramenta_lida": ferr}
