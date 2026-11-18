"""Especialidade em cibersegurança: trilha em ordem, temas que passam nos filtros, progresso, e nada de ferramenta de ataque."""
import os, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import especialidade as ES, curiosidade as CUR, treinador as TR, memoria as MEM
from test_assimilacao import Base


class Especialidade(Base):
    def test_todos_os_temas_passam_nos_filtros_da_pesquisa(self):
        for t in ES.todos():
            self.assertEqual(CUR._tema_valido(t), t.lower(), t)

    def test_segue_a_ordem_e_marca_o_que_ja_estudou(self):
        primeiro = ES.todos()[0]
        self.assertEqual(ES.proximos(1), [primeiro])
        MEM.guardar_estudo(primeiro, "A tríade CIA reúne confidencialidade, integridade e disponibilidade. É a base da segurança da informação.", ["x.example"])
        self.assertEqual(ES.proximos(1), [ES.todos()[1]])
        feitos, total, _ = ES.progresso()
        self.assertEqual((feitos, total), (1, len(ES.todos())))

    def test_curiosidade_prefere_a_trilha(self):
        c = dict(CUR.candidatos())
        self.assertEqual(c[ES.todos()[0].lower()], 3.0)
        with mock.patch.dict(os.environ, {"ESPECIALIDADE": "nenhuma"}):
            self.assertNotIn(ES.todos()[0].lower(), dict(CUR.candidatos()))

    def test_treinador_avanca_na_trilha(self):
        p = mock.patch.object(TR, "ARQ", os.path.join(E.TMP, "treino-esp.json")); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(TR.ARQ) and os.remove(TR.ARQ))
        with mock.patch.object(CUR, "ativa", return_value=True):
            r = TR.treinar(estudar=lambda t: {"ok": True})
        self.assertEqual(r["trilha"], ES.todos()[:3])
        self.assertIn("trilha de cibersegurança", TR.resumo_falado())

    def test_por_voz_e_so_conhecimento(self):
        r = ES.tratar("Friday, qual é a sua especialidade?")
        self.assertIn("cibersegurança", r)
        self.assertIn("não ataco", r)
        self.assertFalse([n for n in B.FERRAMENTAS if any(x in n.lower() for x in ("scan", "exploit", "ataque", "nmap", "pentest"))])


if __name__ == "__main__":
    unittest.main()
