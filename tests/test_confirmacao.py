"""Fase 1.3 — confirmação de ação sensível (nível 2) presa à ação proposta.

Antes: "sim", "pode", "pode fazer" e "isso" — respostas de conversa comuns — executavam a ação pendente (SMS, ligação, relé, esquecer memória)
se saíssem em até 45 s, mesmo respondendo a outra pergunta; e o botão «Confirmo» (painel e notificação permanente) confirmava QUALQUER coisa pendente.

Agora, para nível 2:
  intenção            "manda um SMS pra mãe"        -> a IA propõe, o corretor cria UMA pendência (id próprio) e diz o que vai executar
  resposta de contexto "sim", "pode", "isso", "ok"   -> nunca executam (logo após a pendência pedem a confirmação clara; depois seguem como conversa)
  consentimento        "confirmo" logo em seguida     -> executa
                       "confirmo <ação>" a qualquer hora enquanto a pendência vale -> executa
  botão                precisa do id da pendência que está na tela
Nível 3 continua só com PIN. Cada confirmação vale uma vez, para a pendência que existia quando foi dita.
"""
import os, time, json, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import main as MAIN

BIN, LOG = E.termux_falso()
S = {"type": "string"}
FEITO = []


def _acao(texto="x"):
    FEITO.append(texto)
    return f"feito {texto}"


B.registrar("mandar_aviso_teste", "ação de teste, nível 2", {"texto": S}, ["texto"], _acao, 2, rotulo="mandar aviso")
B.registrar("apagar_cache_teste", "outra ação de teste, nível 2", {}, [], lambda: _acao("cache"), 2)


