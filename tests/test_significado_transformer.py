"""Motor Transformer (ONNX) da rede de significado: usa o modelo pré-treinado congelado e ajusta só o adaptador dela.

O modelo de teste é gerado aqui: mesmo formato do Transformer exportado (input_ids/attention_mask → last_hidden_state) e um
tokenizador de verdade (tokenizers), com vetores feitos à mão para «treino ≈ academia» e «joins ≈ sql». Assim o caminho todo roda.
"""
import hashlib, json, os, tempfile, time, unittest
from unittest import mock
import _ambiente as E  # noqa: F401
import broker as B, catalogo  # noqa: F401
import neuronios as N, significado as S, assimilacao as A
from test_assimilacao import Base, ia

try:
    import numpy as np, onnx, onnxruntime  # noqa: F401
    from onnx import helper, TensorProto, numpy_helper
    from tokenizers import Tokenizer, models, pre_tokenizers
    TEM = True
except ImportError:
    TEM = False

PALAVRAS = ["[UNK]", "treino", "academia", "musculacao", "joins", "sql", "prova", "musica", "praia"]


def criar_modelo(pasta, d=16, semente=3):
    rng = np.random.default_rng(semente)
    E = rng.normal(size=(len(PALAVRAS), d)).astype(np.float32)
    grupo_a, grupo_b = rng.normal(size=d), rng.normal(size=d)
    for i, w in enumerate(PALAVRAS):
        if w in ("treino", "academia", "musculacao"):
            E[i] = grupo_a * 3 + rng.normal(size=d) * .4
        if w in ("joins", "sql", "prova"):
            E[i] = grupo_b * 3 + rng.normal(size=d) * .4
    g = helper.make_graph(
        [helper.make_node("Gather", ["E", "input_ids"], ["last_hidden_state"], axis=0)], "mini_transformer",
        [helper.make_tensor_value_info("input_ids", TensorProto.INT64, [1, None]),
         helper.make_tensor_value_info("attention_mask", TensorProto.INT64, [1, None])],
        [helper.make_tensor_value_info("last_hidden_state", TensorProto.FLOAT, [1, None, d])],
        [numpy_helper.from_array(E, "E")])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 13)])
    m.ir_version = 8
    onnx.save(m, os.path.join(pasta, "model.onnx"))
    tok = Tokenizer(models.WordLevel({w: i for i, w in enumerate(PALAVRAS)}, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.save(os.path.join(pasta, "tokenizer.json"))
    with open(os.path.join(pasta, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"modelo": "teste", "prefixo": "", "limiar": 0.7}, f)


@unittest.skipUnless(TEM, "onnxruntime/tokenizers/onnx não instalados")
class Transformer(Base):
    def setUp(self):
        super().setUp()
        self.mod = tempfile.mkdtemp(prefix="tr-", dir=E.TMP)
        criar_modelo(self.mod)
        p = mock.patch.dict(os.environ, {"SIGNIFICADO_TRANSFORMER": self.mod})
        p.start(); self.addCleanup(p.stop)
        S._tr.update(dir=None)
        self.addCleanup(lambda: S._tr.update(dir=None, sess=None))
        self.t = time.time() - 100_000

    def hash_modelo(self):
        return hashlib.sha256(open(os.path.join(self.mod, "model.onnx"), "rb").read()).hexdigest()

    def topicos(self, *nomes):
        for n in nomes:
            self.t += A.CONTEXTO_S + 60
            N._ult.update(chave=None, t=0.0)
            with ia(n.lower()):
                A.assimilar("fala", f"falei de {n}", self.t)

    def test_usa_o_transformer_quando_ele_existe(self):
        self.assertEqual(S.motor(), "transformer")
        self.assertEqual(S.limiar(), 0.7)
        self.assertGreater(S.parecenca("treino", "academia"), S.parecenca("treino", "joins") + 0.5)

    def test_assunto_novo_se_liga_pelo_transformer(self):
        self.topicos("Academia", "Joins")
        self.topicos("Musculacao")
        e = N._estado()
        self.assertGreater(N._peso(e, N._chave("Topicos/Musculacao", "Topicos/Academia")), 0)
        self.assertEqual(N._peso(e, N._chave("Topicos/Musculacao", "Topicos/Joins")), 0)

    def test_feedback_treina_o_adaptador_e_nao_mexe_no_transformer(self):
        antes_pesos = self.hash_modelo()
        self.topicos("Treino", "Academia")
        antes = S.parecenca("treino", "academia")
        S.tratar("treino não tem nada a ver com academia")
        self.assertGreater(S.ajustar(epocas=60), 0)
        self.assertLess(S.parecenca("treino", "academia"), antes - 0.05)
        self.assertEqual(self.hash_modelo(), antes_pesos)                         # o pré-treinado fica congelado
        self.assertTrue(self.base(".cerebro", "significado_adaptador.npz").exists())   # o que é dela fica no cofre

    def test_sinapse_aproxima_pelo_adaptador(self):
        self.topicos("Treino", "Joins")
        antes = S.parecenca("treino", "joins")
        with N._trava:
            N._estado()["sin"][N._chave("Topicos/Treino", "Topicos/Joins")] = [4.0, time.time()]
        S.ajustar(epocas=60)
        self.assertGreater(S.parecenca("treino", "joins"), antes + 0.05)

    def test_adaptador_volta_do_cofre_depois_de_reiniciar(self):
        self.topicos("Treino", "Academia")
        S.tratar("treino não tem nada a ver com academia")
        S.ajustar(epocas=60)
        depois = S.parecenca("treino", "academia")
        S._tr.update(dir=None)                                                   # «reinicia» o processo
        self.assertAlmostEqual(S.parecenca("treino", "academia"), depois, places=4)

    def test_termo_desconhecido_nao_tem_significado_nem_vira_igual_a_outro(self):
        self.assertIsNone(S.vetor("xablau desconhecido"))
        self.assertIsNone(S.parecenca("xablau", "zumbaia"))                    # dois «[UNK]» não podem parecer 100% iguais
        self.assertIsNotNone(S.vetor("Treino"))                                # maiúscula não atrapalha

    def test_sem_o_modelo_volta_para_a_rede_propria(self):
        with mock.patch.dict(os.environ, {"SIGNIFICADO_TRANSFORMER": tempfile.mkdtemp(dir=E.TMP)}):
            S._tr.update(dir=None)
            self.assertNotEqual(S.motor(), "transformer")


if __name__ == "__main__":
    unittest.main()
