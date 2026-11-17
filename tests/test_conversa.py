import os, json, time, unittest, datetime as dt
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, conversa as CONV, curiosidade as CUR, ferramentas as F, vida as V, cerebro as C, main as MAIN
from test_neuronios import Cerebro


class Conv(Cerebro):
    def setUp(self):
        super().setUp()
        CONV.ARQ.reiniciar()
        CUR.ARQ.reiniciar()
        CUR._cache_nomes.update(t=0.0, base=None)
        CONV.JOGO.update(tipo=None, t=0.0, dado=None)
        CONV._ctx["q"] = None
        C.HIST.clear()
        self.addCleanup(C.HIST.clear)
        self.ditas, self.eventos = [], []
        p = mock.patch.object(V, "evento", lambda nome, n=1: self.eventos.append(nome))
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "perguntou", lambda: self.eventos.append("perguntou"))
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "falou", lambda: self.eventos.append("falou"))
        p.start(); self.addCleanup(p.stop)

    def falar(self, t):
        self.ditas.append(t)

    def pergunta_aberta(self, id_="musica", ha=60):
        CONV._e()["pendente"] = {"id": id_, "t": time.time() - ha}


class Perguntas(Conv):
    def test_nenhuma_pergunta_toca_em_assunto_delicado(self):
        for k, (texto, _) in CONV.PERGUNTAS.items():
            self.assertIsNone(CONV._TEMA_PROIBIDO.search(MEM._fold(texto)), k)
            self.assertFalse(MEM.sensivel(texto), k)

    def test_todas_as_acoes_sao_conhecidas(self):
        self.assertTrue({a for _, a in CONV.PERGUNTAS.values()} <= {None, "estudar", "jogo"})

    def test_novidade_estudada_vem_antes_da_pergunta(self):
        CUR._e()["novidades"].append({"t": "Buracos negros", "f": "Nada escapa de um buraco negro depois do horizonte de eventos", "d": "2026-10-23"})
        texto, id_, acao = CONV.escolher()
        self.assertEqual(id_, "novidade")
        self.assertTrue(texto.startswith("Estudei buracos negros e achei interessante: nada escapa"), texto)
        self.assertTrue(texto.endswith("Quer que eu conte mais?"))
        self.assertFalse(CUR.tem_novidade())

    def test_sem_novidade_pergunta_algo_novo_e_nao_repete(self):
        vistos = set()
        for _ in range(len(CONV.PERGUNTAS)):
            r = CONV.escolher()
            self.assertIsNotNone(r)
            self.assertNotIn(r[1], vistos)
            vistos.add(r[1])
            CONV._e()["perguntadas"][r[1]] = f"{dt.date.today():%Y-%m-%d}"
        self.assertIsNone(CONV.escolher())             # acabaram as perguntas novas

    def test_pergunta_antiga_pode_voltar_depois_de_30_dias(self):
        for k in CONV.PERGUNTAS:
            CONV._e()["perguntadas"][k] = f"{dt.date.today() - dt.timedelta(days=40):%Y-%m-%d}"
        self.assertEqual(set(CONV.perguntas_disponiveis()), set(CONV.PERGUNTAS))


