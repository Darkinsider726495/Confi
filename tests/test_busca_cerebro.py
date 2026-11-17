"""Busca semântica (RAG) da memória — comportamento seguro e degradável.

O essencial a garantir: sem o LightRAG instalado (o caso do celular e do ambiente de teste), o módulo
NUNCA derruba a memória — disponivel() é False, buscar() devolve [], indexar() avisa, e memoria.lembrar
continua funcionando normalmente pela busca por palavra. Também: o índice fica FORA do cofre e só a
memória confiável entra na fila (Estudos/Visao ficam de fora)."""
import os
import unittest
import _ambiente as E
import memoria as MEM
import busca_cerebro as BC


class Degradacao(unittest.TestCase):
    """RAG desligado/indisponível: tudo continua de pé. É o estado do ambiente de teste (CEREBRO_RAG=0),
    e também o do celular (sem lightrag). A FRIDAY nunca depende da busca semântica."""
    def setUp(self):
        MEM.guardar("A Kornix é a minha empresa de cibersegurança.", 5)

    def test_indisponivel_tudo_degrada_sem_quebrar(self):
        self.assertFalse(BC.disponivel())            # CEREBRO_RAG=0 no ambiente de teste
        self.assertEqual(BC.buscar("empresa de segurança"), [])
        r = BC.indexar()
        self.assertEqual(r.get("indexadas"), 0)
        self.assertIn("erro", r)

    def test_lembrar_continua_funcionando(self):
        # com ou sem lightrag, o lembrar normal (por palavra) tem de responder
        texto = MEM.lembrar("Kornix")
        self.assertIn("Kornix", texto)

    def test_resumo_nunca_quebra(self):
        r = BC.resumo()
        self.assertIn("disponivel", r)
        self.assertIn("ligado", r)

    def test_buscar_vazio_ou_memoria_desligada(self):
        self.assertEqual(BC.buscar("   "), [])
        orig = os.environ.get("OBSIDIAN_VAULT")
        os.environ["OBSIDIAN_VAULT"] = "off"
        try:
            self.assertFalse(BC.disponivel())
            self.assertEqual(BC.buscar("qualquer"), [])
        finally:
            if orig is not None:
                os.environ["OBSIDIAN_VAULT"] = orig


class Selecao(unittest.TestCase):
    """O que entra na fila de indexação: só a memória confiável, nunca Estudos/Visao, nunca privada."""
    def test_so_memoria_confiavel_entra_na_fila(self):
        MEM.guardar("Fato confiável sobre o projeto FRIDAY.", 4)
        # grava um "estudo" (conteúdo da internet) direto na pasta Estudos
        est = MEM.base() / "Estudos"
        est.mkdir(parents=True, exist_ok=True)
        (est / "coisa-da-web.md").write_text("---\ntipo: estudo\norigem: web\n---\nTexto vindo da internet.", encoding="utf-8")
        fila = BC._notas_para_indexar()
        pastas = {rel.split("/")[0] for rel, _, _ in fila}
        self.assertTrue(pastas.issubset(set(BC.PASTAS_INDEX)), pastas)
        self.assertNotIn("Estudos", pastas)
        self.assertNotIn("Visao", pastas)

    def test_o_indice_fica_fora_do_cofre(self):
        d = BC._dir_indice()
        cofre = str(MEM.raiz() or "")
        self.assertTrue(cofre)
        self.assertFalse(os.path.abspath(d).startswith(os.path.abspath(cofre)),
                         "o índice RAG não pode ficar dentro do cofre do Obsidian")

    def test_manifesto_evita_reindexar_o_que_nao_mudou(self):
        MEM.guardar("Nota que não muda.", 3)
        fila1 = BC._notas_para_indexar()
        self.assertTrue(fila1)
        # simula que tudo foi indexado
        man = {rel: mtime for rel, mtime, _ in fila1}
        BC._salvar_manifesto(man)
        fila2 = BC._notas_para_indexar()
        self.assertEqual(fila2, [], "nota sem alteração não deve voltar para a fila")


if __name__ == "__main__":
    unittest.main()
