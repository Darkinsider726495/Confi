"""Treinador diário: aprofunda os assuntos do dia, revisa o estudo mais antigo, reajusta as redes; respeita a curiosidade do dono."""
import os, time, unittest, datetime as dt
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import treinador as TR, curiosidade as CUR, memoria as MEM
from test_assimilacao import Base, ia
import assimilacao as A


class Treinador(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(TR, "ARQ", os.path.join(E.TMP, "treino-teste.json")); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(TR.ARQ) and os.remove(TR.ARQ))
        with ia("banco de dados, joins"):
            A.assimilar("fala", "estudei banco de dados e joins hoje")
        MEM.guardar_estudo("vulcões", "Os vulcões nascem quando o magma sobe pela crosta. A lava esfria e forma novas rochas.", ["geo.example"])
        self.estudados = []

    def estudar(self, t):
        self.estudados.append(t)
        return {"ok": True}

    def test_aprofunda_os_assuntos_do_dia_e_revisa_o_mais_antigo(self):
        with mock.patch.object(CUR, "ativa", return_value=True):
            r = TR.treinar(estudar=self.estudar)
        self.assertIn("Banco de dados", r["estudados"])
        self.assertIn("Joins", r["estudados"])
        self.assertEqual(r["revisado"], "Vulcões")
        self.assertIn("aprofundei 2 assunto", TR.resumo_falado())

    def test_sem_curiosidade_nao_estuda_mas_treina_as_redes(self):
        with mock.patch.object(CUR, "ativa", return_value=False):
            r = TR.treinar(estudar=self.estudar)
        self.assertEqual(self.estudados, [])
        self.assertTrue(r.get("sem_curiosidade"))
        self.assertIn("curiosidade está desligada", TR.resumo_falado())

    def test_o_dono_pode_por_teto(self):
        with mock.patch.object(CUR, "ativa", return_value=True), mock.patch.dict(os.environ, {"TREINO_MAX_ESTUDOS": "1"}):
            r = TR.treinar(estudar=self.estudar)
        self.assertEqual(len(r["estudados"]), 1)

    def test_uma_vez_por_dia_depois_da_hora(self):
        cedo = dt.datetime.now().replace(hour=2, minute=0).timestamp()
        tarde = dt.datetime.now().replace(hour=15, minute=0).timestamp()
        with mock.patch.object(TR, "treinar") as t, mock.patch("threading.Thread") as th:
            TR.gancho(cedo)
            self.assertFalse(th.called)                                 # antes das 03:00, não
            TR.gancho(tarde); TR.gancho(tarde + 60)
            self.assertEqual(th.call_count, 1)                           # depois, uma vez só no dia

    def test_por_voz_e_sem_ferramenta_da_ia(self):
        self.assertIn("desligado", TR.tratar("desliga o treino diário"))
        self.assertEqual(TR.gancho(), [])
        self.assertIn("ligado", TR.tratar("liga o treino diário"))
        self.assertIn("Ainda não treinei", TR.tratar("como foi o seu treino?"))
        self.assertFalse([n for n in B.FERRAMENTAS if "trein" in n.lower()])


class CotaDoFundo(unittest.TestCase):
    def test_fundo_espera_a_vez_e_da_passagem_ao_dono(self):
        import cerebro as C
        dormiu = []
        with mock.patch.dict(os.environ, {"FUNDO_INTERVALO_S": "20", "FUNDO_DONO_S": "120"}):
            C._FUNDO.update(ult=time.time(), dono=0.0)
            C._esperar_vez_do_fundo(dormir=lambda s: (dormiu.append(s), C._FUNDO.update(ult=0.0)))
            self.assertTrue(dormiu)                                      # chamada logo depois de outra: espera
            dormiu.clear()
            C._FUNDO.update(ult=0.0, dono=time.time())
            C._esperar_vez_do_fundo(dormir=lambda s: (dormiu.append(s), C._FUNDO.update(dono=0.0)))
            self.assertTrue(dormiu)                                      # você acabou de falar: o fundo espera
        C._FUNDO.update(ult=0.0, dono=0.0)


if __name__ == "__main__":
    unittest.main()
