"""Testes do promotor com projeto temporário: não alteram a FRIDAY do desenvolvedor."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from friday import evolucao as E


class ProjetoTemporario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="test-evolucao-")
        self.root = Path(self.tmp.name) / "projeto"
        self.friday = self.root / "friday"
        self.tests = self.root / "tests"
        self.friday.mkdir(parents=True)
        self.tests.mkdir()
        (self.friday / "memoria.py").write_text("def valor():\n    return 1\n", encoding="utf-8")
        generated = self.friday / "generated"
        generated.mkdir()
        (generated / "__init__.py").write_text('"""Módulos gerados isolados da FRIDAY."""\n', encoding="utf-8")
        (self.tests / "test_valor.py").write_text(
            "from friday.memoria import valor\n\ndef test_valor():\n    assert valor() == 1\n",
            encoding="utf-8",
        )
        self.state = self.root / ".evolucao"
        self.backups = self.state / "backups"
        self.journal = self.state / "diario.jsonl"
        self.patches = [
            patch.object(E, "BASE", self.root),
            patch.object(E, "FRIDAY_DIR", self.friday),
            patch.object(E, "STATE_DIR", self.state),
            patch.object(E, "BACKUP_DIR", self.backups),
            patch.object(E, "JOURNAL", self.journal),
        ]
        for p in self.patches:
            p.start()
        self.cmd = [[sys.executable, "-m", "pytest", "-q", "tests"]]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def fonte(self):
        return (self.friday / "memoria.py").read_text(encoding="utf-8")

    def test_bloqueia_modulos_protegidos_e_caminhos_invalidos(self):
        for nome in ("friday/broker.py", "friday/evolucao.py", "friday/mae.py", "friday/main.py"):
            with self.assertRaises(PermissionError):
                E._alvo(nome)
        for nome in ("../friday/memoria.py", "/tmp/memoria.py", "friday/sub/memoria.py"):
            with self.assertRaises(ValueError):
                E._alvo(nome)

    def test_rejeita_sintaxe_invalida_antes_de_rodar_testes(self):
        with self.assertRaises(SyntaxError):
            E.promover("friday/memoria.py", "def quebrado(:", self.cmd)

    def test_rejeita_nova_capacidade_sensivel(self):
        with self.assertRaises(PermissionError):
            E.validar_candidato("friday/memoria.py", "import subprocess\ndef valor():\n    return 1\n")

    def test_rejeita_nova_operacao_de_arquivo_no_candidato(self):
        candidato = self.fonte() + "\nimport os\nos.remove('/tmp/nao-apagar')\n"
        with self.assertRaises(PermissionError):
            E.validar_candidato("friday/memoria.py", candidato)

    def test_comando_inline_e_modulo_arbitrario_sao_bloqueados(self):
        with self.assertRaises(ValueError):
            E._validar_comandos([[sys.executable, "-c", "print('x')"]])
        with self.assertRaises(ValueError):
            E._validar_comandos([[sys.executable, "-m", "http.server"]])

    def test_baseline_com_falha_nao_altera_arquivo(self):
        antes = (self.friday / "memoria.py").read_bytes()
        with patch.object(E, "_executar_testes", return_value=(False, [{"codigo": 1}])):
            r = E.promover("friday/memoria.py", self.fonte() + "\n# candidato\n", self.cmd)
        self.assertEqual(r["status"], "bloqueado")
        self.assertEqual((self.friday / "memoria.py").read_bytes(), antes)
        self.assertFalse(self.backups.exists())

    def test_falha_no_staging_nao_toca_arquivo_ativo(self):
        antes = (self.friday / "memoria.py").read_bytes()
        with patch.object(E, "_executar_testes", side_effect=[
            (True, [{"codigo": 0}]), (False, [{"codigo": 1, "saida": "falha simulada"}]),
        ]):
            r = E.promover("friday/memoria.py", self.fonte() + "\n# candidato\n", self.cmd)
        self.assertEqual(r["status"], "rejeitado")
        self.assertEqual((self.friday / "memoria.py").read_bytes(), antes)
        self.assertFalse(self.backups.exists())

    def test_falha_pos_promocao_restaura_bytes_originais(self):
        antes = (self.friday / "memoria.py").read_bytes()
        with patch.object(E, "_executar_testes", side_effect=[
            (True, [{"codigo": 0}]), (True, [{"codigo": 0}]), (False, [{"codigo": 1, "saida": "falha pos"}]),
        ]):
            r = E.promover("friday/memoria.py", self.fonte() + "\n# candidato\n", self.cmd)
        self.assertEqual(r["status"], "revertido")
        self.assertEqual((self.friday / "memoria.py").read_bytes(), antes)
        backup = self.root / r["backup"]
        self.assertEqual(backup.read_bytes(), antes)
        manifest = json.loads((backup.parent / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["sha256"], hashlib.sha256(antes).hexdigest())

    def test_promove_com_sucesso_e_cria_backup_read_only(self):
        original = self.fonte()
        novo = original + "\n# candidato aceito\n"
        r = E.promover("friday/memoria.py", novo, self.cmd)
        self.assertEqual(r["status"], "promovido", r)
        self.assertEqual(self.fonte(), novo)
        backup = self.root / r["backup"]
        self.assertEqual(backup.read_text(encoding="utf-8"), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o400)
        self.assertEqual((self.root / r["backup"]).parent.stat().st_mode & 0o777, 0o500)
        self.assertEqual(len(E.historico()), 1)

    def test_candidato_com_defeito_e_rejeitado_com_teste_real(self):
        original = self.fonte()
        candidato = "def valor():\n    return 2\n"
        r = E.promover("friday/memoria.py", candidato, self.cmd, timeout=30)
        self.assertEqual(r["status"], "rejeitado", r)
        self.assertEqual(self.fonte(), original)
        self.assertFalse(self.backups.exists())

    def test_cria_modulo_novo_apenas_em_generated_com_teste_dedicado(self):
        test_file = self.tests / "test_demo.py"
        test_file.write_text(
            "import pytest\n"
            "def test_harness():\n    assert True\n"
            "def test_valor():\n"
            "    pytest.importorskip('friday.generated.demo')\n"
            "    from friday.generated.demo import valor\n"
            "    assert valor() == 7\n",
            encoding="utf-8",
        )
        cmd = self.cmd  # inclui tests/test_demo.py e a suíte do projeto temporário
        candidato = "def valor():\n    return 7\n"
        r = E.promover("friday/generated/demo.py", candidato, cmd, timeout=30)
        self.assertEqual(r["status"], "promovido", r)
        self.assertEqual((self.friday / "generated" / "demo.py").read_text(encoding="utf-8"), candidato)
        manifest = json.loads((self.root / r["backup"]).parent.joinpath("manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["original_existe"])
        self.assertEqual(manifest["bytes"], 0)

    def test_modulo_novo_exige_teste_dedicado(self):
        with self.assertRaises(ValueError):
            E.promover("friday/generated/demo.py", "def valor():\n    return 7\n", self.cmd)
        self.assertFalse((self.friday / "generated" / "demo.py").exists())

    def test_rollback_remove_modulo_que_foi_criado_agora(self):
        test_file = self.tests / "test_demo.py"
        test_file.write_text(
            "import pytest\n"
            "def test_harness():\n    assert True\n"
            "def test_valor():\n"
            "    pytest.importorskip('friday.generated.demo')\n"
            "    from friday.generated.demo import valor\n"
            "    assert valor() == 7\n",
            encoding="utf-8",
        )
        cmd = [[sys.executable, "-m", "pytest", "-q", "tests/test_demo.py"]]
        with patch.object(E, "_executar_testes", side_effect=[
            (True, [{"codigo": 0}]), (True, [{"codigo": 0}]), (False, [{"codigo": 1}]),
        ]):
            r = E.promover("friday/generated/demo.py", "def valor():\n    return 7\n", cmd)
        self.assertEqual(r["status"], "revertido")
        self.assertFalse((self.friday / "generated" / "demo.py").exists())
        backup = self.root / r["backup"]
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_bytes(), b"")
        # «nada é apagado»: o módulo revertido sai de friday/ mas fica recuperável em .evolucao/arquivo/
        arquivados = list((self.state / "arquivo").glob("*-rollback-demo.py"))
        self.assertEqual(len(arquivados), 1)
        self.assertEqual(arquivados[0].read_text(encoding="utf-8"), "def valor():\n    return 7\n")

    def test_escrita_atomica_que_falha_arquiva_o_tmp_em_vez_de_apagar(self):
        alvo = self.friday / "memoria.py"
        antes = alvo.read_bytes()
        with patch.object(E.os, "replace", side_effect=[OSError("disco cheio"), None]) as rep, \
             patch("os.unlink") as unlink, patch("os.remove") as remove:
            with self.assertRaises(OSError):
                E._escrever_atomico(alvo, b"novo")
        unlink.assert_not_called(); remove.assert_not_called()
        self.assertEqual(rep.call_count, 2)                      # 1ª: a troca (falhou); 2ª: o arquivamento do .tmp
        self.assertEqual(rep.call_args_list[1].args[1].parent, self.state / "arquivo")
        self.assertEqual(alvo.read_bytes(), antes)              # o arquivo ativo não foi tocado

    def test_sem_mudanca_nao_promove(self):
        r = E.promover("friday/memoria.py", self.fonte(), self.cmd)
        self.assertEqual(r["status"], "sem_mudanca")


if __name__ == "__main__":
    unittest.main()
