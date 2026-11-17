"""Fase 7 — pré-córtex distribuído (friday/pre_cortex/), modo LOCAL: o fluxo inteiro de um objetivo, do pedido à aprendizagem.

Mapa (as 18 áreas da missão; as do modo distribuído, da tela e da segurança estão nos outros test_pre_cortex_*):
  1 recepção e interpretação · 2 recuperar experiência relevante · 3 gerar e comparar hipóteses · 4 plano com critérios · 5 plano inseguro rejeitado (aqui: execução barrada
  e crítica obrigatória; regras da crítica em test_pre_cortex_neuronios) · 7 tempo esgotado e trabalhador fora · 8 mensagens duplicadas · 9 cancelamento · 10 falha parcial ·
  11 verificação independente · 12 aprendizagem com a diferença entre previsão e resultado · 13 recuperação depois de reinício · 14 bloqueio de laço · 15 autorização humana antes
  de ação externa · 17 demonstração (o mesmo cenário que ela roda).
"""
import json, os, tempfile, threading, time, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import experiencias as X, ferramentas as F, tarefas as T
from test_experiencias import Base
from test_tarefas import mente, sms_enviados
import pre_cortex.config as CF
import pre_cortex.contrato as C
import pre_cortex.execucao as EX
import pre_cortex.explicar as EXPL
import pre_cortex.fases as FS
import pre_cortex.hub as HB
from pre_cortex.percepcao import Percepcao
from pre_cortex.contexto import ContextoMemoria

PEDIDO = "Monte um plano de estudos de Python para 4 semanas, com no máximo 90 minutos por dia, e guarde"
SMS = "Mande um SMS para mae dizendo que chego tarde"


def tipos(h, pcid):
    return [e["tipo"] for e in h.eventos(0, pcid, 5000)]


def planos(d):
    return [(p["plano"].get("estrategia"), (p.get("verificacao") or {}).get("veredito")) for p in d["planos"]]


class BasePC(Base):
    """Cofre, tarefas e experiências novos a cada teste (Base); um hub com pasta própria. Sem o vigia: os testes chamam `vigiar()` quando querem uma volta dele."""

    def hub(self, pasta=None, **cfg):
        c = CF.Config()
        c.aplicar({"espera_entre_tentativas_s": 0.0, **cfg}, "teste")
        self.assertEqual(c.avisos, [], c.avisos)
        h = HB.Hub(c, pasta or self.pasta, vigia=False)
        self.addCleanup(h.encerrar, 2.0)
        return h

    def setUp(self):
        super().setUp()
        self.pasta = tempfile.mkdtemp(prefix="pc-", dir=E.TMP)

    def rodar_ate(self, h, texto, ate=None, timeout=60, **kw):
        r = h.submeter(texto, **kw)
        self.assertTrue(r["ok"], r)
        est = h.esperar(r["id"], timeout, ate=ate)
        return r["id"], est, h.dossie(r["id"])


