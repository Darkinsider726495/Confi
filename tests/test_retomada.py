"""Fase 6 — retomada depois de reinício ou queda (friday/retomada.py + tarefas.recuperar/confirmacao_perdida).

Mapa dos testes da missão:  D retomar depois de interrupção (queda simulada e queda REAL de processo) · I coordenação (retomadas disputando recurso) ·
F (confirmação perdida no reinício nunca vira execução; «sim» não a ressuscita) · G (registro sem conteúdo) · e a regra central: ação que pode já ter acontecido e
não dá para conferir NUNCA é repetida sozinha.
A queda é simulada levantando uma `BaseException` dentro da ferramenta (ninguém a captura, o disco fica exatamente como numa queda) e depois `T.reiniciar()` (só o disco sobra).
"""
import ast, json, os, subprocess, sys, threading, time, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import coordenador as CO, experiencias as X, ferramentas as F, retomada as R, tarefas as T
from test_coordenador import Base as BaseC
from test_tarefas import SEGREDO, sms_enviados
from test_neuronios import LOG

RAIZ = Path(os.path.dirname(os.path.abspath(__file__))).parent / "friday"
TESTES = Path(os.path.dirname(os.path.abspath(__file__)))


class Queda(BaseException):
    """O processo morreu aqui. BaseException para nenhum `except Exception` do código a engolir."""


def tochas():
    return E.ler_log(LOG).count("CMD termux-torch")


class Base(BaseC):
    def setUp(self):
        super().setUp()
        R._ULTIMA["v"] = None
        R._ERROS.update(n=0, ultimo="")
        self.addCleanup(R._ULTIMA.update, v=None)

    def cair(self, ferramenta, tid, depois_do_efeito=False):
        """Executa a tarefa com a ferramenta caindo no meio. Com `depois_do_efeito` a ação REAL acontece e só depois o processo morre."""
        real = B.FERRAMENTAS[ferramenta]["fn"]

        def fn(**kw):
            if depois_do_efeito:
                real(**kw)
            raise Queda()
        with mock.patch.dict(B.FERRAMENTAS[ferramenta], {"fn": fn}):
            with self.assertRaises(Queda):
                T.executar(tid)

    def reiniciar(self):
        """Processo novo: só o disco sobra (memória das tarefas, argumentos vivos, reservas e confirmação pendente somem)."""
        T.reiniciar()
        T.ATIVAS.clear()
        CO.reiniciar()
        B.PEND = None

    def tarefa_de(self, objetivo="pedido", passos=None, **kw):
        return T.criar(objetivo, passos=passos or [self.lembrete()], **kw)

    def estado(self, tid):
        return T.obter(tid)["estado"]


