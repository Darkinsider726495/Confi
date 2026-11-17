"""Fase 7 — o pré-córtex visto de fora: API HTTP (servidor próprio da demonstração e o painel da FRIDAY), voz, segurança do pacote e a demonstração rodando de ponta a ponta.

Mapa: 16 tela atualizada por eventos reais (aqui: a API que a tela consulta; no navegador: tests/e2e_precortex.py) · 15 autorização (pela API) · 17 demonstração completa ·
18 compatibilidade com o resto (sem botão de desligar, nada apagado, sem segredo, trabalhadores sem o corretor).
"""
import ast, http.client, json, os, re, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import main as M
from test_pre_cortex_fluxo import BasePC, PEDIDO, SMS
import pre_cortex.api as API
import pre_cortex.fachada as PC

RAIZ = Path(__file__).resolve().parent.parent
PCDIR = RAIZ / "friday" / "pre_cortex"
TOKEN = "k" * 40


def req(porta, metodo, caminho, corpo=None, token=TOKEN, host=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=15)
    c.putrequest(metodo, caminho, skip_host=True)
    c.putheader("Host", host if host is not None else f"127.0.0.1:{porta}")
    if token is not None:
        c.putheader("X-Friday-Token", token)
    dados = json.dumps(corpo).encode() if corpo is not None else b""
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