class Fluxo(BasePC):
    def test_pedido_vira_objetivo_estruturado(self):                                              # área 1
        h = self.hub()
        pcid, est, d = self.rodar_ate(h, PEDIDO, so_planejar=True)
        i = d["interpretacao"]
        self.assertEqual(i["tipo_objetivo"], "plano_de_estudo")
        self.assertEqual((i["parametros"]["semanas"], i["parametros"]["minutos_dia"], i["parametros"]["topico"].lower()), (4, 90, "python"))
        self.assertTrue(i["registrar"])
        self.assertFalse(i["efeitos"]["externo"])
        for campo in ("id", "descricao", "origem", "resultado_esperado", "prioridade", "restricoes", "recursos", "estado", "proxima_etapa", "dependencias", "historico_decisoes", "criterios_de_conclusao"):
            self.assertIn(campo, d, campo)
        self.assertEqual(d["origem"], "pedido_do_dono")
        self.assertTrue(d["criterios_de_conclusao"])
        self.assertIn("90", " ".join(d["restricoes"]))

    def test_cenario_da_demonstracao_falha_detectada_revisada_e_aprendida(self):                   # áreas 4, 11, 12, 17
        h = self.hub()
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual(est, "concluido")
        self.assertEqual(planos(d), [("anotar", "falha_total"), ("anotar_em_partes", "sucesso")])
        # a falha não foi fabricada: o corretor recusou o argumento grande demais e a verificação (outro módulo, lendo o banco) achou zero do esperado
        ex1 = d["planos"][0]["execucao"]
        self.assertIn("tamanho:texto", json.dumps(ex1, ensure_ascii=False))
        v1 = d["planos"][0]["verificacao"]
        self.assertTrue(v1["fonte"])
        self.assertEqual(v1["medidas"]["fracao"], 0.0)
        # a aprendizagem registrou previsão × resultado das duas tentativas, uma de cada
        self.assertEqual([a["resultado"] for a in d["aprendizados"]], ["falha", "sucesso"])
        regs = X.cognitivas()
        self.assertEqual(sorted(r["resultado"] for r in regs), ["falha", "sucesso"])
        # a ordem das fases é a da missão
        ts = tipos(h, pcid)
        ordem = ["interpretacao", "contexto", "hipoteses", "plano", "critica", "autorizacao_dispensada", "execucao_registrada", "tarefa_criada", "execucao_concluida", "verificacao", "aprendizagem", "replanejamento"]
        pos = [ts.index(x) for x in ordem]
        self.assertEqual(pos, sorted(pos), list(zip(ordem, pos)))
        self.assertEqual(ts[-1], "concluido")

    def test_experiencia_anterior_muda_a_escolha_seguinte(self):                                  # áreas 2 e 12
        h = self.hub()
        _, est1, d1 = self.rodar_ate(h, PEDIDO)
        _, est2, d2 = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est1, est2), ("concluido", "concluido"))
        self.assertEqual(planos(d2), [("anotar_em_partes", "sucesso")])
        ranking = {r["id"]: r for r in d2["hipoteses"]["escolha"]["ranking"]}
        self.assertEqual(ranking["anotar_em_partes"]["cognitivas"]["sucessos"], 1)
        self.assertEqual(ranking["anotar"]["cognitivas"]["falhas"], 1)
        self.assertGreater(ranking["anotar_em_partes"]["p"], ranking["anotar"]["p"])
        # as experiências usadas são citadas por id e dá para refazer a conta com o que existia no instante da escolha
        ids = set(ranking["anotar_em_partes"]["cognitivas"]["ids"]) | set(ranking["anotar"]["cognitivas"]["ids"])
        self.assertEqual(ids, {a["id"] for a in d1["aprendizados"]})
        ok, div = X.conferir_escolha_cognitiva(d2["hipoteses"]["escolha"])
        self.assertTrue(ok, div)

    def test_hipoteses_sao_comparadas_com_evidencia_previsao_e_revisao(self):                     # área 3
        h = self.hub()
        _, _, d = self.rodar_ate(h, PEDIDO, so_planejar=True)
        hs = d["hipoteses"]["hipoteses"]
        self.assertGreaterEqual(len(hs), 3)
        for x in hs:
            self.assertFalse(x["confianca"]["calibrada"])
            self.assertTrue(x["previsao"]["texto"] and x["condicoes_de_revisao"])
            self.assertIn("evidencias_a_favor", x)
            self.assertIn("evidencias_contra", x)
        esc = d["hipoteses"]["escolha"]
        self.assertIn("p=(sucessos+1)/(n+2)", esc["regra"])
        self.assertEqual(esc["escolhida"], esc["ranking"][0]["id"])

    def test_plano_tem_os_dez_campos_e_criterios_de_sucesso(self):                                 # área 4
        h = self.hub()
        _, est, d = self.rodar_ate(h, PEDIDO, so_planejar=True)
        self.assertEqual(est, "plano_pronto")
        p = d["planos"][-1]["plano"]
        for campo in ("objetivo", "estado_inicial", "etapas", "resultado_esperado", "criterios_de_sucesso", "riscos_e_incertezas", "alternativas", "condicoes_para_interromper",
                      "criterios_de_verificacao", "previsao"):
            self.assertTrue(p.get(campo), campo)
        for e in p["etapas"]:
            self.assertIn("depende_de", e)
            self.assertTrue(e["resultado_esperado"] and e["justificativa"])
        tipos_c = {c["tipo"] for c in p["criterios_de_sucesso"]}
        self.assertTrue({"semanas", "dias", "limite_diario", "completo"} <= tipos_c, tipos_c)
        self.assertEqual(p["hash"], C.hash_plano(p))

    def test_so_planejar_nao_executa_nada(self):
        h = self.hub()
        notas0 = F.marca_notas()
        pcid, est, d = self.rodar_ate(h, PEDIDO, so_planejar=True)
        self.assertEqual(est, "plano_pronto")
        self.assertEqual(T.listar(), [])
        self.assertEqual(d["execucoes"], {})
        self.assertEqual(F.marca_notas(), notas0)
        self.assertFalse(d["resultado_final"]["executado"])
        # pedir para executar depois reabre o fluxo pela autorização (e roda de verdade)
        self.assertTrue(h.executar(pcid)["ok"])
        self.assertEqual(h.esperar(pcid, 60), "concluido")