class Recuperar(Base):
    def test_D_efeito_ja_existia_confere_por_fora_e_nao_repete(self):
        tid = self.tarefa_de()
        self.cair("criar_lembrete", tid, depois_do_efeito=True)
        self.assertEqual((self.estado(tid), T.obter(tid)["passos"][0]["estado"]), (T.EXECUTANDO, "executando"), "é assim que uma queda deixa o disco")
        self.reiniciar()
        rel = R.retomar_pendentes()
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.CONCLUIDA, "verificado"))
        self.assertEqual((t["passos"][0]["verificacao"]["veredito"], t["passos"][0]["verificacao"]["forca"]), ("confirmado", "independente"))
        self.assertEqual(len(self.lembretes()), 1, "o lembrete criado antes da queda não foi duplicado")
        self.assertEqual([(i["tarefa"], i["acao"], i["estado"]) for i in rel["itens"]], [(tid, "conferiu", T.CONCLUIDA)])
        self.assertIn("já existia", rel["itens"][0]["motivo"])
        self.assertEqual([x["estado"] for x in self.fim], [T.CONCLUIDA], "quem escuta o fim das tarefas (experiências, objetivos) é avisado")

    def test_D_efeito_ausente_prova_que_nao_aconteceu_e_refaz_uma_vez(self):
        tid = self.tarefa_de()
        self.cair("criar_lembrete", tid, depois_do_efeito=False)
        self.assertEqual(self.lembretes(), [])
        self.reiniciar()
        rel = R.retomar_pendentes()
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"], t["passos"][0]["tentativas"]), (T.CONCLUIDA, "verificado", 2))
        self.assertEqual(len(self.lembretes()), 1)
        self.assertEqual([i["acao"] for i in rel["itens"]], ["conferiu", "retomou"])
        self.assertIn("não chegou a acontecer", rel["itens"][0]["motivo"])

    def test_D_o_que_nao_da_para_conferir_nao_e_repetido_e_pede_o_dono(self):
        tid = self.tarefa_de("acender", passos=[{"descricao": "ligar", "ferramenta": "lanterna", "args": {"ligar": True}}])
        antes = tochas()
        self.cair("lanterna", tid, depois_do_efeito=True)
        self.assertEqual(tochas(), antes + 1, "a lanterna acendeu e o processo caiu")
        self.reiniciar()
        rel = R.retomar_pendentes()
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"], t["passos"][0]["codigo"]), (T.PRECISA_INTERVENCAO, "intervencao", "interrompido"))
        self.assertEqual(tochas(), antes + 1, "NÃO repetiu uma ação que pode já ter acontecido")
        self.assertIn("não repeti", t["causa"])
        self.assertEqual([(i["acao"], i["estado"]) for i in rel["itens"]], [("pediu_dono", T.PRECISA_INTERVENCAO)])
        self.assertEqual(R.retomar_pendentes()["itens"], [], "uma segunda rodada não mexe em nada: continua esperando o dono")
        self.assertEqual(tochas(), antes + 1)

    def test_D_o_dono_diz_que_aconteceu_e_a_tarefa_conclui_com_a_palavra_dele(self):
        tid = self.tarefa_de("acender", passos=[{"descricao": "ligar", "ferramenta": "lanterna", "args": {"ligar": True}}])
        self.cair("lanterna", tid, depois_do_efeito=True)
        self.reiniciar()
        R.retomar_pendentes()
        ok, _ = T.confirmar_manual(tid)
        t = T.obter(tid)
        self.assertEqual((ok, t["estado"], t["passos"][0]["verificacao"]["forca"]), (True, T.CONCLUIDA, "dono"))

    def test_D_o_dono_pode_mandar_repetir_e_so_entao_repete(self):
        tid = self.tarefa_de("acender", passos=[{"descricao": "ligar", "ferramenta": "lanterna", "args": {"ligar": True}}])
        antes = tochas()
        self.cair("lanterna", tid, depois_do_efeito=True)
        self.reiniciar()
        R.retomar_pendentes()
        ok, _ = T.reabrir(tid)
        T.executar(tid)
        self.assertEqual((ok, tochas()), (True, antes + 2), "repetir foi decisão explícita do dono (retomar a tarefa N)")

    def test_D_leitura_pode_ser_repetida_porque_nao_muda_nada(self):
        tid = T.criar("ver a hora", passos=[{"descricao": "hora", "ferramenta": "hora_data", "args": {}}])
        self.cair("hora_data", tid)
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual(self.estado(tid), T.CONCLUIDA)
        self.assertEqual([i["acao"] for i in rel["itens"]], ["conferiu", "retomou"])

    def test_D_laco_de_queda_para_na_segunda(self):
        """Uma ferramenta que derruba o processo toda vez não pode ser repetida para sempre (cai, volta, repete, cai…)."""
        tid = self.tarefa_de()
        chamadas = []

        def derruba(**kw):
            chamadas.append(1)
            raise Queda()
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": derruba}):
            with self.assertRaises(Queda):
                T.executar(tid)                                                    # queda 1
            self.reiniciar()
            with self.assertRaises(Queda):
                R.retomar_pendentes()                                              # conferiu: não aconteceu; repetiu; queda 2
            self.reiniciar()
            rel = R.retomar_pendentes()                                            # já caiu MAX_QUEDAS vezes: não repete
        t = T.obter(tid)
        self.assertEqual(len(chamadas), T.MAX_QUEDAS, "a ação só foi tentada MAX_QUEDAS vezes")
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.PRECISA_INTERVENCAO, "intervencao"))
        self.assertIn("interrompido", t["causa"])
        self.assertEqual([i["acao"] for i in rel["itens"]], ["pediu_dono"])
        self.assertEqual(R.retomar_pendentes()["itens"], [], "e a rodada seguinte já não mexe nela")

    def test_D_nao_mexe_em_tarefa_que_este_processo_esta_executando(self):
        tid = self.tarefa_de()
        self.cair("criar_lembrete", tid)
        T.ATIVAS.clear()
        T._ativar(tid)
        self.addCleanup(T._desativar, tid)
        self.assertIsNone(T.recuperar(tid))
        self.assertEqual(R.retomar_pendentes()["itens"], [])
        self.assertEqual((self.estado(tid), T.obter(tid)["passos"][0]["estado"]), (T.EXECUTANDO, "executando"))

    def test_recuperar_so_age_em_tarefa_executando_ou_verificando(self):
        pronta, concluida, falhou = self.tarefa_de(), self.tarefa_de(), self.tarefa_de()
        T.executar(concluida)
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Erro: quebrou"}):
            T.executar(falhou)
        antes = {t: T.obter(t) for t in (pronta, concluida, falhou)}
        self.assertEqual([antes[t]["estado"] for t in (pronta, concluida, falhou)], [T.PRONTA, T.CONCLUIDA, T.FALHOU])
        for tid in antes:
            self.assertIsNone(T.recuperar(tid))
            self.assertEqual(T.obter(tid), antes[tid], "nada mudou")
        self.assertIsNone(T.recuperar("t9999"))
        self.assertIsNone(T.recuperar(None))

    def test_passo_executando_com_argumentos_perdidos_tambem_pede_o_dono(self):
        """Ação sensível: os argumentos nem foram para o disco. Não dá para conferir nem repetir."""
        tid = T.criar("anotar", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": "minha senha é hunter2xyz"}}])
        self.cair("anotar", tid)
        self.reiniciar()
        R.retomar_pendentes()
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"]), (T.PRECISA_INTERVENCAO, "intervencao"))
        self.assertEqual(self.notas("minha senha é hunter2xyz"), 0)

    def test_so_o_passo_interrompido_e_recuperado_os_outros_ficam_como_estavam(self):
        tid = T.criar("dois", passos=[self.lembrete("primeiro-zq", 5), self.lembrete("segundo-zq", 6, depende_de=["p1"])])
        T.executar_proximo(tid)                                                  # p1 verificado
        self.cair("criar_lembrete", tid, depois_do_efeito=True)                    # p2 executa e cai
        self.reiniciar()
        R.retomar_pendentes()
        t = T.obter(tid)
        self.assertEqual((t["estado"], [p["estado"] for p in t["passos"]]), (T.CONCLUIDA, ["verificado", "verificado"]))
        self.assertEqual((len(self.lembretes("primeiro-zq")), len(self.lembretes("segundo-zq"))), (1, 1))


class ConfirmacaoPerdida(Base):
    PLANO = [{"descricao": "avisar a mãe", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEGREDO}}]

    def pedir(self):
        tid = T.criar("avisar", passos=self.PLANO)
        T.executar(tid)
        self.assertEqual((self.estado(tid), self.sms()), (T.BLOQUEADA, 0))
        return tid

    def test_F_confirmacao_perdida_no_reinicio_pede_o_dono_e_nada_roda(self):
        tid = self.pedir()
        self.reiniciar()
        rel = R.retomar_pendentes()
        t = T.obter(tid)
        self.assertEqual((t["estado"], t["passos"][0]["estado"], self.sms()), (T.PRECISA_INTERVENCAO, "intervencao", 0))
        self.assertEqual([(i["acao"], i["estado"]) for i in rel["itens"]], [("pediu_dono", T.PRECISA_INTERVENCAO)])
        self.assertIn("confirmação", t["causa"])
        self.assertIn("nada foi executado", t["causa"])

    def test_F_sim_ou_pode_depois_do_reinicio_nao_executam_o_que_se_perdeu(self):
        import main as MAIN
        tid = self.pedir()
        self.reiniciar()
        R.retomar_pendentes()
        with mock.patch("cerebro.responder", return_value="Certo, chefe."):
            for frase in ("sim", "pode", "pode fazer", "confirmo", "claro"):
                MAIN.processar(frase)
        self.assertEqual((self.sms(), self.estado(tid), B.pendente_publico()), (0, T.PRECISA_INTERVENCAO, None))

    def test_F_sem_os_argumentos_o_retomar_nao_inventa_a_acao(self):
        """Nível 2: o texto e o contato nunca foram para o disco. Depois do reinício «retomar» não tem do que refazer a ação: pede ao dono."""
        tid = self.pedir()
        self.reiniciar()
        R.retomar_pendentes()
        ok, _ = T.reabrir(tid)
        T.executar(tid)
        t = T.obter(tid)
        self.assertEqual((ok, t["estado"], self.sms(), B.pendente_publico()), (True, T.PRECISA_INTERVENCAO, 0, None))
        self.assertIn("argumentos", t["causa"])

    def test_F_com_os_dados_ainda_vivos_retomar_pede_uma_confirmacao_nova(self):
        tid = self.pedir()
        velha = B.pendente_publico()["id"]
        B.PEND = None                                                             # a confirmação se perdeu, mas este processo ainda tem os dados
        self.assertTrue(T.confirmacao_perdida(tid))
        ok, _ = T.reabrir(tid)
        T.executar(tid)
        nova = B.pendente_publico()
        self.assertEqual((ok, self.estado(tid), self.sms()), (True, T.BLOQUEADA, 0))
        self.assertIsNotNone(nova)
        self.assertNotEqual(nova["id"], velha, "a confirmação é NOVA, presa à ação; a antiga nunca volta")
        B.cancelar()

    def test_confirmacao_ainda_viva_nao_e_tocada(self):
        tid = self.pedir()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(tid), rel["itens"]), (T.BLOQUEADA, []))
        self.assertIsNotNone(B.pendente_publico())
        B.cancelar()

    def test_confirmacao_que_sumiu_sem_aviso_e_tratada_uma_vez_so(self):
        tid = self.pedir()
        B.PEND = None
        self.assertTrue(T.confirmacao_perdida(tid))
        self.assertFalse(T.confirmacao_perdida(tid), "já tratada")
        self.assertFalse(T.confirmacao_perdida("t9999"))
        self.assertFalse(T.confirmacao_perdida(None))


