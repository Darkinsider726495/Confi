"""Fase 2 — o corretor passa a dizer, de forma ESTRUTURADA, o que aconteceu com um pedido, e a avisar quem acompanha o fim de cada ação.

Antes, `executar()` devolvia só texto («Feito.», «AÇÃO PENDENTE…», «Pedido inválido…») e quem quisesse saber se algo foi executado, ficou pendente, foi recusado ou
deu erro tinha de adivinhar pelo começo da frase. Agora:
  - `executar_estruturado()` devolve {estado, texto, pendencia, nivel, erro, codigo, ajustes}; `executar()` continua devolvendo o MESMO texto de sempre;
  - `OBSERVADORES` recebem um evento quando uma ação é executada (inclusive depois de uma confirmação), cancelada, expira ou é substituída.
    O evento leva os argumentos e o resultado CRUS só em memória; a trilha de auditoria continua sem conteúdo.
"""
import json, os, time, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401

BIN, LOG = E.termux_falso()


def trilha_texto():
    with open(B.AUDITORIA, encoding="utf-8") as f:
        return f.read()


class Base(unittest.TestCase):
    def setUp(self):
        B.PEND = None
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)
        self.eventos = []
        B.OBSERVADORES.append(self.eventos.append)
        self.addCleanup(lambda: B.OBSERVADORES.remove(self.eventos.append) if self.eventos.append in B.OBSERVADORES else None)
        self.addCleanup(setattr, B, "PEND", None)
        self.feitos = []
        B.registrar("acao_n1_est", "teste", {"x": {"type": "string"}}, ["x"], lambda x: self.feitos.append(x) or f"feito {x}", 1)
        B.registrar("acao_n2_est", "teste", {"x": {"type": "string"}}, ["x"], lambda x: self.feitos.append(x) or f"feito {x}", 2, rotulo="fazer teste")
        B.registrar("acao_n3_est", "teste", {"x": {"type": "string"}}, ["x"], lambda x: self.feitos.append(x) or f"feito {x}", 3, rotulo="fazer teste critico")
        B.registrar("acao_n4_est", "teste", {}, [], lambda: "nunca", 4)
        B.registrar("acao_erro_est", "teste", {}, [], lambda: "Erro: algo deu errado", 1)
        B.registrar("acao_explode_est", "teste", {}, [], lambda: 1 / 0, 1)
        self.addCleanup(lambda: [B.FERRAMENTAS.pop(n, None) for n in ("acao_n1_est", "acao_n2_est", "acao_n3_est", "acao_n4_est", "acao_erro_est", "acao_explode_est")])