class Autorizacao(BasePC):
    def test_acao_externa_espera_o_dono_e_nada_sai_antes(self):                                   # área 15
        h = self.hub()
        pcid, est, d = self.rodar_ate(h, SMS, ate=("aguardando_autorizacao",))
        self.assertEqual(est, "aguardando_autorizacao")
        self.assertEqual(sms_enviados(), self.sms0)
        self.assertEqual(T.listar(), [])
        pedido = d["autorizacao"]
        self.assertTrue(any("nível 2" in e["motivo"] or "fora do aparelho" in e["motivo"] for e in pedido["exigencias"]))
        # autorização presa ao plano exato
        self.assertFalse(h.autorizar(pcid, plano_hash="0" * 32)["ok"])
        self.assertFalse(h.autorizar(pcid, versao=pedido["plano_versao"] + 1)["ok"])
        self.assertEqual(h.dossie(pcid)["estado"], "aguardando_autorizacao")
        self.assertEqual(T.listar(), [])
        r = h.autorizar(pcid, pedido["plano_versao"], pedido["plano_hash"])
        self.assertTrue(r["ok"], r)
        # autorizar o plano NÃO substitui a confirmação do corretor (nível 2)
        self.assertEqual(h.esperar(pcid, 30, ate=("aguardando_confirmacao_do_corretor",)), "aguardando_confirmacao_do_corretor")
        self.assertEqual(sms_enviados(), self.sms0)
        pend = B.pendente_publico()
        self.assertIsNotNone(pend)
        ok, _ = B.confirmar_botao(pend["id"])
        self.assertTrue(ok)
        self.assertEqual(sms_enviados(), self.sms0 + 1)
        h.vigiar()                                                                                  # o vigia percebe que o corretor respondeu e acorda o objetivo
        est = h.esperar(pcid, 30)
        # SMS não tem leitor independente: a verificação fica inconclusiva e vai ao dono; nunca vira «sucesso»
        self.assertEqual(est, "precisa_do_dono")
        d = h.dossie(pcid)
        self.assertEqual(d["planos"][-1]["verificacao"]["veredito"], "inconclusivo")
        self.assertEqual(sms_enviados(), self.sms0 + 1, "não repetiu")

    def test_negar_bloqueia_sem_executar(self):
        h = self.hub()
        pcid, est, _ = self.rodar_ate(h, SMS, ate=("aguardando_autorizacao",))
        self.assertTrue(h.negar(pcid)["ok"])
        d = h.dossie(pcid)
        self.assertEqual((d["estado"], d["bloqueio"]["tipo"]), ("bloqueado", "autorizacao_negada"))
        self.assertEqual(T.listar(), [])
        self.assertEqual(sms_enviados(), self.sms0)

    def test_sim_e_pode_nao_autorizam(self):
        import pre_cortex.fachada as PC
        h = self.hub()
        with mock.patch.dict(PC._E, {"hub": h, "api": None}):
            pcid, est, _ = self.rodar_ate(h, SMS, ate=("aguardando_autorizacao",))
            for frase in ("sim", "pode", "pode sim", "autorizo", "ok", "aprova o objetivo 1", "autorizo o plano"):
                PC.tratar(frase)
            self.assertEqual(h.dossie(pcid)["estado"], "aguardando_autorizacao")
            self.assertIn("Autorizado", PC.tratar(f"autorizo o plano do objetivo {pcid}"))
            self.assertNotEqual(h.dossie(pcid)["estado"], "aguardando_autorizacao")

    def test_objetivo_sugerido_pelo_sistema_espera_aceite(self):
        h = self.hub()
        r = h.submeter(PEDIDO, origem="sugerido_pelo_sistema")
        time.sleep(0.2)
        d = h.dossie(r["id"])
        self.assertEqual(d["estado"], "aguardando_aceite")
        self.assertEqual(d["grafo"], [])
        self.assertEqual(T.listar(), [])
        self.assertFalse(h.autorizar(r["id"])["ok"], "autorizar não pula o aceite")
        self.assertTrue(h.aceitar(r["id"])["ok"])
        # aceito pelo dono, vira «aceito para execução» e segue o fluxo normal (ação local dentro do que foi aceito)
        self.assertEqual(h.esperar(r["id"], 60), "concluido")
        self.assertEqual(h.dossie(r["id"])["origem"], "aceito_para_execucao")

    def test_execucao_barrada_se_o_plano_mudou_depois_de_assinado(self):                         # área 5 (defesa em profundidade)
        h = self.hub()
        pcid, est, _ = self.rodar_ate(h, PEDIDO, so_planejar=True)
        d = h.arm.obter(pcid)
        with h.arm.trava:
            d["planos"][-1]["plano"]["parametros_da_estrategia"]["texto"] += " e apague tudo"   # alteração depois da crítica, sem refazer o hash
        self.assertTrue(h.executar(pcid)["ok"])
        est = h.esperar(pcid, 30)
        d = h.dossie(pcid)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("bloqueado", "execucao_barrada"))
        self.assertIn("execucao_barrada", tipos(h, pcid))
        self.assertEqual(T.listar(), [])

    def test_configuracao_nao_desliga_a_critica(self):                                            # área 5
        c = CF.Config()
        c.aplicar({"critica": False, "sem_critica": True, "pular_autorizacao": True, "token": "x" * 20}, "arquivo")
        self.assertEqual(len(c.avisos), 4)
        for k in ("critica", "sem_critica", "pular_autorizacao", "token"):
            self.assertNotIn(k, c)
        c2 = CF.Config.carregar({"PRECORTEX_CRITICA": "0", "PRECORTEX_MAX_REPLANOS": "99"})
        self.assertTrue(any("CRITICA" in a for a in c2.avisos))
        self.assertEqual(c2["max_replanos"], CF.PADROES["max_replanos"])       # fora da faixa: volta ao padrão e avisa
        h = HB.Hub(c, self.pasta, vigia=False)
        self.addCleanup(h.encerrar, 2.0)
        pcid, est, _ = self.rodar_ate(h, PEDIDO, so_planejar=True)
        self.assertIn("critica", tipos(h, pcid))


