"""Fase 7 — cada um dos nove neurônios do pré-córtex, isolado: responsabilidade, entradas e saídas, e o que ele NÃO pode fazer.

As entradas são as reais: um objetivo roda «só planejar» num hub local e o dossiê dele vira o material dos testes; depois cada neurônio é chamado direto, com a entrada mexida.
Mapa: 1 percepção · 2 contexto · 3 hipóteses · 4 planejamento · 5 crítica (área 5: plano inseguro rejeitado) · 6 coordenação (no fluxo e no registro antes de agir) ·
7 verificação (área 11) · 8 aprendizagem (área 12) · 9 monitoramento; e exploração controlada.
"""
import copy, os, tempfile, unittest
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import experiencias as X
from test_experiencias import Base
import pre_cortex.catalogo_neuronios as K
import pre_cortex.config as CF
import pre_cortex.contrato as C
import pre_cortex.execucao as EX
import pre_cortex.exploracao as EXP
import pre_cortex.hub as HB
import pre_cortex.leitores as L
from pre_cortex.neuronio import Contexto
from pre_cortex.percepcao import Percepcao
from pre_cortex.contexto import ContextoMemoria
from pre_cortex.hipoteses import Hipoteses
from pre_cortex.planejamento import Planejamento
from pre_cortex.critica import Critica
from pre_cortex.verificador import Verificador
from pre_cortex.aprendizagem import Aprendizagem
from pre_cortex.monitor import Monitor

PEDIDO = "Monte um plano de estudos de Python para 4 semanas, com no máximo 90 minutos por dia, e guarde"


def ctx(cancelado=False, corr="pc0001"):
    return Contexto({"id": "m-0123456789abcdef", "correlacao": corr, "plano": None}, lambda: cancelado, "teste", "teste")


class BaseN(Base):
    def material(self, pedido=PEDIDO):
        """Roda «só planejar» e devolve o dossiê + as peças que a crítica recebe."""
        c = CF.Config()
        h = HB.Hub(c, tempfile.mkdtemp(prefix="pc-", dir=E.TMP), vigia=False)
        self.addCleanup(h.encerrar, 2.0)
        r = h.submeter(pedido, so_planejar=True)
        self.assertEqual(h.esperar(r["id"], 60), "plano_pronto")
        d = h.dossie(r["id"])
        plano = d["planos"][-1]["plano"]
        passos = EX.derivar_passos(plano, d["interpretacao"])
        cand = next(c for c in d["contexto"]["candidatas"] if c["id"] == plano["estrategia"])
        corpo_critica = {"plano": plano, "passos_derivados": passos, "catalogo_ferramentas": h._catalogo_para_critica(passos), "interpretacao": d["interpretacao"],
                         "tentativas_anteriores": [], "limites_declarados": cand["limites_declarados"], "origem_objetivo": {"origem": "pedido_do_dono", "aceito": True},
                         "limites_de_ciclo": {"max_replanos": 3}}
        return d, plano, passos, corpo_critica


class Contrato9(unittest.TestCase):
    def test_nove_neuronios_com_papel_interface_e_estado(self):
        ds = K.descricoes()
        self.assertEqual([x["numero"] for x in ds], list(range(1, 10)))
        for x in ds:
            for campo in ("nome", "papel", "responsabilidade", "entradas", "saidas", "confianca", "critico", "acoes"):
                self.assertTrue(x.get(campo) is not None and x.get(campo) != "", (x["nome"], campo))
        self.assertEqual({n for n, c in K.criticos().items() if c}, {"percepcao", "planejamento", "critica", "verificador"})
        self.assertEqual({n for n, c in K.criticos().items() if not c}, {"contexto", "hipoteses", "aprendizagem", "monitor"}, "os que o fluxo sabe substituir em modo degradado")

    def test_acao_desconhecida_e_cancelamento_viram_resposta_de_erro(self):
        p = Percepcao()
        with self.assertRaises(C.ErroNeuronio) as e:
            p.tratar("apagar_tudo", {}, ctx())
        self.assertEqual(e.exception.codigo, "acao_desconhecida")
        with self.assertRaises(C.ErroNeuronio) as e:
            Verificador().tratar("verificar", {"plano": {}, "passos_derivados": [{"ferramenta": "anotar"}]}, ctx(cancelado=True))
        self.assertEqual(e.exception.codigo, "cancelada")


