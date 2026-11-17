import os, json, datetime as dt, unittest
from unittest import mock
import _ambiente as E
import broker as B, ferramentas as F, android as A, catalogo  # noqa: F401
import telemetria as T, protocolos as P, cerebro as C
import main as M
from test_http import req

BIN, LOG = E.termux_falso()
ENV = {"PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG}


def limpar():
    B.PEND = None
    B._falhas.clear()
    B._bloq = 0.0
    if os.path.exists(B.AUDITORIA):
        os.remove(B.AUDITORIA)
    F._kv_set("silencio_ate", None)
    open(LOG, "w").close()


class Base(unittest.TestCase):
    def setUp(self):
        limpar()
        p = mock.patch.dict(os.environ, ENV)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(limpar)


JSON_CLIMA = {"current": {"temperature_2m": 22.4, "weather_code": 3},
              "daily": {"temperature_2m_max": [27.2], "temperature_2m_min": [18.0], "precipitation_probability_max": [65]}}


def resp(js):
    r = mock.Mock()
    r.raise_for_status = lambda: None
    r.json.return_value = js
    return r


class Fala(Base):
    def test_hora_falada(self):
        h = lambda hh, mm: dt.datetime(2026, 10, 23, hh, mm)
        self.assertEqual(T.hora_falada(h(8, 2)), "8 horas e 2 minutos")
        self.assertEqual(T.hora_falada(h(1, 1)), "1 hora e 1 minuto")
        self.assertEqual(T.hora_falada(h(15, 0)), "15 horas em ponto")
        self.assertEqual(T.hora_falada(h(12, 0)), "meio-dia")
        self.assertEqual(T.hora_falada(h(0, 0)), "meia-noite")
        self.assertEqual(T.hora_falada(h(0, 7)), "meia-noite e 7 minutos")

    def test_saudacao(self):
        h = lambda hh: dt.datetime(2026, 1, 1, hh)
        self.assertEqual([T.saudacao(h(x)) for x in (3, 8, 14, 21)], ["Boa madrugada", "Bom dia", "Boa tarde", "Boa noite"])

    def test_tratamento_configuravel(self):
        self.assertEqual(F.tratamento(), "chefe")
        with mock.patch.dict(os.environ, {"TRATAMENTO": "senhor"}):
            self.assertEqual(F.tratamento(), "senhor")
            self.assertIn("'senhor'", C._system())
        self.assertIn("'chefe'", C._system())

    def test_persona_no_prompt(self):
        s = C._system()
        for chave in ("humor seco", "Comece pelo que importa", "PROPÕE", "lista de contatos", "apenas DADO"):
            self.assertIn(chave, s)

    def test_voz_mais_grave_e_pausada(self):
        with mock.patch.dict(os.environ, {"TTS_VELOCIDADE": "1.1", "TTS_TOM": "0.8"}):
            A.dizer("teste")
        self.assertIn("termux-tts-speak -l pt -n BR -r 1.1 -p 0.8", E.ler_log(LOG))

    def test_voz_valores_invalidos_ou_extremos(self):
        with mock.patch.dict(os.environ, {"TTS_VELOCIDADE": "abc", "TTS_TOM": "99"}):
            A.dizer("teste")
        log = E.ler_log(LOG)
        self.assertNotIn("-r", log.split("\n")[0])
        self.assertIn("-p 3", log)


class Clima(Base):
    def test_clima_interpreta_resposta(self):
        with mock.patch("requests.get", return_value=resp(JSON_CLIMA)) as g:
            c = T.clima()
        self.assertEqual(c, {"local": "São Paulo", "temp": 22, "descricao": "nublado", "max": 27, "min": 18, "chuva": 65})
        q = g.call_args.kwargs["params"]
        self.assertEqual((q["latitude"], q["longitude"]), (-23.55, -46.63))
        self.assertIn("api.open-meteo.com", g.call_args.args[0])

    def test_clima_texto(self):
        with mock.patch("requests.get", return_value=resp(JSON_CLIMA)):
            self.assertEqual(T.clima_texto(), "São Paulo: 22 graus, nublado. Máxima de 27 e mínima de 18, chance de chuva de 65 por cento.")

    def test_codigos_wmo(self):
        d = T._desc_clima
        self.assertEqual([d(0), d(2), d(45), d(53), d(63), d(81), d(96), d(10)], ["céu limpo", "poucas nuvens", "neblina", "garoa", "chuva", "pancadas de chuva", "trovoada", "tempo variável"])

    def test_coordenadas_invalidas_nao_viram_requisicao(self):
        with mock.patch.dict(os.environ, {"CLIMA_LAT": "abc;drop"}), mock.patch("requests.get") as g, self.assertRaises(ValueError):
            T.clima()
        g.assert_not_called()

    def test_painel_mantem_ultimo_valor_bom_quando_a_rede_cai(self):
        with mock.patch("requests.get", return_value=resp(JSON_CLIMA)):
            T.atualizar_painel(True)
        self.assertEqual(T.PAINEL["clima"]["temp"], 22)
        with mock.patch("requests.get", side_effect=OSError("sem rede")):
            T.atualizar_painel(True)  # não levanta
        self.assertEqual(T.PAINEL["clima"]["temp"], 22)
        self.assertIsNotNone(T.PAINEL["metricas"].get("disco"))

    def test_metricas_do_celular(self):
        m = T.metricas()
        self.assertEqual((m["bateria"], m["carregando"]), (80, False))
        with mock.patch.dict(os.environ, {"TERMUX_BATTERY_STATUS": '{"percentage": 55, "plugged": "AC", "status": "CHARGING"}'}):
            self.assertEqual(T.metricas()["carregando"], True)

    def test_leads_painel(self):
        self.assertIsNone(T.leads_painel())  # sem Supabase configurado
        with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "k"}), \
                mock.patch("ferramentas._leads_desde", return_value=[{"nome": "Ana"}, {"nome": "Bruno"}, {"nome": "Caio"}, {"nome": "Duda"}]):
            self.assertEqual(T.leads_painel(), {"n": 4, "nomes": ["Bruno", "Caio", "Duda"]})