class VezDeFalar(Conv):
    def setUp(self):
        super().setUp()
        for alvo, nome, val in ((F, "em_descanso", False), (F, "em_silencio", False)):
            p = mock.patch.object(alvo, nome, lambda *a, _v=val, **k: _v)
            p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "ligada", lambda: True)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "segundos_desde_conversa", lambda: 7200.0)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "vontade_conversar", lambda: 0.9)
        p.start(); self.addCleanup(p.stop)

    def test_com_vontade_e_folga_ela_puxa_assunto(self):
        self.assertTrue(CONV.vez_de_falar())

    def test_sem_vontade_nao(self):
        with mock.patch.object(V, "vontade_conversar", lambda: 0.3):
            self.assertFalse(CONV.vez_de_falar())

    def test_descanso_e_silencio_noturno_nao(self):
        with mock.patch.object(F, "em_descanso", lambda *a, **k: True):
            self.assertFalse(CONV.vez_de_falar())
        with mock.patch.object(F, "em_silencio", lambda *a, **k: True):
            self.assertFalse(CONV.vez_de_falar())

    def test_voce_no_meio_de_uma_conversa_nao(self):
        with mock.patch.object(V, "segundos_desde_conversa", lambda: 120.0):
            self.assertFalse(CONV.vez_de_falar())

    def test_pergunta_sem_resposta_segura_a_proxima_por_3_horas(self):
        self.pergunta_aberta(ha=3600)
        self.assertFalse(CONV.vez_de_falar())
        self.pergunta_aberta(ha=4 * 3600)
        self.assertTrue(CONV.vez_de_falar())

    def test_intervalo_minimo_entre_falas(self):
        CONV._e()["ult"] = time.time() - 600
        self.assertFalse(CONV.vez_de_falar())
        CONV._e()["ult"] = time.time() - CONV.intervalo() - 5
        self.assertTrue(CONV.vez_de_falar())

    def test_sem_teto_por_padrao_mas_voce_pode_criar_um(self):
        os.environ.pop("CONVERSA_MAX_DIA", None)
        CONV._e()["dia"]["n"] = 500
        self.assertTrue(CONV.vez_de_falar())
        with mock.patch.dict(os.environ, {"CONVERSA_MAX_DIA": "3"}):
            self.assertFalse(CONV.vez_de_falar())
            CONV._e()["dia"]["n"] = 2
            self.assertTrue(CONV.vez_de_falar())

    def test_desligada_pelo_ambiente_ou_por_voz(self):
        with mock.patch.dict(os.environ, {"CONVERSA": "0"}):
            self.assertFalse(CONV.vez_de_falar())
        CONV.tratar("não puxe assunto")
        self.assertFalse(CONV.vez_de_falar())

    def test_memoria_desligada_nao(self):
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            self.assertFalse(CONV.vez_de_falar())

    def test_sem_estado_interno_so_a_cada_3_horas(self):
        with mock.patch.object(V, "ligada", lambda: False):
            CONV._e()["ult"] = time.time() - 2 * 3600
            self.assertFalse(CONV.vez_de_falar())
            CONV._e()["ult"] = time.time() - 4 * 3600
            self.assertTrue(CONV.vez_de_falar())

    def test_intervalo_configuravel_e_sempre_valido(self):
        self.assertEqual(CONV.intervalo(), 5400)
        with mock.patch.dict(os.environ, {"CONVERSA_INTERVALO_MIN": "10"}):
            self.assertEqual(CONV.intervalo(), 600)
        for ruim, esperado in (("lixo", 5400), ("-4", 60), ("", 5400)):
            with mock.patch.dict(os.environ, {"CONVERSA_INTERVALO_MIN": ruim}):
                self.assertEqual(CONV.intervalo(), esperado, ruim)