class N1Percepcao(unittest.TestCase):
    def interp(self, t):
        return Percepcao().tratar("interpretar", {"texto": t}, ctx())["interpretacao"]

    def test_plano_de_estudo(self):
        i = self.interp(PEDIDO)
        self.assertEqual((i["tipo_objetivo"], i["parametros"]["semanas"], i["parametros"]["minutos_dia"]), ("plano_de_estudo", 4, 90))
        self.assertFalse(i["efeitos"]["externo"])
        self.assertTrue(i["criterios_de_conclusao"])
        self.assertFalse(i["confianca"].get("calibrada", False))

    def test_acao_externa_com_contato_e_mensagem(self):
        i = self.interp("Mande um SMS para mae dizendo que chego tarde")
        self.assertEqual(i["tipo_objetivo"], "acao_externa")
        self.assertTrue(i["efeitos"]["externo"])
        self.assertEqual(i["efeitos"]["ferramenta_possivel"], "enviar_sms")
        self.assertEqual((i["parametros"]["contato"], i["parametros"]["mensagem"]), ("mae", "chego tarde"))

    def test_falta_dado_vira_pergunta(self):
        i = self.interp("mande um sms")
        self.assertIn("contato", i["faltando"])

    def test_pedido_nao_suportado_pede_esclarecimento(self):
        i = self.interp("qual é a capital da França?")
        self.assertFalse(i["suportado"])
        self.assertTrue(i["pede_esclarecimento"])

    def test_idempotente(self):
        self.assertEqual(self.interp(PEDIDO), self.interp(PEDIDO))


