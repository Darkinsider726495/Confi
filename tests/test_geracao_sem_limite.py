"""Geração sem limite: o fluxo de tokens não acaba sozinho (janela deslizante), a API manda o texto ao vivo (SSE) e o modelo próprio não gasta cota."""
import json, os, tempfile, threading, unittest, urllib.request
from itertools import islice
from pathlib import Path
from unittest import mock
import numpy as np
import _ambiente as E  # noqa: F401
from modelo.gpt import GPT
from modelo import treino as TR, api as API, chaves as K

TEXTO = ("Dono: o que é phishing?\nFRIDAY: É uma mensagem falsa para roubar dados. Desconfie de links.\n\n"
         "A FRIDAY estuda cibersegurança todos os dias e conversa com o dono sobre redes e senhas fortes. ") * 40


class SemLimite(unittest.TestCase):
    def test_fluxo_vai_muito_alem_do_contexto_sem_quebrar(self):
        m = GPT(vocab=50, ctx=16, d=16, cabecas=2, camadas=1, semente=2)
        toks = list(islice(m.fluxo([1, 2, 3], temperatura=0.9, rng=np.random.default_rng(0)), 500))   # 30× o contexto
        self.assertEqual(len(toks), 500)
        self.assertTrue(all(0 <= t < 50 for t in toks))

    def test_gerar_sem_n_para_so_quando_mandam(self):
        m = GPT(vocab=50, ctx=16, d=16, cabecas=2, camadas=1, semente=2)
        out = m.gerar([1], n=None, temperatura=0.9, parar=lambda novos: len(novos) >= 77, rng=np.random.default_rng(1))
        self.assertEqual(len(out), 77)

    def test_modelo_proprio_nao_gasta_a_cota_diaria(self):
        import cerebro as C
        with mock.patch.dict(os.environ, {"IA_PROVEDOR": "propria"}), mock.patch.object(C.F, "contar_llm", return_value=False) as cota, \
             mock.patch.object(C, "_propria", return_value="resposta do modelo dela"):
            self.assertEqual(C._responder("oi"), "resposta do modelo dela")
        cota.assert_not_called()


class ApiAoVivo(unittest.TestCase):
    def test_fluxo_sse_chega_em_pedacos_e_termina(self):
        pasta = Path(tempfile.mkdtemp(dir=E.TMP))
        with mock.patch.object(TR, "PASTA", pasta), mock.patch.object(API, "PASTA", pasta), \
             mock.patch.object(K, "ARQ", os.path.join(E.TMP, "chaves-fluxo.json")), mock.patch.object(API, "ARQ_TOKEN", os.path.join(E.TMP, "mestra-fluxo")):
            TR.treinar(vocab=320, ctx=24, d=16, cabecas=2, camadas=1, passos=10, lote=4, relatorio=lambda *a: None, texto=TEXTO, amostra=None)
            s = API.servir("127.0.0.1", 0)
            threading.Thread(target=s.serve_forever, daemon=True).start()
            self.addCleanup(s.server_close); self.addCleanup(s.shutdown)
            chave = K.criar("teste")
            corpo = json.dumps({"messages": [{"role": "user", "content": "oi"}], "stream": True, "max_tokens": 60}).encode()
            r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{s.server_address[1]}/v1/chat/completions", data=corpo,
                                                              headers={"Authorization": f"Bearer {chave}"}), timeout=60)
            self.assertIn("text/event-stream", r.headers["Content-Type"])
            linhas = [l for l in r.read().decode().split("\n\n") if l.startswith("data: ")]
            self.assertEqual(linhas[-1], "data: [DONE]")
            for l in linhas[:-1]:
                self.assertEqual(json.loads(l[6:])["object"], "chat.completion.chunk")
            texto = "".join(json.loads(l[6:])["choices"][0]["delta"]["content"] for l in linhas[:-1])
            self.assertNotIn("\nDono:", texto)                                    # para quando o «Dono» falaria


if __name__ == "__main__":
    unittest.main()