class Briefing(Base):
    AGORA = dt.datetime(2026, 10, 23, 8, 2)

    def setUp(self):
        super().setUp()
        for v in ("clima", "leads"):
            T.PAINEL[v] = None
        self.addCleanup(lambda: T.PAINEL.update(clima=None, leads=None))
        from contextlib import closing
        with closing(F._db()) as c:  # agenda limpa a cada teste
            c.execute("delete from lembretes")
            c.commit()

    def com_rede_caida(self):
        return mock.patch("requests.get", side_effect=OSError("sem rede"))

    def test_briefing_completo(self):
        T.PAINEL["clima"] = {"local": "São Paulo", "temp": 22, "descricao": "nublado", "max": 27, "min": 18, "chuva": 65}
        F.criar_lembrete(30, "ligar para o cliente")
        with mock.patch("telemetria.leads_painel", return_value={"n": 2, "nomes": ["Ana", "Bruno"]}):
            b = T.briefing(self.AGORA)
        self.assertTrue(b.startswith("Bom dia, chefe. São 8 horas e 2 minutos de sexta-feira, 23 de outubro."), b)
        self.assertIn("22 graus e nublado; máxima de 27, mínima de 18, com 65 por cento de chance de chuva.", b)
        self.assertIn("Você tem 1 lembrete:", b)
        self.assertIn("ligar para o cliente", b)
        self.assertIn("2 leads novos nas últimas 24 horas: Ana, Bruno.", b)
        self.assertIn("Bateria do celular em 80 por cento.", b)
        self.assertTrue(b.endswith("Todos os sistemas operacionais."))

    def test_briefing_sem_rede_e_sem_lembretes_nao_quebra(self):
        with self.com_rede_caida():
            b = T.briefing(self.AGORA)
        self.assertNotIn("Lá fora", b)
        self.assertIn("Sua agenda está livre", b)
        self.assertIn("Todos os sistemas operacionais.", b)

    def test_chuva_baixa_nao_e_mencionada(self):
        T.PAINEL["clima"] = {"local": "SP", "temp": 30, "descricao": "céu limpo", "max": 32, "min": 20, "chuva": 10}
        b = T.briefing(self.AGORA)
        self.assertIn("máxima de 32, mínima de 20.", b)
        self.assertNotIn("chance de chuva", b)

    def test_alertas(self):
        with self.com_rede_caida(), mock.patch.dict(os.environ, {"TERMUX_BATTERY_STATUS": '{"percentage": 12, "plugged": "UNPLUGGED", "status": "DISCHARGING"}'}):
            self.assertIn("Atenção: bateria baixa.", T.briefing(self.AGORA))
        B.executar("anotar", {"texto": "x"})
        with open(B.AUDITORIA, "a") as f:
            f.write('{"adulterada": 1}\n')
        with self.com_rede_caida():
            self.assertIn("a trilha de auditoria falhou", T.briefing(self.AGORA))

    def test_sem_leads_configurados_nao_fala_de_leads(self):
        with self.com_rede_caida():
            self.assertNotIn("lead", T.briefing(self.AGORA))
        with self.com_rede_caida(), mock.patch("telemetria.leads_painel", return_value={"n": 0, "nomes": []}):
            self.assertIn("Nenhum lead novo", T.briefing(self.AGORA))

    def test_relatorio(self):
        r = T.relatorio()
        self.assertTrue(r.startswith("Relatório de sistemas, chefe. Núcleo online há"))
        self.assertIn("auditoria íntegra", r)
        self.assertIn("Bateria em 80 por cento.", r)
        self.assertIn("chamadas hoje", r)
        self.assertTrue(r.endswith("Sem alertas."))
        F.silenciar(10)
        self.assertIn("Modo foco ativo por mais", T.relatorio())


