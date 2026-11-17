"""Testes da fila local de candidatos, sem API e sem modificar arquivos reais."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday import evolucao as E
from friday import gerador_local as G


class GeradorLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-gerador-local-")
        self.root = Path(self.tmp.name) / "project"
        self.friday = self.root / "friday"
        self.tests = self.root / "tests"
        self.friday.mkdir(parents=True)
        self.tests.mkdir()
        (self.friday / "memoria.py").write_text("def valor():\n    return 1\n", encoding="utf-8")
        self.state = self.root / ".evolucao"
        self.patches = [
            patch.object(E, "BASE", self.root),
            patch.object(E, "FRIDAY_DIR", self.friday),
            patch.object(E, "STATE_DIR", self.state),
            patch.object(E, "BACKUP_DIR", self.state / "backups"),
            patch.object(E, "JOURNAL", self.state / "diario.jsonl"),
            patch.object(G, "RAIZ", self.state / "candidatos"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_substituicao_literal_cria_candidato_em_quarentena(self):
        candidato = G.gerar_substituicao("friday/memoria.py", "return 1", "return 2", "teste local")
        self.assertTrue(candidato["id"].startswith("cand-"))
        self.assertEqual(candidato["estado"], "aguardando_testes")
        manifesto, codigo = G.obter(candidato["id"])
        self.assertEqual(manifesto["alvo"], "friday/memoria.py")
        self.assertIn("return 2", codigo)
        self.assertIn(candidato["id"], [x["id"] for x in G.listar()])
        # A fila não ativa o candidato sozinha.
        self.assertIn("return 1", (self.friday / "memoria.py").read_text(encoding="utf-8"))

    def test_ambiguidade_nao_gera_candidato(self):
        (self.friday / "memoria.py").write_text(
            "def valor():\n    return 1\n\ndef outra():\n    return 1\n", encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            G.gerar_substituicao("friday/memoria.py", "return 1", "return 0")
        self.assertEqual(G.listar(), [])

    def test_alvo_protegido_nao_entra_na_fila(self):
        with self.assertRaises(PermissionError):
            G.gerar_substituicao("friday/evolucao.py", "x", "y")

    def test_hash_alterado_bloqueia_leitura(self):
        candidato = G.gerar_substituicao("friday/memoria.py", "return 1", "return 2")
        pasta = G.RAIZ / candidato["id"]
        (pasta / "candidato.py").chmod(0o600)
        (pasta / "candidato.py").write_text("def valor():\n    return 999\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            G.obter(candidato["id"])


if __name__ == "__main__":
    unittest.main()
