import os, re, json, shutil, hashlib, subprocess, http.client, unittest
from pathlib import Path
from unittest import mock
import _ambiente as E
import broker as B, catalogo  # noqa: F401
import memoria as MEM, anatomia as AN, maos as MAOS, prefrontal as P, main as MAIN
from test_neuronios import Cerebro

TOKEN = "t" * 40
RAIZ = Path(__file__).resolve().parent.parent / "friday"
ESTATICO = RAIZ / "static" / "maos"
CUBO = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]


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
        return r.status, txt, h


class Base(Cerebro):
    def setUp(self):
        super().setUp()
        MAOS._e.update(gestos={}, ultimo="", t=0.0)
        MAOS._ult_salvo.clear()
        P.ARQ.reiniciar(); P._foco.clear(); P._hab.clear()


class Gestos(Base):
    def test_so_aceita_os_nomes_da_lista_fixa(self):
        for g in MAOS.GESTOS:
            self.assertTrue(MAOS.gesto(g), g)
        for ruim in ("foto", "../x", "", None, 7, ["construir"], "CONSTRUIR", "construir ", "{'x':1}", "a" * 5000):
            self.assertFalse(MAOS.gesto(ruim), ruim)
        self.assertEqual(MAOS.resumo()["gestos"], len(MAOS.GESTOS))

    def test_gesto_entra_no_foco_do_precortex_so_como_rotulo(self):
        MAOS.gesto("construir")
        f = P.foco()
        self.assertEqual([(i["origem"], i["tipo"]) for i in f], [("maos", "construir")])
        self.assertEqual(f[0]["resumo"], "")                                           # nenhum conteúdo: nem imagem, nem pontos da mão

    def test_a_lista_de_gestos_da_pagina_e_do_servidor_e_a_mesma(self):
        js = (ESTATICO / "maos.js").read_text(encoding="utf-8")
        enviados = set(re.findall(r"gesto\('([a-z]+)'", js))
        self.assertTrue(enviados and enviados <= set(MAOS.GESTOS), enviados - set(MAOS.GESTOS))
        self.assertEqual(set(re.findall(r"modo ===? '([a-z]+)'", js)) - {"nenhum"} - set(MAOS.GESTOS) - {"fixar"}, set())


