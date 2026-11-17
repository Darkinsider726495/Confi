"""E2E no Chromium: painel do pré-córtex no HUD (barras de cada vontade, «tudo ao mesmo tempo», metas) e o atalho para as mãos.
Rode:  python tests/e2e_prefrontal.py      (precisa do Playwright; salva hud-prefrontal.png em E2E_SAIDA)"""
import os, sys, time
import _ambiente as E
import main as M
import prefrontal as PFC
from playwright.sync_api import sync_playwright

BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
M.TOKEN = "k" * 40
M.T.clima = lambda: {"local": "São Paulo", "temp": 24, "descricao": "poucas nuvens", "max": 27, "min": 18, "chuva": 30}
M.T.atualizar_painel(True)
SAIDA = os.environ.get("E2E_SAIDA", E.TMP)
srv = M.iniciar_http("127.0.0.1", 0)
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
falhas = []


def ok(cond, msg):
    print(("✔ " if cond else "✖ ") + msg)
    if not cond:
        falhas.append(msg)


def espera(pg, expr, tempo=8.0):
    fim = time.time() + tempo
    while time.time() < fim:
        if pg.evaluate(expr):
            return True
        time.sleep(0.1)
    raise AssertionError("tempo esgotado: " + expr)


# ela adota as duas metas dela e pensa uma vez (vontades decididas cada uma por si)
PFC.semear()
ok(len(PFC.resumo()["metas"]) == 2, "ela adotou duas metas próprias")
r = PFC.pensar()
dec = r["decisao"]
print("   decisão desta rodada:", dec["agir"], "· simultâneo:", dec["simultaneo"])

with sync_playwright() as pw:
    nav = pw.chromium.launch()
    ctx = nav.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    erros, consola = [], []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: consola.append((m.type, m.text)))
    pg.goto(URL + "#t=" + M.TOKEN)
    pg.wait_for_selector("#lkt:text-is('ONLINE')", state="attached", timeout=8000)
    pg.wait_for_selector("#boot", state="hidden", timeout=8000)
    espera(pg, "document.getElementById('ppfc').style.display === ''")
    ok(pg.is_visible("#ppfc"), "o painel do pré-córtex aparece")
    linhas = pg.evaluate("Array.from(document.querySelectorAll('#pci li')).map(li=>[li.children[0].textContent, li.querySelector('i').style.width, li.children[2].textContent])")
    nomes = [l[0] for l in linhas]
    ok(nomes == list(PFC.IMPULSOS), f"uma barra para cada vontade, todas ao mesmo tempo ({nomes})")
    ok(all(l[1].endswith("%") for l in linhas), f"cada barra tem a sua largura ({[l[1] for l in linhas]})")
    ok(all(l[2] in ("agir", "quieta", "não posso") for l in linhas), "cada vontade mostra a sua própria decisão")
    ok(pg.inner_text("#pcn").lower() in ("tudo ao mesmo tempo", "agindo", "atenta"), f"o título diz o que ela está fazendo: «{pg.inner_text('#pcn')}»")
    ok("quem escolhe sou eu" in pg.inner_text("#pcd").lower(), "o painel diz que quem decide é ela")
    metas = pg.evaluate("Array.from(document.querySelectorAll('#pcm li')).map(li=>li.textContent)")
    ok(len(metas) == 2 and all("%" in m for m in metas), f"as metas dela aparecem com o progresso ({metas})")
    sist = pg.inner_text("#sist")
    ok("Mãos" in sist, "«Mãos» aparece em Sistemas")
    ok(pg.is_visible("#bmaos"), "o atalho para as mãos está no painel")
    # nada novo no painel pode desligar ou travar nada: não há botão de parar
    textos = [b.lower() for b in pg.evaluate("Array.from(document.querySelectorAll('#ppfc button')).map(b=>b.textContent)")]
    ok(not any(w in t for t in textos for w in ("desligar", "parar", "pausar", "apagar")), f"o painel não tem botão de desligar/parar ({textos})")
    pg.screenshot(path=os.path.join(SAIDA, "hud-prefrontal.png"), full_page=False)
    with pg.expect_navigation():
        pg.click("#bmaos")
    ok(pg.url.endswith("/maos"), "o atalho abre a página das mãos")
    ok(not erros, f"nenhum erro de JavaScript ({erros[:2]})")
    ok(not [m for m in consola if m[0] == "error"], f"nenhum erro no console ({[m for m in consola if m[0] == 'error'][:2]})")
    nav.close()

print()
print("FALHAS:" if falhas else "TUDO OK", *falhas, sep="\n  " if falhas else " ")
sys.exit(1 if falhas else 0)
