"""GRU da rotina: o gradiente está certo, ela aprende uma rotina de verdade, só confia quando vence o jeito simples e só sugere."""
import json, time, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import rotina as R, conversa as CONV
from test_assimilacao import Base

try:
    import numpy as np
except ImportError:
    np = None

DIA = 86400


def registrar(base, eventos):
    arq = base(".cerebro", "atividades.jsonl")
    arq.parent.mkdir(parents=True, exist_ok=True)
    with open(arq, "a", encoding="utf-8") as f:
        for t, origem, assuntos in eventos:
            r = {"t": t, "origem": origem, "tipo": "assimilacao" if assuntos else "fala", "saliencia": 0.5}
            if assuntos:
                r["assuntos"] = assuntos
            f.write(json.dumps(r) + "\n")


def meia_noite(t):
    return time.mktime(time.localtime(t)[:3] + (0, 0, 0, 0, 0, -1))


def rotina_sintetica(dias, fim):
    """Dia sim, dia não: 8h fala de Treino e, nesses dias, às 20h fala de SQL. Pela hora sozinha, 20h é 50%; pela sequência do dia, dá
    para saber. É aí que a memória temporal da GRU vence o «jeito simples». Termina em `fim`."""
    ev = []
    for d in range(dias):
        dia0 = meia_noite(fim) - (dias - 1 - d) * DIA
        ev.append((dia0 + 13 * 3600 + 300, "fala", ["Almoço"]))
        if (dias - 1 - d) % 2 == 0:                   # hoje (o último dia) é dia de treino
            ev.append((dia0 + 8 * 3600 + 300, "fala", ["Treino"]))
            ev.append((dia0 + 20 * 3600 + 300, "fala", ["SQL"]))
    return ev


@unittest.skipUnless(np is not None, "sem NumPy")
class Gradiente(unittest.TestCase):
    def test_retropropagacao_no_tempo_confere_com_diferenca_finita(self):
        rng = np.random.default_rng(0)
        p = R.nova_rede(4, 3, oculto=5)
        for k in p:
            p[k] = p[k] + rng.normal(size=p[k].shape) * 0.3
        xs = rng.normal(size=(2, 6, 4))
        ys = (rng.random((2, 3)) > 0.5).astype(float)
        _, g = R.perda_e_gradientes(p, xs, ys)
        for k in p:
            for idx in [tuple(rng.integers(0, s) for s in p[k].shape) for _ in range(3)]:
                v = p[k][idx]
                p[k][idx] = v + 1e-5; mais, _ = R.perda_e_gradientes(p, xs, ys)
                p[k][idx] = v - 1e-5; menos, _ = R.perda_e_gradientes(p, xs, ys)
                p[k][idx] = v
                self.assertAlmostEqual(g[k][idx], (mais - menos) / 2e-5, places=4, msg=k)


@unittest.skipUnless(np is not None, "sem NumPy")
class Rotina(Base):
    def setUp(self):
        super().setUp()
        R._mod.update(v=None)
        self.addCleanup(lambda: R._mod.update(v=None))
        self.fim = meia_noite(time.time()) + 19 * 3600 + 1800     # hoje, 19h30 (o que vem depois ainda não aconteceu)

    def test_com_pouco_dado_ela_espera(self):
        registrar(self.base, rotina_sintetica(3, self.fim))
        r = R.treinar(self.fim)
        self.assertFalse(r["ok"])
        self.assertIn("7 dias", r["motivo"])
        self.assertIn("juntando dados", R.tratar("como é a minha rotina?"))
        self.assertIsNone(R.sugestao())

    def test_aprende_a_rotina_e_vence_o_jeito_simples(self):
        registrar(self.base, rotina_sintetica(14, self.fim))
        r = R.treinar(self.fim)
        self.assertTrue(r["ok"], r)
        self.assertIn("assunto:SQL", r["rotulos"])
        self.assertTrue(r["confiavel"], r)
        self.assertTrue(self.base(".cerebro", "rotina_gru.npz").exists())    # o modelo fica no cofre
        prev = dict(R.previsao(self.fim))                    # hoje treinou → às 20h vem o SQL (a hora sozinha diria 50%)
        self.assertGreater(prev["assunto:SQL"], 0.7, prev)
        self.assertGreater(prev["assunto:SQL"], prev["assunto:Treino"])

    def test_registro_so_tem_rotulos_nunca_frases(self):
        registrar(self.base, rotina_sintetica(14, self.fim))
        R.treinar(self.fim, epocas=5)
        d = np.load(str(self.base(".cerebro", "rotina_gru.npz")))
        meta = json.loads(str(d["meta"]))
        self.assertTrue(all(r == "fala" or r.startswith("assunto:") or r in ("visao", "maos") for r in meta["rotulos"]))

    def test_sem_confianca_nao_sugere(self):
        registrar(self.base, rotina_sintetica(14, self.fim))
        R.treinar(self.fim)
        self.assertIsNotNone(R.sugestao(self.fim))                          # confiável: às 19h30 ela se adiantaria
        p, meta = R.carregar()
        meta["confiavel"] = False
        self.assertIsNone(R.sugestao(self.fim))
        self.assertIn("ainda não acerto", R.tratar("o que você acha que eu vou fazer agora?"))

    def test_conversa_se_adianta_uma_vez_e_so_sugere(self):
        registrar(self.base, rotina_sintetica(14, self.fim))
        R.treinar(self.fim)
        agora = self.fim
        l = CONV.preparar_lembranca(agora)
        self.assertIsNotNone(l)
        self.assertIn("sql", l["texto"].lower())
        self.assertIn("Quer que eu prepare", l["texto"])
        CONV._e().setdefault("lembradas", {})[l["chave"]] = agora
        l2 = CONV.preparar_lembranca(agora + 600)
        self.assertTrue(l2 is None or not l2["chave"].startswith("R:"))   # no mesmo dia, não repete

    def test_treino_automatico_no_maximo_uma_vez_por_dia(self):
        registrar(self.base, rotina_sintetica(14, self.fim))
        R._treino["t"] = 0.0
        with mock.patch.object(R, "treinar", return_value={"ok": True}) as t:
            R.treinar_se_for_hora(self.fim)
            R.treinar_se_for_hora(self.fim + 3600)
            R.treinar_se_for_hora(self.fim + R.TREINO_A_CADA_S + 1)
        self.assertEqual(t.call_count, 2)

    def test_frase_comum_nao_e_comando(self):
        self.assertIsNone(R.tratar("minha rotina hoje foi corrida"))

    def test_nao_ha_ferramenta_da_ia_para_a_rotina(self):
        self.assertFalse([n for n in B.FERRAMENTAS if "rotina" in n.lower()] if hasattr(B, "FERRAMENTAS") else [])


class SemNumpy(Base):
    def test_sem_numpy_responde_sem_erro(self):
        with mock.patch.object(R, "np", None):
            self.assertIn("NumPy", R.tratar("como é a minha rotina?"))
            self.assertFalse(R.treinar()["ok"])
            self.assertIsNone(R.sugestao())


if __name__ == "__main__":
    unittest.main()
