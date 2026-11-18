"""BPE contínuo: aprende tokens novos com texto novo SEM mudar os números dos antigos; o modelo ganha as linhas novas e continua igual no que sabia."""
import json, os, tempfile, time, unittest
from pathlib import Path
from unittest import mock
import numpy as np
import _ambiente as E  # noqa: F401
from modelo.tokenizador import BPETokenizer
from modelo.gpt import GPT
from modelo import continuo as C, treino as TR

BASE = "a memória da FRIDAY guarda sinapses entre os assuntos que você conversa com ela todos os dias. " * 30
NOVO = "injeção de SQL e cross site scripting são vulnerabilidades web; ransomware sequestra arquivos. " * 30


class BpeContinuo(unittest.TestCase):
    def test_tokens_antigos_nunca_mudam_e_aprende_os_novos(self):
        tk = BPETokenizer(400).train(BASE)
        antes = dict(tk.vocab)
        ids_antes = tk.encode(BASE[:200])
        novos = tk.atualizar(NOVO, crescer=40)
        self.assertTrue(novos)
        for i, b in antes.items():
            self.assertEqual(tk.vocab[i], b)                       # nenhum token antigo mudou
        self.assertTrue(any("SQL" in t or "ransom" in t or "vulnera" in t for t in novos), novos)
        self.assertLess(len(tk.encode(NOVO)), len(BPETokenizer(400).train(BASE).encode(NOVO)))   # o texto novo fica mais curto
        self.assertEqual(tk.decode(tk.encode(NOVO + BASE)), NOVO + BASE)
        self.assertEqual(tk.encode(BASE[:200])[:3], ids_antes[:3])

    def test_contagem_vai_e_volta_do_disco(self):
        tk = BPETokenizer(300).train(BASE)
        arq = os.path.join(E.TMP, "tok-cont.json")
        tk.salvar(arq)
        tk2 = BPETokenizer.carregar(arq)
        self.assertEqual(sum(tk2.contagem.values()), sum(tk.contagem.values()))
        self.assertEqual(tk2.atualizar(NOVO, crescer=10), tk.atualizar(NOVO, crescer=10))

    def test_modelo_ganha_linhas_novas_sem_mudar_as_antigas(self):
        m = GPT(vocab=300, ctx=8, d=8, cabecas=2, camadas=1)
        velho = m.p["wte"].copy()
        self.assertEqual(m.expandir_vocab(340), 40)
        np.testing.assert_array_equal(m.p["wte"][:300], velho)
        self.assertEqual(m.logits([[1, 2]]).shape[-1], 340)

    def test_rodadas_em_laco_leem_so_o_texto_novo(self):
        pasta = Path(tempfile.mkdtemp(dir=E.TMP))
        corpus = Path(tempfile.mkdtemp(dir=E.TMP))
        (corpus / "modelos_ia" / "corpus").mkdir(parents=True)
        (corpus / "modelos_ia" / "corpus" / "a.txt").write_text(BASE, encoding="utf-8")
        with mock.patch.object(C, "PASTA", pasta), mock.patch.object(C, "ESTADO", pasta / "bpe_continuo.json"), mock.patch.object(C, "RAIZ", corpus), \
             mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            r1 = C.rodada(crescer=30)
            self.assertGreater(r1["vocab"], 256)
            r2 = C.rodada(crescer=30)
            self.assertEqual(r2["texto"], 0)                          # nada mudou: não relê
            time.sleep(0.01)
            (corpus / "modelos_ia" / "corpus" / "b.txt").write_text(NOVO, encoding="utf-8")
            r3 = C.rodada(crescer=30)
            self.assertGreater(r3["texto"], 0)
            self.assertTrue(r3["novos"])
            ditos = []
            C.laco(intervalo=0, relatorio=ditos.append, dormir=lambda s: None, vezes=2)
            self.assertEqual(sum(1 for d in ditos if d.startswith("rodada")), 2)


if __name__ == "__main__":
    unittest.main()
