"""E2E no Chromium: página das mãos (/maos) com o CSP de verdade, bibliotecas locais e câmera FALSA do Chromium.
Não testa a detecção real de mãos (precisa de uma câmera com mãos): testa tudo em volta — a página carrega sem violar o CSP,
o MediaPipe inicia sem eval, a câmera abre e fecha, e pontos de mão inventados passam pelo MESMO caminho da câmera
(construir → fixar → salvar → reiniciar → carregar), com o servidor e o cofre de verdade.
Rode:  python tests/e2e_maos.py      (precisa do Playwright; salva maos-*.png em E2E_SAIDA)"""
import os, sys, time, json, math
import _ambiente as E
import main as M
import maos as MAOS
from playwright.sync_api import sync_playwright

BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
M.TOKEN = "k" * 40
SAIDA = os.environ.get("E2E_SAIDA", E.TMP)

srv = M.iniciar_http("127.0.0.1", 0)
RAIZ = f"http://127.0.0.1:{srv.server_address[1]}"
falhas = []


def ok(cond, msg):
    print(("✔ " if cond else "✖ ") + msg)
    if not cond:
        falhas.append(msg)


def espera(pg, expr, tempo=10.0):
    """O CSP proíbe eval: espera por polling com evaluate (CDP), não com wait_for_function de texto."""
    fim = time.time() + tempo
    while time.time() < fim:
        if pg.evaluate(expr):
            return True
        time.sleep(0.1)
    raise AssertionError("tempo esgotado: " + expr)


# ---- mãos inventadas (mesma geometria do tests/maos_gestos_node.js): pulso embaixo, dedos para cima
def mao(dedos="", pinca=False, cx=0.5, cy=0.0):
    p = [None] * 21
    p[0] = {"x": cx, "y": 0.9 + cy, "z": 0}
    base, dx = {"i": 5, "m": 9, "a": 13, "p": 17}, {"i": -0.06, "m": -0.02, "a": 0.02, "p": 0.06}
    for f in "imap":
        b, x, est = base[f], cx + dx[f], f in dedos
        p[b] = {"x": x, "y": 0.72 + cy, "z": 0}
        p[b + 1] = {"x": x, "y": 0.6 + cy, "z": 0}
        p[b + 2] = {"x": x, "y": (0.4 if est else 0.74) + cy, "z": 0}
        p[b + 3] = p[b + 2]
    p[1], p[2], p[3] = ({"x": cx - 0.08, "y": 0.85 + cy, "z": 0}, {"x": cx - 0.1, "y": 0.78 + cy, "z": 0}, {"x": cx - 0.1, "y": 0.7 + cy, "z": 0})
    p[4] = {"x": p[8]["x"] + 0.01, "y": p[8]["y"] + 0.01, "z": 0} if pinca else {"x": cx - 0.2, "y": 0.7 + cy, "z": 0}
    return p


def quadro(esq=None, dir=None):
    lms, lado = [], []
    if esq is not None:
        lms.append(esq); lado.append({"label": "Left"})
    if dir is not None:
        lms.append(dir); lado.append({"label": "Right"})
    return {"multiHandLandmarks": lms, "multiHandedness": lado}


class Relogio:
    def __init__(self):
        self.t = 100000.0

    def passo(self, pg, r, dt=50.0):
        self.t += dt
        pg.evaluate("([r,t])=>{window.__maos.injetar(r,t);return 1}", [r, self.t])


def segura(pg, rel, r, ms):
    for _ in range(int(ms / 50) + 1):
        rel.passo(pg, r)


