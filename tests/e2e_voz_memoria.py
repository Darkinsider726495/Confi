"""E2E no Chromium: voz privada (microfone falso -> /transcrever -> servidor de voz simulado) e painel de Memória (cofre do Obsidian).
Rode:  python tests/e2e_voz_memoria.py      (precisa do Playwright; usa o CSP de verdade, sem bypass)"""
import os, sys, time, wave, math, random, struct
import _ambiente as E
import main as M
from playwright.sync_api import sync_playwright

BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
M.TOKEN = "k" * 40
M.T.clima = lambda: {"local": "São Paulo", "temp": 24, "descricao": "poucas nuvens", "max": 27, "min": 18, "chuva": 30}
M.T.atualizar_painel(True)
M.C.responder = lambda t: f"Resposta da IA: {t}"
M.falar = lambda t, proativo=False: (M.ESTADO.update(estado="falando", friday=t), time.sleep(0.3), M.ESTADO.update(estado="em espera"))[0]

# servidor de voz simulado: guarda o que o painel mandou e responde com falas combinadas
recebidos, falas = [], []
M.VR.stt_ativo = lambda: True
M.VR.tts_ativo = lambda: False
M.VR.transcrever = lambda dados, tipo="audio/wav": (recebidos.append(dados), falas.pop(0) if falas else "")[1]

SAIDA = os.environ.get("E2E_SAIDA", E.TMP)

# áudio falso do microfone: 1 s de silêncio, 1,6 s de "fala" (tom modulado + ruído), 3 s de silêncio; repete
WAV = os.path.join(E.TMP, "mic-falso.wav")
SR = 48000
random.seed(1)
with wave.open(WAV, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    quadros = []
    for i in range(int(SR * 5.6)):
        t = i / SR
        if 1.0 <= t < 2.6:
            v = 0.35 * math.sin(2 * math.pi * 180 * t) * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * t)) + random.uniform(-0.05, 0.05)
        else:
            v = random.uniform(-0.002, 0.002)
        quadros.append(struct.pack("<h", int(max(-1, min(1, v)) * 32767)))
    w.writeframes(b"".join(quadros))

srv = M.iniciar_http("127.0.0.1", 0)
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
falhas = []


def ok(cond, msg):
    print(("✔ " if cond else "✖ ") + msg)
    if not cond:
        falhas.append(msg)