class ModoFoco(Base):
    def test_silenciar_e_voltar(self):
        self.assertFalse(F.em_silencio())
        self.assertIn("30 minutos", F.silenciar(30))
        self.assertTrue(F.em_silencio())
        self.assertTrue(0 < F.silencio_ativo() <= 1800)
        F.voltar_a_falar()
        self.assertFalse(F.em_silencio())
        self.assertEqual(F.silencio_ativo(), 0)

    def test_limites_e_expiracao(self):
        F.silenciar(10 ** 9)
        self.assertLessEqual(F.silencio_ativo(), 60 * 60 * 24)
        F._kv_set("silencio_ate", time_passado())
        self.assertEqual(F.silencio_ativo(), 0)
        F._kv_set("silencio_ate", "lixo")
        self.assertEqual(F.silencio_ativo(), 0)

    def test_ferramentas_do_foco_no_corretor(self):
        self.assertIn("Modo foco", B.executar("silenciar", {"minutos": 15}))
        self.assertTrue(F.em_silencio())
        B.executar("voltar_a_falar", {})
        self.assertFalse(F.em_silencio())

    def test_falar_proativo_em_foco_so_notifica(self):
        M.ANDROID = True
        self.addCleanup(setattr, M, "ANDROID", False)
        F.silenciar(10)
        M.falar("Novo lead: Ana", proativo=True)
        log = E.ler_log(LOG)
        self.assertIn("termux-notification", log)
        self.assertNotIn("tts-speak", log)
        open(LOG, "w").close()
        M.falar("Resposta ao pedido do usuário")  # resposta direta ao usuário continua falada
        self.assertIn("tts-speak", E.ler_log(LOG))


def time_passado():
    import time
    return time.time() - 100


