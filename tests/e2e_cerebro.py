"""E2E no Chromium: tela do cérebro 3D dentro do painel (HUD), com o CSP de verdade, cofre de demonstração e comando de voz.
Rode:  python tests/e2e_cerebro.py      (precisa do Playwright; salva hud-cerebro-*.png em E2E_SAIDA)"""
import os, sys, time
import _ambiente as E
import main as M
import demo_cerebro
from playwright.sync_api import sync_playwright

BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
os.environ["FRIDAY_VIDA"] = "1"  # neste teste o estado interno fica ligado: a faixa DOP/SER/ACH/ENE precisa aparecer
M.TOKEN = "k" * 40
M.T.clima = lambda: {"local": "São Paulo", "temp": 24, "descricao": "poucas nuvens", "max": 27, "min": 18, "chuva": 30}
M.T.atualizar_painel(True)
M.falar = lambda t, proativo=False: (M.ESTADO.update(estado="falando", friday=t), time.sleep(0.3), M.ESTADO.update(estado="em espera"))[0]
SAIDA = os.environ.get("E2E_SAIDA", E.TMP)
COFRE = os.path.join(E.TMP, "cofre")

srv = M.iniciar_http("127.0.0.1", 0)
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
falhas = []


def ok(cond, msg):
    print(("✔ " if cond else "✖ ") + msg)
    if not cond:
        falhas.append(msg)


def espera(pg, expr, tempo=8.0):
    """O CSP do painel proíbe eval: espera por polling com evaluate (CDP), não com wait_for_function de texto."""
    fim = time.time() + tempo
    while time.time() < fim:
        if pg.evaluate(expr):
            return True
        time.sleep(0.1)
    raise AssertionError("tempo esgotado: " + expr)


# pixels realmente desenhados no canvas (não só "o elemento existe")
PIXELS = """()=>{const c=document.getElementById('cc'),x=c.getContext('2d'),d=x.getImageData(0,0,c.width,c.height).data;let n=0,claros=0;
  for(let i=0;i<d.length;i+=16){n++;if(d[i]+d[i+1]+d[i+2]>150)claros++}return {n,claros,w:c.width,h:c.height}}"""