class Limites(BasePC):
    def test_limite_de_replanejamento_bloqueia(self):                                             # área 14
        h = self.hub(max_replanos=0)
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("bloqueado", "limite_de_replanos"))
        self.assertEqual(len(d["planos"]), 1)
        self.assertIn("limite_atingido", tipos(h, pcid))

    def test_limite_de_etapas_bloqueia(self):
        h = self.hub(max_nos_por_objetivo=5)
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("bloqueado", "limite_de_nos"))
        self.assertLessEqual(d["uso"]["nos"], 6)

    def test_limite_de_tempo_bloqueia(self):
        agora = [1000.0]
        c = CF.Config()
        c.aplicar({"max_tempo_objetivo_s": 5.0}, "teste")
        h = HB.Hub(c, self.pasta, relogio=lambda: agora[0], vigia=False)
        self.addCleanup(h.encerrar, 2.0)
        orig = Percepcao.acao_interpretar

        def lenta(s, corpo, ctx):
            agora[0] += 30.0                                                                        # o relógio do hub anda 30 s enquanto a percepção trabalha
            return orig(s, corpo, ctx)
        with mock.patch.object(Percepcao, "acao_interpretar", lenta):
            pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("bloqueado", "limite_de_tempo"))

    def test_replanejamento_que_nao_muda_nada_e_laco(self):                                       # área 14
        h = self.hub()
        with mock.patch.object(FS, "assinatura", lambda plano: "sempre-igual"):
            pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("bloqueado", "laco_de_replanejamento"))
        self.assertIn("laco_detectado", tipos(h, pcid))
        self.assertEqual(len(d["planos"]), 1)

    def test_quando_tudo_falha_para_e_chama_o_dono(self):                                        # área 14: termina, não fica tentando para sempre
        h = self.hub(max_replanos=10)
        recusa = {"fn": lambda **kw: "Não consegui salvar."}
        with mock.patch.dict(B.FERRAMENTAS["anotar"], recusa), mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], recusa), mock.patch.dict(B.FERRAMENTAS["criar_arquivo"], recusa):
            pcid, est, d = self.rodar_ate(h, PEDIDO, timeout=120)
        self.assertEqual((est, d["bloqueio"]["tipo"]), ("precisa_do_dono", "sem_alternativas"))
        estrategias = [p["plano"]["estrategia"] for p in d["planos"]]
        self.assertEqual(len(estrategias), len(set(estrategias)), "nenhuma estratégia repetida")
        self.assertLessEqual(len(estrategias), 4)
        self.assertTrue(all(v in ("falha_total", "parcial") for _, v in planos(d)))