class Protocolos(Base):
    def test_reconhece_pedidos(self):
        casos = {"bom dia": "briefing", "Bom dia, Friday!": None, "Friday, bom dia": "briefing", "protocolo foco": "foco", "Ativar protocolo FOCO.": "foco",
                 "modo foco": "foco", "boa noite": "noite", "relatório de sistemas": "relatorio", "Friday, relatório de sistemas!": "relatorio",
                 "pode falar": "retomar", "protocolo inexistente": "?", "que horas são": None, "me lembra de ligar": None, "": None}
        for texto, esperado in casos.items():
            with self.subTest(t=texto):
                self.assertEqual(P.achar(texto), esperado)

    def test_foco_executa_via_corretor_e_audita(self):
        r = P.tratar("protocolo foco")
        self.assertIn("Modo foco ativo por uma hora, chefe", r)
        self.assertTrue(F.em_silencio())
        eventos = [(e["ferramenta"], e["decisao"]) for e in B.ultimos(8)]
        self.assertIn(("protocolo:foco", "iniciado"), eventos)
        self.assertIn(("silenciar", "automatico"), eventos)  # o passo passou pelo corretor
        self.assertIn(("protocolo:foco", "executado"), eventos)
        self.assertTrue(B.verificar_auditoria()[0])
        self.assertIn("Voltei a falar", P.tratar("pode falar"))
        self.assertFalse(F.em_silencio())

    def test_briefing_e_relatorio_por_protocolo(self):
        with mock.patch("requests.get", side_effect=OSError):
            self.assertIn("Todos os sistemas operacionais", P.tratar("bom dia"))
        self.assertIn("Relatório de sistemas", P.tratar("protocolo relatorio"))

    def test_exemplo_de_protocolos_do_pacote_e_valido(self):
        """O friday/protocolos.exemplo.json que a documentação manda copiar tem que funcionar de verdade."""
        ex = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "friday", "protocolos.exemplo.json")
        with mock.patch.object(P, "ARQ", ex):
            nomes = set(P.carregar())
            self.assertTrue({"trabalho", "sair"} <= nomes and {"briefing", "foco"} <= nomes)  # os do usuário somam aos padrão
            self.assertEqual(P.achar("modo trabalho"), "trabalho")
            self.assertIn("Modo trabalho, chefe", P.tratar("protocolo trabalho"))
            self.assertTrue(F.em_silencio())  # o passo de ferramenta rodou pelo corretor
            with mock.patch("requests.get", side_effect=OSError):
                self.assertIn("Todos os sistemas operacionais", P.tratar("vou sair"))

    def test_lista_e_desconhecido(self):
        self.assertIn("foco", P.tratar("quais protocolos"))
        r = P.tratar("protocolo zzz")
        self.assertIn("Não tenho esse protocolo", r)
        self.assertIn("briefing", r)
        self.assertIn("Não tenho o protocolo zzz", P.executar("zzz"))

    def test_protocolo_do_usuario_substitui_e_invalidos_sao_ignorados(self):
        arq = os.path.join(E.TMP, "protocolos.json")
        with open(arq, "w", encoding="utf-8") as f:
            json.dump({"Festa": {"desc": "Cena de festa", "apelidos": ["hora da festa"], "passos": [{"falar": "Festa ligada, @tratamento."}]},
                       "foco": {"desc": "Meu foco", "passos": [{"falar": "foco personalizado"}]},
                       "quebrado": {"passos": "não é lista"}, "vazio": {"passos": []}, "perigoso": {"passos": [{"ferramenta": 5}]}}, f)
        with mock.patch.object(P, "ARQ", arq):
            self.assertEqual(P.tratar("hora da festa"), "Festa ligada, chefe.")
            self.assertEqual(P.tratar("protocolo foco"), "foco personalizado")
            self.assertFalse(F.em_silencio())
            nomes = {x["nome"] for x in P.resumo()}
            self.assertTrue({"festa", "foco", "briefing"} <= nomes)
            self.assertFalse(nomes & {"quebrado", "vazio", "perigoso"})
        with mock.patch.object(P, "ARQ", os.path.join(E.TMP, "nao-existe.json")):
            self.assertIn("Modo foco ativo", P.tratar("protocolo foco"))
        with open(arq, "w") as f:
            f.write("{json quebrado")
        with mock.patch.object(P, "ARQ", arq):
            self.assertIn("briefing", {x["nome"] for x in P.resumo()})  # arquivo ruim não derruba os padrões

    def test_passo_pendente_pausa_o_protocolo(self):
        arq = os.path.join(E.TMP, "p2.json")
        with open(arq, "w") as f:
            json.dump({"avisar": {"desc": "x", "passos": [{"ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": "oi"}},
                                                         {"falar": "isto não pode ser dito antes da confirmação"}]}}, f)
        with mock.patch.object(P, "ARQ", arq):
            r = P.tratar("protocolo avisar")
        self.assertIn("pausado em enviar_sms", r)
        self.assertNotIn("não pode ser dito", r)
        self.assertNotIn("sms-send", E.ler_log(LOG))
        self.assertEqual(B.pendente_publico()["tipo"], "voz")

    def test_leitura_externa_no_protocolo_sobe_o_nivel_do_passo_seguinte(self):
        arq = os.path.join(E.TMP, "p3.json")
        with open(arq, "w") as f:
            json.dump({"cruzado": {"desc": "x", "passos": [{"ferramenta": "leads_novos", "args": {}},
                                                          {"ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": "oi"}}]}}, f)
        with mock.patch.object(P, "ARQ", arq), mock.patch("ferramentas._leads_desde", return_value=[]), \
                mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x", "SUPABASE_SERVICE_KEY": "k"}):
            P.tratar("protocolo cruzado")
        self.assertEqual(B.pendente_publico()["tipo"], "pin")  # contaminou: agora só com PIN

    def test_ferramenta_inexistente_no_protocolo_nao_executa_nada(self):
        arq = os.path.join(E.TMP, "p4.json")
        with open(arq, "w") as f:
            json.dump({"hack": {"desc": "x", "passos": [{"ferramenta": "run_shell", "args": {"cmd": "id"}}]}}, f)
        with mock.patch.object(P, "ARQ", arq):
            self.assertIn("Ferramenta desconhecida", P.tratar("protocolo hack"))

    def test_ia_nao_dispara_protocolos(self):
        self.assertNotIn("executar_protocolo", {d["name"] for d in B.definicoes()})
        self.assertIn("listar_protocolos", {d["name"] for d in B.definicoes()})