with sync_playwright() as pw:
    nav = pw.chromium.launch()
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    pg = ctx.new_page()
    consola, erros = [], []
    pg.on("console", lambda m: consola.append(m.text))
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto(URL + "#t=" + M.TOKEN)
    pg.wait_for_selector("#lkt:text-is('ONLINE')", state="attached", timeout=6000)
    pg.wait_for_selector("#boot", state="hidden", timeout=8000)

    # --- cofre vazio: abre sem quebrar ---
    ok(pg.is_visible("#pmem") and pg.is_visible("#bcer"), "painel de Memória traz o botão do cérebro")
    pg.click("#bcer")
    pg.wait_for_selector("#cer", state="visible", timeout=5000)
    pg.wait_for_selector("#cnum:has-text('0 NEURÔNIOS')", timeout=5000)
    ok(True, "cérebro vazio abre e mostra 0 neurônios")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#cer", state="hidden", timeout=3000)
    ok(True, "Esc fecha a tela do cérebro")

    # --- cofre de demonstração ---
    demo_cerebro.criar(COFRE)
    import neuronios as N
    N.sonhar(True)
    N._res.update(t=0.0, v=None)  # o painel guarda os totais por 10 s
    import memoria as MEM
    MEM._resumo.update(t=0.0, v=None)
    pg.reload()
    pg.wait_for_selector("#boot", state="hidden", timeout=8000)
    pg.wait_for_selector("#mn:has-text('neurônios')", timeout=8000)
    import re
    m_ = re.match(r"(\d+) neurônios", pg.inner_text("#mn").lower())
    ok(bool(m_) and int(m_.group(1)) >= 90 and " sinapses" in pg.inner_text("#mn").lower(), f"painel mostra neurônios e sinapses: {pg.inner_text('#mn')!r}")

    pg.click("#bcer")
    pg.wait_for_selector("#cer", state="visible", timeout=5000)
    pg.wait_for_selector("#cleg span", timeout=5000)
    ok(pg.evaluate("CER.S.modo") == "regiao", "abre no modo anatômico (regiões do cérebro)")
    chips = pg.locator("#cleg span").all_inner_texts()
    ok(len(chips) >= 8 and any("frontal" in c.lower() for c in chips) and any("hipocampo" in c.lower() for c in chips), f"legenda mostra as regiões ({len(chips)}): {chips[:4]}")
    occ = [c for c in chips if "occipital" in c.lower()]
    ok(len(occ) == 1 and "vazio" not in occ[0].lower(), f"lobo occipital tem neurônios (as coisas que ela viu): {occ}")
    ok(pg.is_visible("#cvida") and "ENE" in pg.inner_text("#cvida"), f"faixa do estado interno visível: {pg.inner_text('#cvida')!r}")
    ok(pg.evaluate("document.getElementById('cmod').textContent") in ("Tipos", "Regiões"), "botão de modo presente")
    pg.click("#cmod")
    espera(pg, "CER.S.modo==='tipo'", 5)
    tipos = pg.locator("#cleg span").all_inner_texts()
    ok(pg.evaluate("CER.S.modo") == "tipo" and tipos != chips, f"o botão alterna para tipos de memória: {tipos[:3]}")
    pg.click("#cmod")
    espera(pg, "CER.S.modo==='regiao'", 5)
    ok(pg.evaluate("CER.S.modo") == "regiao", "e volta para as regiões")
    ok(pg.locator("#cleg span").count() >= 6, f"legenda com os grupos ({pg.locator('#cleg span').count()})")
    ok("NEURÔNIOS" in pg.inner_text("#cnum") and "SINAPSES" in pg.inner_text("#cnum"), f"contagem no topo: {pg.inner_text('#cnum')!r}")
    ok(pg.evaluate("document.body.style.overflow") == "hidden", "rolagem da página travada atrás do cérebro")
    espera(pg, "document.getElementById('cc').width>100")
    time.sleep(4.8)  # fim da animação de entrada
    px = pg.evaluate(PIXELS)
    ok(px["claros"] > 40, f"o canvas realmente desenhou os neurônios ({px['claros']} pixels claros de {px['n']})")
    ok(pg.evaluate("CER.S.nos.length") > 60 and pg.evaluate("CER.S.ar.length") > 100, "motor 3D carregou nós e sinapses do /cerebro")
    pg.screenshot(path=os.path.join(SAIDA, "hud-cerebro-mobile.png"))

    # --- busca ---
    pg.fill("#cq", "retaguarda")
    ok(pg.evaluate("CER.S.busca&&CER.S.busca.size") >= 1, "busca destaca neurônios")
    pg.fill("#cq", "zzzxxyy")
    ok(pg.evaluate("CER.S.busca&&CER.S.busca.size") == 0, "busca sem resultado não destaca nada (e não quebra)")
    pg.fill("#cq", "retaguarda")
    time.sleep(2.8)  # a câmera centraliza no resultado

    # --- tocar num neurônio abre a nota (texto vem de /nota, com a chave) ---
    c = pg.locator("#cc").bounding_box()
    achou = False
    for dx, dy in [(0, 0), (10, 0), (-10, 0), (0, 10), (0, -10), (18, 0), (-18, 0), (0, 18), (0, -18)]:
        pg.mouse.click(c["x"] + c["width"] / 2 + dx, c["y"] + c["height"] / 2 + dy)
        time.sleep(0.15)
        if pg.is_visible("#cinfo"):
            achou = True
            break
    ok(achou, "tocar no neurônio focado abre o cartão da nota")
    if achou:
        espera(pg, "document.getElementById('cis').textContent.length>8 && document.getElementById('cis').textContent!=='…'", 5)
        ok("retaguarda" in pg.inner_text("#cit").lower() or pg.inner_text("#cit"), f"cartão mostra o título: {pg.inner_text('#cit')!r}")
        ok(len(pg.inner_text("#cis")) > 8, f"e o trecho vindo de /nota: {pg.inner_text('#cis')[:70]!r}")
        ok(pg.evaluate("getComputedStyle(document.getElementById('cleg')).opacity") == "0", "a legenda sai de cima do cartão da nota (mobile)")
        pg.screenshot(path=os.path.join(SAIDA, "hud-cerebro-nota.png"))

    # --- modo cinema: some a interface; tocar na tela traz de volta ---
    pg.click("#cci")
    ok(pg.evaluate("CER.S.cinema") and pg.evaluate("document.getElementById('cer').classList.contains('limpo')"), "Cinema liga a câmera automática e esconde a interface")
    pg.mouse.click(c["x"] + 8, c["y"] + c["height"] - 8)
    ok(not pg.evaluate("document.getElementById('cer').classList.contains('limpo')"), "tocar na tela traz a interface de volta")
    pg.click("#cci")

    # --- evolução em tempo real: nova memória aparece sem reabrir (polling de 3 s) ---
    antes = pg.evaluate("CER.S.nos.length")
    M.processar("lembre que o aquário fica na sala")
    espera(pg, f"CER.S.nos.length>{antes}", 9)
    ok(True, "memória nova nasce como neurônio com a tela aberta")

    # --- sem teto de sinapses: milhares chegam ao painel; o desenho escolhe só quantas traçar por quadro ---
    reqs = []
    pg.on("request", lambda r: reqs.append(r.url))
    ids_ = [n["id"] for n in N.grafo()["nos"]][:100]
    e_ = N._estado()
    agora_ = time.time()
    for a in range(len(ids_)):
        for b in range(a + 1, len(ids_)):
            e_["sin"].setdefault(N._chave(ids_[a], ids_[b]), [0.6 + ((a * 7 + b * 3) % 10) / 10, agora_])
    total_ = N.grafo()["stats"]["sinapses"]
    espera(pg, f"CER.S.ar.length>={total_}", 15)
    ok(total_ > 4000 and pg.evaluate("CER.S.ar.length") == total_, f"o painel recebeu TODAS as sinapses ({total_}), sem corte")
    ok(f"{total_} SINAPSES" in pg.inner_text("#cnum"), f"e conta todas: {pg.inner_text('#cnum')!r}")
    ok(400 <= pg.evaluate("CER.S.orc") <= total_, f"orçamento de traços por quadro: {pg.evaluate('CER.S.orc')}")
    time.sleep(1.5)
    ok(pg.evaluate(PIXELS)["claros"] > 40, "com milhares de sinapses o cérebro continua desenhando")
    time.sleep(3.5)
    ok(any("/cerebro?leve=1" in u for u in reqs), "o painel confere a rede com uma consulta leve a cada 3 s")
    ok(len([u for u in reqs if u.endswith("/cerebro")]) <= 2, f"e só baixa a rede inteira quando algo muda ({len([u for u in reqs if u.endswith('/cerebro')])} vez(es))")

    # --- fechar e reabrir mantém tudo funcionando ---
    pg.click("#cer .x[aria-label='Fechar']")
    pg.wait_for_selector("#cer", state="hidden", timeout=3000)
    ok(pg.evaluate("document.body.style.overflow") == "", "fechar libera a rolagem")
    pg.click("#bcer")
    pg.wait_for_selector("#cer", state="visible", timeout=5000)
    time.sleep(1.2)
    ok(pg.evaluate(PIXELS)["claros"] > 40, "reabrir redesenha o cérebro")
    pg.keyboard.press("Escape")

    # --- comando de voz: 'mostre seu cérebro' abre a tela sozinho ---
    pg.fill("#txt", "Friday, mostre seu cérebro")
    pg.click("#ctl button")
    pg.wait_for_selector("#cer", state="visible", timeout=8000)
    ok(True, "'mostre seu cérebro' abre a tela do cérebro no painel")
    pg.keyboard.press("Escape")
    pg.wait_for_selector("#b[data-estado='em espera']", timeout=8000)

    ok(not [m for m in consola if "Content Security Policy" in m or "Refused" in m], f"nenhum bloqueio do CSP {[m for m in consola if 'Content' in m]}")
    ok(not erros, f"sem erros de JavaScript {erros}")

    # --- desktop + movimento reduzido ---
    d = nav.new_context(viewport={"width": 1280, "height": 860}, reduced_motion="reduce").new_page()
    derros = []
    d.on("pageerror", lambda e: derros.append(str(e)))
    d.goto(URL + "#t=" + M.TOKEN)
    d.wait_for_selector("#boot", state="hidden", timeout=8000)
    d.click("#bcer")
    d.wait_for_selector("#cer", state="visible", timeout=5000)
    time.sleep(1.5)
    ok(d.evaluate(PIXELS)["claros"] > 40, "movimento reduzido: desenha quadro parado, sem animação contínua")
    d.screenshot(path=os.path.join(SAIDA, "hud-cerebro-desktop.png"))
    ok(not derros, f"sem erros de JavaScript no desktop {derros}")
    nav.close()

srv.shutdown(); srv.server_close()
print(f"\n{len(falhas)} falha(s)." if falhas else "\nTudo certo.")
sys.exit(1 if falhas else 0)