class FalhasEComunicacao(BasePC):
    def test_modulo_critico_fora_bloqueia_e_volta_sozinho(self):                                 # área 7
        h = self.hub(tentativas_msg=2)
        h.destinos["revisao"].derrubado = True
        pcid, est, d = self.rodar_ate(h, PEDIDO)
        self.assertEqual((est, d["bloqueio"]["tipo"], d["bloqueio"]["recuperavel"]), ("bloqueado", "modulo_indisponivel", True))
        self.assertIn(d["bloqueio"]["modulo"], ("critica", "verificador"))
        self.assertEqual(T.listar(), [], "nada executa sem a crítica")
        ts = tipos(h, pcid)
        self.assertEqual(ts.count("tentativa_falhou"), 2 * ts.count("modulo_indisponivel"))
        h.atualizar_saude()
        self.assertEqual(h.ultimo_monitor["modo"], "bloqueado")
        h.destinos["revisao"].derrubado = False
        h.vigiar()                                                                                  # o vigia vê o módulo de volta e retoma
        self.assertEqual(h.esperar(pcid, 60), "concluido")
        self.assertIn("retomada_automatica", tipos(h, pcid))

    def test_modulo_que_pode_faltar_segue_degradado_e_pede_o_dono(self):                          # área 7 (degradado)
        h = self.hub()

        def quebra(s, corpo, ctx):
            raise C.ErroNeuronio("erro_interno", "falha simulada no contexto")
        with mock.patch.object(ContextoMemoria, "acao_recuperar", quebra):
            pcid, est, d = self.rodar_ate(h, PEDIDO, ate=("aguardando_autorizacao",))
        self.assertEqual(est, "aguardando_autorizacao")
        self.assertTrue(d["contexto"]["degradado"])
        self.assertTrue(any("degradado" in e["motivo"] for e in d["autorizacao"]["exigencias"]))
        self.assertIn("modo_degradado", tipos(h, pcid))
        self.assertEqual(T.listar(), [])

    def test_sem_hipoteses_usa_o_catalogo_e_pede_o_dono(self):
        from pre_cortex.hipoteses import Hipoteses
        h = self.hub()

        def quebra(s, corpo, ctx):
            raise C.ErroNeuronio("erro_interno", "falha simulada nas hipóteses")
        with mock.patch.object(Hipoteses, "acao_gerar", quebra):
            pcid, est, d = self.rodar_ate(h, PEDIDO, ate=("aguardando_autorizacao",))
        self.assertEqual(est, "aguardando_autorizacao")
        self.assertTrue(d["hipoteses"]["degradado"])
        self.assertIn("EMERGÊNCIA", d["hipoteses"]["escolha"]["regra"])
        self.assertTrue(any("hipóteses não foram comparadas" in e["motivo"] for e in d["autorizacao"]["exigencias"]))

    def test_tempo_esgotado_reenvia_o_mesmo_id_e_a_duplicata_nao_reprocessa(self):              # áreas 7 e 8
        h = self.hub(timeout_msg_s=0.15, tentativas_msg=6)
        chamadas = []
        orig = Percepcao.acao_interpretar

        def lenta(s, corpo, ctx):
            chamadas.append(ctx.mensagem["id"])
            time.sleep(0.4)
            return orig(s, corpo, ctx)
        with mock.patch.object(Percepcao, "acao_interpretar", lenta):
            pcid, est, d = self.rodar_ate(h, PEDIDO, so_planejar=True)
        self.assertEqual(est, "plano_pronto")
        self.assertEqual(len(chamadas), 1, "o neurônio rodou uma vez só, apesar dos reenvios")
        evs = [e for e in h.eventos(0, pcid, 5000) if e.get("acao") == "interpretar"]
        enviados = [e for e in evs if e["tipo"] == "mensagem_enviada"]
        self.assertGreaterEqual(len(enviados), 2)
        self.assertEqual(len({e["id"] for e in enviados}), 1, "reenvio com o MESMO id")
        self.assertTrue(any(e["tipo"] == "tentativa_falhou" and "timeout" in e["motivo"] for e in evs))
        rec = [e for e in evs if e["tipo"] == "mensagem_recebida"]
        self.assertTrue(rec[-1]["duplicada"])
        self.assertGreaterEqual(h.trabalhadores["cognicao"].duplicatas, 1)

    def test_cancelar_durante_o_processamento(self):                                              # área 9
        h = self.hub()
        comecou, solta = threading.Event(), threading.Event()
        orig = Percepcao.acao_interpretar

        def presa(s, corpo, ctx):
            comecou.set()
            solta.wait(5)
            ctx.conferir_cancelamento()                                                             # cooperativo: o neurônio confere e para
            return orig(s, corpo, ctx)
        with mock.patch.object(Percepcao, "acao_interpretar", presa):
            r = h.submeter(PEDIDO)
            self.assertTrue(comecou.wait(5))
            self.assertTrue(h.cancelar(r["id"])["ok"])
            solta.set()
            est = h.esperar(r["id"], 30)
        self.assertEqual(est, "cancelado")
        self.assertEqual(T.listar(), [])
        self.assertIn(r["id"], h.trabalhadores["cognicao"]._cancelados)
        # depois de cancelado, mensagens novas desse objetivo são recusadas pelo trabalhador
        msg = C.criar("hub", "percepcao", "interpretar", {"texto": "x"}, correlacao=r["id"])
        self.assertEqual(h.trabalhadores["cognicao"].processar(msg)["erro"]["codigo"], "cancelada")

    def test_cancelar_enquanto_espera_o_dono(self):
        h = self.hub()
        pcid, est, _ = self.rodar_ate(h, SMS, ate=("aguardando_autorizacao",))
        self.assertTrue(h.cancelar(pcid)["ok"])
        self.assertEqual(h.dossie(pcid)["estado"], "cancelado")
        self.assertFalse(h.autorizar(pcid)["ok"])
        self.assertEqual(sms_enviados(), self.sms0)

    def test_falha_parcial_e_detectada_e_replanejada(self):                                       # área 10 (falha injetada: só a 2ª parte é recusada)
        h = self.hub()
        orig = B.FERRAMENTAS["anotar"]["fn"]

        def parte2_falha(**kw):
            if "[parte 2/" in str(kw.get("texto", "")):
                return "Não consegui salvar."
            return orig(**kw)
        with mock.patch.dict(B.FERRAMENTAS["anotar"], {"fn": parte2_falha}):
            pcid, est, d = self.rodar_ate(h, PEDIDO, timeout=90)
        vs = planos(d)
        self.assertEqual(vs[0], ("anotar", "falha_total"))
        self.assertEqual(vs[1], ("anotar_em_partes", "parcial"))
        v = d["planos"][1]["verificacao"]
        self.assertGreater(v["medidas"]["fracao"], 0.0)
        self.assertLess(v["medidas"]["fracao"], 1.0)
        self.assertEqual(d["aprendizados"][1]["resultado"], "parcial")
        self.assertGreaterEqual(len(vs), 3, "replanejou depois da falha parcial")
        # as outras estratégias também esbarram no limite do corretor: o objetivo termina parado, dentro dos limites, e nunca como «concluído»
        self.assertNotIn("sucesso", [v for _, v in vs])
        self.assertIn(est, ("bloqueado", "precisa_do_dono"))
        self.assertIn(d["bloqueio"]["tipo"], ("limite_de_replanos", "sem_alternativas"))


