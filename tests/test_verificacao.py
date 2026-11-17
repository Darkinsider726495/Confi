"""Fase 2 — conferir o EFEITO de uma ação por fora da ferramenta (friday/verificacao.py).

Teste B da missão: uma ferramenta que RESPONDE «deu certo» sem ter feito nada não pode contar como objetivo cumprido.
Para provar isso aqui cada ferramenta é rodada de duas formas: de verdade (o efeito existe → confirmado) e MENTINDO (a função devolve a mesma frase de
sucesso, mas não grava nada → refutado). O que já existia antes da ação não vale: só o que apareceu depois da marca de `antes()`.
"""
import json, os, time, unittest
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import ferramentas as F, memoria as MEM, neuronios as NEU, verificacao as V
from test_neuronios import Cerebro

SEGREDO = "zq-conteudo-particular-8841"


def mente(nome, resposta):
    """A ferramenta `nome` passa a responder `resposta` sem fazer nada."""
    return mock.patch.dict(B.FERRAMENTAS[nome], {"fn": lambda **kw: resposta})


class Base(Cerebro):
    def rodar(self, nome, args, falsa=None):
        """(base, resultado, veredito): marca → executa pelo corretor (nível 1 roda direto) → confere."""
        base = V.antes(nome, args)
        ctx = mente(nome, falsa) if falsa else mock.patch.dict(os.environ, {})
        with ctx:
            r = B.executar_estruturado(nome, args)
        self.assertEqual(r["estado"], "executada", r)
        return base, r, V.depois(nome, args, base, r["texto"], r["erro"])

    def assertVeredito(self, v, veredito, forca=None):
        self.assertEqual(v["veredito"], veredito, v)
        if forca:
            self.assertEqual(v["forca"], forca, v)
        self.assertNotIn(SEGREDO, json.dumps(v, ensure_ascii=False), "a evidência não carrega o conteúdo pedido")


class Lembrete(Base):
    ARGS = {"minutos": 7, "texto": SEGREDO}

    def test_criado_de_verdade(self):
        _, _, v = self.rodar("criar_lembrete", self.ARGS)
        self.assertVeredito(v, "confirmado", "independente")

    def test_ferramenta_mente(self):
        _, r, v = self.rodar("criar_lembrete", self.ARGS, falsa="Lembrete criado para daqui a 7 minutos.")
        self.assertIn("criado", r["texto"], "a ferramenta disse que deu certo")
        self.assertVeredito(v, "refutado", "independente")
        self.assertIn("tinha respondido que deu certo", v["evidencia"])

    def test_lembrete_igual_que_ja_existia_nao_vale(self):
        F.criar_lembrete(7, SEGREDO)                                  # já havia um idêntico
        _, _, v = self.rodar("criar_lembrete", self.ARGS, falsa="Lembrete criado.")
        self.assertVeredito(v, "refutado")

    def test_horario_errado_nao_vale(self):
        base = V.antes("criar_lembrete", self.ARGS)
        F.criar_lembrete(60, SEGREDO)                                 # mesmo texto, mas daqui a uma hora
        self.assertVeredito(V.depois("criar_lembrete", self.ARGS, base, "Lembrete criado."), "refutado")

    def test_texto_diferente_nao_vale(self):
        base = V.antes("criar_lembrete", self.ARGS)
        F.criar_lembrete(7, "outra coisa")
        self.assertVeredito(V.depois("criar_lembrete", self.ARGS, base, "Lembrete criado."), "refutado")

    def test_lembrete_que_ja_disparou_continua_sendo_evidencia(self):
        base = V.antes("criar_lembrete", {"minutos": 0.1, "texto": SEGREDO})
        F.criar_lembrete(0.1, SEGREDO)
        import sqlite3
        c = sqlite3.connect(F.DB)
        c.execute("update lembretes set feito=1 where texto=?", (SEGREDO,))
        c.commit(); c.close()
        self.assertVeredito(V.depois("criar_lembrete", {"minutos": 0.1, "texto": SEGREDO}, base, "ok"), "confirmado")


class Nota(Base):
    def test_anotada_de_verdade(self):
        self.assertVeredito(self.rodar("anotar", {"texto": SEGREDO})[2], "confirmado", "independente")

    def test_ferramenta_mente(self):
        self.assertVeredito(self.rodar("anotar", {"texto": SEGREDO}, falsa="Anotado.")[2], "refutado")

    def test_nota_igual_antiga_nao_vale(self):
        F.anotar(SEGREDO)
        self.assertVeredito(self.rodar("anotar", {"texto": SEGREDO}, falsa="Anotado.")[2], "refutado")