class N2a4Cognicao(BaseN):
    def test_contexto_separa_fato_inferencia_e_desconhecido_e_traz_a_experiencia(self):          # 2
        d, *_ = self.material()
        cx = ContextoMemoria().tratar("recuperar", {"interpretacao": d["interpretacao"]}, ctx())
        self.assertTrue(all(f["tipo"] == "fato" and f["origem"] for f in cx["fatos"]))
        self.assertTrue(all(x["tipo"] == "desconhecido" for x in cx["desconhecidos"]))
        self.assertEqual({c["id"] for c in cx["candidatas"]}, {"anotar", "anotar_em_partes", "criar_arquivo", "guardar_memoria"})
        # uma experiência registrada aparece na contagem da estratégia, na faixa de tamanho certa, com o id
        X.registrar_cognitiva({"objetivo": "pc0099", "tentativa": 1, "plano": {"id": "p", "versao": 1, "hash": "h" * 32}, "tipo_objetivo": "plano_de_estudo", "estrategia": "criar_arquivo",
                               "condicoes": {**X.ambiente(), "faixa_tamanho": "ate_2000"}, "resultado": "sucesso", "hipotese": {"id": "h1", "texto": "t"}, "previsao": {"texto": "p", "criterios": []},
                               "observado": {"resumo": "ok", "criterios": []}, "discrepancias": [], "fatores": [], "licoes": [], "investigar": [],
                               "proposta_de_ajuste": {"parametro": "ordem_de_estrategias", "escopo": "x", "efeito": "y", "reversivel": True}})
        cx2 = ContextoMemoria().tratar("recuperar", {"interpretacao": d["interpretacao"]}, ctx())
        ca = next(c for c in cx2["candidatas"] if c["id"] == "criar_arquivo")
        self.assertEqual(ca["cognitivas_por_faixa"]["ate_2000"]["sucessos"], 1)
        self.assertEqual(ca["cognitivas_por_faixa"]["ate_500"]["n"], 0, "experiência de outra faixa não conta")

    def test_hipoteses_ordenam_pela_evidencia_e_excluem_o_ja_tentado_e_o_inviavel(self):        # 3
        d, *_ = self.material()
        cands = copy.deepcopy(d["contexto"]["candidatas"])
        for c in cands:
            if c["id"] == "criar_arquivo":
                c["cognitivas_por_faixa"]["ate_2000"] = {"n": 2, "sucessos": 2, "falhas": 0, "p": 0.75, "ids": ["c0001", "c0002"], "inconclusivas": 0, "confianca": 0.5}
            if c["id"] == "guardar_memoria":
                c["limites_declarados"] = [{"campo": "texto", "maximo": 100, "unidade": "caracteres", "fonte": "teste"}]
        h = Hipoteses().tratar("gerar", {"interpretacao": d["interpretacao"], "conteudo": d["conteudo"], "candidatas": cands, "ambiente": d["contexto"]["ambiente"],
                                         "tentativas_anteriores": [{"estrategia": "anotar", "resultado": "falha"}]}, ctx())
        esc = h["escolha"]
        self.assertEqual(esc["escolhida"], "criar_arquivo")
        excl = {x["id"] for x in esc["excluidas"]}
        self.assertIn("anotar", excl)
        gm = next(r for r in esc["ranking"] if r["id"] == "guardar_memoria") if any(r["id"] == "guardar_memoria" for r in esc["ranking"]) else None
        self.assertTrue(gm is None or not gm["viavel"], "limite declarado estourado torna a hipótese inviável")
        for x in h["hipoteses"]:
            self.assertFalse(x["confianca"]["calibrada"])

    def test_planejamento_sem_estrategia_viavel_nao_inventa(self):                               # 4
        d, plano, *_ = self.material()
        hip = copy.deepcopy(d["hipoteses"])
        hip["escolha"]["escolhida"], hip["escolha"]["ranking"] = None, []
        with self.assertRaises(C.ErroNeuronio) as e:
            Planejamento().tratar("montar_plano", {"interpretacao": d["interpretacao"], "hipoteses": hip, "conteudo": d["conteudo"], "contexto": d["contexto"], "candidatas": d["contexto"]["candidatas"],
                                                   "objetivo": {"id": d["id"], "descricao": d["descricao"]}, "versao": 2, "limites": {"max_replanos": 3}}, ctx())
        self.assertEqual(e.exception.codigo, "dependencia_ausente")

    def test_plano_assinado_pelo_hash(self):
        _, plano, *_ = self.material()
        self.assertEqual(plano["hash"], C.hash_plano(plano))
        p2 = copy.deepcopy(plano)
        p2["etapas"][0]["descricao"] += "!"
        self.assertNotEqual(C.hash_plano(p2), plano["hash"])


