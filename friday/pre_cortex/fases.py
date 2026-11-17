"""As fases do fluxo de um objetivo, escritas como métodos do hub (`Hub(Fases)`).

Objetivo → Contexto → Hipóteses → Previsões → Plano → Riscos → Autorização → Execução → Verificação → Aprendizagem → Replanejamento.

Cada fase LÊ o que as anteriores gravaram no dossiê e GRAVA o próprio resultado antes de apontar a próxima: por isso, depois de uma queda, o hub continua da primeira fase que
não terminou (os neurônios cognitivos são idempotentes). Só a execução pelo corretor é protegida por registro antes de agir (execucao.py).

Regras que as fases fazem cumprir (todas testadas):
 • nada avança por cima de uma falha crítica (percepção, planejamento, crítica, verificação): o objetivo fica «bloqueado» e diz qual módulo;
 • módulo que pode faltar (contexto, hipóteses, aprendizagem) faz o fluxo seguir em MODO DEGRADADO — e modo degradado sempre exige o dono antes de agir;
 • a crítica é obrigatória e o veredito vale só para o hash do plano que ela viu; a autorização também;
 • a execução só começa com crítica aprovada + autorização para o MESMO hash; sem isso, é bloqueada aqui, mesmo que o motor tenha errado antes;
 • a verificação usa leitura independente; o que não dá para conferir fica «inconclusivo» e vai ao dono, nunca vira sucesso;
 • limites de tentativas, replanejamentos, revisões da crítica, tempo e nós: estourou, bloqueia; plano repetido (mesma assinatura) é laço e bloqueia.
"""
import time

import experiencias as X
import verificacao as V

from . import catalogo_neuronios as K
from . import catalogo_pc as CAT
from . import contrato as C
from . import dossie as D
from . import execucao as EX
from . import exploracao as EXP

FAIXAS = ("ate_500", "ate_1000", "ate_2000", "acima_2000")


class Cancelado(Exception):
    """O dono cancelou o objetivo."""


class Parar(Exception):
    """Sai da linha do objetivo sem mudar o estado que já foi gravado (espera pelo dono ou pelo corretor, ou fim de fluxo)."""


class LimiteExcedido(Exception):
    def __init__(self, tipo, texto):
        super().__init__(texto)
        self.tipo, self.texto = tipo, texto


class ModuloIndisponivel(Exception):
    def __init__(self, modulo, texto):
        super().__init__(texto)
        self.modulo, self.texto = modulo, texto


class ChamadaFalhou(Exception):
    def __init__(self, modulo, codigo, texto):
        super().__init__(texto)
        self.modulo, self.codigo, self.texto = modulo, codigo, texto


def assinatura(plano):
    """O que torna um plano «o mesmo plano»: tudo, menos versão, hash, hora e o diff de revisão. Usado para pegar replanejamento que não muda nada."""
    return C.hash_de({k: v for k, v in plano.items() if k not in ("hash", "gerado_em", "versao", "revisao", "id")})