class ViaPainel(Base):
    @classmethod
    def setUpClass(cls):
        M.TOKEN = "t" * 40
        cls.srv = M.iniciar_http("127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        f = mock.patch.object(M, "falar")
        self.falar = f.start()
        self.addCleanup(f.stop)

    def test_falar_com_protocolo_nao_gasta_ia(self):
        with mock.patch("cerebro.responder") as r, mock.patch("requests.get", side_effect=OSError):
            _, j, _ = req(self.porta, "POST", "/falar", {"texto": "bom dia"})
        r.assert_not_called()
        self.assertIn("Todos os sistemas operacionais", j["resposta"])

    def test_endpoint_protocolo(self):
        self.assertEqual(req(self.porta, "POST", "/protocolo", {"nome": "foco"}, token=None)[0], 401)
        self.assertEqual(req(self.porta, "POST", "/protocolo", {"nome": "nao-existe"})[0], 404)
        self.assertEqual(req(self.porta, "POST", "/protocolo", {"nome": 5})[0], 404)
        self.assertEqual(req(self.porta, "POST", "/protocolo", {})[0], 404)
        s, j, _ = req(self.porta, "POST", "/protocolo", {"nome": "foco"})
        self.assertEqual((s, j["ok"]), (200, True))
        self.assertIn("Modo foco ativo", j["resposta"])
        self.assertTrue(F.em_silencio())

    def test_state_traz_telemetria_do_painel(self):
        T.PAINEL["clima"] = {"local": "SP", "temp": 20, "descricao": "nublado", "max": 25, "min": 15, "chuva": 40}
        self.addCleanup(lambda: T.PAINEL.update(clima=None))
        T.atualizar_painel(True)
        _, j, _ = req(self.porta, "GET", "/state")
        for k in ("metricas", "clima", "leads", "protocolos", "ia", "uptime", "foco", "tratamento", "ferramentas"):
            self.assertIn(k, j)
        self.assertEqual(j["tratamento"], "chefe")
        self.assertGreater(j["ferramentas"], 10)
        self.assertEqual(j["metricas"]["bateria"], 80)
        self.assertEqual({p["nome"] for p in j["protocolos"]} >= {"briefing", "foco", "relatorio"}, True)

    def test_modo_da_ia_aparece_no_estado(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}), mock.patch("cerebro._nuvem", return_value="ok"):
            C.responder("oi")
        self.assertEqual(T.MODO_IA["v"], "nuvem")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}), mock.patch("cerebro._nuvem", side_effect=OSError), mock.patch("cerebro._local", return_value="local"):
            C.responder("oi")
        self.assertEqual(T.MODO_IA["v"], "reserva local")
        with mock.patch("cerebro._nuvem", side_effect=RuntimeError("sem chave")), mock.patch("cerebro._local", return_value="local"):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            C.responder("oi")
        self.assertIn("sem chave", T.MODO_IA["v"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