class Modelos(Base):
    def test_salvar_cria_versao_dado_e_neuronio_do_lobo_frontal(self):
        r = MAOS.guardar_modelo("Minha casa", CUBO)
        self.assertEqual((r["ok"], r["blocos"], r["versao"]), (True, 4, 1))
        arqs = list(self.base(".cerebro", "modelos3d", "minha-casa").glob("*.json"))
        self.assertEqual(len(arqs), 1)
        d = json.loads(arqs[0].read_text(encoding="utf-8"))
        self.assertEqual((d["nome"], len(d["blocos"]), d["rascunho"]), ("Minha casa", 4, False))
        nota = MEM._ler_nota(self.base("Memorias") / "Modelo 3D Minha casa.md")
        self.assertEqual(AN.regiao_de(nota["meta"]["tipo"]), "frontal")
        self.assertIn("4 blocos, 2×2×2", nota["corpo"])

    def test_cada_salvamento_e_uma_versao_nova_e_nada_e_sobrescrito(self):
        MAOS.guardar_modelo("casa", CUBO, agora=1000.0)
        MAOS.guardar_modelo("casa", CUBO + [[2, 0, 0]], agora=1010.0)
        MAOS.guardar_modelo("casa", CUBO + [[2, 0, 0], [3, 0, 0]], agora=1020.0)
        pasta = self.base(".cerebro", "modelos3d", "casa")
        arqs = MAOS._versoes(pasta)
        self.assertEqual(len(arqs), 3)
        self.assertEqual(len(MAOS.carregar("casa")), 6)                                 # o mais novo
        self.assertEqual([len(json.loads(a.read_text())["blocos"]) for a in arqs], [4, 5, 6])

    def test_versoes_no_mesmo_segundo_ficam_em_ordem_e_a_mais_nova_vence(self):
        pasta = self.base(".cerebro", "modelos3d", "casa")
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, n in (("2026-01-01_00-00-00.json", 1), ("2026-01-01_00-00-00-2.json", 2), ("2026-01-01_00-00-00-10.json", 10), ("2026-01-01_00-00-01.json", 3), ("lixo.json", 99)):
            (pasta / nome).write_text(json.dumps({"nome": "casa", "blocos": [[i, 0, 0] for i in range(n)]}), encoding="utf-8")
        self.assertEqual([a.name for a in MAOS._versoes(pasta)], ["2026-01-01_00-00-00.json", "2026-01-01_00-00-00-2.json", "2026-01-01_00-00-00-10.json", "2026-01-01_00-00-01.json"])
        self.assertEqual(len(MAOS.carregar("casa")), 3)                                  # 00-00-01 é a mais nova; «lixo.json» é ignorado

    def test_pressa_e_recusada_mas_nome_diferente_passa(self):
        MAOS.guardar_modelo("casa", CUBO, agora=1000.0)
        with self.assertRaisesRegex(ValueError, "calma"):
            MAOS.guardar_modelo("casa", CUBO, agora=1001.0)
        self.assertTrue(MAOS.guardar_modelo("torre", CUBO, agora=1001.0)["ok"])
        self.assertTrue(MAOS.guardar_modelo("casa", CUBO, agora=1006.0)["ok"])

    def test_blocos_invalidos_sao_recusados_sem_gravar_nada(self):
        ruins = [[], None, "x", [[0, 0]], [[0, 0, 0, 0]], [[0.5, 0, 0]], [[True, 0, 0]], [["1", 0, 0]], [[501, 0, 0]], [[0, -501, 0]], [[0, 0, float("nan")]], [{"x": 1}],
                 [[0, 0, 0]] * 0, [[i, 0, 0] for i in range(20001)] if False else [[i % 500, i // 500 % 500, i // 250000] for i in range(20001)]]
        for i, v in enumerate(ruins):
            with self.assertRaises(ValueError, msg=repr(v)[:60]):
                MAOS.guardar_modelo(f"m{i}", v)
        self.assertFalse(self.base(".cerebro", "modelos3d").exists())

    def test_nome_sensivel_ou_com_caminho_nao_escapa_do_cofre(self):
        with self.assertRaises(ValueError):
            MAOS.guardar_modelo("minha senha é 12345678", CUBO)
        r = MAOS.guardar_modelo("../../../etc/passwd", CUBO)
        self.assertTrue(r["ok"])
        for f in self.base(".cerebro", "modelos3d").rglob("*"):
            self.assertTrue(str(f.resolve()).startswith(str(self.base().resolve())), f)
        self.assertFalse(Path(self.dir, "..", "etc").exists())
        self.assertIsNone(MAOS.carregar("../../../etc/passwd/../../x"))

    def test_lista_e_carrega_e_duplicatas_somem(self):
        MAOS.guardar_modelo("Torre", CUBO + CUBO)
        MAOS.guardar_modelo("casa", CUBO)
        self.assertEqual(MAOS.modelos(), ["casa", "Torre"])
        self.assertEqual(len(MAOS.carregar("Torre")), 4)                                # blocos repetidos viram um só
        self.assertIsNone(MAOS.carregar("nao existe")); self.assertIsNone(MAOS.carregar(None)); self.assertIsNone(MAOS.carregar(7))

    def test_cofre_desligado_nao_grava_e_diz_por_que(self):
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            with self.assertRaises(RuntimeError):
                MAOS.guardar_modelo("casa", CUBO)
            self.assertEqual(MAOS.modelos(), [])

    def test_arquivo_adulterado_nao_derruba_o_carregamento(self):
        MAOS.guardar_modelo("casa", CUBO)
        arq = next(self.base(".cerebro", "modelos3d", "casa").glob("*.json"))
        arq.write_text('{"nome": "casa", "blocos": [[9999999, 0, 0]]}', encoding="utf-8")
        self.assertIsNone(MAOS.carregar("casa"))
        arq.write_text("{lixo", encoding="utf-8")
        self.assertIsNone(MAOS.carregar("casa"))
        self.assertEqual(MAOS.modelos(), [])

    def test_por_voz(self):
        with mock.patch.object(MAIN.C, "responder", side_effect=AssertionError("foi parar na IA")):
            self.assertIn("/maos", MAIN.processar("como uso as mãos?"))
            self.assertIn("ainda não salvou", MAIN.processar("meus modelos 3d"))
            MAOS.guardar_modelo("casa", CUBO)
            self.assertIn("casa", MAIN.processar("quais são os meus modelos?"))


class Rotas(Base):
    @classmethod
    def setUpClass(cls):
        MAIN.TOKEN = TOKEN
        cls.srv = MAIN.iniciar_http("127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_pagina_tem_csp_proprio_camera_so_para_si_e_nenhum_script_inline(self):
        st, corpo, h = req(self.porta, "GET", "/maos", token=None)
        self.assertEqual(st, 200)
        csp = h["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'wasm-unsafe-eval'", csp)
        self.assertNotIn("unsafe-eval'", csp.replace("wasm-unsafe-eval", ""))              # nada de eval puro
        self.assertNotIn("'unsafe-inline'", csp.split("style-src")[0])                     # script inline continua proibido
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(h["Permissions-Policy"], "camera=(self), microphone=(), geolocation=()")
        self.assertEqual(h["X-Frame-Options"], "DENY")
        html = corpo.decode()
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>")                          # todo <script> da página tem src
        self.assertNotRegex(html, r"\son[a-z]+\s*=")                                       # e nenhum onclick="..."
        for src in re.findall(r'<script src="([^"]+)"', html):
            self.assertTrue(src.startswith("/static/maos/"), src)                          # nada de CDN: tudo local

    def test_os_painel_principal_continua_com_o_csp_de_sempre(self):
        _, _, h = req(self.porta, "GET", "/", token=None)
        self.assertEqual(h["Content-Security-Policy"], "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")

    def test_estaticos_so_a_lista_fixa_com_o_tipo_certo(self):
        for nome, tipo in MAOS.ESTATICOS.items():
            st, corpo, h = req(self.porta, "GET", f"/static/maos/{nome}", token=None)
            self.assertEqual(st, 200, nome)
            self.assertEqual(h["Content-Type"], tipo, nome)
            self.assertEqual(h["X-Content-Type-Options"], "nosniff")
            self.assertEqual(len(corpo) if isinstance(corpo, bytes) else len(json.dumps(corpo)) > 0, len((ESTATICO / nome).read_bytes()) if isinstance(corpo, bytes) else True)
        for ruim in ("../maos.py", "..%2Fmaos.py", "%2e%2e/maos.py", "maos.py", "hands.js/", "hands.js?x=../x", "hands_solution_wasm_bin.wasm", ".", "", "LICENSE-three.txt/../../.env", "%00hands.js", "SHA256SUMS", "NOTICE.txt"):
            st, *_ = req(self.porta, "GET", "/static/maos/" + ruim, token=None)
            self.assertIn(st, (404, 400), ruim) if "?" not in ruim else self.assertIn(st, (200, 404))
        self.assertEqual(req(self.porta, "GET", "/static/", token=None)[0], 404)
        self.assertEqual(req(self.porta, "GET", "/static/friday/main.py", token=None)[0], 404)

    def test_toda_a_lista_existe_no_disco_e_nada_a_mais_e_servido(self):
        self.assertEqual({p.name for p in ESTATICO.iterdir()} - {"NOTICE.txt", "SHA256SUMS"}, set(MAOS.ESTATICOS))

    def test_host_estranho_e_barrado_dns_rebinding(self):
        for caminho in ("/maos", "/static/maos/maos.js", "/modelos3d"):
            self.assertEqual(req(self.porta, "GET", caminho, host="evil.example")[0], 421, caminho)

    def test_gesto_exige_chave_e_so_aceita_nome_da_lista(self):
        self.assertEqual(req(self.porta, "POST", "/gesto", {"gesto": "construir"}, token=None)[0], 401)
        self.assertEqual(req(self.porta, "POST", "/gesto", {"gesto": "construir"}, token="x" * 40)[0], 401)
        st, j, _ = req(self.porta, "POST", "/gesto", {"gesto": "construir"})
        self.assertEqual((st, j["ok"]), (200, True))
        st, j, _ = req(self.porta, "POST", "/gesto", {"gesto": "tirar_foto"})
        self.assertEqual((st, j["ok"]), (200, False))
        self.assertEqual(MAOS.resumo()["gestos"], 1)
        self.assertEqual(req(self.porta, "POST", "/gesto", bruto=b"x" * 5000)[0], 413)

    def test_modelo_salvar_listar_carregar_pela_api(self):
        self.assertEqual(req(self.porta, "POST", "/modelo3d", {"nome": "casa", "voxels": CUBO}, token=None)[0], 401)
        st, j, _ = req(self.porta, "POST", "/modelo3d", {"nome": "casa", "voxels": CUBO})
        self.assertEqual((st, j["ok"], j["blocos"]), (200, True, 4))
        st, j, _ = req(self.porta, "GET", "/modelos3d")
        self.assertEqual(j["modelos"], ["casa"])
        self.assertEqual(req(self.porta, "GET", "/modelos3d", token=None)[0], 401)
        st, j, _ = req(self.porta, "GET", "/modelo3d?nome=casa")
        self.assertEqual(sorted(map(tuple, j["voxels"])), sorted(map(tuple, CUBO)))
        self.assertEqual(req(self.porta, "GET", "/modelo3d?nome=nao-existe")[0], 404)
        self.assertEqual(req(self.porta, "GET", "/modelo3d?nome=casa", token=None)[0], 401)

    def test_modelo_invalido_grande_ou_sem_json(self):
        self.assertEqual(req(self.porta, "POST", "/modelo3d", {"nome": "x", "voxels": [[0, 0, 0.5]]})[0], 400)
        self.assertEqual(req(self.porta, "POST", "/modelo3d", bruto=b"{lixo")[0], 400)
        self.assertEqual(req(self.porta, "POST", "/modelo3d", bruto=b"[1,2]")[0], 400)
        self.assertEqual(req(self.porta, "POST", "/modelo3d", bruto=b"")[0], 400)
        self.assertEqual(req(self.porta, "POST", "/modelo3d", bruto=b" " * (MAIN.LIM_MODELO + 1))[0], 413)
        with mock.patch.dict(os.environ, {"OBSIDIAN_VAULT": "off"}):
            self.assertEqual(req(self.porta, "POST", "/modelo3d", {"nome": "z", "voxels": CUBO})[0], 503)

    def test_20_mil_blocos_cabem_no_limite_de_tamanho(self):
        vs = [[i % 40, i // 40 % 40, i // 1600] for i in range(20000)]
        corpo = json.dumps({"nome": "grande", "voxels": vs}).encode()
        self.assertLess(len(corpo), MAIN.LIM_MODELO)
        st, j, _ = req(self.porta, "POST", "/modelo3d", bruto=corpo)
        self.assertEqual((st, j.get("blocos")), (200, 20000))


class Arquivos(unittest.TestCase):
    def test_bibliotecas_locais_batem_com_as_do_npm_e_tem_licenca(self):
        hashes = {l.split()[1].split("/")[-1]: l.split()[0] for l in (RAIZ / "static" / "maos" / "SHA256SUMS").read_text().splitlines() if l.strip()}
        for nome, h in hashes.items():
            self.assertEqual(hashlib.sha256((ESTATICO / nome).read_bytes()).hexdigest(), h, nome)
        self.assertTrue((ESTATICO / "LICENSE-three.txt").read_text().startswith("The MIT License"))

    def test_a_pagina_nao_carrega_nada_de_fora(self):
        for arq in (RAIZ / "maos.html", ESTATICO / "maos.js", ESTATICO / "maos_gestos.js"):
            texto = arq.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"https?://(?!127\.0\.0\.1|localhost)[\w.-]+\.(?:com|net|org|io|dev|app)", arq.name)
            for ruim in (r"\beval\(", r"new Function\(", r"document\.write", r"\.innerHTML\b", r"insertAdjacentHTML", r"outerHTML", r"sendBeacon", r"WebSocket", r"XMLHttpRequest", r"importScripts"):
                self.assertIsNone(re.search(ruim, texto), (arq.name, ruim))

    def test_so_o_nome_do_gesto_e_o_modelo_saem_da_pagina(self):
        js = (ESTATICO / "maos.js").read_text(encoding="utf-8")
        envios = re.findall(r"chamar\('([^']+)',", js)                                   # só as chamadas com corpo (POST) mandam algo daqui para a FRIDAY
        self.assertEqual(sorted(set(envios)), ["/gesto", "/modelo3d"])
        todos = set(re.findall(r"chamar\('([^']+)'", js))                                # e as leituras só pedem a lista e os blocos que você mesmo guardou
        self.assertEqual(todos, {"/gesto", "/modelo3d", "/modelos3d", "/modelo3d?nome="})
        self.assertEqual(len(re.findall(r"\bfetch\(", js)), 1)                             # um único ponto de saída
        self.assertNotRegex(js, r"toDataURL|toBlob|getImageData|captureStream|MediaRecorder|ImageCapture")   # nunca transforma o vídeo em imagem para enviar

    def test_camera_so_enquanto_a_pagina_esta_aberta(self):
        js = (ESTATICO / "maos.js").read_text(encoding="utf-8")
        self.assertIn("getTracks().forEach(function (t) { t.stop(); })", js)
        self.assertRegex(js, r"addEventListener\('pagehide'.*fecharCamera")
        self.assertRegex(js, r"visibilitychange")

    def test_o_servidor_nunca_pede_a_camera_das_maos(self):
        for arq in ("main.py", "maos.py", "prefrontal.py", "visao.py"):
            texto = (RAIZ / arq).read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"/maos.*(?:abrir|pedir_camera|window\.open)|abrir_maos|pedir_maos", arq)

    @unittest.skipUnless(shutil.which("node"), "sem node")
    def test_gestos_com_pontos_inventados_no_node(self):
        r = subprocess.run(["node", str(RAIZ.parent / "tests" / "maos_gestos_node.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
