"""Confinamento do Laboratório de Modificação Destrutiva (MAE): nada sai de .lab/ — nem por caminho,
nem por symlink, nem por nome oculto; toda exclusão tem snapshot antes e é recuperável; o teste do
laboratório roda num subprocess confinado (cwd = raiz do lab, ambiente limpo, tempo limite)."""
import os, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401  (registro das ferramentas lab_* no corretor)
import laboratorio as LAB


SENTINELA = os.path.join(E.TMP, "fora_do_lab.txt")


def fora(msg):
    with open(SENTINELA, "w", encoding="utf-8") as f:
        f.write(msg)


def ler_fora():
    with open(SENTINELA, encoding="utf-8") as f:
        return f.read()


def dentro(msg, rel="alvo.py"):
    p = os.path.join(LAB.LAB_ROOT, rel)
    os.makedirs(os.path.dirname(p) or LAB.LAB_ROOT, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(msg)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        LAB._lab_absoluto()
        import shutil
        for raiz, dirs, arqs in os.walk(LAB.LAB_ROOT, topdown=False):
            for a in arqs:
                p = os.path.join(raiz, a)
                os.remove(p) if not os.path.islink(p) else os.remove(p)
            for d in dirs:
                p = os.path.join(raiz, d)
                if os.path.islink(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p)
        fora("conteúdo de fora")


class Confinamento(Base):
    def test_toda_operacao_de_exclusao_fica_preso_no_laboratorio(self):
        """A prova pedida: exclusão e recriação DENTRO do lab, e nenhum arquivo de fora é tocado —
        nem com fuga de caminho, nem com caminho absoluto, nem com symlink."""
        p = dentro("vou ser excluída")
        r = LAB.excluir("alvo.py")
        self.assertIn("recuperável", r)
        self.assertFalse(os.path.exists(p))                       # exclusão real, dentro do lab
        vid = LAB.historico_versoes("alvo.py")[0]["id"]
        self.assertEqual(LAB.ler_versao(vid, "alvo.py"), "vou ser excluída")   # mas recuperável
        self.assertEqual(LAB.ler("alvo.py") if os.path.exists(p) else "", "")  # não voltou sozinha
        self.assertEqual(ler_fora(), "conteúdo de fora")   # nada de fora foi tocado
        LAB.criar("alvo.py", "recriada")
        self.assertEqual(LAB.ler("alvo.py"), "recriada")          # recriação dentro do lab funciona

    def test_fuga_de_caminho_e_recusada(self):
        for rel in ("../fora_do_lab.txt", "sub/../../fora_do_lab.txt", "..\\fora_do_lab.txt", "/etc/passwd"):
            with self.assertRaises(ValueError, msg=rel):
                LAB.criar(rel, "x")
        self.assertEqual(ler_fora(), "conteúdo de fora")
        self.assertFalse(os.path.exists("/etc/passwd.txt"))

    def test_symlink_para_fora_e_recusado(self):
        p = os.path.join(LAB.LAB_ROOT, "link.txt")
        os.symlink(SENTINELA, p)
        with self.assertRaises(ValueError):
            LAB.ler("link.txt")
        with self.assertRaises(ValueError):
            LAB.editar("link.txt", "x")
        self.assertEqual(ler_fora(), "conteúdo de fora")

    def test_pasta_vinculada_para_fora_e_recusada(self):
        os.makedirs(os.path.join(LAB.LAB_ROOT, "sub"))
        os.rmdir(os.path.join(LAB.LAB_ROOT, "sub"))
        os.symlink(E.TMP, os.path.join(LAB.LAB_ROOT, "sub"))
        with self.assertRaises(ValueError):
            LAB.criar("sub/invade.txt", "x")
        self.assertFalse(os.path.exists(os.path.join(E.TMP, "invade.txt")))

    def test_areas_internas_e_nomes_ocultos_ficam_fora_do_alcance(self):
        for rel in (".versoes/x.txt", ".grave/x.txt", ".env", "p/.secreta.txt"):
            with self.assertRaises(ValueError, msg=rel):
                LAB.criar(rel, "x")

    def test_tipo_de_arquivo_nao_permitido_e_recusado(self):
        with self.assertRaises(ValueError):
            LAB.criar("programa.exe", "x")
        LAB.criar("modulo.py", "ok")     # as permitidas passam
        LAB.criar("nota.md", "ok")
        self.assertIn("modulo.py", LAB.listar())


class Ciclo(Base):
    def test_editar_tira_snapshot_e_restaurar_volta(self):
        LAB.criar("alvo.py", "versão 1")
        LAB.editar("alvo.py", "versão 2")
        self.assertEqual(LAB.ler("alvo.py"), "versão 2")
        self.assertGreaterEqual(len(LAB.historico_versoes("alvo.py")), 1)
        vid = LAB.historico_versoes("alvo.py")[0]["id"]
        LAB.restaurar(vid, "alvo.py")
        self.assertEqual(LAB.ler("alvo.py"), "versão 1")

    def test_diferenca_mostra_o_que_mudou(self):
        LAB.criar("alvo.py", "a\nb\n")
        LAB.editar("alvo.py", "a\nc\n")
        vid = LAB.historico_versoes("alvo.py")[0]["id"]
        d = LAB.diferenca_versoes(vid, "alvo.py")
        self.assertIn("-b", d)
        self.assertIn("+c", d)

    def test_renomear_copia_e_a_antiga_fica_recuperavel(self):
        LAB.criar("alvo.py", "conteúdo")
        r = LAB.renomear("alvo.py", "novo.py")
        self.assertIn("novo.py", r)
        self.assertEqual(LAB.ler("novo.py"), "conteúdo")
        self.assertFalse(os.path.exists(os.path.join(LAB.LAB_ROOT, "alvo.py")))
        vid = LAB.historico_versoes("alvo.py")[0]["id"]
        self.assertEqual(LAB.ler_versao(vid, "alvo.py"), "conteúdo")

    def test_criar_nunca_sobrescreve(self):
        LAB.criar("alvo.py", "primeira")
        with self.assertRaises(ValueError):
            LAB.criar("alvo.py", "segunda")
        self.assertEqual(LAB.ler("alvo.py"), "primeira")


class TesteConfinado(Base):
    def gravar(self, corpo):
        LAB.permitir_teste(corpo)          # o teste só roda se o conteúdo for conhecido (aqui, registrado pelo próprio teste)
        LAB.criar("teste_prova.py", corpo)

    def test_so_arquivo_de_teste_designado_roda(self):
        LAB.criar("malicioso.py", "print('oi')")
        with self.assertRaises(ValueError):
            LAB.testar("malicioso.py")
        with self.assertRaises(ValueError):
            LAB.testar("nao_existe.py")

    def test_o_teste_roda_de_verdade_no_laboratorio(self):
        self.gravar("import alvo\nprint(alvo.versao())\n")
        LAB.criar("alvo.py", 'def versao():\n    return "v1"\n')
        r = LAB.testar("teste_prova.py")
        self.assertTrue(r.startswith("PASSOU"))
        self.assertIn("v1", r)

    def test_falha_do_teste_e_reportada_com_a_saida(self):
        self.gravar("raise SystemExit(3)")
        r = LAB.testar("teste_prova.py")
        self.assertTrue(r.startswith("FALHOU"))
        self.assertIn("(código 3)", r)

    def test_o_subprocesso_nao_herda_o_ambiente_da_friday(self):
        self.gravar("import os\nprint('DB' if 'FRIDAY_DB' in os.environ else 'limpo')\nprint(os.getcwd())\n")
        r = LAB.testar("teste_prova.py")
        self.assertTrue(r.startswith("PASSOU"))
        self.assertIn("limpo", r)                    # sem o FRIDAY_DB, PIN, auditoria...
        self.assertIn(os.path.realpath(LAB.LAB_ROOT), os.path.realpath(r.splitlines()[-1]))

    def test_teste_sem_tempo_e_abortado(self):
        self.gravar("import time\ntime.sleep(10)\n")
        with mock.patch.object(LAB, "TESTE_TIMEOUT", 2):
            r = LAB.testar("teste_prova.py")
        self.assertTrue(r.startswith("FALHOU"))
        self.assertIn("abortado", r)


class Corretor(Base):
    def test_as_ferramentas_do_laboratorio_existem_no_corretor(self):
        for nome, nivel in [("lab_criar", 1), ("lab_ler", 0), ("lab_listar", 0), ("lab_editar", 1),
                            ("lab_excluir", 1), ("lab_renomear", 1), ("lab_restaurar", 1),
                            ("lab_diferenca", 0), ("lab_historico", 0), ("lab_testar", 1)]:
            self.assertIn(nome, B.FERRAMENTAS, nome)
            self.assertEqual(B.FERRAMENTAS[nome]["nivel"], nivel, nome)

    def test_o_corretor_executa_e_recusa_pelo_mesmo_caminho(self):
        with B.uso_interno():                                  # como o ciclo do MAE chama
            r = B.executar_estruturado("lab_criar", {"rel": "pelo_corretor.py", "conteudo": "ok"}, B.Turno())
            self.assertEqual(r["estado"], "executada")
            r = B.executar_estruturado("lab_criar", {"rel": "../fuga.py", "conteudo": "x"}, B.Turno())
        self.assertEqual(r["estado"], "executada")            # a ferramenta rodou e devolveu o erro dela
        self.assertIn("recusada", r["texto"].lower())
        self.assertFalse(os.path.exists(os.path.join(LAB.LAB_ROOT, "..", "fuga.py")))


if __name__ == "__main__":
    unittest.main()