class Retomar(Base):
    def test_pronta_recente_do_dono_e_retomada_pelo_corretor_e_conferida(self):
        tid = self.tarefa_de()
        self.assertEqual(self.estado(tid), T.PRONTA)
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(tid), len(self.lembretes())), (T.CONCLUIDA, 1))
        self.assertEqual([(i["acao"], i["estado"]) for i in rel["itens"]], [("retomou", T.CONCLUIDA)])
        self.assertEqual(R.retomar_pendentes()["itens"], [], "idempotente: o que já terminou não é tocado de novo")
        self.assertEqual(len(self.lembretes()), 1)

    def test_o_corretor_continua_decidindo_e_a_auditoria_registra(self):
        self.tarefa_de()
        self.reiniciar()
        n0 = len(B.ultimos(50))
        with mock.patch.object(B, "executar_estruturado", wraps=B.executar_estruturado) as ex:
            R.retomar_pendentes()
        self.assertEqual([c.args[0] for c in ex.call_args_list], ["criar_lembrete"], "o único caminho até a ferramenta é o corretor")
        novas = B.ultimos(50)[n0 - len(B.ultimos(50)):] if len(B.ultimos(50)) > n0 else B.ultimos(50)
        self.assertTrue(any("criar_lembrete" in json.dumps(x) for x in novas), "a ação ficou na trilha de auditoria")
        self.assertTrue(B.verificar_auditoria()[0])

    def test_pronta_entre_dois_passos_de_uma_execucao_em_curso_nao_e_tocada(self):
        """Entre um passo e outro a tarefa fica PRONTA; se este processo a está executando, a retomada não pode entrar no meio."""
        tid = self.tarefa_de("dois", passos=[self.lembrete("um-zq", 5), self.lembrete("dois-zq", 6, depende_de=["p1"])])
        T.executar_proximo(tid)
        self.assertEqual(self.estado(tid), T.PRONTA)
        T._ativar(tid)
        self.addCleanup(T._desativar, tid)
        rel = R.retomar_pendentes()
        self.assertEqual((rel["itens"], len(self.lembretes("dois-zq"))), ([], 0))

    def test_origem_ia_nao_e_retomada_sozinha(self):
        tid = self.tarefa_de(origem="ia")
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(tid), self.lembretes()), (T.PRONTA, []))
        self.assertEqual([i["acao"] for i in rel["itens"]], ["pediu_dono"])
        self.assertIn("conversa", rel["itens"][0]["motivo"])

    def test_origens_retomaveis_nao_incluem_a_conversa(self):
        self.assertNotIn("ia", R.ORIGENS_RETOMAVEIS)
        self.assertTrue(set(R.ORIGENS_RETOMAVEIS) <= set(T.ORIGENS))

    def test_meta_e_objetivo_aprovado_sao_retomaveis(self):
        for origem in ("meta", "propria"):
            with self.subTest(origem=origem):
                tid = self.tarefa_de(origem=origem, **({"meta": "m1"} if origem == "meta" else {}))
                self.reiniciar()
                R.retomar_pendentes()
                self.assertEqual(self.estado(tid), T.CONCLUIDA)

    def test_parada_ha_muito_tempo_nao_recomeca_sozinha(self):
        tid = self.tarefa_de()
        t = T.obter(tid)
        rel = R.retomar_pendentes(agora=t["atualizada"] + R.IDADE_MAX_S + 60)
        self.assertEqual((self.estado(tid), self.lembretes()), (T.PRONTA, []))
        self.assertIn("parada há", rel["itens"][0]["motivo"])
        rel = R.retomar_pendentes(agora=t["atualizada"] + R.IDADE_MAX_S + 60, idade_max_s=10 * R.IDADE_MAX_S)
        self.assertEqual(self.estado(tid), T.CONCLUIDA)

    def test_F_nivel_2_nao_e_retomado_pede_o_dono(self):
        tid = T.criar("avisar", passos=[{"descricao": "sms", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": "oi"}}])
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(tid), self.sms(), B.pendente_publico()), (T.PRONTA, 0, None), "nem executou nem abriu confirmação sozinha")
        self.assertEqual([i["acao"] for i in rel["itens"]], ["pediu_dono"])
        self.assertIn("nível 2", rel["itens"][0]["motivo"])

    def test_nivel_ilegivel_no_disco_e_tratado_como_sensivel(self):
        tid = self.tarefa_de()
        T.obter(tid)
        with T._trava:
            T._vivo(tid)["passos"][0]["nivel"] = None
            T.ARQ.salvar()
        self.reiniciar()
        R.retomar_pendentes()
        self.assertEqual((self.estado(tid), self.lembretes()), (T.PRONTA, []))

    def test_argumentos_que_nao_ficaram_guardados_pedem_o_dono(self):
        tid = T.criar("anotar", passos=[{"descricao": "anotar", "ferramenta": "anotar", "args": {"texto": "minha senha é hunter2xyz"}}])
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(tid), self.notas("minha senha é hunter2xyz")), (T.PRONTA, 0))
        self.assertIn("argumentos", rel["itens"][0]["motivo"])

    def test_dependencia_roda_na_ordem(self):
        a = self.tarefa_de("a", passos=[self.lembrete("primeira-zq")])
        b = self.tarefa_de("b", passos=[self.lembrete("segunda-zq")], depende_de=[a])
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(a), self.estado(b)), (T.CONCLUIDA, T.CONCLUIDA))
        retomados = [i["tarefa"] for i in rel["itens"] if i["acao"] == "retomou"]
        self.assertEqual(retomados, [a, b])

    def test_dependencia_que_nao_termina_deixa_esperando_com_o_motivo(self):
        a = self.tarefa_de("a")
        T.cancelar(a)
        b = self.tarefa_de("b", depende_de=[a])
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(b), self.lembretes()), (T.PRONTA, []))
        self.assertEqual([(i["tarefa"], i["acao"]) for i in rel["itens"]], [(b, "esperou")])
        self.assertIn(a, rel["itens"][0]["motivo"])

    def test_limite_por_rodada(self):
        tids = [self.tarefa_de(f"n{i}", passos=[self.lembrete(f"lim-{i}-zq")]) for i in range(3)]
        with mock.patch.object(R, "MAX_TAREFAS", 2):
            rel = R.retomar_pendentes()
        self.assertEqual(sorted(self.estado(t) for t in tids), sorted([T.CONCLUIDA, T.CONCLUIDA, T.PRONTA]))
        self.assertEqual([i["acao"] for i in rel["itens"]].count("esperou"), 1)
        R.retomar_pendentes()
        self.assertEqual({self.estado(t) for t in tids}, {T.CONCLUIDA})

    def test_falha_do_corretor_aparece_no_relatorio_e_na_contagem(self):
        tid = self.tarefa_de()
        with mock.patch.object(T, "executar", side_effect=RuntimeError("quebrou")):
            rel = R.retomar_pendentes()
        self.assertEqual(([i["acao"] for i in rel["itens"]], rel["resumo"]["erros"], R._ERROS["n"]), (["pediu_dono"], 1, 1))
        self.assertIn("RuntimeError", rel["itens"][0]["motivo"])
        self.assertEqual(R.resumo()["erros"], 1)

    def test_so_uma_rodada_de_cada_vez(self):
        self.assertTrue(R._trava.acquire(blocking=False))
        try:
            rel = R.retomar_pendentes()
            self.assertEqual((rel["ocupada"], rel["itens"]), (True, []))
            self.assertIn("conferindo", R.tratar("retoma o que ficou pendente"))
        finally:
            R._trava.release()

    def test_nada_a_fazer_diz_que_nao_achou_nada(self):
        rel = R.retomar_pendentes()
        self.assertEqual(rel["itens"], [])
        self.assertIn("Não achei nada interrompido", R.falar(rel))
        self.assertIn("Não achei nada interrompido", R.falar(None))
        self.assertFalse(self.base(".cerebro", "retomada.jsonl").exists(), "rodada vazia não escreve nada")


