import os, json, http.client, stat, unittest
from unittest import mock
import _ambiente as E
import broker as B
import main as M

BIN, LOG = E.termux_falso()
TOKEN = "t" * 40


def req(porta, metodo, caminho, corpo=None, token=TOKEN, host=None, bruto=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    c.putrequest(metodo, caminho, skip_host=True)
    c.putheader("Host", host if host is not None else f"127.0.0.1:{porta}")
    if token is not None:
        c.putheader("X-Friday-Token", token)
    dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else b"")
    c.putheader("Content-Length", str(len(dados)))
    c.endheaders(dados)
    r = c.getresponse()
    txt = r.read()
    h = dict(r.getheaders())
    c.close()
    try:
        return r.status, json.loads(txt), h
    except ValueError:
        return r.status, txt.decode(errors="replace"), h


class Painel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        M.TOKEN = TOKEN
        cls.srv = M.iniciar_http("127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        B.PEND = None
        B._falhas.clear()
        B._bloq = 0.0
        if os.path.exists(B.AUDITORIA):
            os.remove(B.AUDITORIA)
        open(LOG, "w").close()
        p = mock.patch.dict(os.environ, {"PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG})
        p.start()
        self.addCleanup(p.stop)
        f = mock.patch.object(M, "falar")  # não fala de verdade
        self.falar = f.start()
        self.addCleanup(f.stop)

    # ---- acesso ----
    def test_saude_sem_chave(self):
        s, j, _ = req(self.porta, "GET", "/saude", token=None)
        self.assertEqual((s, j), (200, {"ok": True}))

    def test_state_exige_chave(self):
        self.assertEqual(req(self.porta, "GET", "/state", token=None)[0], 401)
        self.assertEqual(req(self.porta, "GET", "/state", token="errada")[0], 401)
        s, j, _ = req(self.porta, "GET", "/state")
        self.assertEqual(s, 200)
        for k in ("estado", "sistema", "lembretes", "pendente", "auditoria", "auditoria_ok", "android"):
            self.assertIn(k, j)

    def test_post_exige_chave(self):
        for caminho in ("/falar", "/confirmar", "/confirmar_voz", "/cancelar", "/ouvir"):
            with self.subTest(c=caminho):
                self.assertEqual(req(self.porta, "POST", caminho, {}, token=None)[0], 401)
                self.assertEqual(req(self.porta, "POST", caminho, {}, token="x")[0], 401)

    def test_host_estranho_e_recusado_dns_rebinding(self):
        for h in ("evil.com", f"evil.com:{self.porta}", "192.168.0.9:8080", ""):
            with self.subTest(h=h):
                self.assertEqual(req(self.porta, "GET", "/state", host=h)[0], 421)
                self.assertEqual(req(self.porta, "POST", "/falar", {"texto": "oi"}, host=h)[0], 421)
        self.assertEqual(req(self.porta, "GET", "/state", host=f"localhost:{self.porta}")[0], 200)

    def test_html_e_cabecalhos_de_seguranca(self):
        s, corpo, h = req(self.porta, "GET", "/", token=None)
        self.assertEqual(s, 200)
        self.assertIn("FRIDAY", corpo)
        self.assertNotIn(TOKEN, corpo)  # a chave nunca vai no HTML
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["Cache-Control"], "no-store")

    def test_rota_desconhecida_e_metodo_options(self):
        self.assertEqual(req(self.porta, "GET", "/etc/passwd", token=None)[0], 404)
        self.assertEqual(req(self.porta, "POST", "/nada", {})[0], 404)
        self.assertEqual(req(self.porta, "OPTIONS", "/falar", token=None)[0], 501)  # sem CORS: página de outro site não consegue chamar

    # ---- /falar ----
    def test_falar_responde_e_fala(self):
        with mock.patch("cerebro.responder", return_value="São três da tarde.") as r:
            s, j, _ = req(self.porta, "POST", "/falar", {"texto": "  que horas são? "})
        self.assertEqual((s, j["ok"], j["resposta"], j["voce"]), (200, True, "São três da tarde.", "que horas são?"))
        r.assert_called_once_with("que horas são?")

    def test_falar_valida_entrada(self):
        for corpo in ({}, {"texto": ""}, {"texto": "   "}, {"texto": 5}, {"texto": "a" * 1001}, {"texto": ["x"]}):
            with self.subTest(c=str(corpo)[:30]):
                self.assertEqual(req(self.porta, "POST", "/falar", corpo)[0], 400)
        self.assertEqual(req(self.porta, "POST", "/falar", bruto=b"{nao json")[0], 400)
        self.assertEqual(req(self.porta, "POST", "/falar", bruto=b"[1,2]")[0], 400)
        self.assertEqual(req(self.porta, "POST", "/falar", bruto=b"x" * 5000)[0], 413)

    def test_falar_sem_falar_em_voz_alta(self):
        with mock.patch("cerebro.responder", return_value="ok"):
            req(self.porta, "POST", "/falar", {"texto": "oi", "falar": False})
        self.falar.assert_not_called()

    # ---- confirmações ----
    def test_botao_confirmo_executa_nivel_2(self):
        B.executar("enviar_sms", {"contato": "mae", "texto": "oi"})
        pid = req(self.porta, "GET", "/state")[1]["pendente"]["id"]       # o painel manda o id da pendência que está na tela
        s, j, _ = req(self.porta, "POST", "/confirmar_voz", {"id": pid})
        self.assertTrue(j["ok"])
        self.assertIn("SMS enviado", j["msg"])
        self.assertIn("sms-send", E.ler_log(LOG))

    def test_botao_confirmo_sem_id_ou_com_id_de_outra_pendencia_nao_executa(self):
        B.executar("enviar_sms", {"contato": "mae", "texto": "oi"})
        antigo = B.pendente_publico()["id"]
        B.executar("ligar", {"contato": "mae"})                              # a IA propôs outra coisa por cima
        for corpo in ({}, {"id": ""}, {"id": antigo}, {"id": 7}, {"id": "../x"}):
            with self.subTest(corpo=corpo):
                _, j, _ = req(self.porta, "POST", "/confirmar_voz", corpo)
                self.assertFalse(j["ok"])
        self.assertNotIn("sms-send", E.ler_log(LOG))
        self.assertNotIn("telephony-call", E.ler_log(LOG))
        self.assertIsNotNone(B.pendente_publico())

    def test_botao_confirmo_nao_libera_nivel_3(self):
        t = B.Turno()
        t.contaminado = True
        B.executar("enviar_sms", {"contato": "mae", "texto": "oi"}, t)
        _, j, _ = req(self.porta, "POST", "/confirmar_voz", {"id": B.pendente_publico()["id"]})
        self.assertIn("PIN", j["msg"])
        self.assertNotIn("sms-send", E.ler_log(LOG))
        self.assertEqual(req(self.porta, "POST", "/confirmar", {"pin": "0000"})[1]["ok"], False)
        self.assertEqual(req(self.porta, "POST", "/confirmar", {"pin": "4321"})[1]["ok"], True)
        self.assertIn("sms-send", E.ler_log(LOG))

    def test_confirmar_sem_pendencia(self):
        self.assertEqual(req(self.porta, "POST", "/confirmar_voz", {})[1], {"ok": False, "msg": "Nada pendente."})

    def test_cancelar(self):
        B.executar("ligar", {"contato": "mae"})
        req(self.porta, "POST", "/cancelar", {})
        self.assertIsNone(B.pendente_publico())
        self.assertNotIn("telephony-call", E.ler_log(LOG))

    def test_pedido_de_confirmacao_pelo_texto_nao_passa_pelo_llm(self):
        B.executar("ligar", {"contato": "mae"})
        with mock.patch("cerebro.responder") as r:
            _, j, _ = req(self.porta, "POST", "/falar", {"texto": "confirmo"})
        r.assert_not_called()
        self.assertIn("Ligando", j["resposta"])

    # ---- voz nativa do Android ----
    def test_ouvir_usa_reconhecimento_do_android(self):
        with mock.patch("cerebro.responder", return_value="são 15h") as r:
            _, j, _ = req(self.porta, "POST", "/ouvir", {})
        self.assertEqual((j["voce"], j["resposta"]), ("que horas são", "são 15h"))
        r.assert_called_once_with("que horas são")

    def test_ouvir_silencio(self):
        with mock.patch.dict(os.environ, {"TERMUX_SPEECH_TO_TEXT": " "}):
            self.assertEqual(req(self.porta, "POST", "/ouvir", {})[1]["ok"], False)

    def test_ouvir_com_comando_falhando(self):
        with mock.patch.dict(os.environ, {"TERMUX_FALHA": "1"}):
            self.assertEqual(req(self.porta, "POST", "/ouvir", {})[0], 502)


class Token(unittest.TestCase):
    def test_token_persistente_e_privado(self):
        arq = os.environ["FRIDAY_TOKEN_ARQ"]
        if os.path.exists(arq):
            os.remove(arq)
        t = M.carregar_token()
        self.assertGreaterEqual(len(t), 32)
        self.assertEqual(M.carregar_token(), t)
        self.assertEqual(stat.S_IMODE(os.stat(arq).st_mode), 0o600)

    def test_token_curto_demais_e_regerado(self):
        arq = os.environ["FRIDAY_TOKEN_ARQ"]
        with open(arq, "w") as f:
            f.write("123")
        self.assertGreaterEqual(len(M.carregar_token()), 32)


if __name__ == "__main__":
    unittest.main(verbosity=2)
