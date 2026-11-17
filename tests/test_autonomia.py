import os, io, re, sys, time, signal, socket, subprocess, textwrap, unittest, contextlib
from unittest import mock
import _ambiente as E

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUP = os.path.join(RAIZ, "termux", "supervisor.sh")
PARAR = os.path.join(RAIZ, "termux", "parar.sh")
BIN, LOG = E.termux_falso()

FAKE = textwrap.dedent('''
    import os, sys, time, threading, http.server
    modo = sys.argv[1]
    if modo == "cai":
        sys.exit(3)
    if modo == "mudo":  # batimento em dia, mas sem painel
        while True:
            open(os.environ["FRIDAY_HEARTBEAT"], "w").write(str(time.time()))
            time.sleep(0.4)
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", int(os.environ["HUD_PORTA"])), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    while True:
        if modo == "saudavel":
            open(os.environ["FRIDAY_HEARTBEAT"], "w").write(str(time.time()))
        time.sleep(0.4)
''')


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Vigia(unittest.TestCase):
    def iniciar(self, modo, extra=None):
        self.d = os.path.join(E.TMP, f"sup-{modo}-{time.time_ns()}")
        os.makedirs(self.d)
        fake = os.path.join(self.d, "fake.py")
        with open(fake, "w") as f:
            f.write(FAKE)
        self.log = os.path.join(self.d, "sup.log")
        self.pidf = os.path.join(self.d, "sup.pid")
        env = {**os.environ, "HOME": self.d, "FRIDAY_LOG": self.log, "FRIDAY_PY": sys.executable, "FRIDAY_ARGS": f"{fake} {modo}",
               "CHECK_INTERVAL": "1", "GRACE_SEGUNDOS": "1", "STALE_SEGUNDOS": "2", "BACKOFF_INICIAL": "1", "BACKOFF_MAX": "2",
               "FRIDAY_PIDFILE": self.pidf, "FRIDAY_HEARTBEAT": os.path.join(self.d, "hb"), "HUD_PORTA": str(porta_livre()), **(extra or {})}
        self.env = env
        self.p = subprocess.Popen(["bash", SUP], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.parar)

    def parar(self):
        if self.p.poll() is None:
            self.p.send_signal(signal.SIGTERM)
            try:
                self.p.wait(8)
            except subprocess.TimeoutExpired:
                self.p.kill()
        for m in re.findall(r"\(pid (\d+)\)", self.texto()):
            try:
                os.kill(int(m), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def texto(self):
        try:
            with open(self.log, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def espera(self, cond, ate=15):
        t = time.time()
        while time.time() - t < ate:
            if cond(self.texto()):
                return True
            time.sleep(0.3)
        return False

    def test_processo_saudavel_nao_e_reiniciado_e_encerra_limpo(self):
        self.iniciar("saudavel")
        self.assertTrue(self.espera(lambda t: "iniciada" in t))
        time.sleep(5)  # passa várias verificações
        t = self.texto()
        self.assertEqual(t.count("iniciada"), 1, t)
        self.assertNotIn("travada", t)
        pid = int(re.search(r"\(pid (\d+)\)", t).group(1))
        self.p.send_signal(signal.SIGTERM)
        self.p.wait(8)
        time.sleep(0.5)
        self.assertFalse(os.path.exists(self.pidf))
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)  # o filho morreu junto

    def test_processo_travado_e_reiniciado(self):
        self.iniciar("travado")  # painel responde, mas o batimento não anda
        self.assertTrue(self.espera(lambda t: "travada" in t and t.count("iniciada") >= 2, 20), self.texto())

    def test_processo_que_cai_volta(self):
        self.iniciar("cai")
        self.assertTrue(self.espera(lambda t: "código 3" in t and t.count("iniciada") >= 2, 20), self.texto())

    def test_painel_mudo_tambem_reinicia(self):
        # batimento em dia, mas o painel não responde (porta errada): 3 falhas seguidas
        self.iniciar("mudo", extra={"STALE_SEGUNDOS": "999"})
        self.assertTrue(self.espera(lambda t: "falhas do painel: 3" in t and t.count("iniciada") >= 2, 25), self.texto())

    def test_parada_do_dono_encerra_na_hora_e_a_friday_nao_resiste(self):
        self.iniciar("saudavel", extra={"CHECK_INTERVAL": "30"})            # intervalo longo: a parada não pode esperar por ele
        self.assertTrue(self.espera(lambda t: "iniciada" in t))
        pid = int(re.search(r"\(pid (\d+)\)", self.texto()).group(1))
        sup = self.p.pid
        t0 = time.time()
        r = subprocess.run(["bash", PARAR], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertLess(time.time() - t0, 6, r.stdout)
        self.assertIn("FRIDAY parada", r.stdout)
        self.assertEqual(self.p.wait(5), 0)
        self.assertFalse(os.path.exists(self.pidf))
        for p_ in (sup, pid):                                                # nem o supervisor nem a FRIDAY ficam vivos
            with self.assertRaises(ProcessLookupError):
                os.kill(p_, 0)
        r = subprocess.run(["bash", PARAR], env=self.env, capture_output=True, text=True, timeout=20)
        self.assertIn("não estava rodando", r.stdout)                        # parar de novo não dá erro

    def test_so_uma_copia(self):
        self.iniciar("saudavel")
        self.assertTrue(self.espera(lambda t: "iniciada" in t))
        r = subprocess.run(["bash", SUP], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertIn("já está rodando", r.stdout)


class Diagnostico(unittest.TestCase):
    def rodar(self, **kw):
        import diagnostico as D
        env = {"PATH": BIN + os.pathsep + os.environ["PATH"], "TERMUX_LOG": LOG, "HOME": os.path.join(E.TMP, "home"),
               "ANTHROPIC_API_KEY": "sk-ant-SEGREDO-123", "SUPABASE_SERVICE_KEY": "eyJ-SEGREDO-456", "HUD_PORTA": str(porta_livre())}
        os.makedirs(env["HOME"], exist_ok=True)
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(buf):
            cod = D.rodar(**kw)
        return cod, buf.getvalue()

    def test_basico_no_celular(self):
        cod, s = self.rodar()
        self.assertIn("✔ Termux:API", s)
        self.assertIn("✔ Bateria / status do celular", s)
        self.assertIn("✔ Voz (alto-falante)", s)
        self.assertIn("✔ PIN das ações críticas", s)
        self.assertIn("✖ Início automático", s)  # HOME de teste não tem ~/.termux/boot/friday
        self.assertIn("2 cadastrado(s)", s)
        self.assertEqual(cod, 1)
        self.assertIn("1 ponto(s)", s)

    def test_nunca_imprime_segredos(self):
        _, s = self.rodar()
        for segredo in ("SEGREDO", "sk-ant", "4321"):
            self.assertNotIn(segredo, s)
        with open(os.environ["FRIDAY_DIAG_ARQ"], encoding="utf-8") as f:
            salvo = f.read()
        self.assertNotIn("SEGREDO", salvo)
        self.assertIn("Termux:API", salvo)

    def test_tudo_certo_com_boot_instalado(self):
        boot = os.path.join(E.TMP, "home", ".termux", "boot")
        os.makedirs(boot, exist_ok=True)
        open(os.path.join(boot, "friday"), "w").close()
        cod, s = self.rodar()
        self.assertIn("✔ Início automático", s)
        self.assertEqual(cod, 0, s)
        self.assertIn("Tudo certo.", s)

    def test_completo_testa_nuvem_internet_e_localizacao(self):
        with mock.patch("cerebro._nuvem", return_value="ok"), mock.patch("internet.pesquisar_web", return_value="1. x"), \
                mock.patch("internet.ler_pagina", return_value="texto " * 30), mock.patch("ferramentas.leads_novos", return_value="Nenhum"):
            os.environ["SUPABASE_URL"] = "https://x.supabase.co"
            self.addCleanup(os.environ.pop, "SUPABASE_URL", None)
            _, s = self.rodar(completo=True)
        for esperado in ("✔ IA na nuvem", "✔ Pesquisa na internet", "✔ Leitura de página", "✔ Localização", "✔ Reconhecimento de voz do Android", "✔ Leads (Supabase)"):
            self.assertIn(esperado, s)

    def test_falha_de_ia_aparece_como_erro_sem_derrubar(self):
        with mock.patch("cerebro._nuvem", side_effect=RuntimeError("sem chave")), mock.patch("internet.pesquisar_web", return_value="1. x"), \
                mock.patch("internet.ler_pagina", return_value="texto " * 30):
            _, s = self.rodar(completo=True)
        self.assertIn("✖ IA na nuvem (1 chamada) — sem chave", s)

    def test_fora_do_celular(self):
        import diagnostico as D
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}), contextlib.redirect_stdout(buf):
            D.rodar()
        self.assertIn("• Termux:API", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
