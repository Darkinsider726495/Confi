"""O script de conexão com a Groq: grava só as linhas certas, nunca mostra a chave, recusa lixo e não quebra o resto do .env."""
import io, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import conectar_groq as CG

CHAVE = "gsk_" + "A1b2C3d4" * 6        # chave falsa, só para o teste


class Conectar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = Path(self.dir.name) / ".env"
        self.addCleanup(self.dir.cleanup)

    def rodar(self, chave, ok=(True, "conectada.")):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(CG, "testar", return_value=ok):
            code = CG.main(entrada=lambda _p: chave, env=self.env)
        return code, out.getvalue()

    def test_grava_so_as_linhas_da_groq_e_mantem_o_resto(self):
        self.env.write_text("OUTRA=1\nIA_PROVEDOR=anthropic\n# GROQ_API_KEY=\nANTHROPIC_API_KEY=sk-ant-x\n", encoding="utf-8")
        code, saida = self.rodar(CHAVE)
        self.assertEqual(code, 0)
        txt = self.env.read_text(encoding="utf-8")
        self.assertIn("IA_PROVEDOR=groq\n", txt)
        self.assertIn(f"GROQ_API_KEY={CHAVE}\n", txt)
        self.assertIn("OUTRA=1\n", txt)
        self.assertIn("ANTHROPIC_API_KEY=sk-ant-x\n", txt)
        self.assertEqual(txt.count("IA_PROVEDOR="), 1)

    def test_nunca_imprime_a_chave(self):
        _, saida = self.rodar(CHAVE)
        self.assertNotIn(CHAVE, saida)
        self.assertNotIn(CHAVE[:20], saida)
        self.assertIn("…" + CHAVE[-4:], saida)

    def test_arquivo_fica_so_para_o_dono(self):
        self.rodar(CHAVE)
        self.assertEqual(os.stat(self.env).st_mode & 0o777, 0o600)

    def test_recusa_o_que_nao_e_chave_e_nao_grava_nada(self):
        self.env.write_text("OUTRA=1\n", encoding="utf-8")
        for lixo in ("", "sk-ant-abc", "gsk_curta", "gsk_tem espaço aqui 1234567890123", "senha123"):
            code, _ = self.rodar(lixo)
            self.assertEqual(code, 2, lixo)
        self.assertEqual(self.env.read_text(encoding="utf-8"), "OUTRA=1\n")

    def test_sem_env_cria_a_partir_do_exemplo(self):
        (Path(self.dir.name) / ".env.example").write_text("# exemplo\nIA_PROVEDOR=groq\nGROQ_API_KEY=\nLLM_MODEL=x\n", encoding="utf-8")
        self.rodar(CHAVE)
        txt = self.env.read_text(encoding="utf-8")
        self.assertIn("LLM_MODEL=x", txt)
        self.assertIn(f"GROQ_API_KEY={CHAVE}", txt)

    def test_conexao_falhou_avisa_sem_mostrar_a_chave(self):
        code, saida = self.rodar(CHAVE, ok=(False, "401 chave inválida"))
        self.assertEqual(code, 1)
        self.assertIn("Não consegui", saida)
        self.assertNotIn(CHAVE, saida)


if __name__ == "__main__":
    unittest.main()
