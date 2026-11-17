import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "empacotar.py"
SPEC = importlib.util.spec_from_file_location("empacotar", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestEmpacotamentoSeguro(unittest.TestCase):
    def test_exclui_segredos_e_estado(self):
        for nome in (".env", ".env.local", ".token", "friday.db", "auditoria.jsonl", "diario.jsonl"):
            with self.subTest(nome=nome):
                self.assertTrue(MOD.excluded(Path("friday") / nome))

    def test_mantem_modelo_de_configuracao(self):
        self.assertFalse(MOD.excluded(Path(".env.example")))
        self.assertFalse(MOD.excluded(Path("servidor/.env.example")))

    def test_exclui_diretorios_de_memoria_e_ambiente(self):
        for nome in ("cofre/FRIDAY/nota.md", ".evolucao/diario.jsonl", ".venv/lib/python.py", "friday/__pycache__/x.pyc"):
            with self.subTest(nome=nome):
                self.assertTrue(MOD.excluded(Path(nome)))

    def test_mantem_codigo_e_documentacao(self):
        self.assertFalse(MOD.excluded(Path("friday/main.py")))
        self.assertFalse(MOD.excluded(Path("README.md")))


if __name__ == "__main__":
    unittest.main()
