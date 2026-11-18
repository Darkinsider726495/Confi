"""Baixar corpus: escolhe só os livros em português, tira a licença do Gutenberg, não baixa duas vezes, espera entre downloads."""
import importlib.util, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E  # noqa: F401

_spec = importlib.util.spec_from_file_location("baixar_corpus", Path(__file__).resolve().parents[1] / "scripts" / "baixar_corpus.py")
BC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BC)

CSV = ('Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n'
       '55752,Text,2017,Dom Casmurro,pt,"Assis, Machado de",,,\n'
       '1342,Text,1998,Pride and Prejudice,en,"Austen, Jane",,,\n'
       '999,Sound,2005,Audio PT,pt,x,,,\n'
       '777,Text,2010,"Os Lusíadas",pt; es,"Camões",,,\n')
LIVRO = ("The Project Gutenberg eBook of Dom Casmurro\nlicença...\n*** START OF THE PROJECT GUTENBERG EBOOK DOM CASMURRO ***\n"
         + "Uma noite destas, vindo da cidade para o Engenho Novo, encontrei no trem da Central um rapaz aqui do bairro. " * 40
         + "\n*** END OF THE PROJECT GUTENBERG EBOOK DOM CASMURRO ***\nlicença longa no fim")


class BaixarCorpus(unittest.TestCase):
    def test_so_livros_de_texto_em_portugues(self):
        self.assertEqual([i for i, _, _ in BC.livros_em_portugues(CSV)], [55752, 777])

    def test_tira_a_licenca_e_nao_baixa_duas_vezes(self):
        pasta = Path(E.TMP) / "corpus-teste"
        chamadas, dormiu = [], []
        def falso(url, timeout=60):
            chamadas.append(url)
            return CSV if "catalog" in url else LIVRO
        with mock.patch.object(BC, "DESTINO", pasta):
            BC.main(["--livros", "5"], baixar=falso, dormir=dormiu.append)
            arqs = sorted(pasta.glob("*.txt"))
            self.assertEqual(len(arqs), 2)
            txt = arqs[0].read_text(encoding="utf-8")
            self.assertIn("Engenho Novo", txt)
            self.assertNotIn("licença", txt)
            self.assertNotIn("START OF", txt)
            n = len(chamadas)
            BC.main(["--livros", "5"], baixar=falso, dormir=dormiu.append)
            self.assertEqual(len(chamadas), n + 1)                 # 2ª vez só lê o catálogo: os livros já estão lá
        self.assertTrue(dormiu)                                    # espera entre downloads (educação com o site)


if __name__ == "__main__":
    unittest.main()