class Arquivo(Base):
    def test_criado_de_verdade(self):
        v = self.rodar("criar_arquivo", {"nome": "ver-a.md", "conteudo": SEGREDO})[2]
        self.assertVeredito(v, "confirmado", "independente")
        self.assertIn("ver-a.md", v["evidencia"])

    def test_ferramenta_mente(self):
        self.assertVeredito(self.rodar("criar_arquivo", {"nome": "ver-b.md", "conteudo": SEGREDO}, falsa="Arquivo ver-b.md criado.")[2], "refutado")

    def test_arquivo_igual_antigo_nao_vale_mas_o_novo_com_sufixo_vale(self):
        a = {"nome": "ver-c.md", "conteudo": SEGREDO}
        B.executar("criar_arquivo", a)                                # ver-c.md já existe com o mesmo conteúdo
        self.assertVeredito(self.rodar("criar_arquivo", a, falsa="Arquivo ver-c-2.md criado.")[2], "refutado", "independente")
        v = self.rodar("criar_arquivo", a)[2]                         # de verdade: nasce ver-c-2.md
        self.assertVeredito(v, "confirmado")
        self.assertIn("ver-c-2.md", v["evidencia"])

    def test_conteudo_diferente_nao_vale(self):
        a = {"nome": "ver-d.md", "conteudo": SEGREDO}
        base = V.antes("criar_arquivo", a)
        B.executar("criar_arquivo", {"nome": "ver-d.md", "conteudo": "outro texto"})
        self.assertVeredito(V.depois("criar_arquivo", a, base, "ok"), "refutado")


class Memoria(Base):
    A = {"texto": f"O usuário gosta de {SEGREDO} nas sextas", "titulo": "Gosto verificado"}

    def test_guardada_de_verdade(self):
        self.assertVeredito(self.rodar("guardar_memoria", self.A)[2], "confirmado", "independente")

    def test_atualizacao_de_nota_existente_tambem_confirma(self):
        B.executar("guardar_memoria", {"texto": "primeira linha da nota", "titulo": "Gosto verificado"})
        time.sleep(0.3)
        self.assertVeredito(self.rodar("guardar_memoria", self.A)[2], "confirmado")

    def test_ferramenta_mente(self):
        self.assertVeredito(self.rodar("guardar_memoria", self.A, falsa="Guardei na memória.")[2], "refutado")

    def test_nota_antiga_com_o_mesmo_texto_nao_vale(self):
        B.executar("guardar_memoria", self.A)
        for f in self.base("Memorias").glob("*.md"):                  # a nota existe há muito tempo
            os.utime(f, (time.time() - 3600, time.time() - 3600))
        self.assertVeredito(self.rodar("guardar_memoria", self.A, falsa="Guardei na memória.")[2], "refutado")

    def test_outra_nota_alterada_agora_nao_vale(self):
        base = V.antes("guardar_memoria", self.A)
        B.executar("guardar_memoria", {"texto": "um assunto sem relação nenhuma com o pedido", "titulo": "Outra nota"})
        self.assertVeredito(V.depois("guardar_memoria", self.A, base, "Guardei na memória."), "refutado")

    def test_cofre_desligado_e_inconclusivo(self):
        base = V.antes("guardar_memoria", self.A)
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            self.assertVeredito(V.depois("guardar_memoria", self.A, base, "ok"), "inconclusivo")


class ModoFoco(Base):
    def tearDown(self):
        F.voltar_a_falar()

    def test_silenciar_de_verdade(self):
        self.assertVeredito(self.rodar("silenciar", {"minutos": 10})[2], "confirmado", "independente")

    def test_silenciar_mentindo(self):
        F.voltar_a_falar()
        self.assertVeredito(self.rodar("silenciar", {"minutos": 10}, falsa="Modo foco ativo por 10 minutos.")[2], "refutado")

    def test_silenciar_com_outro_tempo_e_inconclusivo(self):
        base = V.antes("silenciar", {"minutos": 10})
        F.silenciar(600)
        self.assertVeredito(V.depois("silenciar", {"minutos": 10}, base, "ok"), "inconclusivo")

    def test_voltar_a_falar(self):
        F.silenciar(30)
        self.assertVeredito(self.rodar("voltar_a_falar", {})[2], "confirmado")
        F.silenciar(30)
        self.assertVeredito(self.rodar("voltar_a_falar", {}, falsa="Voltei a falar normalmente.")[2], "refutado")


class Pedido(Base):
    A = {"texto": f"Quero poder pedir {SEGREDO} por voz", "titulo": "Pedido verificado"}

    def test_pedido_de_verdade(self):
        self.assertVeredito(self.rodar("pedir_evolucao", self.A)[2], "confirmado", "independente")

    def test_ferramenta_mente(self):
        self.assertVeredito(self.rodar("pedir_evolucao", self.A, falsa="Pedido anotado.")[2], "refutado")

    def test_titulo_repetido_com_outro_texto_nao_vale(self):
        B.executar("pedir_evolucao", {"texto": "Um pedido bem diferente do outro", "titulo": "Pedido verificado"})
        v = self.rodar("pedir_evolucao", self.A)[2]                   # a ferramenta responde «já tenho esse pedido» e não grava o texto novo
        self.assertVeredito(v, "refutado")