with sync_playwright() as pw:
    nav = pw.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"])
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, permissions=["camera"])
    pg = ctx.new_page()
    consola, erros, pedidos = [], [], []
    pg.on("console", lambda m: consola.append((m.type, m.text)))
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("request", lambda r: pedidos.append(r.url))

    # a chave do painel mora no localStorage da mesma origem
    pg.goto(RAIZ + "/#t=" + M.TOKEN)
    pg.wait_for_selector("#lkt:text-is('ONLINE')", state="attached", timeout=8000)

    # ------------------------------------------------------------ 1) sem câmera: a página e o caminho dos gestos
    consola.clear(); erros.clear(); pedidos.clear()
    resp = pg.goto(RAIZ + "/maos?semcamera")
    csp = resp.headers.get("content-security-policy", "")
    ok("'wasm-unsafe-eval'" in csp and "'unsafe-eval'" not in csp.replace("'wasm-unsafe-eval'", ""), "CSP da página das mãos libera só WebAssembly (nada de eval de texto)")
    ok("camera=(self)" in resp.headers.get("permissions-policy", ""), "só esta origem pode pedir a câmera")
    espera(pg, "window.__maos && window.__maos.pronto === true")
    ok(pg.evaluate("typeof THREE !== 'undefined' && typeof Hands !== 'undefined' && typeof MaosGestos !== 'undefined'"), "three.js, MediaPipe e gestos carregaram dos arquivos locais")
    ok(pg.evaluate("document.getElementById('tres').getContext('webgl2') !== null || document.getElementById('tres').getContext('webgl') !== null"), "WebGL ativo (o 3D desenha)")
    ok(not [e for e in erros], f"nenhum erro de JavaScript ({erros[:2]})")
    ok(not [m for m in consola if m[0] == "error"], f"nenhum erro no console/CSP ({[m for m in consola if m[0] == 'error'][:2]})")

    rel = Relogio()
    nada = quadro()
    rel.passo(pg, nada)
    ok(pg.evaluate("window.__maos.modo") == "nenhum" and pg.evaluate("window.__maos.maos") == 0, "sem mãos: modo «nenhum»")

    # construir: pinça da direita, segura 500 ms, depois arrasta para a esquerda desenhando uma linha
    cx = 0.5
    segura(pg, rel, quadro(None, mao("i", pinca=True, cx=cx)), 600)
    ok(pg.evaluate("window.__maos.modo") == "construir", "pinça da direita → modo «construir»")
    for i in range(24):
        cx -= 0.012
        rel.passo(pg, quadro(None, mao("i", pinca=True, cx=cx)))
    esboco = pg.evaluate("window.__maos.cena.esboco()")
    ok(esboco >= 3, f"o esboço virou uma linha de blocos ({esboco})")
    pg.screenshot(path=os.path.join(SAIDA, "maos-1-construindo.png"))

    # fixar: palma aberta da direita
    segura(pg, rel, quadro(None, mao("imap", cx=0.5)), 150)
    blocos = pg.evaluate("window.__maos.cena.colocados()")
    ok(blocos >= 3 and pg.evaluate("window.__maos.cena.esboco()") == 0, f"palma aberta fixou o esboço em blocos ({blocos})")
    ok("construir" in pg.evaluate("window.__maos.gestos") and "fixar" in pg.evaluate("window.__maos.gestos"), "os nomes dos gestos foram anotados na página")
    espera(pg, "document.getElementById('blocos').textContent !== '0'")
    time.sleep(0.4)
    res = MAOS.resumo()
    ok(res["gestos"] >= 2 and res["ultimo"] in MAOS.GESTOS, f"o servidor recebeu só o NOME dos gestos ({res['gestos']}, último «{res['ultimo']}»)")

    # salvar pelo botão
    pg.fill("#nome", "casa de teste")
    pg.click("#salvar")
    espera(pg, "window.__maos.salvo >= 1")
    ok("casa de teste" in MAOS.modelos(), "«Salvar modelo» guardou o modelo no cofre")
    lista = pg.evaluate("window.__maos.cena.lista()")
    ok(sorted(MAOS.carregar("casa de teste")) == sorted(lista) and len(lista) == blocos, "o servidor devolve exatamente os blocos que estavam na cena")
    espera(pg, "Array.from(document.getElementById('lista').options).some(o=>o.value==='casa de teste')")
    ok(True, "a lista «modelos guardados» da página mostra o modelo")

    # reiniciar: dois punhos segurando 1 s; antes guarda um rascunho (nada é perdido)
    segura(pg, rel, quadro(mao(""), mao("")), 1200)
    espera(pg, "window.__maos.cena.colocados() === 0")
    ok(True, "dois punhos segurando limparam a cena")
    espera(pg, "window.__maos.salvo >= 2")
    ok("rascunho" in MAOS.modelos(), "antes de limpar, ela guardou um rascunho")

    # carregar o modelo de volta
    pg.select_option("#lista", "casa de teste")
    espera(pg, f"window.__maos.cena.colocados() === {blocos}")
    ok(True, "escolher o modelo na lista traz os blocos de volta")
    pg.screenshot(path=os.path.join(SAIDA, "maos-2-carregado.png"))

    # duas palmas: gira o mundo (depois de segurar 1 s)
    segura(pg, rel, quadro(mao("imap", cx=0.3), mao("imap", cx=0.7)), 1300)
    ok(pg.evaluate("window.__maos.modo") == "girar", "duas palmas → modo «girar»")

    ok(all(u.startswith(RAIZ) or u.startswith("blob:") or u.startswith("data:") for u in pedidos), f"nenhum pedido saiu para fora do servidor ({[u for u in pedidos if not u.startswith(RAIZ)][:3]})")

    # ------------------------------------------------------------ 2) com a câmera falsa do Chromium
    consola.clear(); erros.clear(); pedidos.clear()
    pg.goto(RAIZ + "/maos")
    try:
        espera(pg, "window.__maos.pronto === true || window.__maos.erro !== ''", 40)
    except AssertionError:
        pass
    estado = pg.evaluate("({pronto: window.__maos.pronto, erro: window.__maos.erro, camera: window.__maos.camera, quadros: window.__maos.quadros})")
    ok(estado["pronto"] and not estado["erro"], f"o MediaPipe iniciou sem eval, com os arquivos locais ({estado})")
    try:
        espera(pg, "window.__maos.camera === true", 15)
    except AssertionError:
        pass
    ok(pg.evaluate("window.__maos.camera") is True, "a câmera (falsa) abriu")
    try:
        espera(pg, "window.__maos.quadros >= 3", 40)
    except AssertionError:
        pass
    q = pg.evaluate("window.__maos.quadros")
    ok(q >= 3, f"o rastreador processa quadros do vídeo ({q}) e, sem mãos na imagem, fica em «nenhum»: {pg.evaluate('window.__maos.modo')}")
    ok(pg.evaluate("window.__maos.modo") == "nenhum", "imagem de teste sem mãos não aciona nenhum gesto")
    pg.screenshot(path=os.path.join(SAIDA, "maos-3-camera.png"))
    ok(not [e for e in erros], f"nenhum erro de JavaScript com a câmera ({erros[:2]})")
    graves = [m for m in consola if m[0] == "error" and "XNNPACK" not in m[1]]
    ok(not graves, f"nenhum erro de CSP/console com a câmera ({graves[:3]})")
    ok(all(u.startswith(RAIZ) or u.startswith("blob:") or u.startswith("data:") for u in pedidos), "com a câmera, nada saiu do servidor local")
    ok(not [u for u in pedidos if u.endswith("/gesto") or u.endswith("/modelo3d")], "sem mãos e sem salvar, nada foi enviado à FRIDAY")

    # a câmera fecha quando a página sai de cena
    pg.evaluate("()=>{window.dispatchEvent(new Event('pagehide'));return 1}")
    espera(pg, "window.__maos.camera === false || (document.getElementById('video').srcObject === null) || document.getElementById('video').srcObject.getTracks().every(t=>t.readyState==='ended')")
    ok(True, "ao sair da página (pagehide) a câmera foi fechada")

    nav.close()

print()
print("FALHAS:" if falhas else "TUDO OK", *falhas, sep="\n  " if falhas else " ")
sys.exit(1 if falhas else 0)
