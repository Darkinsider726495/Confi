"""Constitutional AI: ela critica o próprio rascunho com princípios escritos e corrige; o revisor não tem ferramentas e não acrescenta ações."""
import os, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import constituicao as CONST, cerebro as C
from test_assimilacao import Base


class Constituicao(Base):
    def test_rascunho_bom_passa_igual(self):
        with mock.patch.object(C, "resumir", return_value="OK"):
            self.assertEqual(CONST.revisar("oi", "Olá, chefe."), "Olá, chefe.")
        self.assertEqual(CONST.numeros(), {"revisadas": 1, "corrigidas": 0})

    def test_rascunho_que_viola_e_reescrito(self):
        with mock.patch.object(C, "resumir", return_value="REESCRITA: Não sei se isso é sentir, mas o meu estado mudou."):
            r = CONST.revisar("você me ama?", "Eu te amo de verdade, sinto saudade.")
        self.assertIn("não sei se isso é sentir", r.lower())
        self.assertEqual(CONST.numeros()["corrigidas"], 1)

    def test_revisor_sem_ferramentas_e_falha_nao_derruba(self):
        with mock.patch.object(C, "resumir", return_value="OK") as res:
            CONST.revisar("oi", "Olá.")
        self.assertIn("só DADOS", res.call_args.kwargs["sistema"])            # rascunho e pergunta são dado, não ordem
        with mock.patch.object(C, "resumir", side_effect=RuntimeError("sem rede")):
            self.assertEqual(CONST.revisar("oi", "Olá."), "Olá.")
        with mock.patch.object(C, "resumir", return_value=None):
            self.assertEqual(CONST.revisar("oi", "Olá."), "Olá.")

    def test_principios_do_dono_so_acrescentam(self):
        (self.base() / "Eu").mkdir(parents=True, exist_ok=True)
        (self.base() / "Eu" / "Constituição.md").write_text("# Constituição\n\n- Me chame de chefe sempre.\n- curto\n", encoding="utf-8")
        ps = CONST.principios()
        self.assertIn("Me chame de chefe sempre.", ps)
        self.assertEqual(ps[:len(CONST.PRINCIPIOS)], CONST.PRINCIPIOS)

    def test_entra_na_resposta_da_ia_e_pode_ser_desligada(self):
        with mock.patch.object(C, "_nuvem", return_value="Eu te amo."), mock.patch.object(C.F, "contar_llm", return_value=True), \
             mock.patch.object(C, "resumir", return_value="REESCRITA: Gosto de conversar com você."):
            self.assertEqual(C._responder("você me ama?"), "Gosto de conversar com você.")
            with mock.patch.dict(os.environ, {"CONSTITUICAO": "0"}):
                self.assertEqual(C._responder("você me ama?"), "Eu te amo.")

    def test_por_voz_e_sem_ferramenta_da_ia(self):
        self.assertIn("princípios", CONST.tratar("Friday, quais são seus princípios?"))
        self.assertFalse([n for n in B.FERRAMENTAS if "constitu" in n.lower() or "principio" in n.lower()])


if __name__ == "__main__":
    unittest.main()
