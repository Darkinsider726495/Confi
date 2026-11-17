"""Rede de significado: as três etapas ENSINAM de verdade (pré-treino, ajuste com sinapses, feedback do dono) e ela só sugere ligações."""
import json, os, time, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import memoria as MEM, neuronios as N, significado as S, assimilacao as A, cerebro as C
from test_assimilacao import Base, ia

# corpus sintético: dois mundos de palavras que nunca se misturam
CORPUS = ([f"o treino na academia foi puxado e a musculação cansou o corpo inteiro {i}" for i in range(60)]
          + [f"a prova de banco de dados cobra consulta sql com joins e tabelas {i}" for i in range(60)]
          + [f"a academia abre cedo e o treino de musculação começa às seis {i}" for i in range(40)]
          + [f"estudar sql para a prova exige praticar joins e consultas nas tabelas {i}" for i in range(40)])


class Pretreino(unittest.TestCase):
    def test_aprende_significado_sozinho_sem_rotulo(self):
        vocab, W = S.pretreinar(CORPUS, epocas=15, min_freq=2)
        with S._trava:
            S._m.update(vocab=vocab, idx={w: i for i, w in enumerate(vocab)}, W=W, raiz="x")
        with mock.patch.object(S, "carregar", return_value=True):
            perto = S.parecenca("treino", "academia")
            longe = S.parecenca("treino", "joins")
        self.assertGreater(perto, longe + 0.3, (perto, longe))

    def test_a_perda_cai_com_o_treino(self):
        perdas = []
        S.pretreinar(CORPUS, epocas=5, relatorio=lambda ep, p: perdas.append(p))
        self.assertLess(perdas[-1], perdas[0])

    def test_texto_de_menos_e_recusado(self):
        with self.assertRaises(ValueError):
            S.pretreinar(["só uma frase curtinha"])

    def test_base_do_pacote_existe_e_nao_tem_dado_pessoal(self):
        self.assertTrue(os.path.exists(S.BASE_NPZ))
        import numpy as np
        vocab = set(str(w) for w in np.load(S.BASE_NPZ)["vocab"])
        self.assertIn("memoria", vocab)
        for pessoal in ("joao", "senha", "cpf"):
            self.assertNotIn(pessoal, vocab - {"senha", "cpf"} if pessoal != "joao" else vocab)


class Ajuste(Base):
    """Etapas 2 e 3, no cofre de teste: sinapses e feedback mexem na rede (e salvam a versão DELA no cofre)."""
    def setUp(self):
        super().setUp()
        vocab, W = S.pretreinar(CORPUS, epocas=15)
        S.salvar(vocab, W)
        self.t = time.time() - 100_000
        S.carregar(forcar=True)
        self.addCleanup(lambda: S._m.update(vocab=None))

    def topicos(self, *nomes):
        for n in nomes:                                   # espaçados no tempo: sem ligação por contexto, só por significado
            self.t += A.CONTEXTO_S + 60
            N._ult.update(chave=None, t=0.0)
            with ia(n.lower()):
                A.assimilar("fala", f"falei de {n}", self.t)

    def test_sinapse_forte_aproxima_os_dois_assuntos(self):
        self.topicos("Treino", "Joins")
        antes = S.parecenca("treino", "joins")
        with N._trava:
            N._estado()["sin"][N._chave("Topicos/Treino", "Topicos/Joins")] = [4.0, time.time()]
        self.assertGreater(S.ajustar(epocas=40), 0)
        self.assertGreater(S.parecenca("treino", "joins"), antes)
        self.assertTrue(self.base(".cerebro", "significado.npz").exists())     # a versão dela fica no cofre

    def test_feedback_do_dono_afasta(self):
        self.topicos("Treino", "Academia")
        antes = S.parecenca("treino", "academia")
        self.assertIn("não têm a ver", S.tratar("treino não tem nada a ver com academia"))
        S.ajustar(epocas=40)
        self.assertLess(S.parecenca("treino", "academia"), antes)

    def test_frase_comum_nao_vira_feedback(self):
        self.assertIsNone(S.tratar("isso tem a ver com aquilo que eu falei ontem de manhã"))
        self.assertFalse(self.base(".cerebro", "significado_feedback.jsonl").exists())

    def test_assunto_novo_se_liga_ao_parecido_que_ela_ja_conhece(self):
        self.topicos("Academia")
        with mock.patch.object(S, "LIMIAR_LIGAR", 0.3):
            self.topicos("Musculação")
        self.assertGreater(N._peso(N._estado(), N._chave("Topicos/Musculação", "Topicos/Academia")), 0)

    def test_assunto_sem_relacao_nao_se_liga(self):
        self.topicos("Academia")
        self.topicos("Joins")
        e = N._estado()
        self.assertEqual(N._peso(e, N._chave("Topicos/Joins", "Topicos/Academia")), 0)

    def test_o_que_e_parecido(self):
        self.topicos("Academia", "Joins", "Tabelas")
        r = S.tratar("o que é parecido com musculação?")
        self.assertIn("academia", r)
        self.assertNotIn("joins", r.split("(")[0])


class SemNumpy(Base):
    def test_sem_numpy_tudo_desliga_sem_erro(self):
        with mock.patch.object(S, "np", None):
            self.assertFalse(S.disponivel())
            self.assertFalse(S.carregar(forcar=True))
            self.assertEqual(S.ligar_por_significado(["Treino"]), [])
            self.assertIn("NumPy", S.tratar("o que é parecido com treino?"))
            with ia("treino"):
                self.assertEqual(A.assimilar("fala", "fui treinar"), ["Treino"])     # a assimilação segue normal


if __name__ == "__main__":
    unittest.main()