class N5Critica(BaseN):
    def revisar(self, corpo):
        return Critica().tratar("revisar", corpo, ctx())

    def test_aprova_o_plano_bom_e_prende_o_veredito_ao_hash(self):
        _, plano, _, corpo = self.material()
        r = self.revisar(corpo)
        self.assertEqual(r["veredito"], "aprovado", r["motivos"])
        self.assertEqual(r["plano_hash"], plano["hash"])
        self.assertFalse(r["autorizacao_necessaria"])

    def test_rejeita_plano_alterado_depois_de_assinado(self):
        _, _, _, corpo = self.material()
        corpo["plano"]["parametros_da_estrategia"]["texto"] += " e mais isto"
        r = self.revisar(corpo)
        self.assertEqual(r["veredito"], "rejeitado")
        self.assertIn("R2_integridade", [m["regra"] for m in r["motivos"]])

    def test_rejeita_ferramenta_de_nivel_4_e_ferramenta_fora_do_catalogo(self):
        _, _, _, corpo = self.material()
        c4 = copy.deepcopy(corpo)
        for k in c4["catalogo_ferramentas"]:
            c4["catalogo_ferramentas"][k]["nivel"] = 4
        self.assertIn("R3b_nivel_proibido", [m["regra"] for m in self.revisar(c4)["motivos"]])
        self.assertEqual(self.revisar(c4)["veredito"], "rejeitado")
        cx = copy.deepcopy(corpo)
        cx["passos_derivados"] = [{**p, "ferramenta": "executar_shell"} for p in cx["passos_derivados"]]
        r = self.revisar(cx)
        self.assertEqual(r["veredito"], "rejeitado")
        self.assertIn("R3_catalogo", [m["regra"] for m in r["motivos"]])

    def test_rejeita_conteudo_sensivel(self):
        _, _, _, corpo = self.material()
        p = corpo["plano"]
        p["parametros_da_estrategia"]["texto"] = "meu cartão 4111 1111 1111 1111"
        p["hash"] = C.hash_plano(p)
        r = self.revisar(corpo)
        self.assertEqual(r["veredito"], "rejeitado")
        self.assertIn("R6_conteudo_sensivel", [m["regra"] for m in r["motivos"]])

    def test_devolve_repeticao_falta_de_campo_acao_sem_verificacao_e_dependencia_adiante(self):
        _, plano, _, corpo = self.material()
        rep = copy.deepcopy(corpo)
        rep["tentativas_anteriores"] = [{"estrategia": plano["estrategia"], "resultado": "falha"}]
        self.assertIn("R8_sem_repeticao", [m["regra"] for m in self.revisar(rep)["motivos"]])
        for mexe, regra in ((lambda p: p.update(alternativas=None), "R1_completude"),
                            (lambda p: [e.update(depende_de=[]) for e in p["etapas"] if e["tipo"] == "verificacao"], "R11_verificacao_independente"),
                            (lambda p: p["etapas"][0].update(depende_de=[p["etapas"][-1]["id"]]), "R12_dependencias")):
            c = copy.deepcopy(corpo)
            mexe(c["plano"])
            c["plano"]["hash"] = C.hash_plano(c["plano"])
            r = self.revisar(c)
            self.assertNotEqual(r["veredito"], "aprovado", regra)
            self.assertIn(regra, [m["regra"] for m in r["motivos"]])

    def test_acao_externa_ou_de_nivel_2_exige_o_dono_mas_a_critica_nao_autoriza(self):
        _, _, _, corpo = self.material()
        for k in corpo["catalogo_ferramentas"]:
            corpo["catalogo_ferramentas"][k] = {"nivel": 2, "perfil": EXP.PERFIS["enviar_sms"]}
        r = self.revisar(corpo)
        self.assertEqual(r["veredito"], "aprovado")
        self.assertTrue(r["autorizacao_necessaria"])
        self.assertTrue(any("nível 2" in e["motivo"] for e in r["exigencias_de_autorizacao"]))
        self.assertNotIn("autorizado", r)


class N7Verificador(BaseN):
    def test_a_execucao_nao_declara_o_proprio_sucesso(self):                                    # área 11
        d, plano, passos, _ = self.material()
        marcas = {passos[0]["ferramenta"]: L.marcar(passos[0]["ferramenta"], passos[0]["args"])}
        v = Verificador().tratar("verificar", {"plano": plano, "passos_derivados": passos, "marcas": marcas, "interpretacao": d["interpretacao"],
                                              "execucao": {"estado": "CONCLUIDA", "codigo": "ok"}}, ctx())            # «a tarefa disse que concluiu»… mas nada foi gravado
        self.assertEqual(v["veredito"], "falha_total")
        self.assertTrue(v["independente"])
        self.assertTrue(v["discordancia_com_a_execucao"])

    def test_sem_leitor_independente_fica_inconclusivo(self):
        d, plano, passos, _ = self.material()
        v = Verificador().tratar("verificar", {"plano": plano, "passos_derivados": [{"ferramenta": "enviar_sms", "args": {}}], "marcas": {}, "interpretacao": d["interpretacao"],
                                              "execucao": {"estado": "CONCLUIDA"}}, ctx())
        self.assertEqual(v["veredito"], "inconclusivo")
        self.assertFalse(v["independente"])

    def test_coerencia_pega_dia_acima_do_limite(self):
        d, *_ = self.material()
        ok = Verificador().tratar("coerencia_conteudo", {"conteudo": d["conteudo"], "interpretacao": d["interpretacao"]}, ctx())
        self.assertTrue(ok["coerente"], ok["problemas"])
        ruim = copy.deepcopy(d["conteudo"])
        ruim["texto"] = ruim["texto"].replace("(55+35=90min)", "(80+40=120min)", 1)
        self.assertNotEqual(ruim["texto"], d["conteudo"]["texto"])
        ruim["hash"] = C.hash_de(ruim["texto"])
        r = Verificador().tratar("coerencia_conteudo", {"conteudo": ruim, "interpretacao": d["interpretacao"]}, ctx())
        self.assertFalse(r["coerente"])
        self.assertIn("nenhum dia acima de 90 min", r["problemas"])
        adult = copy.deepcopy(d["conteudo"])
        adult["texto"] += "\nlinha a mais"
        self.assertFalse(Verificador().tratar("coerencia_conteudo", {"conteudo": adult, "interpretacao": d["interpretacao"]}, ctx())["coerente"], "hash não confere")


