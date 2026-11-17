"""Sinapses não têm teto: nem quantas existem, nem quantas ela descobre por noite, nem quantas o painel conta. Só você pode pôr um teto (CEREBRO_*)."""
import os, re, time, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, neuronios as N
from test_neuronios import Cerebro

FRIDAY = Path(__file__).resolve().parent.parent / "friday"


class Padrao(unittest.TestCase):
    def test_nenhum_teto_de_sinapses_por_padrao(self):
        for nome in ("MAX_SINAPSES", "MAX_USO", "MAX_DESC", "DESC_NOITE", "DESC_CICLO", "DESC_DIA", "SONHOS_NOITE"):
            self.assertEqual(getattr(N, nome), 0, nome)       # 0 = sem teto

    def test_so_o_dono_poe_teto_pelo_env_e_lixo_nao_quebra(self):
        casos = {"100": 100, "2.9": 2, "-5": 0, "0": 0, "abc": 0, "": 0}
        for valor, esperado in casos.items():
            with mock.patch.dict(os.environ, {"CEREBRO_MAX_SINAPSES": valor}):
                self.assertEqual(N._teto("MAX_SINAPSES"), esperado, valor)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CEREBRO_MAX_SINAPSES", None)
            self.assertEqual(N._teto("MAX_SINAPSES"), 0)

    def test_o_codigo_nao_tem_numero_fixo_limitando_sinapses(self):
        n = (FRIDAY / "neuronios.py").read_text(encoding="utf-8")
        self.assertNotIn("[:1500]", n)                        # o painel recebia só as 1500 mais fortes e contava errado
        self.assertNotIn("> 800", n)                          # candidatas a sinapse eram apagadas acima de 800
        for f in sorted(FRIDAY.glob("*.py")):
            self.assertNotRegex(f.read_text(encoding="utf-8"), r"descobrir\(\s*\d", f"{f.name}: descobrir com número fixo")


class SemTeto(Cerebro):
    def setUp(self):
        super().setUp()
        N._dorm.update(v=None, raiz=None, sujo=False)
        p = mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "0"})
        p.start(); self.addCleanup(p.stop)

    def test_milhares_de_sinapses_ficam_ativas_e_nenhuma_adormece_por_quantidade(self):
        e = N._estado()
        agora = time.time()
        for i in range(6000):
            e["sin"][f"Memorias/A{i}|Memorias/B{i}"] = [2.0, agora]
        N._salvar()
        self.assertEqual(len(N._estado()["sin"]), 6000)
        self.assertEqual(N._dormentes(), {})
        N.sonhar(True)                                        # o sono esmaece um pouco, mas não corta por quantidade
        self.assertEqual(len(N._estado()["sin"]), 6000)
        self.assertEqual(N._dormentes(), {})

    def test_o_painel_conta_e_recebe_todas_as_sinapses(self):
        n = 80
        for i in range(n):
            self.nota("Memorias", f"Nota {i}", f"Assunto {i}", tags="[friday]")
        e = N._estado()
        agora = time.time()
        for i in range(n):
            for j in range(i + 1, n):
                e["sin"][N._chave(f"Memorias/Nota {i}", f"Memorias/Nota {j}")] = [1.0, agora]
        total = n * (n - 1) // 2                              # 3160: mais do dobro do antigo corte de 1500
        g = N.grafo()
        self.assertGreater(total, 1500)
        self.assertEqual(g["stats"]["sinapses"], total)
        self.assertEqual(len(g["arestas"]), total)

    def test_contagem_de_uso_tambem_nao_e_cortada(self):
        e = N._estado()
        for i in range(3000):
            e["uso"][f"Memorias/N{i}"] = 1
        N._salvar()
        self.assertEqual(len(N._estado()["uso"]), 3000)

    def test_candidatas_a_sinapse_nao_sao_apagadas_acima_de_800(self):
        e = N._estado()
        for i in range(1200):
            e["desc"][f"a{i}|b{i}"] = {"p": "2026-01-01", "u": "2026-01-01", "t": "x", "s": 0.3}
        N._salvar()
        self.assertEqual(len(N._estado()["desc"]), 1200)

    def test_descobre_quantas_houver_sem_limite_por_noite_nem_por_dia(self):
        pares = [(0.5, f"Memorias/A{i}", f"Memorias/B{i}", "termo") for i in range(150)]
        with mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "1"}), mock.patch.object(N, "_pares_parecidos", lambda: pares), mock.patch.object(N, "_promover", lambda *a: None):
            self.assertEqual(N.descobrir(), 150)              # o antigo limite era 40 por noite e 60 por dia
            self.assertEqual(len(N._estado()["desc"]), 150)

    def test_teto_opcional_do_dono_continua_funcionando(self):
        pares = [(0.5, f"Memorias/A{i}", f"Memorias/B{i}", "termo") for i in range(50)]
        with mock.patch.dict(os.environ, {"MEMORIA_DESCOBRIR": "1"}), mock.patch.object(N, "_pares_parecidos", lambda: pares), mock.patch.object(N, "_promover", lambda *a: None):
            with mock.patch.object(N, "DESC_DIA", 7):
                self.assertEqual(N.descobrir(), 7)
        with mock.patch.object(N, "MAX_DESC", 10):
            N._salvar()
            self.assertLessEqual(len(N._estado()["desc"]), 10)

    def test_homeostase_nao_limita_quantas_so_reescala_a_forca(self):
        e = N._estado()
        agora = time.time()
        for i in range(40):
            e["sin"][N._chave("Memorias/Centro", f"Memorias/V{i}")] = [1.0, agora]
        qtd = len(e["sin"])
        n = N._homeostase(e)
        self.assertEqual(n, 1)                                # só o «centro» passava de 14
        self.assertEqual(len(e["sin"]), qtd)                  # nenhuma sinapse some
        self.assertAlmostEqual(sum(v[0] for v in e["sin"].values()), N.HOMEOSTASE_CAP, delta=0.5)
        with mock.patch.object(N, "HOMEOSTASE_CAP", 0):       # CEREBRO_HOMEOSTASE=0: sem regulação nenhuma
            antes = {k: list(v) for k, v in e["sin"].items()}
            self.assertEqual(N._homeostase(e), 0)
            self.assertEqual(e["sin"], antes)


if __name__ == "__main__":
    unittest.main()