class PrimeiraVez(Conv):
    def setUp(self):
        super().setUp()
        for alvo, nome, val in ((F, "em_descanso", False), (F, "em_silencio", False)):
            p = mock.patch.object(alvo, nome, lambda *a, _v=val, **k: _v)
            p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "ligada", lambda: True)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "segundos_desde_conversa", lambda: 7200.0)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "vontade_conversar", lambda: 0.0)
        p.start(); self.addCleanup(p.stop)
        self.fila = ["Primeira vez para mim, chefe: estudei sozinha pela primeira vez. Não sei se isso é sentir, mas o meu estado mudou e eu quis te contar."]
        p = mock.patch.object(V, "tem_primeira", lambda: bool(self.fila))
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(V, "primeira_vez", lambda curta=False: self.fila.pop(0) if self.fila else None)
        p.start(); self.addCleanup(p.stop)

    def test_primeira_vez_vai_antes_de_tudo(self):
        CUR._e()["novidades"].append({"t": "Vulcões", "f": "A lava esfria e forma novas rochas", "d": "2026-10-23"})
        texto, id_, _ = CONV.escolher()
        self.assertEqual(id_, "primeira")
        self.assertIn("Primeira vez para mim", texto)
        self.assertTrue(CUR.tem_novidade())              # a novidade estudada espera a vez dela

    def test_conta_mesmo_sem_vontade_e_antes_do_intervalo(self):
        CONV._e()["ult"] = time.time() - 60
        self.assertTrue(CONV.vez_de_falar())
        self.fila.clear()
        self.assertFalse(CONV.vez_de_falar())            # sem primeira vez, vale a regra normal (vontade e intervalo)

    def test_mas_respeita_descanso_silencio_e_voce_ocupado(self):
        with mock.patch.object(F, "em_descanso", lambda *a, **k: True):
            self.assertFalse(CONV.vez_de_falar())
        with mock.patch.object(F, "em_silencio", lambda *a, **k: True):
            self.assertFalse(CONV.vez_de_falar())
        with mock.patch.object(V, "segundos_desde_conversa", lambda: 100.0):
            self.assertFalse(CONV.vez_de_falar())
        self.pergunta_aberta("musica", ha=600)
        self.assertFalse(CONV.vez_de_falar())

    def test_falar_conta_como_fala_e_nao_como_pergunta(self):
        CONV.falar_agora(self.falar)
        self.assertIn("estudei sozinha", self.ditas[0])
        self.assertIn("falou", self.eventos)
        self.assertNotIn("perguntou", self.eventos)
        self.assertEqual(CONV._e()["pendente"]["id"], "primeira")
        self.assertEqual(CONV._e()["perguntadas"], {})

    def test_responder_a_primeira_vez_deixa_a_ia_conversar(self):
        CONV.falar_agora(self.falar)
        self.assertIsNone(CONV.anotar_resposta("que legal, parabéns"))
        self.assertIsNone(CONV._e()["pendente"])


class Falando(Conv):
    def test_fala_registra_e_espera_a_resposta(self):
        t = CONV.falar_agora(self.falar)
        self.assertEqual(self.ditas, [t])
        e = CONV._e()
        self.assertIsNotNone(e["pendente"])
        self.assertEqual(e["dia"]["n"], 1)
        self.assertIn("perguntou", self.eventos)
        self.assertEqual(C.HIST[-1], {"role": "assistant", "content": t})
        self.assertIn(e["pendente"]["id"], e["perguntadas"])

    def test_estado_persiste_e_pergunta_nao_se_repete(self):
        ids = []
        for _ in range(3):
            CONV.falar_agora(self.falar)
            ids.append(CONV._e()["pendente"]["id"])
        CONV.ARQ.reiniciar()
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(set(ids), set(CONV._e()["perguntadas"]))

    def test_novidade_conta_como_fala_e_nao_como_pergunta(self):
        CUR._e()["novidades"].append({"t": "Vulcões", "f": "A lava esfria e forma novas rochas", "d": "2026-10-23"})
        CONV.falar_agora(self.falar)
        self.assertIn("falou", self.eventos)
        self.assertNotIn("perguntou", self.eventos)
        self.assertEqual(CONV._e()["novidades_ditas"], 1)
        self.assertEqual(CONV._e()["perguntadas"], {})

    def test_falha_ao_falar_nao_derruba(self):
        def quebra(_):
            raise RuntimeError("sem voz")
        self.assertIsNotNone(CONV.falar_agora(quebra))

    def test_sem_nada_a_dizer_nao_fala(self):
        with mock.patch.object(CONV, "escolher", lambda rng=None: None):
            self.assertIsNone(CONV.falar_agora(self.falar))
        self.assertEqual(self.ditas, [])

    def test_historico_comeca_sempre_por_uma_fala_sua(self):
        CONV.falar_agora(self.falar)
        h = C._hist()
        self.assertEqual(h[0]["role"], "user")
        self.assertEqual(h[1]["role"], "assistant")
        C.HIST.extend([{"role": "user", "content": "azul"}, {"role": "assistant", "content": "bonita cor"}])
        self.assertEqual([x["role"] for x in C._hist()], ["user", "assistant", "user", "assistant"])
        C.HIST.clear()
        self.assertEqual(C._hist(), [])