class Coordenacao(Base):
    def test_I_duas_retomadas_no_mesmo_recurso_uma_depois_da_outra(self):
        f = self.ferramenta_lenta(demora=0.05)
        a, b = self.tarefa(f, "rele1"), self.tarefa(f, "rele1")
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(a), self.estado(b), self.pico), (T.EXECUTADA_SEM_VERIFICACAO, T.EXECUTADA_SEM_VERIFICACAO, 1))
        decisoes = [(d["alvo"], d["decisao"]) for d in CO.decisoes_recentes(10)]
        self.assertIn((b, "esperar"), decisoes, "a segunda esperou pelo mesmo recurso")
        self.assertEqual(decisoes[-1], (b, "executar_agora"), "e depois foi a vez dela")
        self.assertEqual([i["acao"] for i in rel["itens"]], ["retomou", "retomou"])

    def test_I_recurso_em_uso_por_outra_execucao_faz_esperar_sem_executar(self):
        f = self.ferramenta_lenta(demora=0.5)
        a, b = self.tarefa(f, "rele1"), self.tarefa(f, "rele1")
        em_andamento = threading.Thread(target=T.executar, args=(a,))
        em_andamento.start()
        time.sleep(0.15)
        rel = R.retomar_pendentes()
        self.assertEqual((self.estado(b), len(self.chamadas)), (T.PRONTA, 1), "b não executou: o recurso está com a tarefa que ainda roda")
        self.assertEqual([(i["tarefa"], i["acao"]) for i in rel["itens"]], [(b, "esperou")])
        self.assertIn("em uso por " + a, rel["itens"][0]["motivo"])
        em_andamento.join()
        R.retomar_pendentes()
        self.assertEqual((self.estado(b), len(self.chamadas), self.pico), (T.EXECUTADA_SEM_VERIFICACAO, 2, 1))

    def test_I_a_tarefa_que_roda_agora_nao_e_tocada_pela_retomada(self):
        f = self.ferramenta_lenta(demora=0.4)
        a = self.tarefa(f, "rele1")
        em_andamento = threading.Thread(target=T.executar, args=(a,))
        em_andamento.start()
        time.sleep(0.1)
        rel = R.retomar_pendentes()
        em_andamento.join()
        self.assertEqual((rel["itens"], len(self.chamadas)), ([], 1), "a mesma ação não foi disparada duas vezes")

    def test_segunda_camada_o_coordenador_tambem_barra_nivel_2_se_a_primeira_falhar(self):
        """Defesa em duas camadas: mesmo que a elegibilidade deixasse passar, o coordenador manda pedir o dono e nada executa."""
        tid = T.criar("avisar", passos=[{"descricao": "sms", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": "oi"}}])
        with mock.patch.object(R, "_elegivel", return_value=(True, "")):
            rel = R.retomar_pendentes()
        self.assertEqual((self.estado(tid), self.sms(), B.pendente_publico()), (T.PRONTA, 0, None))
        self.assertEqual([i["acao"] for i in rel["itens"]], ["pediu_dono"])
        self.assertEqual([d["decisao"] for d in CO.decisoes_recentes(5)], ["pedir_dono"])


class Privacidade(Base):
    def test_G_registro_e_fala_sem_conteudo(self):
        a = T.criar(f"avisar sobre {SEGREDO}", passos=[self.lembrete(SEGREDO)])
        b = T.criar("outra", passos=[{"descricao": f"nota {SEGREDO}", "ferramenta": "anotar", "args": {"texto": SEGREDO}}], origem="ia")
        self.cair("criar_lembrete", T.criar(f"caiu {SEGREDO}", passos=[self.lembrete(SEGREDO)]), depois_do_efeito=True)
        self.reiniciar()
        rel = R.retomar_pendentes()
        self.assertTrue(rel["itens"])
        for texto in (json.dumps(rel, ensure_ascii=False), R.falar(rel), json.dumps(R.resumo()), R.tratar("o que você retomou?") or "",
                      self.base(".cerebro", "retomada.jsonl").read_text(encoding="utf-8"), self.base(".cerebro", "coordenacao.jsonl").read_text(encoding="utf-8")):
            self.assertNotIn(SEGREDO, texto)
        self.assertNotIn("zq-conteudo", self.base(".cerebro", "retomada.jsonl").read_text(encoding="utf-8"))

    def test_registro_em_linhas_de_json_validas_com_ids_e_acoes(self):
        self.tarefa_de()
        R.retomar_pendentes()
        linhas = [json.loads(l) for l in self.base(".cerebro", "retomada.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(linhas), 1)
        self.assertEqual(set(linhas[0]), {"em", "itens", "resumo"})
        self.assertTrue(all(set(i) == {"tarefa", "acao", "motivo", "estado"} and i["acao"] in R.ACOES for i in linhas[0]["itens"]))

    def test_registro_estragado_ou_ausente_nao_derruba(self):
        self.assertIsNone(R.ultima())
        self.base(".cerebro").mkdir(parents=True, exist_ok=True)
        for lixo in ("lixo\n", "[1]\n", '{"itens": 7}\n', "\n"):
            self.base(".cerebro", "retomada.jsonl").write_text(lixo, encoding="utf-8")
            self.assertIsNone(R.ultima())
        self.assertEqual(R.resumo()["ultima"], None)


class PorVoz(Base):
    def test_retomar_por_voz_confere_e_conta_sem_conteudo(self):
        tid = self.tarefa_de()
        self.cair("criar_lembrete", tid, depois_do_efeito=True)
        self.reiniciar()
        fala = R.tratar("Retoma o que ficou pendente.")
        self.assertIn("conferi 1", fala)
        self.assertEqual(self.estado(tid), T.CONCLUIDA)
        self.assertEqual(len(self.lembretes()), 1)

    def test_variacoes_da_frase(self):
        for frase in ("retome o que ficou pendente", "retomar as tarefas interrompidas", "continua de onde parou", "continue de onde você parou", "retoma o que ficou pela metade"):
            with self.subTest(frase=frase):
                self.assertIsNotNone(R.tratar(frase))

    def test_perguntar_so_le(self):
        tid = self.tarefa_de()
        self.cair("criar_lembrete", tid, depois_do_efeito=True)
        self.reiniciar()
        fala = R.tratar("o que ficou interrompido?")
        self.assertIn("1 tarefa(s) paradas no meio", fala)
        self.assertEqual((self.estado(tid), len(self.lembretes())), (T.EXECUTANDO, 1), "perguntar não conferiu nem mudou nada")
        self.assertEqual(R.interrompidas(), [tid])

    def test_nao_e_com_ela(self):
        for frase in ("que horas são", "retoma a tarefa 3", "minhas tarefas", "o que ficou pendente", "", None, "x" * 500):
            self.assertIsNone(R.tratar(frase), frase)

    def test_painel_so_tem_contagens(self):
        self.tarefa_de()
        R.retomar_pendentes()
        r = R.resumo()
        self.assertEqual(set(r), {"interrompidas", "ultima", "erros"})
        self.assertEqual((r["interrompidas"], r["ultima"]["retomou"]), (0, 1))
        self.assertTrue(all(isinstance(v, int) for v in r["ultima"].values()))


class AoIniciar(Base):
    def test_fala_so_quando_ha_algo_a_contar(self):
        falas = []
        R.ao_iniciar(falas.append, pausa_s=0)
        self.assertEqual(falas, [], "nada interrompido: fica quieta")
        self.tarefa_de()
        R.ao_iniciar(falas.append, pausa_s=0)
        self.assertEqual(len(falas), 1)
        self.assertTrue(falas[0].startswith("Depois do reinício"))

    def test_nunca_levanta_excecao(self):
        with mock.patch.object(R, "retomar_pendentes", side_effect=RuntimeError("x")):
            self.assertIsNone(R.ao_iniciar(lambda m: None, pausa_s=0))
        self.assertEqual(R._ERROS["n"], 1)


class QuedaReal(Base):
    """O processo MORRE de verdade (os._exit) no pior momento: depois do efeito e antes de qualquer registro."""
    FILHO = r'''
import os, sys
sys.path.insert(0, os.environ["TESTE_TESTS"])
import _ambiente
for k in ("FRIDAY_DB", "FRIDAY_AUDITORIA", "OBSIDIAN_VAULT"):
    os.environ[k] = os.environ["TESTE_" + k]
import broker as B, catalogo, tarefas as T
real = B.FERRAMENTAS["criar_lembrete"]["fn"]
def morre(**kw):
    real(**kw)
    os._exit(7)
B.FERRAMENTAS["criar_lembrete"]["fn"] = morre
tid = T.criar("lembrar de beber agua", passos=[{"descricao": "criar", "ferramenta": "criar_lembrete", "args": {"minutos": 20, "texto": os.environ["TESTE_TEXTO"]}}])
T.executar(tid)
'''

    def test_D_queda_real_de_processo_e_retomada_sem_duplicar(self):
        env = dict(os.environ, TESTE_TESTS=str(TESTES), TESTE_FRIDAY_DB=os.environ["FRIDAY_DB"], TESTE_FRIDAY_AUDITORIA=os.environ["FRIDAY_AUDITORIA"],
                   TESTE_OBSIDIAN_VAULT=os.environ["OBSIDIAN_VAULT"], TESTE_TEXTO=SEGREDO, PYTHONPATH=str(RAIZ))
        r = subprocess.run([sys.executable, "-c", self.FILHO], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 7, r.stderr[-800:])
        self.assertEqual(len(self.lembretes()), 1, "o efeito aconteceu antes da queda")
        self.reiniciar()
        self.assertEqual([t["estado"] for t in T.listar()], [T.EXECUTANDO], "o disco que o processo morto deixou")
        rel = R.retomar_pendentes()
        self.assertEqual(([t["estado"] for t in T.listar()], len(self.lembretes())), ([T.CONCLUIDA], 1))
        self.assertEqual(rel["itens"][0]["acao"], "conferiu")


class SoRetoma(unittest.TestCase):
    def test_nao_importa_o_corretor_nem_cria_threads_nem_executa_ferramenta(self):
        arv = ast.parse((RAIZ / "retomada.py").read_text(encoding="utf-8"))
        importados = {a.name for n in ast.walk(arv) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(arv) if isinstance(n, ast.ImportFrom)}
        self.assertNotIn("broker", importados)
        self.assertNotIn("subprocess", importados)
        chamadas = {n.func.attr for n in ast.walk(arv) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse({"Thread", "executar_estruturado", "executar_proximo", "confirmar"} & chamadas)
        self.assertNotIn("threading.Thread", (RAIZ / "retomada.py").read_text(encoding="utf-8"))

    def test_a_ia_nao_tem_ferramenta_de_retomada(self):
        for nome in B.FERRAMENTAS:
            self.assertNotRegex(nome, r"retom|recuper", nome)

    def test_tarefas_nao_importa_a_retomada(self):
        arv = ast.parse((RAIZ / "tarefas.py").read_text(encoding="utf-8"))
        importados = {a.name for n in ast.walk(arv) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(arv) if isinstance(n, ast.ImportFrom)}
        self.assertNotIn("retomada", importados)

    def test_limites_sao_constantes_do_codigo(self):
        self.assertEqual((R.IDADE_MAX_S, T.MAX_QUEDAS), (1800.0, 2))
        self.assertLessEqual(R.MAX_RODADAS, 10)


if __name__ == "__main__":
    unittest.main()