class ServidorDaDemonstracao(BasePC):
    def setUp(self):
        super().setUp()
        self.h = self.hub()
        self.srv = API.ServidorApi(self.h, TOKEN).iniciar()
        self.addCleanup(self.srv.parar)
        self.p = self.srv.porta

    def test_pagina_sem_chave_dados_com_chave_e_host_conferido(self):
        s, html, hd = req(self.p, "GET", "/precortex", token=None)
        self.assertEqual(s, 200)
        self.assertIn("Mapa dos neurônios", html)
        self.assertIn("default-src 'self'", hd["Content-Security-Policy"])
        self.assertNotIn(TOKEN, html)
        self.assertEqual(req(self.p, "GET", "/precortex/estado", token=None)[0], 401)
        self.assertEqual(req(self.p, "GET", "/precortex/estado", token="errada")[0], 401)
        self.assertEqual(req(self.p, "POST", "/precortex/objetivo", {"texto": PEDIDO}, token=None)[0], 401)
        self.assertEqual(req(self.p, "GET", "/precortex", host="evil.example")[0], 421)
        self.assertEqual(req(self.p, "GET", "/precortex/estado", host="evil.example")[0], 421)

    def test_objetivo_pela_api_e_a_tela_ve_os_eventos_reais(self):                                # área 16
        s, j, _ = req(self.p, "GET", "/precortex/estado")
        self.assertEqual((s, len(j["neuronios"]), j["modo"], j["backend"]), (200, 9, "local", "deterministico"))
        self.assertEqual({n["estado"] for n in j["neuronios"]} - {"ocioso", "recebendo", "processando", "aguardando", "concluido", "bloqueado", "erro"}, set())
        s, r, _ = req(self.p, "POST", "/precortex/objetivo", {"texto": PEDIDO})
        self.assertEqual(s, 200)
        self.assertEqual(self.h.esperar(r["id"], 60), "concluido")
        s, ev, _ = req(self.p, "GET", "/precortex/eventos?desde=0")
        tipos = [e["tipo"] for e in ev["eventos"]]
        for t in ("objetivo_recebido", "interpretacao", "hipoteses", "plano", "critica", "verificacao", "aprendizagem", "concluido"):
            self.assertIn(t, tipos)
        self.assertEqual(ev["seq"], ev["eventos"][-1]["seq"])
        s, ev2, _ = req(self.p, "GET", f"/precortex/eventos?desde={ev['seq']}")
        self.assertEqual(ev2["eventos"], [], "só o que é novo")
        time.sleep(0.4)                                                                              # a saúde dos trabalhadores é relida no máximo a cada 0,35 s
        s, j, _ = req(self.p, "GET", f"/precortex/estado?id={r['id']}")
        det = j["detalhe"]
        self.assertEqual(det["objetivo"]["estado"], "concluido")
        self.assertEqual(len(det["perguntas"]), 12)
        self.assertEqual([p["versao"] for p in det["planos"]], [1, 2])
        estados = {n["nome"]: n for n in j["neuronios"]}
        self.assertGreaterEqual(estados["percepcao"]["concluidas"], 1)        # números que vêm do trabalhador, não da tela
        self.assertEqual(estados["percepcao"]["trabalhador"], "cognicao")
        s, o, _ = req(self.p, "GET", f"/precortex/objetivo?id={r['id']}")
        self.assertEqual(o["objetivo"]["id"], r["id"])
        self.assertEqual(req(self.p, "GET", "/precortex/objetivo?id=pc9999")[0], 404)
        s, nn, _ = req(self.p, "GET", "/precortex/neuronios")
        self.assertEqual(len(nn["neuronios"]), 9)

    def test_controles_autorizar_negar_cancelar_limpar(self):                                    # área 15 pela API
        s, r, _ = req(self.p, "POST", "/precortex/objetivo", {"texto": SMS})
        self.assertEqual(self.h.esperar(r["id"], 60, ate=("aguardando_autorizacao",)), "aguardando_autorizacao")
        a = self.h.dossie(r["id"])["autorizacao"]
        self.assertEqual(req(self.p, "POST", "/precortex/controle", {"acao": "autorizar", "id": r["id"], "versao": a["plano_versao"], "hash": "f" * 32})[0], 409)
        self.assertEqual(self.h.dossie(r["id"])["estado"], "aguardando_autorizacao")
        self.assertEqual(req(self.p, "POST", "/precortex/controle", {"acao": "negar", "id": r["id"]})[0], 200)
        self.assertEqual(self.h.dossie(r["id"])["estado"], "bloqueado")
        s, r2, _ = req(self.p, "POST", "/precortex/objetivo", {"texto": SMS})
        self.h.esperar(r2["id"], 60, ate=("aguardando_autorizacao",))
        self.assertEqual(req(self.p, "POST", "/precortex/controle", {"acao": "cancelar", "id": r2["id"]})[0], 200)
        self.assertEqual(self.h.dossie(r2["id"])["estado"], "cancelado")
        s, lim, _ = req(self.p, "POST", "/precortex/controle", {"acao": "limpar"})
        self.assertTrue(lim["ok"])
        self.assertEqual(req(self.p, "GET", "/precortex/estado")[1]["objetivos"], [])

    def test_nao_ha_rota_nem_acao_que_pare_algo(self):
        for acao in ("parar", "desligar", "encerrar", "shutdown", "kill", "pausar", "reiniciar"):
            self.assertEqual(req(self.p, "POST", "/precortex/controle", {"acao": acao, "id": "pc0001"})[0], 400, acao)
        for rota in ("/parar", "/desligar", "/encerrar", "/sair", "/pausar", "/shutdown", "/stop", "/kill", "/reiniciar", "/precortex/parar", "/precortex/encerrar"):
            self.assertEqual(req(self.p, "POST", rota, {})[0], 404, rota)
            self.assertIn(req(self.p, "GET", rota)[0], (401, 404), rota)
        self.assertEqual(req(self.p, "GET", "/saude")[0], 200, "o servidor continua no ar")

    def test_entradas_ruins(self):
        self.assertEqual(req(self.p, "POST", "/precortex/objetivo", {"texto": ""})[0], 400)
        self.assertEqual(req(self.p, "POST", "/precortex/objetivo", {"texto": "x" * 1001})[0], 400)
        self.assertEqual(req(self.p, "POST", "/precortex/controle", {"acao": "cancelar", "id": "../etc"})[0], 400)
        self.assertEqual(req(self.p, "GET", "/precortex/estado?id=<script>")[0], 200)