class Reinicio(BasePC):
    def test_queda_no_meio_do_fluxo_continua_da_fase_certa(self):                                # área 13
        h1 = self.hub()
        comecou = threading.Event()
        from pre_cortex.hipoteses import Hipoteses
        orig = Hipoteses.acao_gerar

        def lenta(s, corpo, ctx):
            comecou.set()
            time.sleep(0.6)
            return orig(s, corpo, ctx)
        with mock.patch.object(Hipoteses, "acao_gerar", lenta):
            r = h1.submeter(PEDIDO)
            self.assertTrue(comecou.wait(10))
            h1.encerrar(3.0)                                                                       # «queda» do hub: a linha sai sem terminar a fase
        d = h1.dossie(r["id"])
        self.assertEqual(d["estado"], "em_andamento")
        self.assertIn(d["fase"], ("hipoteses", "plano"))                                        # a fase em que a linha caiu (gravada antes de cair)
        self.assertEqual(T.listar(), [])
        h2 = self.hub()                                                                             # mesmo diretório: lê o que ficou gravado
        feitos = h2.recuperar_tudo()
        self.assertEqual(feitos, [(r["id"], "retomado", d["fase"])])
        self.assertEqual(h2.esperar(r["id"], 60), "concluido")
        d2 = h2.dossie(r["id"])
        self.assertEqual(len(d2["planos"]), 2)
        self.assertEqual(len(T.listar()), 2, "uma tarefa por plano, nenhuma repetida")
        self.assertIn("recuperado", tipos(h2, r["id"]))

    def test_tarefa_criada_mas_nao_entregue_ao_corretor_executa_uma_vez_depois(self):            # área 13 (registro antes de agir)
        h1 = self.hub()
        criada = threading.Event()
        orig_criar = EX.criar_tarefa

        def criar_e_avisar(*a, **k):
            r = orig_criar(*a, **k)
            criada.set()
            return r
        with mock.patch.object(EX, "executar_em_segundo_plano", lambda reg, evento: None), mock.patch.object(EX, "criar_tarefa", criar_e_avisar):
            r = h1.submeter(PEDIDO)
            self.assertTrue(criada.wait(20))
            time.sleep(0.2)
            h1.encerrar(3.0)
        d = h1.dossie(r["id"])
        self.assertEqual((d["estado"], d["fase"]), ("em_andamento", "execucao"))
        (reg,) = d["execucoes"].values()
        self.assertEqual(T.obter(reg["tarefa"])["estado"], T.PRONTA)
        h2 = self.hub()
        h2.recuperar_tudo()
        self.assertEqual(h2.esperar(r["id"], 60), "concluido")
        for t in T.listar():
            self.assertTrue(all(int(p.get("tentativas") or 0) <= 1 for p in T.obter(t["id"])["passos"]), "nenhum passo executado duas vezes")

    def test_espera_pelo_dono_sobrevive_ao_reinicio(self):                                       # área 13
        h1 = self.hub()
        pcid, est, d = self.rodar_ate(h1, SMS, ate=("aguardando_autorizacao",))
        h1.encerrar(2.0)
        h2 = self.hub()
        self.assertEqual(h2.recuperar_tudo(), [(pcid, "esperando_dono", "autorizacao")])
        self.assertEqual(h2.dossie(pcid)["estado"], "aguardando_autorizacao")
        self.assertEqual(sms_enviados(), self.sms0)
        p = h2.dossie(pcid)["autorizacao"]
        self.assertTrue(h2.autorizar(pcid, p["plano_versao"], p["plano_hash"])["ok"])
        self.assertEqual(h2.esperar(pcid, 30, ate=("aguardando_confirmacao_do_corretor",)), "aguardando_confirmacao_do_corretor")
        self.assertEqual(sms_enviados(), self.sms0)

    def test_limpar_cenario_arquiva_e_nao_toca_nas_experiencias(self):                           # área 16 (controle «limpar»)
        h = self.hub()
        pcid, est, _ = self.rodar_ate(h, PEDIDO)
        self.assertEqual(est, "concluido")
        exp = X.resumo_cognitivo()["total"]
        r = h.limpar_cenario()
        self.assertTrue(r["ok"] and r["arquivado_em"])
        self.assertTrue(os.path.isfile(os.path.join(r["arquivado_em"], "objetivos.json")))
        self.assertTrue(os.path.isfile(os.path.join(r["arquivado_em"], "eventos.jsonl")))
        self.assertEqual(h.arm.ids(), [])
        self.assertEqual(X.resumo_cognitivo()["total"], exp)
        self.assertEqual(h.submeter(PEDIDO, so_planejar=True)["id"], "pc0002", "os números não voltam")