class N8Aprendizagem(BaseN):
    def registrar(self, d, plano, veredito="falha_total", tentativa=1, codigo="tamanho:texto"):
        ver = {"veredito": veredito, "observado_resumo": "nada do esperado apareceu", "fonte": "banco", "criterios": [{"id": c["id"], "ok": veredito == "sucesso", "esperado": 1, "observado": 0}
                                                                                                                 for c in plano["criterios_de_sucesso"]],
               "medidas": {"esperado_tamanho": 1400, "observado_tamanho": None, "prefixo_preservado": 0, "fracao": 0.0}}
        return Aprendizagem().tratar("registrar", {"objetivo": d["id"], "tentativa": tentativa, "plano": plano, "verificacao": ver, "interpretacao": d["interpretacao"],
                                                   "hipoteses": d["hipoteses"]["hipoteses"], "execucao": {"estado": "FALHOU", "codigo": codigo, "causa": "recusado"}}, ctx())

    def test_falha_vira_investigacao_e_hipotese_nao_regra(self):                                # área 12
        d, plano, *_ = self.material()
        r = self.registrar(d, plano)
        self.assertTrue(r["registrado"])
        self.assertEqual(r["resultado"], "falha")
        hip = [l for l in r["licoes"] if l["tipo"] == "hipotese"]
        self.assertTrue(hip and all(l["n"] == 1 and l["confianca"] < 1 and l["revisavel_se"] for l in hip))
        self.assertIn("NÃO vale como regra", " ".join(l["texto"] for l in hip))
        causais = [f for f in r["fatores"] if f["tipo"] == "hipotese"]
        self.assertTrue(causais)
        for f in causais:
            self.assertNotIn("causou", f["texto"].lower().replace("não prova", ""))
            self.assertLess(f["confianca"], 1.0)
        self.assertTrue(r["investigar"])
        self.assertTrue(all(not t["executado"] for t in r["propostas_de_teste"]))
        # sem prêmio nem castigo: nenhum número de recompensa no registro; o ajuste proposto é só da ordem das estratégias, e reversível
        texto = str(r).lower()
        for palavra in ("recompensa", "punicao", "punição", "castigo", "premio", "prêmio", "reward", "penalty"):
            self.assertNotIn(palavra, texto)
        aj = r["registro"]["proposta_de_ajuste"]
        self.assertEqual(aj["parametro"], "ordem_de_estrategias")
        self.assertTrue(aj["reversivel"])
        self.assertIn(aj["parametro"], X.PARAMETROS_AUTORIZADOS)

    def test_mesma_tentativa_nao_e_registrada_duas_vezes(self):
        d, plano, *_ = self.material()
        a, b = self.registrar(d, plano), self.registrar(d, plano)
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b["duplicado"])
        self.assertEqual(X.resumo_cognitivo()["total"], 1)

    def test_ajuste_fora_do_autorizado_e_recusado_e_revogar_desfaz_sem_apagar(self):
        d, plano, *_ = self.material()
        r = self.registrar(d, plano)
        reg = copy.deepcopy(r["registro"])
        for k in ("id", "em", "k"):
            reg.pop(k, None)
        reg["tentativa"] = 9
        for alvo in ("max_replanos", "critica", "nivel_max", "autorizacao"):
            reg["proposta_de_ajuste"] = {"parametro": alvo, "escopo": "x", "efeito": "y", "reversivel": True}
            self.assertIsNone(X.registrar_cognitiva(reg), alvo)
        antes = X.sinais_cognitivas(plano["estrategia"], plano["tipo_objetivo"], r["registro"]["condicoes"])
        self.assertEqual(antes["falhas"], 1)
        self.assertTrue(X.revogar_cognitiva(r["id"], "teste: o dono discordou"))
        depois = X.sinais_cognitivas(plano["estrategia"], plano["tipo_objetivo"], r["registro"]["condicoes"])
        self.assertEqual(depois["n"], 0)
        self.assertEqual([x["id"] for x in X.cognitivas(incluir_revogadas=True)], [r["id"]], "o registro continua no arquivo")
        self.assertEqual(X.cognitivas(), [])


