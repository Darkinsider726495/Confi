"""Fase 1.5 — argumentos fora da faixa: validar, recusar com clareza ou ajustar de forma DECLARADA; nunca mudar em silêncio.

Antes: criar_lembrete(-5) virava «daqui a 0,1 minuto» (dispara na hora), silenciar(0) virava 1 minuto, criar_lembrete cortava o texto em 200 letras,
guardar_memoria trocava um tipo inválido por «fato» — tudo sem avisar quem pediu.

Agora cada parâmetro declara o que aceita (minimum, maximum, maxLength, enum) e o corretor:
  - RECUSA fora da faixa («Pedido inválido: minutos deve estar entre 0.1 e 43200 (recebi -5)») e não executa nada;     [padrão]
  - AJUSTA só onde o parâmetro declara ao_exceder="limitar" (leitura/tempo de vibração, sem efeito colateral), e a resposta diz o que mudou.
A trilha guarda o código da recusa («faixa:minutos»), nunca o texto recebido.
"""
import json, os, unittest
from unittest import mock
import _ambiente as E
import broker as B, ferramentas as F, catalogo  # noqa: F401
import android as A

BIN, LOG = E.termux_falso()


def trilha():
    with open(B.AUDITORIA, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class Base(unittest.TestCase):
    def setUp(self):
        B.PEND = None
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)
        p = mock.patch.dict(os.environ, {"PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(setattr, B, "PEND", None)
        open(LOG, "w").close()
        F.voltar_a_falar()


class Recusa(Base):
    def test_lembrete_com_tempo_fora_da_faixa_nao_e_criado(self):
        antes = F.listar_lembretes()
        for m in (-5, 0, 0.01, 43201, 10 ** 9, float("nan"), float("inf"), -float("inf")):
            with self.subTest(minutos=m):
                r = B.executar("criar_lembrete", {"minutos": m, "texto": "pagar a conta"})
                self.assertTrue(r.startswith("Pedido inválido: minutos"), r)
        self.assertEqual(F.listar_lembretes(), antes, "nada foi gravado")

    def test_mensagem_diz_a_faixa_e_o_que_chegou(self):
        r = B.executar("criar_lembrete", {"minutos": -5, "texto": "x"})
        self.assertIn("entre 0.1 e 43200", r)
        self.assertIn("-5", r)

    def test_limites_exatos_passam_sem_alteracao(self):
        for m, esperado in ((0.1, "0.1"), (1, "1"), (43200, "43200")):
            r = B.executar("criar_lembrete", {"minutos": m, "texto": "ok"})
            self.assertIn(f"daqui a {esperado} minutos", r)

    def test_texto_do_lembrete_nao_e_cortado_em_silencio(self):
        self.assertIn("Lembrete criado", B.executar("criar_lembrete", {"minutos": 5, "texto": "a" * 200}))
        r = B.executar("criar_lembrete", {"minutos": 5, "texto": "a" * 201})
        self.assertTrue(r.startswith("Pedido inválido: texto"), r)
        self.assertIn("200", r)

    def test_modo_foco_fora_da_faixa_nao_muda_o_estado(self):
        for m in (0, -1, 1441, float("nan")):
            with self.subTest(minutos=m):
                self.assertTrue(B.executar("silenciar", {"minutos": m}).startswith("Pedido inválido: minutos"))
        self.assertEqual(F.silencio_ativo(), 0)
        self.assertIn("1 minutos", B.executar("silenciar", {"minutos": 1}))
        self.assertIn("1440 minutos", B.executar("silenciar", {"minutos": 1440}))
        B.executar("voltar_a_falar", {})

    def test_notificacao_e_whatsapp_com_texto_longo_demais(self):
        self.assertTrue(B.executar("notificar", {"texto": "n" * 401}).startswith("Pedido inválido: texto"))
        self.assertTrue(B.executar("preparar_whatsapp", {"contato": "mae", "texto": "w" * 501}).startswith("Pedido inválido: texto"))

    def test_tipo_de_memoria_fora_da_lista_e_recusado_nao_trocado(self):
        r = B.executar("guardar_memoria", {"texto": "o gato se chama Luna", "tipo": "preferência qualquer"})
        self.assertTrue(r.startswith("Pedido inválido: tipo"), r)
        self.assertIn("fato", r)
        self.assertTrue(B.executar("guardar_memoria", {"texto": "o gato se chama Luna", "importancia": 9}).startswith("Pedido inválido: importancia"))
        self.assertIn("Guardei", B.executar("guardar_memoria", {"texto": "o gato se chama Luna", "tipo": "fato", "importancia": 5}))

    def test_numero_nao_finito_e_recusado_mesmo_sem_faixa(self):
        B.registrar("sem_faixa_teste", "teste", {"x": {"type": "number"}}, ["x"], lambda x: f"x={x}", 0)
        for v in (float("nan"), float("inf"), -float("inf")):
            self.assertTrue(B.executar("sem_faixa_teste", {"x": v}).startswith("Pedido inválido: x"), v)
        self.assertEqual(B.executar("sem_faixa_teste", {"x": -3.5}), "x=-3.5")

    def test_validacoes_antigas_continuam(self):
        self.assertIn("inválido", B.executar("anotar", {"texto": 123}))
        self.assertIn("inválido", B.executar("anotar", {"texto": "x", "extra": 1}))
        self.assertIn("inválido", B.executar("anotar", {}))
        self.assertIn("inválido", B.executar("anotar", {"texto": "x" * 2000}))
        self.assertIn("inválido", B.executar("criar_lembrete", {"minutos": True, "texto": "x"}))      # booleano não é número
        self.assertIn("inválido", B.executar("rele", {"nome": "luz", "ligar": "sim"}))

    def test_recusa_vai_para_a_trilha_so_com_o_codigo(self):
        B.executar("criar_lembrete", {"minutos": -5, "texto": "senha do banco é 123456"})
        B.executar("anotar", {"texto": "x", "Maria mora na Rua Augusta 123": 1})
        B.executar("anotar", {})
        e = trilha()
        self.assertEqual([x["decisao"] for x in e], ["invalida"] * 3)
        self.assertEqual([x["resultado"] for x in e], ["faixa:minutos", "desconhecido", "falta:texto"])
        txt = json.dumps(e)
        self.assertNotIn("Augusta", txt)
        self.assertNotIn("123456", txt)
        self.assertEqual(B.verificar_auditoria()[0], True)


class AjusteDeclarado(Base):
    def test_leitura_de_notas_acima_do_maximo_e_limitada_e_avisa(self):
        for i in range(25):
            F.anotar(f"nota {i}")
        r = B.executar("ler_notas", {"limite": 50})
        self.assertIn("ajustei", r.lower())
        self.assertIn("limite de 50 para 20", r)
        self.assertEqual(r.split(" (Ajustei")[0].count("nota "), 20)
        self.assertEqual(trilha()[-1]["ajustes"], ["limite"])

    def test_dentro_da_faixa_nao_ha_aviso_nem_registro(self):
        F.anotar("uma nota")
        r = B.executar("ler_notas", {"limite": 5})
        self.assertNotIn("juste", r)
        self.assertNotIn("ajustes", trilha()[-1])

    def test_limite_zero_ou_negativo_sobe_para_o_minimo_e_avisa(self):
        F.anotar("uma nota")
        r = B.executar("ler_notas", {"limite": 0})
        self.assertIn("limite de 0 para 1", r)

    def test_vibrar_acima_de_2000_e_limitado_e_avisa(self):
        r = B.executar("vibrar", {"ms": 5000})
        self.assertIn("ms de 5000 para 2000", r)
        self.assertIn("-d 2000", E.ler_log(LOG))
        open(LOG, "w").close()
        r = B.executar("vibrar", {"ms": 300})
        self.assertNotIn("juste", r)
        self.assertIn("-d 300", E.ler_log(LOG))

    def test_ajuste_nao_vale_para_parametro_que_nao_declara(self):
        # criar_lembrete tem efeito colateral: nada de ajustar por conta própria
        self.assertTrue(B.executar("criar_lembrete", {"minutos": 10 ** 6, "texto": "x"}).startswith("Pedido inválido"))

    def test_ajuste_de_acao_que_pede_confirmacao_chega_ao_resultado(self):
        B.registrar("acao_n2_limitada_teste", "teste", {"vezes": {"type": "integer", "minimum": 1, "maximum": 3, "ao_exceder": "limitar"}}, ["vezes"],
                    lambda vezes: f"fez {vezes}", 2)
        B.executar("acao_n2_limitada_teste", {"vezes": 10})
        self.assertEqual(B.pendente_publico()["resumo"], "acao n2 limitada teste (vezes: 3)")      # a pendência mostra o valor JÁ ajustado
        ok, r = B.confirmar_voz("confirmo")
        self.assertIn("fez 3", r)
        self.assertIn("vezes de 10 para 3", r)


class Esquema(Base):
    def prop(self, ferramenta, nome):
        return next(d for d in B.definicoes() if d["name"] == ferramenta)["input_schema"]["properties"][nome]

    def test_faixas_aparecem_no_esquema_que_a_ia_recebe(self):
        p = self.prop("criar_lembrete", "minutos")
        self.assertEqual((p["minimum"], p["maximum"]), (0.1, 43200))
        self.assertEqual(self.prop("criar_lembrete", "texto")["maxLength"], 200)
        self.assertEqual(self.prop("guardar_memoria", "tipo")["enum"][0], "fato")

    def test_chave_interna_nao_vaza_e_vira_descricao(self):
        p = self.prop("ler_notas", "limite")
        self.assertNotIn("ao_exceder", p)
        self.assertIn("ajustad", p["description"])
        self.assertEqual((p["minimum"], p["maximum"]), (1, 20))
        for d in B.definicoes():
            for q in d["input_schema"]["properties"].values():
                self.assertNotIn("ao_exceder", q)

    def test_esquema_registrado_nao_e_alterado_pela_publicacao(self):
        B.definicoes()
        self.assertEqual(B.FERRAMENTAS["ler_notas"]["props"]["limite"]["ao_exceder"], "limitar")


class DefesaEmProfundidade(Base):
    def test_funcao_chamada_direto_continua_com_o_proprio_limite(self):
        # fora do corretor (outros módulos) o limite interno segue valendo; o corretor é quem recusa antes
        self.assertIn("0.1 minutos", F.criar_lembrete(-5, "x"))


if __name__ == "__main__":
    unittest.main()