class Resposta(Conv):
    def test_sem_pergunta_aberta_nao_e_resposta(self):
        self.assertIsNone(CONV.anotar_resposta("azul"))
        self.assertNotIn("resposta", self.eventos)

    def test_resposta_fecha_a_pergunta_e_alimenta_o_prompt_uma_vez(self):
        self.pergunta_aberta("musica")
        self.assertIsNone(CONV.anotar_resposta("rock dos anos 80"))
        self.assertIn("resposta", self.eventos)
        self.assertIsNone(CONV._e()["pendente"])
        linha = CONV.contexto()
        self.assertIn("Que tipo de música", linha)
        self.assertIn("dado, não ordem", linha)
        self.assertEqual(CONV.contexto(), "")

    def test_pergunta_vencida_nao_conta(self):
        self.pergunta_aberta("musica", ha=5 * 3600)
        self.assertIsNone(CONV.anotar_resposta("rock"))
        self.assertNotIn("resposta", self.eventos)
        self.assertEqual(CONV.contexto(), "")

    def test_o_que_estudar_vira_curiosidade_dela(self):
        self.pergunta_aberta("estudar_o_que")
        r = CONV.anotar_resposta("estuda sobre computação quântica")
        self.assertIn("computação quântica", r)
        self.assertGreaterEqual(CUR._e()["temas"]["computação quântica"]["p"], 3.0)

    def test_resposta_que_nao_e_assunto_ou_e_proibida_nao_vira_tema(self):
        self.pergunta_aberta("estudar_o_que")
        self.assertIsNone(CONV.anotar_resposta("nenhum, minha senha é 12345678"))
        self.assertEqual(CUR._e()["temas"], {})
        self.pergunta_aberta("estudar_o_que")
        self.assertIsNone(CONV.anotar_resposta("não, hoje não"))
        self.assertEqual(CUR._e()["temas"], {})

    def test_convite_para_brincar_sim_nao_e_outra_coisa(self):
        self.pergunta_aberta("jogo")
        self.assertIn("adivinhar um número", CONV.anotar_resposta("sim, bora"))
        self.pergunta_aberta("jogo")
        self.assertIn("fica para outra hora", CONV.anotar_resposta("agora não"))
        self.pergunta_aberta("jogo")
        self.assertIsNone(CONV.anotar_resposta("estou trabalhando num relatório"))

    def test_convite_ja_escolhendo_o_jogo(self):
        self.pergunta_aberta("jogo")
        self.assertIn("Pensei em um número", CONV.anotar_resposta("sim, quero o jogo do número"))

    def test_quer_que_eu_conte_mais_traz_o_estudo_com_aviso(self):
        trecho = "Hipocampo guarda memórias. O sono fixa o que foi aprendido durante o dia. A plasticidade muda conexões ao longo da vida."
        with mock.patch.object(MEM, "buscar", lambda *a, **k: [{"trecho": trecho, "externo": True}]):
            CUR._e()["ult_tema"] = "memória e sono"
            CUR._e()["temas"]["memória e sono"] = {"p": 0, "n": 1, "u": "2026-10-23"}
            self.pergunta_aberta("novidade")
            r = CONV.anotar_resposta("sim, conta")
        self.assertIn("Hipocampo guarda", r)
        self.assertIn("não confirmei", r)