class RaciocinioObservavel(BasePC):
    def test_as_doze_perguntas_vem_dos_dados(self):                                              # área 5 da missão (raciocínio observável)
        h = self.hub()
        _, _, d = self.rodar_ate(h, PEDIDO)
        q = {p["n"]: p for p in EXPL.perguntas(d)}
        self.assertEqual(len(q), 12)
        self.assertTrue(all(q[n]["disponivel"] for n in q))
        self.assertIn("anotar_em_partes", q[9]["resposta"])
        self.assertIn(d["aprendizados"][-1]["id"], q[11]["resposta"])
        self.assertIn("1 vez", q[12]["resposta"])
        for p in q.values():
            for it in p["itens"]:
                self.assertIn(it["tipo"], ("fato", "inferencia", "hipotese", "desconhecido", "incerteza"))
                self.assertTrue(it["fonte"])
        # outro pedido, outras respostas: nada é texto fixo
        _, _, d6 = self.rodar_ate(h, "Monte um plano de estudos de Python para 6 semanas, com no máximo 45 minutos por dia, e guarde")
        q6 = {p["n"]: p for p in EXPL.perguntas(d6)}
        self.assertIn("6 semana", q6[1]["resposta"])
        self.assertNotEqual(q6[9]["resposta"], q[9]["resposta"])

    def test_antes_de_rodar_a_resposta_diz_que_nao_sabe(self):
        h = self.hub()
        r = h.submeter(PEDIDO, origem="sugerido_pelo_sistema")
        q = {p["n"]: p for p in EXPL.perguntas(h.dossie(r["id"]))}
        self.assertFalse(q[4]["disponivel"])
        self.assertIn("ainda não", q[4]["resposta"])


if __name__ == "__main__":
    unittest.main()