class N9Monitor(unittest.TestCase):
    def avaliar(self, saude, esperados):
        return Monitor().tratar("avaliar", {"saude": saude, "esperados": esperados, "objetivos": [], "agora": 1.0}, ctx("sistema"))

    def neur(self, **k):
        return {"estado": "ocioso", "em_andamento": 0, "recebidas": 10, "concluidas": 10, "falhas": 0, "duplicadas": 0, "tempo_medio_ms": 3.0, "tempo_p95_ms": 5.0, **k}

    def test_modos_normal_degradado_e_bloqueado(self):
        esp = {"percepcao": {"trabalhador": "cognicao", "critico": True}, "contexto": {"trabalhador": "hub", "critico": False}}
        ok = {"cognicao": {"disponivel": True, "neuronios": {"percepcao": self.neur()}}, "hub": {"disponivel": True, "neuronios": {"contexto": self.neur()}}}
        self.assertEqual(self.avaliar(ok, esp)["modo"], "normal")
        sem_ctx = {"cognicao": ok["cognicao"], "hub": {"disponivel": False, "erro": "x"}}
        self.assertEqual(self.avaliar(sem_ctx, esp)["modo"], "degradado")
        sem_perc = {"cognicao": {"disponivel": False, "erro": "x"}, "hub": ok["hub"]}
        r = self.avaliar(sem_perc, esp)
        self.assertEqual(r["modo"], "bloqueado")
        self.assertEqual(r["criticos_fora"], ["percepcao"])

    def test_confianca_cai_com_a_taxa_de_falha_e_modulos_nao_sao_iguais(self):
        esp = {"percepcao": {"trabalhador": "w", "critico": True}, "critica": {"trabalhador": "w", "critico": True}}
        s = {"w": {"disponivel": True, "neuronios": {"percepcao": self.neur(concluidas=5, falhas=5), "critica": self.neur()}}}
        r = self.avaliar(s, esp)["modulos"]
        self.assertLess(r["percepcao"]["confianca"], r["percepcao"]["confianca_base"])
        self.assertEqual(r["percepcao"]["estado"], "com_erros")
        self.assertNotEqual(r["percepcao"]["confianca_base"], r["critica"]["confianca_base"])


class Exploracao(unittest.TestCase):
    def test_explorar_nao_e_liberdade(self):
        self.assertEqual(EXP.avaliar({"id": "anotar", "ferramentas": ["anotar"]})["modo"], "executar_no_escopo")
        fora = EXP.avaliar({"id": "anotar", "ferramentas": ["anotar"]}, no_escopo_do_pedido=False)
        self.assertTrue(fora["exige_autorizacao"])
        teste = EXP.avaliar({"id": "anotar", "ferramentas": ["anotar"]}, experimento=True, simulacao_possivel=True)
        self.assertEqual(teste["modo"], "simular")
        sms = EXP.avaliar({"id": "sms", "ferramentas": ["enviar_sms"]}, experimento=True, simulacao_possivel=True)
        self.assertEqual((sms["modo"], sms["exige_autorizacao"], sms["risco"]), ("pedir_autorizacao", True, "alto"))
        desconhecida = EXP.avaliar({"id": "x", "ferramentas": ["baixar_da_internet"]})
        self.assertEqual(desconhecida["modo"], "recusar")
        for a in (fora, teste, sms):
            self.assertTrue(a["criterios_de_parada"])
            self.assertFalse(a["calibrada"])


if __name__ == "__main__":
    unittest.main()
