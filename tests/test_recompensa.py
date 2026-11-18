"""Aprendizado por recompensa: o feedback do dono muda o ESTILO que ela escolhe, e só o estilo."""
import random, time, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import recompensa as RC, cerebro as C
from test_assimilacao import Base


class Recompensa(Base):
    def setUp(self):
        super().setUp()
        RC._ult.update(ctx=None, jeito=None, t=0.0)

    def votar(self, jeito_bom, n=40, texto="como funciona o SQL?"):
        rng = random.Random(1)
        for _ in range(n):
            j, _ = RC.escolher(texto, rng=rng)
            RC.recompensar(j == jeito_bom)

    def test_aprende_o_jeito_que_o_dono_aprova(self):
        self.votar("exemplo")
        rng = random.Random(7)
        escolhas = [RC.escolher("como funciona o SQL?", rng=rng)[0] for _ in range(200)]
        self.assertGreater(escolhas.count("exemplo") / 200, 0.7)

    def test_contexto_diferente_aprende_separado(self):
        self.votar("exemplo", texto="como funciona o SQL?")
        self.assertNotIn(RC.contexto("faça uma lista de compras"), RC._ler())

    def test_feedback_por_voz_e_so_para_a_ultima_resposta_recente(self):
        self.assertIn("não tenho uma resposta recente", RC.tratar("boa resposta"))
        RC.escolher("como funciona o SQL?")
        self.assertIn("Vou responder mais vezes", RC.tratar("Friday, boa resposta!"))
        self.assertIn("não tenho uma resposta recente", RC.tratar("resposta ruim"))      # um voto por resposta
        RC.escolher("como funciona o SQL?", agora=time.time() - 3600)
        self.assertIsNone(RC.recompensar(True))                                           # velha demais
        self.assertIsNone(RC.tratar("o SQL não é ruim"))

    def test_mostra_o_que_aprendeu(self):
        self.votar("direto")
        self.assertIn("direto ao ponto", RC.tratar("o que você aprendeu com meu feedback?"))

    def test_so_estilo_entra_no_prompt_e_nenhuma_frase_vai_ao_disco(self):
        with mock.patch.object(C, "_nuvem", return_value="ok") as nuv, mock.patch.object(C.F, "contar_llm", return_value=True):
            C._responder("como funciona o SQL com meu CPF 123.456.789-09?")
        self.assertIn("ESTILO DESTA RESPOSTA", nuv.call_args[0][2])
        RC.recompensar(True)
        self.assertNotIn("123.456", self.base(".cerebro", "recompensa.json").read_text(encoding="utf-8"))

    def test_nao_ha_ferramenta_da_ia_para_se_recompensar(self):
        self.assertFalse([n for n in B.FERRAMENTAS if "recompens" in n.lower() or "feedback" in n.lower()])


if __name__ == "__main__":
    unittest.main()