class NoPainelDaFriday(BasePC):
    """As mesmas rotas dentro do servidor do painel (main.py), com a chave do painel."""

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
        super().setUp()
        self.h = self.hub()
        p = mock.patch.dict(PC._E, {"hub": self.h, "api": None})
        p.start()
        self.addCleanup(p.stop)

    def test_rotas_no_painel(self):
        s, html, _ = req(self.porta, "GET", "/precortex", token=None)
        self.assertEqual(s, 200)
        self.assertIn("PRÉ-CÓRTEX", html)
        self.assertEqual(req(self.porta, "GET", "/precortex/estado", token=None)[0], 401)
        s, r, _ = req(self.porta, "POST", "/precortex/objetivo", {"texto": PEDIDO, "so_planejar": True})
        self.assertEqual(s, 200, r)
        self.assertEqual(self.h.esperar(r["id"], 60), "plano_pronto")
        s, st, _ = req(self.porta, "GET", "/state")
        self.assertTrue(st["precortex"]["ativo"])
        self.assertEqual(st["precortex"]["por_estado"], {"plano_pronto": 1})

    def test_voz_pelo_processar(self):
        with mock.patch.object(M.C, "responder", side_effect=AssertionError("não devia ir para a IA")):
            r = M.processar("pré-córtex: " + SMS)
            self.assertIn("pc0001", r)
            self.assertEqual(self.h.esperar("pc0001", 60, ate=("aguardando_autorizacao",)), "aguardando_autorizacao")
            self.assertIn("esperando a sua autorização", M.processar("como está o pré-córtex?"))
            self.assertIn("pc0001", M.processar("explique o objetivo pc1"))
            self.assertIn("Neguei", M.processar("nego o plano do objetivo pc1"))

    def test_resumo_nao_cria_o_hub(self):
        with mock.patch.dict(PC._E, {"hub": None, "api": None}):
            self.assertEqual(PC.resumo(), {"ativo": False, "pagina": "/precortex"})
            self.assertIsNone(PC._E["hub"])
            self.assertEqual(PC.ao_iniciar(), [], "sem objetivos gravados, nada nasce na partida")
            self.assertIsNone(PC._E["hub"])


