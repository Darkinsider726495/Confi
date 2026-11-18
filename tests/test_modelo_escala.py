"""Modelo próprio pronto para escalar: cache KV (mesma resposta, mais rápido), continuar de onde parou, ajuste fino, chaves da API (só hash no disco)."""
import json, os, tempfile, threading, unittest, urllib.error, urllib.request
from pathlib import Path
from unittest import mock
import numpy as np
import _ambiente as E  # noqa: F401
from modelo.gpt import GPT
from modelo import treino as TR, chaves as K, api as API

TEXTO = ("Dono: o que é injeção de SQL?\nFRIDAY: É quando a entrada do usuário vira parte da consulta. A defesa é parametrizar.\n\n"
         "A FRIDAY estuda cibersegurança e guarda sinapses entre os assuntos que você conversa com ela. ") * 40


class CacheKV(unittest.TestCase):
    def test_mesma_resposta_com_e_sem_cache_inclusive_hibrido_e_passando_do_contexto(self):
        for R in (1, 2):
            m = GPT(vocab=120, ctx=16, d=16, cabecas=2, camadas=2, semente=4, repeticoes=R)
            self.assertEqual(m.gerar([3, 7, 9], n=40, temperatura=0, kv=False), m.gerar([3, 7, 9], n=40, temperatura=0, kv=True))


class TreinoLongo(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(dir=E.TMP))
        p = mock.patch.object(TR, "PASTA", self.pasta); p.start(); self.addCleanup(p.stop)
        self.conf = dict(vocab=320, ctx=24, d=16, cabecas=2, camadas=1, lote=4, lr=2e-3, relatorio=lambda *a: None, texto=TEXTO, amostra=None)

    def test_continua_de_onde_parou_com_o_otimizador(self):
        TR.treinar(passos=20, salvar_cada=10, **self.conf)
        o = np.load(self.pasta / "otimizador.npz")
        self.assertEqual(int(o["passo"]), 20)
        _, _, hist = TR.treinar(passos=30, continuar=True, **self.conf)
        self.assertEqual(len(hist), 10)                                         # só os 10 passos que faltavam
        self.assertEqual(int(np.load(self.pasta / "otimizador.npz")["passo"]), 30)

    def test_interromper_salva_o_ponto(self):
        from modelo.gpt import AdamW
        chamadas = {"n": 0}
        original = AdamW.passo
        def corta(self_, *a, **k):
            chamadas["n"] += 1
            if chamadas["n"] == 7:
                raise KeyboardInterrupt                                          # você apertou Ctrl+C durante o passo 7
            return original(self_, *a, **k)
        with mock.patch.object(AdamW, "passo", corta), self.assertRaises(KeyboardInterrupt):
            TR.treinar(passos=50, salvar_cada=0, **self.conf)
        self.assertEqual(int(np.load(self.pasta / "otimizador.npz")["passo"]), 6)  # Ctrl+C no passo 7: o 6 ficou salvo

    def test_ajuste_fino_parte_do_modelo_treinado(self):
        with self.assertRaises(ValueError):
            TR.treinar(passos=5, ajuste=True, **self.conf)                       # sem modelo ainda: recusa
        TR.treinar(passos=10, **self.conf)
        m, _, _ = TR.treinar(passos=10, ajuste=True, **self.conf)
        self.assertEqual(GPT.carregar(self.pasta / "modelo.npz").meta["fase"], "ajuste")


class Chaves(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(K, "ARQ", os.path.join(E.TMP, "chaves-teste.json")); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(K.ARQ) and os.remove(K.ARQ))

    def test_cria_valida_revoga_e_so_o_hash_vai_ao_disco(self):
        c = K.criar("celular")
        self.assertTrue(c.startswith("fri_"))
        self.assertEqual(K.valida(c), "celular")
        self.assertIsNone(K.valida(c + "x"))
        disco = open(K.ARQ, encoding="utf-8").read()
        self.assertNotIn(c, disco)                                               # a chave em si nunca fica gravada
        with self.assertRaises(ValueError):
            K.criar("celular")                                                   # nome ativo repetido
        self.assertTrue(K.revogar("celular"))
        self.assertIsNone(K.valida(c))
        self.assertEqual(K.listar()[0]["usos"], 1)
        with self.assertRaises(ValueError):
            K.criar("../x")

    def test_api_aceita_chave_com_nome_e_recusa_revogada(self):
        pasta = Path(tempfile.mkdtemp(dir=E.TMP))
        with mock.patch.object(TR, "PASTA", pasta), mock.patch.object(API, "PASTA", pasta), \
             mock.patch.object(API, "ARQ_TOKEN", os.path.join(E.TMP, "mestra-teste")):
            TR.treinar(vocab=300, ctx=16, d=16, cabecas=2, camadas=1, passos=5, lote=4, relatorio=lambda *a: None, texto=TEXTO, amostra=None)
            s = API.servir("127.0.0.1", 0)
            threading.Thread(target=s.serve_forever, daemon=True).start()
            self.addCleanup(s.server_close); self.addCleanup(s.shutdown)
            url = f"http://127.0.0.1:{s.server_address[1]}/v1/chat/completions"
            corpo = json.dumps({"messages": [{"role": "user", "content": "oi"}], "max_tokens": 5}).encode()
            c = K.criar("pc")
            r = urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers={"Authorization": f"Bearer {c}"}))
            self.assertEqual(r.status, 200)
            K.revogar("pc")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers={"Authorization": f"Bearer {c}"}))
            self.assertEqual(e.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
