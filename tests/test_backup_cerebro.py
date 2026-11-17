"""Backup do cérebro: tudo do cofre entra, segredo e Privado/ não; restaurar não apaga nada e recusa zip com caminho suspeito."""
import importlib.util, os, tempfile, unittest, zipfile
from pathlib import Path
import _ambiente as E  # noqa: F401
import memoria as M
from test_assimilacao import Base

_spec = importlib.util.spec_from_file_location("backup_cerebro", Path(__file__).resolve().parents[1] / "scripts" / "backup_cerebro.py")
BK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BK)


class Backup(Base):
    def setUp(self):
        super().setUp()
        b = self.base()
        for rel, txt in {"Topicos/SQL.md": "# SQL", ".cerebro/rotina_gru.npz": "x", "Privado/diario.md": "segredo", ".env": "CHAVE=1"}.items():
            (b / rel).parent.mkdir(parents=True, exist_ok=True)
            (b / rel).write_text(txt, encoding="utf-8")
        self.saida = tempfile.mkdtemp(dir=E.TMP)

    def nomes(self, arq):
        with zipfile.ZipFile(arq) as z:
            return set(z.namelist())

    def test_entra_o_cerebro_e_fica_de_fora_o_segredo_e_o_privado(self):
        arq, n = BK.criar(self.saida)
        nomes = self.nomes(arq)
        self.assertIn("FRIDAY/Topicos/SQL.md", nomes)
        self.assertIn("FRIDAY/.cerebro/rotina_gru.npz", nomes)
        self.assertNotIn("FRIDAY/Privado/diario.md", nomes)
        self.assertFalse([x for x in nomes if x.endswith(".env")])

    def test_privado_so_quando_o_dono_pede(self):
        arq, _ = BK.criar(self.saida, com_privado=True)
        self.assertIn("FRIDAY/Privado/diario.md", self.nomes(arq))

    def test_restaurar_guarda_o_atual_e_volta_o_backup(self):
        arq, _ = BK.criar(self.saida)
        (self.base() / "Topicos" / "SQL.md").write_text("# SQL mudado", encoding="utf-8")
        antigo, n = BK.restaurar(arq)
        self.assertEqual((self.base() / "Topicos" / "SQL.md").read_text(encoding="utf-8"), "# SQL")
        self.assertEqual((antigo / "Topicos" / "SQL.md").read_text(encoding="utf-8"), "# SQL mudado")   # nada apagado

    def test_zip_com_caminho_suspeito_e_recusado_sem_mexer_em_nada(self):
        mau = Path(self.saida) / "mau.zip"
        with zipfile.ZipFile(mau, "w") as z:
            z.writestr("FRIDAY/../../fora.txt", "x")
        with self.assertRaises(SystemExit):
            BK.restaurar(mau)
        self.assertTrue((self.base() / "Topicos" / "SQL.md").exists())


if __name__ == "__main__":
    unittest.main()