with sync_playwright() as pw:
    nav = pw.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", f"--use-file-for-fake-audio-capture={WAV}"])
    ctx = nav.new_context(viewport={"width": 390, "height": 900}, permissions=["microphone"])
    pg = ctx.new_page()
    consola, erros = [], []
    pg.on("console", lambda m: consola.append(m.text))
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto(URL + "#t=" + M.TOKEN)
    pg.wait_for_selector("#lkt:text-is('ONLINE')", state="attached", timeout=6000)
    pg.wait_for_selector("#boot", state="hidden", timeout=8000)

    # --- painel de Memória ---
    ok(pg.is_visible("#pmem"), "painel de Memória aparece quando o cofre está ligado")
    ok("0 neurônios" in pg.inner_text("#mn").lower(), f"cofre novo está vazio: {pg.inner_text('#mn')!r}")
    ok("Nada guardado" in pg.inner_text("#mr"), "painel convida a guardar a primeira memória")
    ok("Obsidian" in pg.inner_text("#sist") and "Memória" in pg.inner_text("#sist"), "linha 'Memória' nos Sistemas")

    pg.fill("#txt", "Friday, lembre que meu café é sem açúcar")
    pg.click("#ctl button")
    pg.wait_for_selector("#f:has-text('Guardei na memória')", timeout=6000)
    ok(True, "'lembre que…' guarda sem chamar a IA e confirma")
    ok(not [c for c in consola if "Resposta da IA" in c], "a IA não foi chamada para guardar")
    pg.wait_for_selector("#mn:has-text('1 neurônio ')", timeout=6000)
    ok("café" in pg.inner_text("#mr").lower(), f"a memória nova aparece no painel: {pg.inner_text('#mr')!r}")
    arqs = [f for f in os.listdir(os.path.join(E.TMP, "cofre", "FRIDAY", "Memorias"))] if os.path.isdir(os.path.join(E.TMP, "cofre", "FRIDAY", "Memorias")) else []
    ok(len(arqs) == 1 and arqs[0].endswith(".md"), f"arquivo .md criado no cofre: {arqs}")
    pg.wait_for_selector("#b[data-estado='em espera']", timeout=6000)

    pg.fill("#txt", "o que você lembra sobre café?")
    pg.click("#ctl button")
    pg.wait_for_selector("#f:has-text('açúcar')", timeout=6000)
    ok(True, "'o que você lembra sobre…' responde com a memória guardada")
    pg.wait_for_selector("#b[data-estado='em espera']", timeout=6000)

    # --- voz privada ---
    ok(pg.is_visible("#vpw") and pg.is_checked("#vp"), "opção 'Voz privada' visível e ligada quando o servidor de voz está configurado")
    ok("privado (faster-whisper)" in pg.inner_text("#sist"), "Sistemas mostra o ouvido privado (faster-whisper)")
    falas.append("lembre que o servidor de casa se chama Hermes")
    pg.click("#bt")
    pg.wait_for_selector("#f:has-text('Guardei na memória')", timeout=15000)
    ok(len(recebidos) == 1, "o áudio foi ao servidor de voz uma vez")
    wav = recebidos[0]
    ok(wav[:4] == b"RIFF" and wav[8:12] == b"WAVE", "áudio enviado é um WAV")
    taxa = int.from_bytes(wav[24:28], "little")
    dur = (len(wav) - 44) / (2 * taxa)
    ok(taxa == 16000 and 1.2 <= dur <= 4.0, f"WAV a 16 kHz com ~{dur:.1f}s de fala (recorte pelo detector de voz)")
    ok("Hermes" in pg.inner_text("#v"), f"texto reconhecido aparece como pedido do usuário: {pg.inner_text('#v')!r}")
    pg.wait_for_selector("#mn:has-text('2 neurônios')", timeout=6000)
    ok(True, "a fala virou memória (2 neurônios no painel)")
    pg.wait_for_selector("#b[data-estado='em espera']", timeout=6000)
    ok(pg.inner_text("#bt") .startswith("Falar") and not pg.evaluate("!!document.querySelector('#bt.on')"), "microfone fecha depois do pedido (modo toque)")

    # servidor de voz recusa -> mensagem clara, microfone fecha
    M.VR.transcrever = lambda dados, tipo="audio/wav": (_ for _ in ()).throw(RuntimeError("servidor de voz fora do ar ou fora de alcance"))
    pg.click("#bt")
    pg.wait_for_selector("#vm:has-text('fora do ar')", timeout=15000)
    ok(True, "servidor de voz fora do ar: avisa em vez de falhar calado")
    pg.screenshot(path=os.path.join(SAIDA, "hud-memoria-mobile.png"), full_page=True)

    # --- desligar a voz privada volta ao navegador ---
    pg.uncheck("#vp")
    ok("navegador" in pg.inner_text("#nota").lower() or "Google" in pg.inner_text("#nota"), "desmarcar 'Voz privada' volta ao aviso do navegador")
    pg.check("#vp")

    ok(not [c for c in consola if "Content Security Policy" in c or "Refused" in c], f"nenhum bloqueio do CSP {[c for c in consola if 'Content' in c]}")
    ok(not erros, f"sem erros de JavaScript {erros}")

    # --- desktop ---
    d = nav.new_context(viewport={"width": 1280, "height": 960}, permissions=["microphone"]).new_page()
    d.goto(URL + "#t=" + M.TOKEN)
    d.wait_for_selector("#lkt:text-is('ONLINE')", timeout=6000)
    d.wait_for_selector("#boot", state="hidden", timeout=8000)
    time.sleep(1)
    d.screenshot(path=os.path.join(SAIDA, "hud-memoria-desktop.png"))
    nav.close()

srv.shutdown(); srv.server_close()
print(f"\n{len(falhas)} falha(s)." if falhas else "\nTudo certo.")
sys.exit(1 if falhas else 0)