class Pacote(unittest.TestCase):
    """O que vale para o resto da FRIDAY vale para o pacote novo (as varreduras antigas só olham friday/*.py)."""
    CONTROLE = re.compile(r"\b(?:os\.kill|os\.killpg|os\._exit|signal\.|pkill|killall|systemctl|poweroff|reboot)\b|\.supervisor\.pid|parar\.sh|termux-wake-unlock|sys\.exit\(")
    APAGA = re.compile(r"\bos\.remove\(|\.unlink\(|rmtree|shutil\.move|os\.rmdir\(|send2trash")

    def arquivos(self):
        return sorted(PCDIR.glob("*.py"))

    def test_sem_codigo_que_pare_a_friday(self):
        for f in self.arquivos():
            self.assertEqual(self.CONTROLE.findall(f.read_text(encoding="utf-8")), [], f.name)
        # «shutdown» só aparece fechando o servidor/pool DO PRÓPRIO objeto (testes e lançador da demonstração), nunca a partir de uma rota
        for f in self.arquivos():
            for linha in f.read_text(encoding="utf-8").splitlines():
                if re.search(r"\bshutdown\b", linha) and not linha.strip().startswith(("#", '"""')):
                    self.assertRegex(linha, r"self\.(_srv|pool|_pool)\.shutdown\(|cancel_futures", (f.name, linha))

    def test_nada_e_apagado(self):
        for f in self.arquivos():
            self.assertEqual(self.APAGA.findall(f.read_text(encoding="utf-8")), [], f.name)

    def test_tela_sem_botao_de_desligar_sem_eval_e_sem_biblioteca_externa(self):
        html = (RAIZ / "friday" / "precortex.html").read_text(encoding="utf-8")
        for acao in re.findall(r'onclick="([^"]+)"', html):
            self.assertNotRegex(acao, r"deslig|pausar|encerr|desativ|shutdown|power", acao)
        self.assertNotRegex(html, r"\beval\(|new Function|<script src=|https?://")

    def test_sem_segredo_no_pacote(self):
        padrao = re.compile(r"sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{12,}|(?i:(?:api[_-]?key|password|senha|secret)\s*[=:]\s*['\"][^'\"]{6,})")
        for f in list(PCDIR.glob("*")) + [RAIZ / "friday" / "precortex.html"]:
            if f.is_file():
                self.assertEqual(padrao.findall(f.read_text(encoding="utf-8")), [], f.name)
        cfg = json.loads((PCDIR / "config.exemplo.json").read_text(encoding="utf-8"))
        self.assertNotIn("token", json.dumps(cfg).lower().replace("precortex_token", ""))

    def test_neuronios_que_rodam_fora_nao_importam_corretor_tarefas_nem_catalogo(self):
        import pre_cortex.catalogo_neuronios as K
        proibidos = {"broker", "tarefas", "catalogo", "ferramentas", "android", "cerebro", "main", "planejador", "coordenador", "retomada"}
        fora = [n for g in K.GRUPOS_PADRAO.values() for n in g]
        mods = {"worker", "transporte", "contrato", "neuronio", "catalogo_neuronios"} | {K.CLASSES[n][0].split(".")[-1] for n in fora}
        vistos, fila = set(), list(mods)
        while fila:
            m = fila.pop()
            if m in vistos or not (PCDIR / f"{m}.py").exists():
                continue
            vistos.add(m)
            arv = ast.parse((PCDIR / f"{m}.py").read_text(encoding="utf-8"))
            for no in ast.walk(arv):
                if isinstance(no, ast.Import):
                    nomes = [a.name for a in no.names]
                elif isinstance(no, ast.ImportFrom):
                    nomes = [no.module or ""] if no.level == 0 else [a.name for a in no.names] + ([no.module] if no.module else [])
                    if no.level:
                        fila.extend(n for n in nomes if n)
                        continue
                else:
                    continue
                for n in nomes:
                    self.assertNotIn(n.split(".")[0], proibidos, (m, n))


class Demonstracao(unittest.TestCase):
    def rodar(self, modo):
        rel = os.path.join(tempfile.mkdtemp(dir=E.TMP), "rel.json")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FRIDAY_", "OBSIDIAN", "PRECORTEX_"))}
        r = subprocess.run([sys.executable, "-m", "friday.pre_cortex.demo", "--modo", modo, "--relatorio", rel], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=240)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        with open(rel, encoding="utf-8") as f:
            return json.load(f), r.stdout

    def test_demonstracao_local(self):                                                          # área 17
        rel, out = self.rodar("local")
        self.assertTrue(rel["ok"])
        nomes = [x["verificacao"] for x in rel["resultados"]]
        self.assertTrue(any("DETECTADA" in n for n in nomes))
        self.assertTrue(any("experiência mudou a escolha" in n for n in nomes))
        self.assertIn("AUTOCONFERÊNCIA", out)

    def test_demonstracao_distribuida_com_dois_processos(self):                                 # áreas 6 e 17
        rel, out = self.rodar("distribuido")
        self.assertTrue(rel["ok"], rel["resultados"])
        pids = {w["pid"] for w in rel["trabalhadores"].values()}
        self.assertEqual(len(pids), 2)
        self.assertNotIn(rel["pid_hub"], pids)
        self.assertTrue(any("OUTROS processos" in x["verificacao"] and x["ok"] for x in rel["resultados"]))
        self.assertTrue(rel["pasta"].startswith(tempfile.gettempdir()), "a demonstração não toca no FRIDAY real")


if __name__ == "__main__":
    unittest.main()