class Estruturado(Base):
    def test_executada_automatica(self):
        r = B.executar_estruturado("acao_n1_est", {"x": "a"})
        self.assertEqual((r["estado"], r["texto"], r["pendencia"], r["nivel"], r["erro"], r["codigo"]), ("executada", "feito a", None, 1, False, "ok"))

    def test_o_texto_de_executar_e_o_mesmo_de_sempre(self):
        casos = [("acao_n1_est", {"x": "a"}), ("acao_erro_est", {}), ("acao_n1_est", {"x": 5}), ("nao_existe_est", {}), ("acao_n4_est", {}), ("acao_n1_est", {})]
        for nome, args in casos:
            with self.subTest(nome=nome, args=args):
                B.PEND = None
                self.assertEqual(B.executar(nome, args), B.executar_estruturado(nome, args)["texto"])

    def test_erro_da_ferramenta_vira_erro_estruturado(self):
        r = B.executar_estruturado("acao_erro_est", {})
        self.assertEqual((r["estado"], r["erro"], r["codigo"]), ("executada", True, "Erro"))
        r = B.executar_estruturado("acao_explode_est", {})
        self.assertEqual((r["estado"], r["erro"], r["codigo"]), ("executada", True, "Erro: ZeroDivisionError"))

    def test_recusas(self):
        r = B.executar_estruturado("nao_existe_est", {})
        self.assertEqual((r["estado"], r["codigo"], r["pendencia"]), ("recusada", "desconhecida", None))
        r = B.executar_estruturado("acao_n1_est", {"x": 5})
        self.assertEqual((r["estado"], r["codigo"]), ("recusada", "tipo:x"))
        self.assertTrue(r["texto"].startswith("Pedido inválido"))
        r = B.executar_estruturado("acao_n1_est", {})
        self.assertEqual((r["estado"], r["codigo"]), ("recusada", "falta:x"))
        self.assertEqual(self.feitos, [])

    def test_nivel_4_e_negado(self):
        r = B.executar_estruturado("acao_n4_est", {})
        self.assertEqual((r["estado"], r["codigo"]), ("negada", "nivel4"))

    def test_manutencao_nega_nivel_2(self):
        marca = os.path.join(B.BASE, "MANUTENCAO")
        with open(marca, "w"):
            pass
        self.addCleanup(lambda: os.path.exists(marca) and os.remove(marca))
        r = B.executar_estruturado("acao_n2_est", {"x": "a"})
        self.assertEqual((r["estado"], r["codigo"]), ("negada", "manutencao"))
        self.assertIsNone(B.pendente_publico())

    def test_pendente_traz_o_id_da_pendencia(self):
        r = B.executar_estruturado("acao_n2_est", {"x": "a"})
        self.assertEqual((r["estado"], r["nivel"]), ("pendente", 2))
        self.assertEqual(r["pendencia"], B.pendente_publico()["id"])
        self.assertTrue(r["texto"].startswith("AÇÃO PENDENTE"))
        self.assertEqual(self.feitos, [], "pendente não executa")

    def test_contaminacao_continua_subindo_o_nivel(self):
        t = B.Turno()
        t.contaminado = True
        r = B.executar_estruturado("acao_n1_est", {"x": "a"}, t)
        self.assertEqual((r["estado"], r["nivel"]), ("pendente", 2), "dado de terceiros no turno: nível 1 sobe para 2")

    def test_ajuste_declarado_aparece_no_resultado(self):
        r = B.executar_estruturado("ler_notas", {"limite": 50})
        self.assertEqual(r["ajustes"], {"limite": (50, 20)})
        self.assertIn("juste", r["texto"])