class Base(unittest.TestCase):
    def setUp(self):
        B.PEND = None
        FEITO.clear()
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)
        p = mock.patch.dict(os.environ, {"PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(setattr, B, "PEND", None)

    def pedir(self, texto="oi"):
        self.assertIn("AÇÃO PENDENTE", B.executar("mandar_aviso_teste", {"texto": texto}))

    def decisoes(self):
        with open(B.AUDITORIA, encoding="utf-8") as f:
            return [json.loads(l).get("decisao") for l in f if l.strip()]


class RespostasVagas(Base):
    def test_sim_pode_isso_nao_executam_nunca(self):
        for frase in ("sim", "Sim!", "pode", "Pode.", "pode fazer", "isso", "Isso!"):
            with self.subTest(frase=frase):
                self.pedir()
                tratado, resp = B.confirmar_voz(frase)
                self.assertEqual(FEITO, [])
                self.assertIsNotNone(B.pendente_publico(), "a pendência continua esperando")
                self.assertTrue(tratado)
                self.assertIn("confirmo mandar aviso", resp)       # diz a frase exata que vale
                self.assertIn("mandar aviso", resp)
                B.cancelar()

    def test_vaga_depois_de_outra_conversa_segue_como_conversa(self):
        # "sim" respondendo a outra pergunta não pode ser sequestrado: passa para a IA, e a ação continua sem executar
        self.pedir()
        self.assertEqual(B.confirmar_voz("que horas são"), (False, ""))
        self.assertEqual(B.confirmar_voz("sim"), (False, ""))
        self.assertEqual(FEITO, [])
        self.assertIsNotNone(B.pendente_publico())

    def test_vaga_sem_pendencia_nao_faz_nada(self):
        self.assertEqual(B.confirmar_voz("sim"), (False, ""))
        self.assertEqual(B.confirmar_voz("pode"), (False, ""))


class ConsentimentoExplicito(Base):
    def test_confirmo_logo_em_seguida_executa_uma_vez(self):
        self.pedir("oi")
        self.assertEqual(B.confirmar_voz("Confirmo!"), (True, "feito oi"))
        self.assertEqual(FEITO, ["oi"])
        self.assertEqual(B.confirmar_voz("confirmo"), (False, ""))     # a confirmação não sobra para a próxima
        self.assertEqual(FEITO, ["oi"])

    def test_confirmo_solto_depois_de_outra_conversa_nao_executa(self):
        # «confirmo» pode ter sido a resposta a OUTRA pergunta ("você confirma o horário?")
        self.pedir()
        self.assertEqual(B.confirmar_voz("qual o horário da reunião"), (False, ""))
        tratado, resp = B.confirmar_voz("confirmo")
        self.assertTrue(tratado)
        self.assertEqual(FEITO, [])
        self.assertIn("confirmo mandar aviso", resp)
        self.assertIsNotNone(B.pendente_publico())

    def test_confirmo_com_o_nome_da_acao_vale_a_qualquer_hora(self):
        self.pedir("até já")
        B.confirmar_voz("qual o horário da reunião")
        B.confirmar_voz("e a previsão do tempo")
        self.assertEqual(B.confirmar_voz("confirmo mandar aviso"), (True, "feito até já"))

    def test_nome_da_acao_com_consentimento_explicito_vale(self):
        for frase in ("autorizo mandar aviso", "Confirmado: mandar aviso!", "eu confirmo mandar aviso", "confirmo, pode mandar o aviso"):
            with self.subTest(frase=frase):
                FEITO.clear()
                self.pedir()
                B.confirmar_voz("outra coisa qualquer")
                self.assertTrue(B.confirmar_voz(frase)[0])
                self.assertEqual(FEITO, ["oi"], frase)

    def test_pode_e_sim_nao_executam_nem_com_o_nome_da_acao(self):
        # «você pode mandar o aviso?» é pergunta, não consentimento: só confirmo/confirmado/autorizo executam
        for frase in ("pode mandar o aviso", "sim, pode mandar aviso", "você pode mandar aviso", "isso, mandar aviso"):
            with self.subTest(frase=frase):
                self.pedir()
                B.confirmar_voz("outra coisa qualquer")
                tratado, resp = B.confirmar_voz(frase)
                self.assertTrue(tratado)
                self.assertEqual(FEITO, [], frase)
                self.assertIn("confirmo mandar aviso", resp)
                B.cancelar()

    def test_nome_da_acao_sem_consentimento_nao_executa(self):
        self.pedir()
        B.confirmar_voz("outra coisa")
        self.assertEqual(B.confirmar_voz("como funciona mandar aviso"), (False, ""))
        self.assertEqual(FEITO, [])

    def test_confirmacao_de_outra_acao_nao_vale(self):
        self.pedir()
        B.confirmar_voz("outra coisa")
        tratado, _ = B.confirmar_voz("confirmo apagar cache teste")
        self.assertEqual(FEITO, [])
        self.assertIsNotNone(B.pendente_publico())

    def test_negacao_cancela(self):
        self.pedir()
        B.confirmar_voz("outra coisa")
        self.assertEqual(B.confirmar_voz("não confirmo mandar aviso"), (True, "Cancelado."))
        self.assertIsNone(B.pendente_publico())
        self.assertEqual(FEITO, [])

    def test_cancela_continua_funcionando(self):
        self.pedir()
        self.assertEqual(B.confirmar_voz("cancela"), (True, "Cancelado."))
        self.assertIsNone(B.pendente_publico())


class SemReuso(Base):
    def test_confirmacao_dita_antes_nao_vale_para_pendencia_nova(self):
        self.assertEqual(B.confirmar_voz("confirmo"), (False, ""))
        self.pedir()
        self.assertEqual(FEITO, [])
        self.assertIsNotNone(B.pendente_publico())

    def test_pendencia_trocada_exige_nova_confirmacao(self):
        self.pedir("primeira")
        B.executar("mandar_aviso_teste", {"texto": "segunda"})     # a IA propôs outra coisa por cima
        self.assertIn("substituido", self.decisoes())
        B.confirmar_voz("outra coisa")
        B.confirmar_voz("confirmo mandar aviso")
        self.assertEqual(FEITO, ["segunda"])                        # só a pendência que existia agora; a primeira nunca roda

    def test_confirmacao_de_uma_acao_nao_executa_a_proxima(self):
        self.pedir("primeira")
        B.confirmar_voz("confirmo")
        B.executar("mandar_aviso_teste", {"texto": "segunda"})
        self.assertEqual(FEITO, ["primeira"])

    def test_expirou_nao_executa(self):
        self.pedir()
        B.PEND["expira"] = time.time() - 1
        self.assertEqual(B.confirmar_voz("confirmo mandar aviso"), (False, ""))
        self.assertEqual(FEITO, [])
        self.assertIn("expirado", self.decisoes())


class Nivel3ContinuaSoPin(Base):
    def test_voz_nao_libera_nivel_3_nem_com_o_nome(self):
        t = B.Turno()
        t.contaminado = True
        B.executar("mandar_aviso_teste", {"texto": "x"}, t)
        self.assertEqual(B.pendente_publico()["tipo"], "pin")
        for frase in ("confirmo", "confirmo mandar aviso", "sim"):
            tratado, resp = B.confirmar_voz(frase)
            self.assertEqual(FEITO, [])
        self.assertIn("PIN", B.confirmar_voz("confirmo mandar aviso")[1])
        self.assertIn("PIN", B.confirmar_botao(B.pendente_publico()["id"])[1])
        self.assertEqual(FEITO, [])
        self.assertTrue(B.confirmar_pin("4321")[0])
        self.assertEqual(FEITO, ["x"])


class Botao(Base):
    def test_botao_com_o_id_certo_executa(self):
        self.pedir()
        pid = B.pendente_publico()["id"]
        self.assertEqual(B.confirmar_botao(pid), (True, "feito oi"))
        self.assertEqual(FEITO, ["oi"])
        self.assertIn("confirmado_botao", self.decisoes())

    def test_botao_sem_id_ou_com_id_antigo_nao_executa(self):
        self.pedir("primeira")
        antigo = B.pendente_publico()["id"]
        self.pedir("segunda")
        for pid in (None, "", antigo, "zzz", 5):
            with self.subTest(pid=pid):
                ok, msg = B.confirmar_botao(pid)
                self.assertFalse(ok)
                self.assertEqual(FEITO, [])
        self.assertIsNotNone(B.pendente_publico())

    def test_botao_sem_pendencia(self):
        self.assertEqual(B.confirmar_botao("abc"), (False, "Nada pendente."))

    def test_botao_nao_reaproveita_id_ja_usado(self):
        self.pedir()
        pid = B.pendente_publico()["id"]
        B.confirmar_botao(pid)
        self.pedir()
        self.assertNotEqual(B.pendente_publico()["id"], pid)
        self.assertFalse(B.confirmar_botao(pid)[0])


class Publico(Base):
    def test_pendente_publico_traz_id_resumo_e_frase(self):
        self.pedir("até já")
        p = B.pendente_publico()
        self.assertTrue(p["id"] and p["id"].isalnum())
        self.assertIn("mandar aviso", p["resumo"])
        self.assertIn("até já", p["resumo"])
        self.assertIn("confirmo", B.frase_pendente())
        self.assertIn(p["resumo"], B.frase_pendente())

    def test_sem_pendencia_nao_ha_frase(self):
        self.assertIsNone(B.frase_pendente())

    def test_mensagem_para_a_ia_diz_como_confirmar(self):
        r = B.executar("mandar_aviso_teste", {"texto": "x"})
        self.assertIn("confirmo", r)
        self.assertIn("sim", r.lower())       # avisa que «sim» solto não vale


class NoFluxoDoPedido(Base):
    def test_resposta_da_ia_ganha_a_pendencia_real_no_fim(self):
        # a IA pode descrever mal a ação; quem fala a verdade é o corretor
        def ia(texto):
            B.executar("mandar_aviso_teste", {"texto": "ligue para o banco"})
            return "Vou só abrir o calendário para você."
        with mock.patch("cerebro.responder", side_effect=ia):
            r = MAIN.processar("faça aquilo")
        self.assertIn("Vou só abrir o calendário", r)
        self.assertIn("mandar aviso", r)
        self.assertIn("ligue para o banco", r)
        self.assertIn("confirmo", r)

    def test_sem_pendencia_nova_nada_e_acrescentado(self):
        with mock.patch("cerebro.responder", return_value="São três da tarde."):
            self.assertEqual(MAIN.processar("que horas são"), "São três da tarde.")

    def test_pendencia_antiga_nao_e_repetida_em_todo_pedido(self):
        self.pedir()
        with mock.patch("cerebro.responder", return_value="Claro."):
            self.assertEqual(MAIN.processar("fale do tempo"), "Claro.")

    def test_sim_solto_pelo_fluxo_do_pedido_nao_executa_e_nao_chama_a_ia(self):
        self.pedir()
        with mock.patch("cerebro.responder") as ia:
            r = MAIN.processar("sim")
        ia.assert_not_called()
        self.assertEqual(FEITO, [])
        self.assertIn("confirmo", r)

    def test_confirmo_pelo_fluxo_do_pedido_executa(self):
        self.pedir("pelo fluxo")
        with mock.patch("cerebro.responder") as ia:
            r = MAIN.processar("confirmo")
        ia.assert_not_called()
        self.assertEqual(r, "feito pelo fluxo")


class NotificacaoDaPendencia(Base):
    def test_notificacao_traz_o_id_da_pendencia_no_botao(self):
        self.pedir("oi")
        p = B.pendente_publico()
        open(LOG, "w").close()
        MAIN._notificar_pendencia(p)
        log = E.ler_log(LOG)
        self.assertIn("mandar aviso", log)
        self.assertIn(f"confirmar_voz {p['id']}", log)

    def test_notificacao_permanente_nao_tem_mais_botao_confirmo_solto(self):
        open(LOG, "w").close()
        MAIN._notificacao_painel(8080, "http://127.0.0.1:8080/#t=x")
        log = E.ler_log(LOG)
        self.assertNotIn("Confirmo", log)
        self.assertIn("Cancelar", log)

    def test_corretor_chama_o_gancho_ao_pedir_nivel_2(self):
        visto = []
        with mock.patch.object(B, "NOTIFICAR_PEDIDO", visto.append):
            self.pedir()
        self.assertEqual(len(visto), 1)
        self.assertEqual(visto[0]["id"], B.pendente_publico()["id"])

    def test_gancho_que_falha_nao_derruba_o_pedido(self):
        def quebra(p):
            raise RuntimeError("sem notificação")
        with mock.patch.object(B, "NOTIFICAR_PEDIDO", quebra):
            self.pedir()
        self.assertIsNotNone(B.pendente_publico())


if __name__ == "__main__":
    unittest.main()