class Leituras(Base):
    def test_leitura_com_resposta(self):
        base = V.antes("listar_lembretes", {})
        v = V.depois("listar_lembretes", {}, base, "Nenhum lembrete pendente.")
        self.assertVeredito(v, "confirmado", "da_resposta")
        self.assertIn("só a resposta", v["evidencia"], "a evidência admite que não olhou o estado")

    def test_leitura_com_erro_ou_vazia(self):
        self.assertVeredito(V.depois("listar_lembretes", {}, {}, "Erro: banco travado", True), "refutado", "da_resposta")
        self.assertVeredito(V.depois("listar_lembretes", {}, {}, "   "), "refutado", "da_resposta")


class SemComoConferir(Base):
    def test_ferramentas_do_celular_nao_sao_verificaveis(self):
        for nome, args in (("enviar_sms", {"contato": "mae", "texto": SEGREDO}), ("ligar", {"contato": "mae"}), ("rele", {"nome": "luz", "ligar": True}),
                           ("lanterna", {"ligar": True}), ("vibrar", {"ms": 100}), ("notificar", {"texto": SEGREDO})):
            with self.subTest(nome):
                self.assertIn(nome, B.FERRAMENTAS, "a ferramenta existe neste ambiente de teste")
                v = V.depois(nome, args, V.antes(nome, args), "Feito.")
                self.assertVeredito(v, "nao_verificavel", "nenhuma")
                self.assertTrue(v["evidencia"])

    def test_ferramenta_sem_conferencia_nao_vira_confirmada(self):
        B.registrar("acao_sem_conferencia_ver", "t", {}, [], lambda: "Feito.", 1)
        self.addCleanup(B.FERRAMENTAS.pop, "acao_sem_conferencia_ver", None)
        v = V.depois("acao_sem_conferencia_ver", {}, V.antes("acao_sem_conferencia_ver", {}), "Feito.")
        self.assertVeredito(v, "nao_verificavel")
        self.assertFalse(V.conferivel("acao_sem_conferencia_ver"))

    def test_desconhecida(self):
        self.assertVeredito(V.depois("nao_existe_ver", {}, {}, "x"), "nao_verificavel")


class Interface(Base):
    def test_a_marca_e_pequena_e_serializavel(self):
        for nome, args in (("criar_lembrete", {"minutos": 1, "texto": SEGREDO}), ("anotar", {"texto": SEGREDO}), ("criar_arquivo", {"nome": "m.md", "conteudo": SEGREDO}),
                           ("guardar_memoria", {"texto": SEGREDO}), ("silenciar", {"minutos": 1})):
            with self.subTest(nome):
                s = json.dumps(V.antes(nome, args))
                self.assertNotIn(SEGREDO, s, "a marca guarda ids e nomes, não o conteúdo")
                self.assertLess(len(s), 400)

    def test_marca_que_falha_vira_inconclusivo(self):
        with mock.patch.object(F, "marca_lembretes", side_effect=OSError("banco")):
            base = V.antes("criar_lembrete", {"minutos": 1, "texto": "x"})
        self.assertIn("sem_marca", base)
        for b in (base, {}):
            v = V.depois("criar_lembrete", {"minutos": 1, "texto": "x"}, b, "ok")
            self.assertVeredito(v, "inconclusivo")
            self.assertIn("marca de antes", v["evidencia"], "diz o motivo de verdade, não um erro interno")

    def test_conferencia_que_quebra_vira_inconclusivo(self):
        base = V.antes("anotar", {"texto": "x"})
        with mock.patch.object(F, "notas_depois", side_effect=OSError("banco")):
            self.assertVeredito(V.depois("anotar", {"texto": "x"}, base, "Anotado."), "inconclusivo")

    def test_so_le_nao_chama_o_corretor(self):
        base = V.antes("anotar", {"texto": SEGREDO})
        F.anotar(SEGREDO)
        with mock.patch.object(B, "executar", side_effect=AssertionError), mock.patch.object(B, "executar_estruturado", side_effect=AssertionError), \
                mock.patch.object(B, "_rodar", side_effect=AssertionError):
            self.assertVeredito(V.depois("anotar", {"texto": SEGREDO}, base, "Anotado."), "confirmado")

    def test_tem_efeito(self):
        self.assertTrue(V.tem_efeito("criar_lembrete") and V.tem_efeito("enviar_sms"))
        self.assertFalse(V.tem_efeito("listar_lembretes") or V.tem_efeito("hora_data") or V.tem_efeito("nao_existe_ver"))

    def test_ferramenta_que_relata_erro_mas_deixou_o_efeito(self):
        base = V.antes("anotar", {"texto": SEGREDO})
        F.anotar(SEGREDO)
        v = V.depois("anotar", {"texto": SEGREDO}, base, "Erro: algo", True)
        self.assertVeredito(v, "confirmado")
        self.assertIn("relatando erro", v["evidencia"])


if __name__ == "__main__":
    unittest.main()