class Eventos(Base):
    def tipos(self):
        return [e["tipo"] for e in self.eventos]

    def test_execucao_automatica_emite_evento_sem_pendencia(self):
        B.executar("acao_n1_est", {"x": "segredo-123"})
        e = self.eventos[-1]
        self.assertEqual((e["tipo"], e["ferramenta"], e["pendencia"], e["erro"], e["resultado"]), ("executada", "acao_n1_est", None, False, "feito segredo-123"))
        self.assertEqual(e["args"], {"x": "segredo-123"})

    def test_evento_leva_o_conteudo_cru_mas_a_trilha_nao(self):
        B.executar("acao_n1_est", {"x": "meu segredo muito particular"})
        self.assertEqual(self.eventos[-1]["args"]["x"], "meu segredo muito particular")
        self.assertNotIn("particular", trilha_texto())

    def test_confirmar_por_voz_emite_executada_com_o_id(self):
        pid = B.executar_estruturado("acao_n2_est", {"x": "a"})["pendencia"]
        ok, r = B.confirmar_voz("confirmo")
        self.assertTrue(ok)
        e = self.eventos[-1]
        self.assertEqual((e["tipo"], e["pendencia"], e["ferramenta"], e["decisao"]), ("executada", pid, "acao_n2_est", "confirmado_voz"))

    def test_confirmar_pelo_botao_emite_executada_com_o_id(self):
        pid = B.executar_estruturado("acao_n2_est", {"x": "a"})["pendencia"]
        B.confirmar_botao(pid)
        self.assertEqual((self.eventos[-1]["tipo"], self.eventos[-1]["pendencia"], self.eventos[-1]["decisao"]), ("executada", pid, "confirmado_botao"))

    def test_confirmar_com_pin_emite_executada_com_o_id(self):
        with mock.patch.dict(os.environ, {"FRIDAY_PIN": "4321"}):
            pid = B.executar_estruturado("acao_n3_est", {"x": "a"})["pendencia"]
            ok, _ = B.confirmar_pin("4321")
        self.assertTrue(ok)
        self.assertEqual((self.eventos[-1]["tipo"], self.eventos[-1]["pendencia"], self.eventos[-1]["decisao"]), ("executada", pid, "confirmado_pin"))

    def test_resposta_vaga_nao_executa_nem_emite(self):
        B.executar("acao_n2_est", {"x": "a"})
        for fala in ("sim", "pode", "isso"):
            B.confirmar_voz(fala)
        self.assertEqual(self.tipos(), [])
        self.assertEqual(self.feitos, [])

    def test_cancelar_por_voz_emite_cancelada(self):
        pid = B.executar_estruturado("acao_n2_est", {"x": "a"})["pendencia"]
        B.confirmar_voz("cancela")
        self.assertEqual(self.tipos(), ["cancelada"])
        self.assertEqual((self.eventos[0]["pendencia"], self.eventos[0]["ferramenta"]), (pid, "acao_n2_est"))

    def test_cancelar_pelo_painel_emite_cancelada(self):
        pid = B.executar_estruturado("acao_n2_est", {"x": "a"})["pendencia"]
        B.cancelar()
        self.assertEqual((self.tipos(), self.eventos[0]["pendencia"]), (["cancelada"], pid))
        B.cancelar()                                                      # sem pendência: nada a avisar
        self.assertEqual(self.tipos(), ["cancelada"])

    def test_expirar_emite_expirada(self):
        pid = B.executar_estruturado("acao_n2_est", {"x": "a"})["pendencia"]
        B.PEND["expira"] = time.time() - 1
        self.assertIsNone(B.pendente_publico())
        self.assertEqual((self.tipos(), self.eventos[0]["pendencia"]), (["expirada"], pid))
        self.assertEqual(self.feitos, [])

    def test_substituir_emite_substituida_da_antiga(self):
        antiga = B.executar_estruturado("acao_n2_est", {"x": "a"})["pendencia"]
        nova = B.executar_estruturado("acao_n2_est", {"x": "b"})["pendencia"]
        self.assertNotEqual(antiga, nova)
        self.assertEqual((self.tipos(), self.eventos[0]["pendencia"]), (["substituida"], antiga))
        B.confirmar_voz("confirmo")
        self.assertEqual(self.feitos, ["b"], "a antiga nunca roda")

    def test_observador_que_quebra_nao_atrapalha_o_corretor(self):
        def ruim(_ev):
            raise RuntimeError("quebrei")
        B.OBSERVADORES.insert(0, ruim)
        self.addCleanup(B.OBSERVADORES.remove, ruim)
        self.assertEqual(B.executar("acao_n1_est", {"x": "a"}), "feito a")
        self.assertEqual(self.tipos(), ["executada"], "os outros observadores seguem recebendo")

    def test_observador_nao_altera_o_que_os_outros_veem(self):
        def mexe(ev):
            ev["args"]["x"] = "adulterado"
            ev["resultado"] = "adulterado"
        B.OBSERVADORES.insert(0, mexe)
        self.addCleanup(B.OBSERVADORES.remove, mexe)
        B.executar("acao_n1_est", {"x": "original"})
        self.assertEqual(self.eventos[-1]["args"], {"x": "original"})
        self.assertEqual(self.eventos[-1]["resultado"], "feito original")

    def test_cadeia_de_hashes_continua_integra(self):
        B.executar("acao_n1_est", {"x": "a"})
        B.executar_estruturado("acao_n2_est", {"x": "b"})
        B.confirmar_voz("confirmo")
        self.assertEqual(B.verificar_auditoria()[0], True)


if __name__ == "__main__":
    unittest.main()
