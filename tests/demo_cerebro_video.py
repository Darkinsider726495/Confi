"""Gera, a partir do cofre de DEMONSTRAÇÃO, o cérebro da FRIDAY em HTML (interativo) e em vídeo MP4 (quadro a quadro, sem GPU).
Uso:  python tests/demo_cerebro_video.py <pasta-de-saida> [--so-html]
Precisa de Playwright (Chromium) e ffmpeg."""
import os, sys, json, shutil, subprocess, tempfile

SAIDA = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else sys.exit(__doc__)
SO_HTML = "--so-html" in sys.argv
os.makedirs(SAIDA, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="demo-cerebro-")
os.environ.update(FRIDAY_DB=os.path.join(TMP, "t.db"), FRIDAY_AUDITORIA=os.path.join(TMP, "aud.jsonl"), FRIDAY_PLATAFORMA="android", FRIDAY_PIN="4321")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_cerebro
demo_cerebro.criar(os.path.join(TMP, "cofre"))
import neuronios as N
antes = N.grafo()
ids_antes = {n["id"] for n in antes["nos"]}
N.sonhar(True)                                   # a consolidação cria os tópicos recorrentes
depois = N.grafo(trechos=True)
caminho_html = N.exportar_html(os.path.join(SAIDA, "cerebro-friday.html"))
print("HTML:", caminho_html, depois["stats"])
if SO_HTML:
    sys.exit(0)

from playwright.sync_api import sync_playwright
LARG, ALT, FPS, DUR = 720, 1280, 30, 31
novos = [i for i, n in enumerate(depois["nos"]) if n["id"] not in ids_antes]
print("nascem durante o sono:", [depois["nos"][i]["t"] for i in novos])
quadros = os.path.join(TMP, "q")
os.makedirs(quadros)
INIT = """
(function(){let a=12345;Math.random=function(){a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296}})();
"""
T_SONO = 21.0
with sync_playwright() as pw:
    nav = pw.chromium.launch()
    pg = nav.new_page(viewport={"width": LARG, "height": ALT}, device_scale_factor=1)
    pg.add_init_script(INIT)
    pg.goto("file://" + caminho_html + "?manual=1&sem_entrada=0&nota=" + "")
    pg.wait_for_function("!!window.__C")
    # nós que nascem no "sono" ficam escondidos até T_SONO (relógio do próprio motor)
    pg.evaluate("""([novos,t])=>{const D=window.__DADOS,set=new Set(novos);D.nos.forEach((n,i)=>{if(set.has(i))n.nasce_em=t});
        D.arestas.forEach(e=>{if(set.has(e[0])||set.has(e[1]))e[4]=t+.6});window.__C.carregar(D)}""", [novos, T_SONO])
    pg.evaluate("window.__C.camera({yaw:.5,pitch:-.16,zoom:1.1})")
    idx = {n["t"]: i for i, n in enumerate(depois["nos"])}
    lembradas = [idx[t] for t in ("Servidor de retaguarda", "Tailscale", "Backup semanal", "Voz privada", "Ntfy", "Corretor de segurança") if t in idx]
    JS_QUADRO = """([t,nota,q])=>{const C=window.__C;document.getElementById('nota').textContent=nota;
        const S=C.S;let nn=0,ns=0;S.nos.forEach(n=>{if(n.nasc>.5)nn++});S.ar.forEach(e=>{if(S.nos[e[0]].nasc>.5&&S.nos[e[1]].nasc>.5&&(e.nasce_em==null||S.t>=e.nasce_em))ns++});
        document.getElementById('nn').firstChild.textContent=nn;document.getElementById('ns').firstChild.textContent=ns;
        if(q!==null){const i=document.getElementById('q');if(i.value!==q){i.value=q;C.buscar(q)}}
        C.passo(1/30);C.desenhar()}"""
    n_quadros = int(DUR * FPS)
    estado = {"busca": False, "lembrou": False, "zoomout": False, "cinema": False}
    for f in range(n_quadros):
        t = f / FPS
        nota, q = "", None
        if t < 3.5:
            nota = "cada ponto é uma memória"
        elif t < 9:
            nota = "cada ligação é uma sinapse"
        elif t < 12.5:
            alvo = "servidor"
            q = alvo[:max(0, min(len(alvo), int((t - 9.2) / .22)))]
            nota = "buscando no cérebro: " + (q or "…")
        elif t < 18:
            q = ""
            nota = "lembrando: “conferir o backup do servidor”"
            if not estado["lembrou"]:
                estado["lembrou"] = True
                pg.evaluate("([ids,i])=>{window.__C.ativar(ids,6.5);window.__C.foco(i,1.45)}", [lembradas, lembradas[0]])
        elif t < T_SONO:
            nota = "o que acende junto, se liga mais"
            if not estado["zoomout"]:
                estado["zoomout"] = True
                pg.evaluate("()=>{window.__C.camera({zoom:window.__C.S.zoom});window.__C.S.zoomT=1.1;window.__C.auto(true)}")
        elif t < 27:
            nota = "durante o sono, ela cria tópicos do que você repete"
        else:
            nota = "o cérebro cresce com o uso · cofre de demonstração"
            if not estado["cinema"]:
                estado["cinema"] = True
                pg.evaluate("()=>window.__C.cinema(true)")
        pg.evaluate(JS_QUADRO, [t, nota, q])
        pg.screenshot(path=os.path.join(quadros, f"{f:05d}.jpg"), type="jpeg", quality=92)
        if f % 150 == 0:
            print("quadro", f, "/", n_quadros, flush=True)
        if f == int(5 * FPS):
            pg.screenshot(path=os.path.join(SAIDA, "cerebro-friday-1.png"))
        if f == int(14.5 * FPS):
            pg.screenshot(path=os.path.join(SAIDA, "cerebro-friday-2-lembrando.png"))
        if f == int(26 * FPS):
            pg.screenshot(path=os.path.join(SAIDA, "cerebro-friday-3-depois-do-sono.png"))
    nav.close()

mp4 = os.path.join(SAIDA, "cerebro-friday.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(quadros, "%05d.jpg"),
                "-vf", f"fade=t=in:st=0:d=0.8,fade=t=out:st={DUR - 1}:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                "-movflags", "+faststart", mp4], check=True)
print("MP4:", mp4, os.path.getsize(mp4) // 1024, "KB")
shutil.rmtree(TMP, ignore_errors=True)