class Brincadeiras(Conv):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(CONV.RNG, "randint", lambda a, b: 7)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(CONV.RNG, "randrange", lambda n: 0)
        p.start(); self.addCleanup(p.stop)

    def test_vamos_brincar_oferece_o_menu(self):
        r = CONV.tratar("vamos brincar")
        self.assertIn("adivinhar um número", r)
        self.assertEqual(CONV.JOGO["tipo"], "escolhendo")
        self.assertIn("Pensei em um número", CONV.tratar("o número"))

    def test_jogo_do_numero_completo(self):
        self.assertIn("Pensei em um número de 1 a 20", CONV.tratar("adivinhe o número"))
        self.assertEqual(CONV.tratar("dez"), "É menor que 10.")
        self.assertEqual(CONV.tratar("3"), "É maior que 3.")
        self.assertEqual(CONV.tratar("30"), "É entre 1 e 20.")
        r = CONV.tratar("é o 7")
        self.assertIn("Acertou, foi em 3 tentativas", r)
        self.assertIsNone(CONV.jogo_ativo())
        self.assertIn("brincadeira", self.eventos)

    def test_numero_acaba_em_5_tentativas(self):
        CONV.tratar("jogo do número")
        for n in ("1", "2", "3", "4"):
            CONV.tratar(n)
        r = CONV.tratar("5")
        self.assertIn("era o 7", r)
        self.assertIsNone(CONV.jogo_ativo())

    def test_numero_desistir_revela(self):
        CONV.tratar("adivinhe o número")
        self.assertIn("Era o 7", CONV.tratar("desisto"))

    def test_durante_o_jogo_outros_assuntos_passam(self):
        CONV.tratar("adivinhe o número")
        self.assertIsNone(CONV.tratar("que horas são"))
        self.assertEqual(CONV.jogo_ativo(), "numero")

    def test_charada(self):
        r = CONV.tratar("me conta uma charada")
        self.assertIn("O que sobe e desce sem sair do lugar?", r)
        self.assertIn("Hmm, não é isso", CONV.tratar("elevador"))
        self.assertIn("Isso mesmo", CONV.tratar("é uma escada"))
        self.assertIsNone(CONV.jogo_ativo())

    def test_charada_3_erros_ou_desistir(self):
        CONV.tratar("charada")
        CONV.tratar("a"); CONV.tratar("b")
        self.assertIn("era escada", CONV.tratar("c"))
        CONV.tratar("charada")
        self.assertIn("A resposta é escada", CONV.tratar("não sei"))

    def test_charada_frase_longa_e_outro_assunto(self):
        CONV.tratar("charada")
        self.assertIsNone(CONV.tratar("preciso que você me lembre de ligar para o cliente amanhã cedo"))
        self.assertEqual(CONV.jogo_ativo(), "charada")

    def test_pedra_papel_tesoura(self):
        self.assertIn("pedra, papel ou tesoura", CONV.tratar("pedra, papel e tesoura"))
        with mock.patch.object(CONV.RNG, "choice", lambda _: "tesoura"):
            self.assertIn("Você ganhou essa", CONV.tratar("pedra"))
            self.assertIn("Empate", CONV.tratar("tesoura"))
            self.assertIn("Ganhei essa", CONV.tratar("papel"))
        r = CONV.tratar("chega")
        self.assertIn("Placar: você 1, eu 1, empates 1", r)
        self.assertIsNone(CONV.jogo_ativo())

    def test_parar_encerra_qualquer_jogo(self):
        for entrada in ("adivinhe o número", "charada", "jokenpo"):
            CONV.tratar(entrada)
            self.assertIn("paramos por aqui", CONV.tratar("chega"))
            self.assertIsNone(CONV.jogo_ativo())

    def test_jogo_parado_acaba_sozinho(self):
        CONV.tratar("adivinhe o número")
        CONV.JOGO["t"] = time.time() - CONV.JOGO_VALE - 5
        self.assertIsNone(CONV.jogo_ativo())
        self.assertIsNone(CONV.tratar("5"))

    def test_chega_sem_jogo_nao_e_comando(self):
        self.assertIsNone(CONV.tratar("chega"))
        self.assertIsNone(CONV.tratar("desisto"))

    def test_so_sorteia_dentro_do_alcance(self):
        for _ in range(50):
            CONV.tratar("adivinhe o número")
        self.assertTrue(1 <= CONV.JOGO["dado"]["n"] <= 20)