class Fases:
    # ------------------------------------------------------------------ utilidades das fases
    def _plano_reg(self, d):
        for p in d["planos"]:
            if p["versao"] == d["plano_atual"]:
                return p
        raise ChamadaFalhou("hub", "erro_interno", "o objetivo não tem plano atual")

    def _ir_para(self, d, fase, proxima=None):
        with self.arm.trava:
            d["fase"] = fase
            if proxima:
                d["proxima_etapa"] = proxima
            d["atualizado_em"] = self.rel()
        self._salvar()

    def _parar_com(self, d, estado, texto, *, tipo=None, modulo=None, recuperavel=False, proxima=None, pausa=False):
        """Grava o estado em que o objetivo fica parado e sai da linha. `pausa` = o relógio do objetivo não conta enquanto espera um humano."""
        with self.arm.trava:
            d["estado"] = estado
            d["bloqueio"] = {"tipo": tipo or estado, "texto": texto, "modulo": modulo, "recuperavel": bool(recuperavel), "em": self.rel()} if estado in ("bloqueado", "precisa_do_dono") else None
            d["proxima_etapa"] = proxima or texto
            d["atualizado_em"] = self.rel()
            if pausa and d["uso"].get("pausa_desde") is None:
                d["uso"]["pausa_desde"] = self.rel()
            D.decisao(d, "coordenacao", f"parei: {D.ROTULO_ESTADO.get(estado, estado)}", texto, self.rel())
        self._salvar()
        self._evento(d, "objetivo_parado", estado=estado, texto=texto, modulo=modulo, recuperavel=bool(recuperavel))
        raise Parar()

    def _no_resumo(self, no, texto):
        with self.arm.trava:
            no["resumo"] = texto[:200]

    # ------------------------------------------------------------------ fase 1: interpretação
    def _fase_interpretacao(self, d):
        no = self._no(d, "interpretacao", "percepcao", "interpretar")
        with self.arm.trava:
            d["no_interpretacao"] = no["id"]
        r = self._chamar_no(d, no, "percepcao", "interpretar", {"texto": d["descricao"]})
        interp = r.get("interpretacao") if isinstance(r, dict) else None
        if not isinstance(interp, dict):
            raise ChamadaFalhou("percepcao", "entrada_invalida", "a percepção não devolveu uma interpretação")
        with self.arm.trava:
            d["interpretacao"] = interp
            d["restricoes"] = list(interp.get("restricoes") or [])
            d["resultado_esperado"] = interp.get("resultado_esperado") or ""
            d["criterios_de_conclusao"] = list(interp.get("criterios_de_conclusao") or [])
            d["recursos"] = ["corretor (nível 1; confirmação do dono acima disso)", "arquivos locais e notas", "nenhuma internet", "nenhum comando de sistema"]
            D.decisao(d, "percepcao", f"entendi o pedido como «{interp.get('tipo_objetivo')}»", f"confiança {interp.get('confianca', {}).get('valor')} (não calibrada): {interp.get('confianca', {}).get('regra')}", self.rel(),
                      {"faltando": interp.get("faltando"), "suposicoes": len(interp.get("suposicoes") or [])})
        self._no_resumo(no, f"tipo {interp.get('tipo_objetivo')}; faltando {interp.get('faltando') or 'nada'}")
        self._evento(d, "interpretacao", tipo_objetivo=interp.get("tipo_objetivo"), suportado=interp.get("suportado"), faltando=interp.get("faltando"),
                     texto=f"entendi como «{interp.get('tipo_objetivo')}»" + (f"; faltam: {', '.join(interp['faltando'])}" if interp.get("faltando") else ""))
        if not interp.get("suportado"):
            self._parar_com(d, "precisa_do_dono", interp.get("pede_esclarecimento") or "não entendi o pedido", tipo="nao_entendi", recuperavel=False, proxima=interp.get("pede_esclarecimento"))
        bloqueantes = [f for f in interp.get("faltando") or [] if f in ("contato", "mensagem")]
        if interp.get("tipo_objetivo") == "acao_externa" and bloqueantes:
            self._parar_com(d, "precisa_do_dono", "faltam dados para montar a ação: " + ", ".join(bloqueantes), tipo="faltam_dados", recuperavel=False,
                            proxima="Diga os dados que faltam (" + ", ".join(bloqueantes) + ") e faça o pedido de novo.")
        self._ir_para(d, "conhecimento", "reunir contexto e gerar o conteúdo")

    # ------------------------------------------------------------------ fase 2: conhecimento (contexto ‖ conteúdo)
    def _contexto_minimo(self, interp, motivo):
        """Contexto de emergência SEM experiências: só o catálogo. Quem o usa fica em modo degradado (exige o dono)."""
        amb = X.ambiente()
        params = dict(interp.get("parametros") or {})
        params["ferramenta_possivel"] = (interp.get("efeitos") or {}).get("ferramenta_possivel")
        zero = {"n": 0, "sucessos": 0, "falhas": 0, "p": 0.5, "ids": [], "inconclusivas": 0, "confianca": 0.0}
        cands = []
        for c in CAT.candidatas(interp["tipo_objetivo"], params, amb):
            por = {f: dict(zero) for f in FAIXAS} if interp["tipo_objetivo"] in CAT.FAMILIA_REGISTRO else {"sem_faixa": dict(zero)}
            cands.append({**c, "sinais_tarefa": dict(zero), "cognitivas_por_faixa": por, "conferencia_independente": all(V.conferivel(f) for f in c["ferramentas"])})
        return {"recuperado_em": self.rel(), "degradado": True, "motivo_degradado": motivo, "ambiente": amb, "fatos": [], "inferencias": [], "hipoteses_previas": [],
                "desconhecidos": [{"texto": "nenhuma experiência foi consultada: o módulo de contexto estava indisponível", "tipo": "desconhecido", "origem": "hub (modo degradado)"}],
                "candidatas": cands, "experiencias": {"cognitivas": [], "tarefa": []}, "licoes_provisorias": [], "memorias": []}

    def _fase_conhecimento(self, d):
        interp = d["interpretacao"]
        trabalhos, nos = [], {}
        nos["contexto"] = self._no(d, "conhecimento", "contexto", "recuperar", depende_de=[d["no_interpretacao"]])
        trabalhos.append(("contexto", lambda: self._chamar_no(d, nos["contexto"], "contexto", "recuperar", {"interpretacao": interp})))
        if d["conteudo"] is None:
            nos["conteudo"] = self._no(d, "conhecimento", "planejamento", "gerar_conteudo", depende_de=[d["no_interpretacao"]])
            trabalhos.append(("conteudo", lambda: self._chamar_no(d, nos["conteudo"], "planejamento", "gerar_conteudo", {"interpretacao": interp})))
        res, err = self._paralelo(d, trabalhos)
        for e in err.values():                                               # cancelamento e limite valem sempre, mesmo se um dos dois deu certo
            if isinstance(e, (Cancelado, LimiteExcedido, Parar)):
                raise e
        if "conteudo" in err:
            raise err["conteudo"]
        if "contexto" in err:
            e = err["contexto"]
            if not isinstance(e, (ModuloIndisponivel, ChamadaFalhou)):
                raise e
            ctx = self._contexto_minimo(interp, str(e)[:200])
            self._degradar(d, "contexto", str(e)[:200], "segui só com o catálogo, sem consultar experiências; o plano vai exigir o dono")
            self._no_resumo(nos["contexto"], "degradado: " + str(e)[:120])
        else:
            ctx = res["contexto"]
        with self.arm.trava:
            d["contexto"] = ctx
            if "conteudo" in res:
                d["conteudo"] = res["conteudo"]["conteudo"]
            c = d["conteudo"]
        self._salvar()
        self._no_resumo(nos["contexto"], f"{len(ctx.get('fatos') or [])} fato(s), {len(ctx['candidatas'])} estratégia(s), degradado={bool(ctx.get('degradado'))}")
        self._evento(d, "contexto", degradado=bool(ctx.get("degradado")), fatos=len(ctx.get("fatos") or []), candidatas=[x["id"] for x in ctx["candidatas"]],
                     desconhecidos=len(ctx.get("desconhecidos") or []), texto=f"reuni {len(ctx.get('fatos') or [])} fato(s) e {len(ctx['candidatas'])} estratégia(s) candidata(s)"
                     + (" (SEM experiências: modo degradado)" if ctx.get("degradado") else ""))
        if "conteudo" in res or d["ciclo"] == 0:
            self._evento(d, "conteudo_gerado", tamanho=c.get("tamanho"), hash=c.get("hash"), texto=f"conteúdo gerado: {c.get('tamanho')} caracteres ({c.get('gerado_por')})")
        self._ir_para(d, "hipoteses", "levantar e comparar hipóteses")

    # ------------------------------------------------------------------ fase 3: hipóteses
    def _hipoteses_minimas(self, ctx, interp, tentadas, motivo):
        ranking, excluidas = [], []
        for i, c in enumerate(ctx["candidatas"]):
            if not c.get("disponivel", True):
                excluidas.append({"id": c["id"], "motivo": c.get("motivo_indisponivel") or "indisponível"})
            elif c["id"] in tentadas:
                excluidas.append({"id": c["id"], "motivo": "já tentada neste objetivo"})
            else:
                perfil = c.get("perfil") or {}
                ranking.append({"id": c["id"], "n": 0, "sucessos": 0, "falhas": 0, "p": 0.5, "experiencias": [], "cognitivas": {"n": 0, "sucessos": 0, "falhas": 0, "p": 0.5, "ids": []},
                                "condicoes_da_contagem": ctx.get("ambiente") or {}, "impacto": perfil.get("impacto", 1.0), "custo": perfil.get("custo", 1.0), "viavel": True, "hipotese": None,
                                "motivo": "ordem do catálogo (hipóteses indisponíveis: nenhuma comparação foi feita)", "posicao": len(ranking) + 1})
        esc = {"em": ctx.get("recuperado_em"), "tipo": interp["tipo_objetivo"], "condicoes": ctx.get("ambiente") or {}, "faixa_tamanho": "sem_faixa",
               "regra": "EMERGÊNCIA: o módulo de hipóteses estava indisponível; usei a primeira estratégia disponível na ordem do catálogo",
               "ranking": ranking, "excluidas": excluidas, "escolhida": ranking[0]["id"] if ranking else None}
        return {"hipoteses": [], "comparacao": [], "escolha": esc, "faixa_tamanho": "sem_faixa", "contexto_degradado": True, "degradado": True, "motivo_degradado": motivo}

    def _fase_hipoteses(self, d):
        ctx, interp = d["contexto"], d["interpretacao"]
        no = self._no(d, "hipoteses", "hipoteses", "gerar", depende_de=[n["id"] for n in d["grafo"] if n["ciclo"] == d["ciclo"] and n["fase"] == "conhecimento"])
        corpo = {"interpretacao": interp, "conteudo": d["conteudo"], "candidatas": ctx["candidatas"], "ambiente": ctx.get("ambiente"), "tentativas_anteriores": d["tentativas_anteriores"],
                 "instante_do_contexto": ctx.get("recuperado_em"), "contexto_degradado": bool(ctx.get("degradado"))}
        try:
            h = self._chamar_no(d, no, "hipoteses", "gerar", corpo)
        except (ModuloIndisponivel, ChamadaFalhou) as e:
            h = self._hipoteses_minimas(ctx, interp, {t["estrategia"] for t in d["tentativas_anteriores"]}, str(e)[:200])
            self._degradar(d, "hipoteses", str(e)[:200], "usei a ordem do catálogo, sem comparar hipóteses; o plano vai exigir o dono")
            self._no_resumo(no, "degradado: " + str(e)[:120])
        with self.arm.trava:
            d["hipoteses"] = h
        self._salvar()
        esc = h["escolha"]
        self._no_resumo(no, f"{len(h.get('hipoteses') or [])} hipótese(s); na frente: {esc.get('escolhida')}")
        self._evento(d, "hipoteses", escolhida=esc.get("escolhida"), ranking=[{"id": r["id"], "p": r["p"], "n": r["n"], "viavel": r["viavel"]} for r in esc.get("ranking") or []],
                     excluidas=[{"id": x["id"], "motivo": x["motivo"]} for x in esc.get("excluidas") or []],
                     texto=f"{len(h.get('hipoteses') or [])} hipótese(s) comparadas; na frente: «{esc.get('escolhida')}»" + (f" ({esc['ranking'][0]['motivo']})" if esc.get("ranking") else ""))
        with self.arm.trava:
            D.decisao(d, "hipoteses", f"estratégia na frente: «{esc.get('escolhida')}»", esc.get("regra") or "", self.rel(),
                      {"ranking": [(r["id"], r["p"], r["n"]) for r in esc.get("ranking") or []]})
        self._ir_para(d, "plano", "montar o plano com previsões, riscos e critérios")

    # ------------------------------------------------------------------ fase 4: plano
    def _fase_plano(self, d):
        no = self._no(d, "plano", "planejamento", "montar_plano", depende_de=[n["id"] for n in d["grafo"] if n["ciclo"] == d["ciclo"] and n["fase"] == "hipoteses"])
        versao = len(d["planos"]) + 1
        ant = self._plano_reg(d)["plano"] if d["planos"] else None
        corpo = {"interpretacao": d["interpretacao"], "hipoteses": d["hipoteses"], "conteudo": d["conteudo"], "contexto": {k: d["contexto"].get(k) for k in ("fatos", "desconhecidos", "degradado")},
                 "candidatas": d["contexto"]["candidatas"], "objetivo": {"id": d["id"], "descricao": d["descricao"]}, "versao": versao,
                 "limites": {"max_replanos": self.cfg["max_replanos"]}, "contexto_degradado": bool(d["contexto"].get("degradado")),
                 "plano_anterior": {"versao": ant["versao"], "estrategia": ant.get("estrategia")} if ant else None, "motivo_da_revisao": d.get("motivo_revisao")}
        try:
            r = self._chamar_no(d, no, "planejamento", "montar_plano", corpo)
        except ChamadaFalhou as e:
            if e.codigo == "dependencia_ausente":                           # esgotou as alternativas permitidas: não é falha do módulo, é fim das opções
                self._no_resumo(no, e.texto[:160])
                self._parar_com(d, "precisa_do_dono", "Esgotei as estratégias permitidas para este objetivo: " + e.texto, tipo="sem_alternativas", recuperavel=False,
                                proxima="Nenhuma estratégia viável e ainda não tentada. Veja o que foi tentado e decida como seguir.")
            raise
        plano = r["plano"]
        sig = assinatura(plano)
        for p in d["planos"]:
            if p.get("assinatura") == sig:
                self._no_resumo(no, "plano igual a um anterior")
                self._evento(d, "laco_detectado", versao=versao, igual_a=p["versao"], texto=f"o plano v{versao} é igual ao v{p['versao']}: repetir não muda nada, então parei")
                self._parar_com(d, "bloqueado", f"O plano v{versao} é idêntico ao v{p['versao']}: replanejar não está mudando nada (laço).", tipo="laco_de_replanejamento", recuperavel=False,
                                proxima="O replanejamento não produziu nada novo; é preciso mudar o pedido ou o ambiente.")
        reg = {"versao": versao, "hash": plano["hash"], "assinatura": sig, "plano": plano, "criado_em": self.rel(), "critica": None, "coerencia": None, "autorizacao": None, "execucao": None,
               "verificacao": None, "aprendizagem": None}
        with self.arm.trava:
            d["planos"].append(reg)
            d["plano_atual"] = versao
            d["motivo_revisao"] = None
            D.decisao(d, "planejamento", f"plano v{versao}: estratégia «{plano.get('estrategia')}»", (plano.get("etapas") or [{}])[-1].get("justificativa") or "", self.rel(), {"hash": plano["hash"]})
        self._salvar()
        self._no_resumo(no, f"plano v{versao}, {len(plano['etapas'])} etapas, estratégia {plano.get('estrategia')}")
        self._evento(d, "plano", versao=versao, hash=plano["hash"], estrategia=plano.get("estrategia"), etapas=len(plano["etapas"]), executavel=plano.get("executavel"),
                     criterios=[c["id"] for c in plano["criterios_de_sucesso"]], texto=f"plano v{versao} montado (estratégia «{plano.get('estrategia')}», {len(plano['etapas'])} etapas, hash {plano['hash'][:8]})")
        self._ir_para(d, "revisao", "revisar o plano (crítica independente) e conferir a coerência do conteúdo")

    # ------------------------------------------------------------------ fase 5: revisão (crítica ‖ coerência)
    def _catalogo_para_critica(self, passos):
        import broker as B
        cat = {}
        for p in passos:
            f = p.get("ferramenta")
            if f in B.FERRAMENTAS:
                cat[f] = {"nivel": CAT.nivel_de(f, p.get("args")), "perfil": EXP.PERFIS.get(f)}
        return cat

    def _fase_revisao(self, d):
        reg = self._plano_reg(d)
        plano, interp = reg["plano"], d["interpretacao"]
        passos = []
        if plano.get("executavel"):
            try:
                passos = EX.derivar_passos(plano, interp)
            except ValueError as e:
                passos = []
                self._evento(d, "passos_nao_derivados", texto=f"o catálogo não consegue montar os passos deste plano: {e}")
        ctx = d["contexto"]
        cand = next((c for c in ctx["candidatas"] if c["id"] == plano.get("estrategia")), {})
        deps = [n["id"] for n in d["grafo"] if n["ciclo"] == d["ciclo"] and n["fase"] == "plano"]
        no_c = self._no(d, "revisao", "critica", "revisar", depende_de=deps)
        no_v = self._no(d, "revisao", "verificador", "coerencia_conteudo", depende_de=deps)
        corpo_c = {"plano": plano, "passos_derivados": passos, "catalogo_ferramentas": self._catalogo_para_critica(passos), "interpretacao": interp,
                   "tentativas_anteriores": d["tentativas_anteriores"], "limites_declarados": cand.get("limites_declarados") or [],
                   "origem_objetivo": {"origem": d["origem"], "aceito": d["origem_aceita"]}, "limites_de_ciclo": {"max_replanos": self.cfg["max_replanos"]}}
        res, err = self._paralelo(d, [("critica", lambda: self._chamar_no(d, no_c, "critica", "revisar", corpo_c, plano=plano)),
                                      ("coerencia", lambda: self._chamar_no(d, no_v, "verificador", "coerencia_conteudo", {"conteudo": d["conteudo"], "interpretacao": interp}, plano=plano))])
        for e in err.values():
            raise e                                                          # os dois são críticos: sem a crítica ou sem a verificação prévia, nada avança (falha fechada)
        cr, co = res["critica"], res["coerencia"]
        if cr.get("plano_hash") != plano["hash"] or (cr.get("veredito") == "aprovado" and cr.get("hash_recalculado") != plano["hash"]):
            raise ChamadaFalhou("critica", "erro_interno", "o veredito da crítica não é sobre o hash do plano enviado")
        with self.arm.trava:
            reg["critica"], reg["coerencia"] = cr, co
            D.decisao(d, "critica", cr["resumo"], "; ".join(c["detalhe"] for c in cr["checagens"] if not c["ok"]) or "todas as regras passaram", self.rel(),
                      {"veredito": cr["veredito"], "plano_hash": cr["plano_hash"], "autorizacao_necessaria": cr["autorizacao_necessaria"]})
        self._salvar()
        self._no_resumo(no_c, f"{cr['veredito']}; autorização {'exigida' if cr['autorizacao_necessaria'] else 'não exigida'}")
        self._no_resumo(no_v, "coerente" if co["coerente"] else "incoerente: " + "; ".join(co["problemas"])[:120])
        self._evento(d, "critica", veredito=cr["veredito"], plano_hash=cr["plano_hash"], versao=plano["versao"], motivos=cr.get("motivos"), regras=[(c["regra"], c["ok"]) for c in cr["checagens"]],
                     autorizacao_necessaria=cr["autorizacao_necessaria"], texto=f"crítica ao plano v{plano['versao']}: {cr['veredito']} — {cr['resumo']}")
        self._evento(d, "coerencia", coerente=co["coerente"], problemas=co["problemas"], texto="verificação prévia do conteúdo: " + ("coerente" if co["coerente"] else "problemas: " + "; ".join(co["problemas"])))
        if cr["veredito"] == "rejeitado":
            self._parar_com(d, "bloqueado", cr["resumo"], tipo="critica_rejeitou", modulo="critica", recuperavel=False, proxima="A crítica rejeitou o plano; nada será executado.")
        if cr["veredito"] == "devolvido" or not co["coerente"]:
            with self.arm.trava:
                d["uso"]["revisoes_critica"] += 1
                n = d["uso"]["revisoes_critica"]
                d["motivo_revisao"] = "; ".join([m["texto"] for m in cr.get("motivos") or []] + co["problemas"])[:400]
            if n > self.cfg["max_revisoes_critica"]:
                self._parar_com(d, "bloqueado", f"A crítica devolveu o plano {n} vez(es) (limite {self.cfg['max_revisoes_critica']}): {d['motivo_revisao']}", tipo="limite_de_revisoes", modulo="critica",
                                recuperavel=False, proxima="O plano continua sendo devolvido; é preciso mudar o pedido.")
            self._evento(d, "plano_devolvido", revisao=n, texto=f"plano devolvido para revisão ({n} de {self.cfg['max_revisoes_critica']}): {d['motivo_revisao']}")
            self._ir_para(d, "plano", "refazer o plano conforme a crítica")
            return
        self._ir_para(d, "autorizacao", "decidir se o dono precisa autorizar")

    # ------------------------------------------------------------------ fase 6: autorização
    def _fase_autorizacao(self, d):
        reg = self._plano_reg(d)
        plano, cr = reg["plano"], reg["critica"]
        if cr is None or cr["plano_hash"] != plano["hash"] or cr["veredito"] != "aprovado":
            self._parar_com(d, "bloqueado", "Sem crítica aprovada para este plano exato.", tipo="sem_critica_valida", modulo="critica", recuperavel=False)
        if not plano.get("executavel") or d["so_planejar"]:
            with self.arm.trava:
                d["resultado_final"] = {"tipo": "plano_entregue", "executado": False, "texto": "plano pronto e conferido; nada foi executado" + (" (pedido só de planejamento)" if d["so_planejar"] else " (este pedido não manda executar)")}
            self._evento(d, "plano_entregue", versao=plano["versao"], texto="plano pronto e conferido; nada foi executado")
            self._parar_com(d, "plano_pronto", "Plano pronto, conferido e não executado.", tipo="plano_pronto", proxima="Revise o plano. Para executar, use «executar» (o plano será revisado de novo se mudar).")
        exig = list(cr.get("exigencias_de_autorizacao") or [])
        if d["contexto"].get("degradado"):
            exig.append({"motivo": "o plano foi feito em modo degradado (sem consultar experiências)", "fonte": "hub"})
        if d["hipoteses"].get("degradado"):
            exig.append({"motivo": "as hipóteses não foram comparadas (módulo indisponível)", "fonte": "hub"})
        if exig:
            with self.arm.trava:
                d["autorizacao"] = {"pedida_em": self.rel(), "plano_versao": plano["versao"], "plano_hash": plano["hash"], "exigencias": exig,
                                    "resumo_do_plano": {"estrategia": plano.get("estrategia"), "etapas": [e["descricao"] for e in plano["etapas"] if e["tipo"] == "execucao"],
                                                         "ferramentas": [f for e in plano["etapas"] if e["tipo"] == "execucao" for f in (e.get("ferramentas") or [])], "riscos": [r["texto"] for r in plano["riscos_e_incertezas"]][:6]}}
                reg["autorizacao"] = {"estado": "pedida", **d["autorizacao"]}
            self._evento(d, "autorizacao_pedida", versao=plano["versao"], plano_hash=plano["hash"], exigencias=[e["motivo"] for e in exig],
                         texto=f"preciso da sua autorização para o plano v{plano['versao']} (hash {plano['hash'][:8]}): " + "; ".join(e["motivo"] for e in exig))
            self._parar_com(d, "aguardando_autorizacao", "Aguardando a autorização do dono para o plano exato (v%d, hash %s)." % (plano["versao"], plano["hash"][:8]), tipo="autorizacao", pausa=True,
                            proxima=f"Diga «autorizo o plano do objetivo {d['id']}» (vale só para este plano) ou «nego o plano do objetivo {d['id']}», ou use o painel /precortex.")
        with self.arm.trava:
            d["autorizacao_concedida"] = {"plano_hash": plano["hash"], "plano_versao": plano["versao"], "via": "escopo_do_pedido", "em": self.rel(),
                                          "motivo": "ação local de baixo impacto, dentro do que o próprio dono pediu; a crítica não exigiu o dono"}
            reg["autorizacao"] = {"estado": "dispensada", **d["autorizacao_concedida"]}
            D.decisao(d, "coordenacao", "autorização dispensada pelo escopo do pedido", d["autorizacao_concedida"]["motivo"], self.rel())
        self._salvar()
        self._evento(d, "autorizacao_dispensada", versao=plano["versao"], texto="o próprio pedido do dono cobre esta ação local de baixo impacto; o corretor continua valendo")
        self._ir_para(d, "execucao", "executar pelo corretor")

    def _exigir_autorizado(self, d, reg):
        """Defesa em profundidade: confere de novo, JUNTO da execução, o que as fases anteriores deveriam ter garantido."""
        plano, cr, au = reg["plano"], reg["critica"], d.get("autorizacao_concedida")
        problemas = []
        if cr is None or cr.get("veredito") != "aprovado" or cr.get("plano_hash") != plano["hash"]:
            problemas.append("não há crítica aprovada para este plano exato")
        if reg["coerencia"] is None or not reg["coerencia"].get("coerente"):
            problemas.append("a verificação prévia do conteúdo não aprovou")
        if not au or au.get("plano_hash") != plano["hash"]:
            problemas.append("não há autorização para este plano exato")
        if C.hash_plano(plano) != plano["hash"]:
            problemas.append("o plano foi alterado depois de assinado")
        if problemas:
            self._evento(d, "execucao_barrada", problemas=problemas, texto="execução barrada: " + "; ".join(problemas))
            self._parar_com(d, "bloqueado", "Execução barrada: " + "; ".join(problemas) + ".", tipo="execucao_barrada", recuperavel=False)

    # ------------------------------------------------------------------ fase 7: execução
    def _fase_execucao(self, d):
        reg_plano = self._plano_reg(d)
        plano = reg_plano["plano"]
        self._exigir_autorizado(d, reg_plano)
        try:
            passos = EX.derivar_passos(plano, d["interpretacao"])
        except ValueError as e:
            self._parar_com(d, "bloqueado", f"Não consegui derivar os passos do catálogo: {e}", tipo="passos", recuperavel=False)
        ev = lambda t, **k: self._evento(d, t, **k)                           # noqa: E731
        no = self._no(d, "execucao", "coordenacao", "executar", depende_de=[n["id"] for n in d["grafo"] if n["ciclo"] == d["ciclo"] and n["fase"] in ("revisao", "autorizacao")])
        self._no_iniciar(no)
        reg = d["execucoes"].get(EX.chave(plano, plano["versao"]))
        if reg is None:
            reg, _ = EX.registrar_antes(d, plano, passos, plano["versao"], salvar=self._salvar, evento=ev)
        th = self._iniciar_execucao(d, reg, plano, passos, ev)
        t0, avisou, relancadas = self.rel(), False, 0
        while True:
            self._conferir(d, tolerar_tempo=True)
            obs = EX.observar(reg)
            if obs["final"]:
                break
            if obs["aguardando_corretor"]:
                with self.arm.trava:
                    reg["estado"] = "aguardando_corretor"
                self._no_fim(no, "aguardando", "esperando a confirmação do dono no corretor")
                self._evento(d, "aguardando_corretor", tarefa=obs["tarefa"], texto=f"o corretor exige a confirmação do dono para a tarefa {obs['tarefa']}; nada foi executado ainda")
                self._parar_com(d, "aguardando_confirmacao_do_corretor", "Aguardando a confirmação do dono no corretor (a autorização do plano não substitui a confirmação da ação).", tipo="confirmacao_do_corretor",
                                pausa=True, proxima="Confirme no corretor (diga «confirmo …» com o PIN, se pedido) ou cancele.")
            if th is not None and not th.is_alive() and obs["estado"] == "PRONTA":
                nunca = all(p["estado"] == "pendente" for p in obs["passos"])
                if nunca and relancadas < 3:                                  # a tarefa esperou um recurso e voltou sem tentar nada: tentar de novo é seguro
                    relancadas += 1
                    self.dormir(0.3)
                    th = EX.executar_em_segundo_plano(reg, evento=ev)
                    continue
                self._parar_com(d, "precisa_do_dono", "A tarefa parou sem terminar e não sei se algo foi executado; por segurança não repeti.", tipo="execucao_parada", recuperavel=False)
            if self.rel() - t0 > self.cfg["timeout_execucao_s"] * 10:
                self._parar_com(d, "precisa_do_dono", f"A execução não terminou em {self.cfg['timeout_execucao_s'] * 10:.0f}s. Não repeti a ação; veja o estado da tarefa {obs['tarefa']}.", tipo="execucao_demorou_demais", recuperavel=False)
            if not avisou and self.rel() - t0 > self.cfg["timeout_execucao_s"]:
                avisou = True
                with self.arm.trava:
                    d["estado"] = "aguardando_execucao"
                self._salvar()
                self._evento(d, "execucao_demorando", tarefa=obs["tarefa"], texto=f"a execução passou de {self.cfg['timeout_execucao_s']:.0f}s; continuo esperando e NÃO vou repetir a ação")
            self.dormir(0.05)
        with self.arm.trava:
            reg["estado"], reg["terminada_em"] = "terminada", self.rel()
            reg_plano["execucao"] = obs
            if d["estado"] == "aguardando_execucao":
                d["estado"] = "em_andamento"
            D.decisao(d, "coordenacao", f"execução pelo corretor terminou: tarefa {obs['tarefa']} {obs['rotulo']}", obs.get("causa") or "sem causa registrada", self.rel(), {"codigo": obs.get("codigo")})
        self._salvar()
        self._no_fim(no, "concluido" if obs["estado"] == "CONCLUIDA" else "falhou", f"tarefa {obs['tarefa']}: {obs['rotulo']}" + (f" ({obs['causa']})" if obs.get("causa") else ""))
        self._evento(d, "execucao_concluida", tarefa=obs["tarefa"], estado=obs["estado"], rotulo=obs["rotulo"], codigo=obs.get("codigo"), causa=obs.get("causa"),
                     texto=f"o corretor terminou: tarefa {obs['tarefa']} {obs['rotulo']}" + (f" — {obs['causa']}" if obs.get("causa") else "") + ". Isto ainda NÃO prova o efeito: falta a verificação independente.")
        self._ir_para(d, "verificacao", "conferir o efeito por leitura independente")

    def _iniciar_execucao(self, d, reg, plano, passos, ev):
        """Cria a tarefa uma única vez (ou reanexa à que já existe) e a executa uma única vez. Devolve a linha que executa neste processo, ou None."""
        import tarefas as T
        origem_t = "usuario" if d["origem"] != "sugerido_pelo_sistema" else "propria"
        if reg["tarefa"] is None:
            EX.criar_tarefa(d, reg, plano, passos, origem_tarefa=origem_t, salvar=self._salvar, evento=ev)
            EX.gravar_intencao(d, reg, plano, (d["hipoteses"] or {}).get("hipoteses"))
            self._salvar()
            return EX.executar_em_segundo_plano(reg, evento=ev)
        obs = EX.observar(reg)
        if T.ATIVAS.get(reg["tarefa"]):
            return None                                                     # este processo já a está executando (reentrada); só esperar
        if obs["final"] or obs["aguardando_corretor"]:
            return None
        if obs["estado"] in ("EXECUTANDO", "VERIFICANDO"):
            r = EX.recuperar(reg)                                           # sobra de queda: o módulo de tarefas olha o mundo e NUNCA repete sozinho
            ev("execucao_recuperada", tarefa=reg["tarefa"], achado=r, texto="depois de uma interrupção, deixei o módulo de tarefas conferir no mundo o que aconteceu (sem repetir)")
            return None
        if obs["estado"] == "PRONTA" and reg["estado"] in ("tarefa_criada",) and all(p["estado"] == "pendente" and not p.get("tentativas") for p in _passos_brutos(reg)):
            return EX.executar_em_segundo_plano(reg, evento=ev)               # criada mas nunca entregue ao corretor: executar agora é seguro
        return None

    # ------------------------------------------------------------------ fase 8: verificação
    def _fase_verificacao(self, d):
        reg_plano = self._plano_reg(d)
        plano = reg_plano["plano"]
        reg = d["execucoes"][EX.chave(plano, plano["versao"])]
        obs = reg_plano["execucao"] or EX.observar(reg)
        passos = EX.derivar_passos(plano, d["interpretacao"])
        no = self._no(d, "verificacao", "verificador", "verificar", depende_de=[n["id"] for n in d["grafo"] if n["ciclo"] == d["ciclo"] and n["fase"] == "execucao"])
        corpo = {"plano": plano, "passos_derivados": passos, "marcas": reg["marcas"], "interpretacao": d["interpretacao"],
                 "execucao": {"estado": obs.get("estado"), "tarefa": obs.get("tarefa"), "codigo": obs.get("codigo"), "causa": obs.get("causa")}}
        ver = self._chamar_no(d, no, "verificador", "verificar", corpo, plano=plano)
        with self.arm.trava:
            reg_plano["verificacao"] = ver
            d["verificacoes"].append({"plano_versao": plano["versao"], "veredito": ver["veredito"], "resumo": ver.get("observado_resumo"), "em": self.rel()})
            del d["verificacoes"][:-20]
            D.decisao(d, "verificador", f"verificação independente: {ver['veredito']}", ver.get("observado_resumo") or "", self.rel(), {"fonte": ver.get("fonte"), "discordancia": ver.get("discordancia_com_a_execucao")})
        self._salvar()
        self._no_resumo(no, f"{ver['veredito']}: {ver.get('observado_resumo')}")
        self._evento(d, "verificacao", veredito=ver["veredito"], independente=ver.get("independente"), fonte=ver.get("fonte"), medidas=ver.get("medidas"), discordancia=ver.get("discordancia_com_a_execucao"),
                     criterios=[(c.get("id"), c.get("ok")) for c in ver.get("criterios") or []],
                     texto=f"verificação independente: {ver['veredito']} — {ver.get('observado_resumo')}" + (" (a execução tinha dito o contrário)" if ver.get("discordancia_com_a_execucao") else ""))
        self._ir_para(d, "aprendizagem", "registrar previsão × resultado")

    # ------------------------------------------------------------------ fase 9: aprendizagem
    def _fase_aprendizagem(self, d):
        reg_plano = self._plano_reg(d)
        plano, ver, obs = reg_plano["plano"], reg_plano["verificacao"], reg_plano["execucao"] or {}
        no = self._no(d, "aprendizagem", "aprendizagem", "registrar", depende_de=[n["id"] for n in d["grafo"] if n["ciclo"] == d["ciclo"] and n["fase"] == "verificacao"])
        corpo = {"objetivo": d["id"], "tentativa": plano["versao"], "plano": plano, "verificacao": ver, "interpretacao": d["interpretacao"], "hipoteses": (d["hipoteses"] or {}).get("hipoteses") or [],
                 "execucao": {"estado": obs.get("estado"), "tarefa": obs.get("tarefa"), "experiencia_tarefa": obs.get("experiencia_tarefa"), "codigo": obs.get("codigo"), "causa": obs.get("causa")}}
        try:
            ap = self._chamar_no(d, no, "aprendizagem", "registrar", corpo, plano=plano)
        except (ModuloIndisponivel, ChamadaFalhou) as e:
            self._degradar(d, "aprendizagem", str(e)[:200], "a lição desta tentativa NÃO foi registrada")
            self._no_resumo(no, "degradado: " + str(e)[:120])
            ap = {"registrado": False, "motivo": str(e)[:200]}
        with self.arm.trava:
            reg_plano["aprendizagem"] = ap
            if ap.get("registrado"):
                d["aprendizados"].append({"plano_versao": plano["versao"], "id": ap.get("id"), "resultado": ap.get("resultado"), "efeito": (ap.get("efeito_na_selecao") or {}).get("texto"),
                                          "licoes": [l["texto"] for l in ap.get("licoes") or []], "investigar": ap.get("investigar"), "hipotese_status": ap.get("hipotese_status"), "em": self.rel()})
                del d["aprendizados"][:-20]
                D.decisao(d, "aprendizagem", f"registrei {ap.get('id')}: {ap.get('resultado')}", (ap.get("efeito_na_selecao") or {}).get("texto") or "", self.rel(), {"hipotese": ap.get("hipotese_status")})
        self._salvar()
        self._no_resumo(no, f"{ap.get('id')} {ap.get('resultado')}" if ap.get("registrado") else "não registrado")
        self._evento(d, "aprendizagem", registrado=ap.get("registrado"), id=ap.get("id"), resultado=ap.get("resultado"), efeito=(ap.get("efeito_na_selecao") or {}).get("texto"),
                     hipotese=ap.get("hipotese_status"), investigar=ap.get("investigar"), duplicado=ap.get("duplicado"),
                     texto=(f"registrei a lição {ap.get('id')}: {ap.get('resultado')}. " + ((ap.get("efeito_na_selecao") or {}).get("texto") or "") + " Uma observação só não vira regra.") if ap.get("registrado")
                     else f"não consegui registrar a lição: {ap.get('motivo')}")
        self._ir_para(d, "decisao", "decidir: concluir, replanejar ou pedir o dono")

    # ------------------------------------------------------------------ fase 10: decisão / replanejamento
    def _fase_decisao(self, d):
        reg_plano = self._plano_reg(d)
        plano, ver = reg_plano["plano"], reg_plano["verificacao"]
        obs = reg_plano["execucao"] or {}
        v = ver["veredito"]
        if v == "sucesso":
            with self.arm.trava:
                d["resultado_final"] = {"tipo": "concluido", "executado": True, "estrategia": plano.get("estrategia"), "texto": ver.get("observado_resumo"), "plano_versao": plano["versao"], "replanos": d["uso"]["replanos"]}
                D.decisao(d, "coordenacao", "objetivo concluído", "a verificação independente confirmou todos os critérios", self.rel())
            self._evento(d, "concluido", texto=f"objetivo concluído com a estratégia «{plano.get('estrategia')}»; a verificação independente confirmou. Tentativas: {len(d['planos'])}", replanos=d["uso"]["replanos"])
            self._ir_para(d, "fim", "nada: concluído")
            with self.arm.trava:
                d["estado"], d["proxima_etapa"], d["bloqueio"] = "concluido", "nada: objetivo concluído e conferido", None
                d["atualizado_em"] = self.rel()
            self._salvar()
            raise Parar()
        if v == "inconclusivo" or obs.get("estado") in ("EXECUTADA_SEM_VERIFICACAO", "PRECISA_INTERVENCAO"):
            with self.arm.trava:
                d["resultado_final"] = {"tipo": "inconclusivo", "executado": True, "estrategia": plano.get("estrategia"), "texto": ver.get("observado_resumo")}
            self._parar_com(d, "precisa_do_dono", f"Executei, mas não consegui conferir por fora ({ver.get('observado_resumo')}). Só você pode dizer se deu certo; não repeti nem repito sozinha.", tipo="inconclusivo",
                            recuperavel=False, proxima="Veja se o efeito aconteceu e me diga; eu não conto como sucesso o que não consegui conferir.")
        # falha parcial ou total: replanejar, dentro dos limites
        with self.arm.trava:
            d["tentativas_anteriores"].append({"estrategia": plano.get("estrategia"), "resultado": "parcial" if v == "parcial" else "falha", "plano_versao": plano["versao"], "plano_hash": plano["hash"],
                                               "motivo": ver.get("observado_resumo"), "aprendizado": (reg_plano["aprendizagem"] or {}).get("id")})
            n = d["uso"]["replanos"]
        if n >= self.cfg["max_replanos"]:
            self._evento(d, "limite_atingido", limite="replanos", texto=f"limite de {self.cfg['max_replanos']} replanejamento(s) atingido")
            self._parar_com(d, "bloqueado", f"Cheguei ao limite de {self.cfg['max_replanos']} replanejamento(s) sem cumprir o objetivo.", tipo="limite_de_replanos", recuperavel=False,
                            proxima="Parei de tentar para não ficar em laço. Veja as tentativas e decida.")
        ef = (reg_plano["aprendizagem"] or {}).get("efeito_na_selecao") or {}
        motivo = (f"«{plano.get('estrategia')}» não cumpriu por inteiro ({ver.get('observado_resumo')}). " + (ef.get("texto") or "") + " Vou procurar outra estratégia permitida, ainda não tentada.").strip()
        with self.arm.trava:
            d["uso"]["replanos"] += 1
            d["ciclo"] += 1
            d["motivo_revisao"] = f"a estratégia anterior («{plano.get('estrategia')}») falhou: {ver.get('observado_resumo')}"
            D.decisao(d, "coordenacao", f"replanejar (replanejamento {d['uso']['replanos']} de {self.cfg['max_replanos']})", motivo, self.rel(), {"de": plano.get("estrategia")})
        self._evento(d, "replanejamento", numero=d["uso"]["replanos"], de=plano.get("estrategia"), resultado=v, texto=f"replanejando: {motivo}")
        self._ir_para(d, "conhecimento", "reunir contexto de novo (já com a lição desta tentativa) e escolher outra estratégia")


def _passos_brutos(reg):
    import tarefas as T
    t = T.obter(reg["tarefa"])
    return t["passos"] if t else []
