"""Modelo próprio: tokenizador BPE (ida e volta), GPT em NumPy (gradiente conferido, aprende), API própria (chave, formato) e a FRIDAY usando ele."""
import json, os, tempfile, threading, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
import numpy as np
import _ambiente as E  # noqa: F401
from modelo.tokenizador import BPETokenizer
from modelo.gpt import GPT, AdamW
from modelo import treino as TR

TEXTO = ("A FRIDAY estuda cibersegurança todos os dias. Injeção de SQL acontece quando a entrada do usuário vira parte da consulta. "
         "A defesa é usar consultas parametrizadas e validar a entrada. XSS acontece quando o site mostra texto do usuário sem escapar. ") * 40


class Tokenizador(unittest.TestCase):
    def test_ida_e_volta_com_acento_e_emoji_e_compressao(self):
        tk = BPETokenizer(600).train(TEXTO)
        for s in ("Injeção de SQL e XSS 😀", "texto que nunca viu: ççç ãõ 123", ""):
            self.assertEqual(tk.decode(tk.encode(s)), s)
        self.assertLess(len(tk.encode(TEXTO)), len(TEXTO.encode()) / 2)        # junta pares: bem menos tokens que bytes

    def test_salva_e_carrega_igual(self):
        tk = BPETokenizer(400).train(TEXTO)
        arq = os.path.join(E.TMP, "tok.json")
        tk.salvar(arq)
        tk2 = BPETokenizer.carregar(arq)
        self.assertEqual(tk.encode(TEXTO[:300]), tk2.encode(TEXTO[:300]))

    def test_texto_curto_nao_quebra(self):
        self.assertEqual(len(BPETokenizer(300).train("a")), 256)               # o bug do max() vazio do código original


class Gpt(unittest.TestCase):
    def test_gradiente_confere_com_diferenca_finita(self):
        m = GPT(vocab=11, ctx=6, d=8, cabecas=2, camadas=2, dtype=np.float64, semente=3)
        rng = np.random.default_rng(0)
        for k in m.p:
            m.p[k] = m.p[k] + rng.normal(size=m.p[k].shape) * 0.1
        idx, alvo = rng.integers(0, 11, (2, 5)), rng.integers(0, 11, (2, 5))
        _, g = m.perda_e_gradientes(idx, alvo)
        for k in m.p:
            i = tuple(rng.integers(0, s) for s in m.p[k].shape)
            v = m.p[k][i]
            m.p[k][i] = v + 1e-6; a, _ = m.perda_e_gradientes(idx, alvo)
            m.p[k][i] = v - 1e-6; b, _ = m.perda_e_gradientes(idx, alvo)
            m.p[k][i] = v
            num = (a - b) / 2e-6
            self.assertAlmostEqual(g[k][i], num, delta=1e-5 + 1e-4 * abs(num), msg=k)

    def test_hibrido_bptt_na_profundidade_gradiente_certo_e_mesmos_parametros(self):
        normal = GPT(vocab=11, ctx=6, d=8, cabecas=2, camadas=2, dtype=np.float64, semente=3)
        m = GPT(vocab=11, ctx=6, d=8, cabecas=2, camadas=2, dtype=np.float64, semente=3, repeticoes=3)
        self.assertEqual(m.n_parametros(), normal.n_parametros())                 # pensa 3x mais fundo com os MESMOS pesos
        rng = np.random.default_rng(0)
        for k in m.p:
            m.p[k] = m.p[k] + rng.normal(size=m.p[k].shape) * 0.1
        idx, alvo = rng.integers(0, 11, (2, 5)), rng.integers(0, 11, (2, 5))
        _, g = m.perda_e_gradientes(idx, alvo)
        for k in m.p:
            i = tuple(rng.integers(0, s) for s in m.p[k].shape)
            v = m.p[k][i]
            m.p[k][i] = v + 1e-5; a, _ = m.perda_e_gradientes(idx, alvo)
            m.p[k][i] = v - 1e-5; b, _ = m.perda_e_gradientes(idx, alvo)
            m.p[k][i] = v
            self.assertAlmostEqual(g[k][i], (a - b) / 2e-5, delta=1e-7, msg=k)
        arq = os.path.join(E.TMP, "hib.npz")
        m.salvar(arq)
        self.assertEqual(GPT.carregar(arq).cfg["repeticoes"], 3)

    def test_aprende_uma_sequencia(self):
        m = GPT(vocab=8, ctx=8, d=16, cabecas=2, camadas=1, semente=1)
        opt = AdamW(m.p, lr=1e-2)
        x = np.array([[1, 2, 3, 4, 5, 6, 7, 1]]); y = np.array([[2, 3, 4, 5, 6, 7, 1, 2]])
        primeira = None
        for _ in range(150):
            perda, g = m.perda_e_gradientes(x, y)
            primeira = primeira or perda
            opt.passo(m.p, g)
        self.assertLess(perda, primeira / 5)
        self.assertEqual(m.gerar([1, 2, 3], n=3, temperatura=0), [4, 5, 6])    # decorou a sequência

    def test_salva_e_carrega(self):
        m = GPT(vocab=20, ctx=8, d=8, cabecas=2, camadas=1)
        arq = os.path.join(E.TMP, "m.npz")
        m.salvar(arq)
        m2 = GPT.carregar(arq)
        np.testing.assert_allclose(m.logits([[1, 2, 3]]), m2.logits([[1, 2, 3]]), rtol=1e-5)


class TreinoEApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = Path(tempfile.mkdtemp(dir=E.TMP))
        cls.p = mock.patch.object(TR, "PASTA", cls.pasta); cls.p.start()
        from modelo import api
        cls.p2 = mock.patch.object(api, "PASTA", cls.pasta); cls.p2.start()
        cls.p3 = mock.patch.object(api, "ARQ_TOKEN", os.path.join(E.TMP, "modelo-token-teste")); cls.p3.start()
        TR.treinar(vocab=400, ctx=32, d=32, cabecas=2, camadas=1, passos=40, lote=4, lr=2e-3, relatorio=lambda *a: None, texto=TEXTO)

    @classmethod
    def tearDownClass(cls):
        cls.p.stop(); cls.p2.stop(); cls.p3.stop()

    def test_treino_salva_e_a_friday_usa_o_modelo_proprio(self):
        import cerebro as C
        self.assertTrue((self.pasta / "modelo.npz").exists())
        with mock.patch.dict(os.environ, {"IA_PROVEDOR": "propria", "PROPRIA_URL": ""}):
            r = C._nuvem([{"role": "user", "content": "o que é injeção de SQL?"}], None)
        self.assertIsInstance(r, str)
        self.assertTrue(r)

    def test_api_propria_com_chave_e_formato_de_chat(self):
        from modelo import api
        s = api.servir("127.0.0.1", 0)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        self.addCleanup(s.server_close); self.addCleanup(s.shutdown)
        url = f"http://127.0.0.1:{s.server_address[1]}/v1/chat/completions"
        corpo = json.dumps({"messages": [{"role": "user", "content": "oi"}], "max_tokens": 10}).encode()
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers={"Authorization": "Bearer errada"}))
        self.assertEqual(c.exception.code, 401)
        r = json.loads(urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers={"Authorization": f"Bearer {api.token()}"})).read())
        self.assertEqual(r["object"], "chat.completion")
        self.assertIn("content", r["choices"][0]["message"])

    def test_nada_de_biblioteca_ou_servico_de_terceiros(self):
        raiz = Path(__file__).resolve().parents[1] / "friday" / "modelo"
        fonte = "".join(f.read_text(encoding="utf-8") for f in raiz.glob("*.py"))
        for proibido in ("import torch", "tensorflow", "transformers", "openai", "groq", "anthropic", "requests"):
            self.assertNotIn(proibido, fonte, proibido)


if __name__ == "__main__":
    unittest.main()