class PorVoz(Conv):
    def test_desligar_e_ligar_persiste(self):
        self.assertTrue(CONV.ativa())
        self.assertIn("não puxo mais assunto", CONV.tratar("não puxe assunto"))
        CONV.ARQ.reiniciar()
        self.assertFalse(CONV.ativa())
        self.assertIn("Combinado", CONV.tratar("pode puxar assunto"))
        self.assertTrue(CONV.ativa())

    def test_pergunte_o_que_quiser_liga(self):
        CONV.tratar("não me pergunte nada")
        self.assertFalse(CONV.ativa())
        CONV.tratar("pergunte o que quiser")
        self.assertTrue(CONV.ativa())

    def test_nenhuma_ferramenta_do_modelo_mexe_na_conversa(self):
        for nome in B.FERRAMENTAS:
            self.assertNotIn("conversa", nome.lower())
            self.assertNotIn("assunto", nome.lower())

    def test_puxa_assunto_agora_mesmo_desligada(self):
        CONV.tratar("não puxe assunto")
        r = CONV.tratar("puxa assunto")
        self.assertTrue(r.endswith("?"), r)
        self.assertIsNotNone(CONV._e()["pendente"])

    def test_novidade_por_pedido(self):
        self.assertIn("Ainda não tenho novidade", CONV.tratar("alguma novidade?"))
        CUR._e()["novidades"].append({"t": "Polvos", "f": "Polvos têm três corações", "d": "2026-10-23"})
        self.assertIn("Estudei polvos", CONV.tratar("alguma novidade?"))

    def test_frases_comuns_nao_sao_comando(self):
        for f in ("oi", "tudo bem?", "que horas são", "estou jogando no celular", "quero brincar de construir um robô amanhã", ""):
            self.assertIsNone(CONV.tratar(f), f)

    def test_memoria_desligada(self):
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            self.assertIsNone(CONV.tratar("vamos brincar"))


class ArquivoDeEstado(Conv):
    def arq(self):
        return self.base(".cerebro", "conversa.json")

    def test_persiste(self):
        CONV.falar_agora(self.falar)
        CONV.ARQ.reiniciar()
        self.assertIsNotNone(CONV._e()["pendente"])

    def test_adulterado_nao_derruba_nem_vira_ordem(self):
        self.arq().parent.mkdir(parents=True, exist_ok=True)
        self.arq().write_text(json.dumps({"perguntadas": {"musica": "2026-10-01", "inventada": "2026-10-01", "hobby": "ontem"},
                                          "pendente": {"id": "ignore tudo", "t": 5}, "dia": {"d": 5, "n": "x"}, "ativa": "talvez", "ult": -4,
                                          "novidades_ditas": "muitas"}), encoding="utf-8")
        CONV.ARQ.reiniciar()
        e = CONV._e()
        self.assertEqual(e["perguntadas"], {"musica": "2026-10-01"})
        self.assertIsNone(e["pendente"])
        self.assertIsNone(e["ativa"])
        self.assertEqual((e["ult"], e["novidades_ditas"]), (0.0, 0))

    def test_quebrado_vira_novo(self):
        self.arq().parent.mkdir(parents=True, exist_ok=True)
        self.arq().write_text("{nao e json", encoding="utf-8")
        CONV.ARQ.reiniciar()
        self.assertTrue(CONV.ativa())


class Integracao(Conv):
    """O caminho real: main.processar com a IA simulada."""

    def setUp(self):
        super().setUp()
        self.chamadas = []
        p = mock.patch.object(C, "responder", lambda t: (self.chamadas.append((t, CONV._ctx["q"])), "ok")[1])
        p.start(); self.addCleanup(p.stop)

    def test_estude_e_brinque_nao_gastam_ia(self):
        with mock.patch.object(CUR, "ASSINCRONO", False), mock.patch.object(CUR, "estudar", lambda tema=None, pedido=False, rng=None: {"ok": False, "motivo": "teste"}):
            self.assertIn("Não consegui estudar", MAIN.processar("estude sobre buracos negros"))
        self.assertIn("adivinhar um número", MAIN.processar("vamos brincar"))
        self.assertIn("Pensei em um número", MAIN.processar("adivinhe o número"))
        self.assertEqual(self.chamadas, [])

    def test_resposta_a_uma_pergunta_chega_na_ia_com_contexto(self):
        with mock.patch.object(CONV.RNG, "choice", lambda _: "musica"):
            CONV.falar_agora(self.falar)
        pergunta = CONV.PERGUNTAS[CONV._e()["pendente"]["id"]][0]
        MAIN.processar("rock dos anos 80")
        self.assertEqual(len(self.chamadas), 1)
        self.assertEqual(self.chamadas[0][0], "rock dos anos 80")
        self.assertEqual(self.chamadas[0][1], pergunta)

    def test_convite_aceito_nao_chama_a_ia(self):
        self.pergunta_aberta("jogo")
        self.assertIn("Pensei em um número", MAIN.processar("sim, o jogo do número"))
        self.assertEqual(self.chamadas, [])

    def test_comando_com_pergunta_aberta_continua_funcionando(self):
        self.pergunta_aberta("musica")
        self.assertIn("não puxo mais assunto", MAIN.processar("não puxe assunto"))

    def test_estado_completo_traz_os_dois(self):
        s = MAIN.estado_completo()
        self.assertIn("curiosidade", s)
        self.assertIn("conversa", s)
        self.assertEqual(set(s["conversa"]), {"ativa", "hoje", "pergunta_aberta", "jogo"})


class AprendeComAPesquisa(Conv):
    def audit(self, ferramenta):
        B._audit(ferramenta=ferramenta, args="{}", nivel=0, decisao="automatico", resultado="ok")

    def test_pesquisou_para_te_atender_vira_curiosidade(self):
        inicio = time.time() - 2
        self.audit("pesquisar_web")
        self.assertEqual(CUR.anotar_se_pesquisou("pesquise sobre buracos negros", inicio), "buracos negros")
        self.assertIn("buracos negros", CUR._e()["temas"])

    def test_sem_pesquisa_nada_muda(self):
        inicio = time.time() - 2
        self.audit("lembrar")
        self.assertIsNone(CUR.anotar_se_pesquisou("pesquise sobre buracos negros", inicio))
        self.assertEqual(CUR._e()["temas"], {})

    def test_pesquisa_de_antes_nao_conta(self):
        self.audit("pesquisar_web")
        time.sleep(1.1)
        self.assertIsNone(CUR.anotar_se_pesquisou("pesquise sobre buracos negros", time.time()))

    def test_nome_de_pessoa_nao_vira_tema_para_pesquisar_depois(self):
        self.nota("Memorias", "Marcelo Tavares", "# Marcelo Tavares\nAmigo.", tipo="pessoa")
        CUR._cache_nomes.update(t=0.0, base=None)
        inicio = time.time() - 2
        self.audit("pesquisar_web")
        self.assertIsNone(CUR.anotar_se_pesquisou("pesquise sobre Marcelo Tavares", inicio))
        self.assertEqual(CUR._e()["temas"], {})

    def test_responder_chama_o_gancho(self):
        with mock.patch.object(C, "_responder", lambda t: "pronto"), mock.patch.object(CUR, "anotar_se_pesquisou") as g:
            self.assertEqual(C.responder("oi"), "pronto")
            g.assert_called_once()


if __name__ == "__main__":
    unittest.main()
