"""Teste ponta a ponta do painel no Chromium (precisa do Playwright). Rode:  python tests/e2e_hud.py
Simula o reconhecimento de voz do navegador, que o Chromium sem cabeça não tem."""
import os, re, sys, time, json
import _ambiente as E
import broker as B
import main as M
from unittest import mock
from playwright.sync_api import sync_playwright

BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
M.TOKEN = "k" * 40
M.T.clima = lambda: {"local": "São Paulo", "temp": 24, "descricao": "poucas nuvens", "max": 27, "min": 18, "chuva": 30}  # sem rede no teste
M.T.atualizar_painel(True)
chamadas = []
M.C.responder = lambda t: (chamadas.append(t), f"Resposta para: {t}")[1]
def _falar_falso(t, proativo=False):  # imita o tempo de fala, sem voz de verdade
    M.ESTADO.update(estado="falando", friday=t)
    time.sleep(0.4)
    M.ESTADO["estado"] = "em espera"


M.falar = _falar_falso
srv = M.iniciar_http("127.0.0.1", 0)
URL = f"http://127.0.0.1:{srv.server_address[1]}/"
SAIDA = os.environ.get("E2E_SAIDA", E.TMP)
FAKE_SR = """
window.__recs=[];
window.SpeechRecognition=window.webkitSpeechRecognition=class{constructor(){window.__recs.push(this)} start(){this.on=true} abort(){this.on=false;this.onend&&this.onend()} stop(){this.abort()}};
window.__fala=(t)=>{const r=window.__recs[window.__recs.length-1];const x=[{transcript:t}];x.isFinal=true;r.onresult({resultIndex:0,results:[x]})};
"""
falhas = []


def ok(cond, msg):
    print(("✔ " if cond else "✖ ") + msg)
    if not cond:
        falhas.append(msg)


with sync_playwright() as pw:
    nav = pw.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])   # câmera de mentira: o Chromium inventa a imagem
    ctx = nav.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True)  # só para o Playwright avaliar textos; o CSP real é conferido no fim
    ctx.add_init_script(FAKE_SR)
    pg = ctx.new_page()
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))

    # 1. sem chave
    pg.goto(URL)
    ok(pg.is_visible("#sc") and not pg.is_visible("#app"), "sem chave: mostra a orientação e esconde o painel")

    # 2. com chave no fragmento: guarda e limpa a URL
    pg.goto(URL + "#t=" + M.TOKEN)
    pg.wait_for_function("getComputedStyle(document.getElementById('boot')).display!='none'", timeout=4000)
    ok(True, "sequência de inicialização aparece na primeira abertura")
    pg.wait_for_function("document.getElementById('lkt').textContent=='ONLINE'", timeout=5000)
    pg.wait_for_function("getComputedStyle(document.getElementById('boot')).display=='none'", timeout=6000)
    ok(True, "sequência de inicialização termina sozinha")
    ok("t=" not in pg.url, "a chave sai da barra de endereços")
    ok(pg.evaluate("localStorage.getItem('friday_t')") == M.TOKEN, "a chave fica guardada no navegador")
    ok(pg.inner_text("#e").strip().lower() in ("em espera", "iniciando"), f"estado exibido: {pg.inner_text('#e')}")

    # 3. texto digitado
    pg.fill("#txt", "que horas são?")
    pg.click("#ctl button")
    pg.wait_for_function("document.getElementById('f').textContent.startsWith('Resposta para')", timeout=5000)
    ok(pg.inner_text("#f") == "Resposta para: que horas são?", "resposta do pedido digitado aparece")
    ok("Você: que horas são?" in pg.inner_text("#v"), "pedido do usuário aparece")

    # 4. escuta contínua com palavra de ativação (reconhecimento simulado)
    pg.wait_for_function("ocupado===false", timeout=5000)  # o painel só volta a ouvir depois que ela termina de falar
    pg.wait_for_function("window.__recs.length>=1", timeout=8000)   # sem tocar em nada: a escuta liga sozinha
    pg.wait_for_function("document.getElementById('bc').textContent.includes('Escutando')", timeout=5000)
    ok(pg.evaluate("window.__recs.length") == 1 and "Escutando" in pg.inner_text("#bc"), "escuta contínua inicia sozinha, sem botão")
    n = len(chamadas)
    pg.evaluate("window.__fala('bom dia pessoal')")
    time.sleep(0.5)
    ok(len(chamadas) == n, "fala sem 'Friday' é ignorada")
    pg.evaluate("window.__fala('Friday, que dia é hoje')")
    pg.wait_for_function("document.getElementById('f').textContent.includes('que dia é hoje')", timeout=5000)
    ok(chamadas[-1] == "que dia é hoje", f"'Friday, ...' envia só o pedido: {chamadas[-1]!r}")
    pg.wait_for_function("!document.getElementById('e').textContent.includes('pensando')", timeout=5000)
    time.sleep(1.8)  # a escuta reinicia depois de ela falar
    pg.evaluate("window.__fala('Fraidei')")
    ok("Pode falar" in pg.inner_text("#vm"), "só a palavra de ativação abre uma janela de escuta")
    pg.evaluate("window.__fala('anota comprar café')")
    pg.wait_for_function("document.getElementById('f').textContent.includes('anota comprar café')", timeout=5000)
    ok(chamadas[-1] == "anota comprar café", "frase seguinte dentro da janela é enviada")
    # sem botão de desligar: o aviso «Escutando sempre» não é clicável e nenhum controle pausa ou encerra a FRIDAY
    ok(pg.evaluate("getComputedStyle(document.getElementById('bc')).pointerEvents") == "none", "«Escutando sempre» é só um aviso: tocar nele não faz nada")
    pg.wait_for_function("ocupado===false && window.__recs[window.__recs.length-1].on===true", timeout=8000)   # ela terminou de falar e voltou a escutar
    time.sleep(1.2)
    n_antes = pg.evaluate("window.__recs.length")
    pg.evaluate("escutar()")   # nem chamando a função: ela já está escutando, nada muda
    time.sleep(1.5)
    ok(pg.evaluate("window.__recs.length") == n_antes and "Escutando" in pg.inner_text("#bc"), "não existe como pausar a escuta pela tela")
    botoes = pg.evaluate("[...document.querySelectorAll('button,[role=button],a')].map(b=>(b.textContent+' '+(b.title||'')+' '+(b.getAttribute('aria-label')||'')).trim())")
    ok(not [b for b in botoes if re.search(r"deslig|paus|parar\b|encerr|sair|power|off\b", b, re.I)], f"nenhum botão desliga, pausa ou encerra a FRIDAY {botoes}")
    pg.evaluate("window.__recs[window.__recs.length-1].onend()")   # o navegador encerrou a escuta por conta própria
    pg.wait_for_function("window.__recs[window.__recs.length-1].on===true", timeout=5000)
    ok(True, "se a escuta cair, ela volta sozinha")
    pg.evaluate("(()=>{const r=window.__recs[window.__recs.length-1];r.onerror({error:'not-allowed'})})()")
    n_recs = pg.evaluate("window.__recs.length")
    time.sleep(4.5)
    ok(pg.evaluate("window.__recs.length") == n_recs and "microfone" in pg.inner_text("#vm"), "sem permissão do microfone: avisa e não fica em laço")
    pg.mouse.click(5, 300)   # um toque libera a nova tentativa
    pg.wait_for_function("window.__recs.length>%d" % n_recs, timeout=6000)
    ok(True, "um toque na tela libera a permissão e ela volta a ouvir")
    ok(pg.evaluate("localStorage.getItem('friday_escuta')") is None, "o painel não guarda mais nenhuma «pausa» da escuta")

    # 4b. painel cinematográfico: medidores, reator, tema, protocolos, auditoria, XSS
    pg.wait_for_function("/^\\d+%/.test(document.getElementById('gt-ram').textContent)", timeout=5000)
    ok(float(pg.evaluate("parseFloat(document.getElementById('ga-ram').style.strokeDashoffset)")) < 213.63, "medidor de memória preenchido")
    ok(pg.evaluate("document.getElementById('b').dataset.estado") in ("em espera", "falando", "pensando", "ouvindo"), "reator recebe o estado")
    ok(pg.evaluate("document.getElementById('ao').textContent").startswith("●"), "indicador de auditoria íntegra")
    ok(pg.inner_text("#ct") == "24°" and "poucas nuvens" in pg.inner_text("#cd"), f"painel de clima: {pg.inner_text('#clima')!r}")
    ok(pg.locator("#sist li").count() >= 5, "lista de sistemas")
    ok("Curiosidade" in pg.inner_text("#sist") and "Conversa" in pg.inner_text("#sist"), "Sistemas mostra a curiosidade e a conversa dela")
    ok(pg.locator("#prot .chip").count() >= 5, "chips de protocolo")
    ok(not pg.is_visible("#pleads"), "painel de leads escondido sem Supabase")
    ok(pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "sem rolagem horizontal no celular")
    tema0 = pg.evaluate("document.body.dataset.tema")
    pg.click("#tm") if pg.is_visible("#tm") else pg.evaluate("tema()")
    tema1 = pg.evaluate("document.body.dataset.tema")
    ok(tema0 == "azul" and tema1 == "ouro" and pg.evaluate("localStorage.getItem('friday_tema')") == "ouro", "tema azul/dourado alterna e fica guardado")
    pg.screenshot(path=os.path.join(SAIDA, "hud-mobile-ouro.png"), full_page=True)
    pg.evaluate("tema('azul')")
    # XSS: o texto da resposta nunca vira HTML
    M.C.responder = lambda t: (chamadas.append(t), "<img src=x onerror=\"window.__xss=1\"><b>negrito</b>")[1]
    pg.fill("#txt", "teste xss")
    pg.click("#ctl button")
    pg.wait_for_function("document.getElementById('f').textContent.includes('negrito')", timeout=5000)
    ok(pg.locator("#f img, #f b").count() == 0 and pg.evaluate("window.__xss") is None, "resposta entra como texto, nunca como HTML")
    M.C.responder = lambda t: (chamadas.append(t), f"Resposta para: {t}")[1]
    # protocolo pelo chip
    pg.click("#prot .chip:text-is('relatorio')")
    pg.wait_for_function("document.getElementById('v').textContent.startsWith('Protocolo: relatorio')", timeout=5000)
    pg.wait_for_function("document.getElementById('f').textContent.length>20 && document.getElementById('f').textContent!='…'", timeout=5000)
    ok("relat" in pg.inner_text("#f").lower() or "sistema" in pg.inner_text("#f").lower(), f"chip de protocolo executa: {pg.inner_text('#f')[:60]!r}")
    pg.wait_for_function("document.getElementById('b').dataset.estado=='em espera'", timeout=5000)
    time.sleep(0.8)

    # 5. ação pendente de nível 2: botão Confirmo
    B.PEND = None
    B.executar("enviar_sms", {"contato": "mae", "texto": "chego às 19h"})
    pg.wait_for_selector("#pend", state="visible", timeout=5000)
    ok(pg.is_visible("#bv"), "nível 2: botão Confirmo visível")
    pg.wait_for_function("document.getElementById('b').dataset.alerta=='1'", timeout=5000)
    ok(True, "reator entra em alerta com ação pendente")
    pg.click("#bv")
    time.sleep(1.2)
    ok("sms-send" in E.ler_log(LOG), "clicar em Confirmo envia o SMS")
    pg.screenshot(path=os.path.join(SAIDA, "hud-mobile.png"), full_page=True)

    # 6. nível 3: só PIN
    B.PEND = None
    t = B.Turno(); t.contaminado = True
    B.executar("enviar_sms", {"contato": "mae", "texto": "x"}, t)
    pg.wait_for_selector("#pend", state="visible", timeout=5000)
    time.sleep(0.8)
    ok(not pg.is_visible("#bv") and pg.is_visible("#pin"), "nível 3: sem botão Confirmo, só campo de PIN")
    pg.fill("#pin", "0000")
    pg.click("text=Confirmar com PIN")
    pg.wait_for_function("document.getElementById('pm').textContent.includes('incorreto')", timeout=5000)
    ok(True, "PIN errado é recusado")
    pg.fill("#pin", "4321")
    pg.click("text=Confirmar com PIN")
    time.sleep(1.2)
    ok(E.ler_log(LOG).count("sms-send") == 2, "PIN certo libera a ação")
    ok("t=" not in pg.url, "URL continua limpa")
    pg.wait_for_function("document.querySelectorAll('#aud li').length>=3", timeout=5000)
    ok("enviar_sms" in pg.inner_text("#aud") and "pin_errado" in pg.inner_text("#aud"), "feed de auditoria mostra as decisões do corretor")

    # 7. chave errada guardada
    ctx2 = nav.new_context(bypass_csp=True)
    p2 = ctx2.new_page()
    p2.goto(URL + "#t=chave-errada-1234")
    p2.wait_for_function("document.getElementById('f').textContent.includes('Chave inválida')", timeout=5000)
    ok(True, "chave errada: avisa em vez de falhar calado")

    # 7b. um navegador que ainda tem a «pausa» antiga guardada: ela é apagada e a escuta liga do mesmo jeito
    ctx5 = nav.new_context(bypass_csp=True)
    ctx5.add_init_script("try{localStorage.setItem('friday_escuta','pausada')}catch(_){}")
    ctx5.add_init_script(FAKE_SR)
    p5 = ctx5.new_page()
    p5.goto(URL + "#t=" + M.TOKEN)
    p5.wait_for_function("window.__recs.length>=1", timeout=8000)
    ok(p5.evaluate("localStorage.getItem('friday_escuta')") is None, "pausa antiga guardada no navegador é descartada e ela escuta mesmo assim")

    # 7c. olhos: a câmera do painel só abre quando a FRIDAY pede, tira uma foto e fecha
    os.environ["VISAO_FONTE"] = "navegador"
    M.VIS.ASSINCRONO = False
    M.VIS.ESPERA_NAVEGADOR = 4.0
    visto = []
    M.C.ver_imagem = lambda dados, mime, instrucao, max_tokens=450, fracao=1.0: (visto.append((dados, mime, instrucao)), "CENA: Uma mesa com um notebook e uma caneca azul.\nCOISAS: notebook; caneca azul")[1]
    ESPIA_CAM = """
    window.__cam=[];window.__camPedidos=[];window.__negar=false;
    (()=>{const g=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia=async c=>{window.__camPedidos.push(JSON.stringify(c));if(window.__negar)throw new DOMException('negado','NotAllowedError');const s=await g(c);window.__cam.push(s);return s}})();
    """
    for velha in (pg, p2, p5):   # os painéis de antes ainda estão abertos: com vários abertos, só um abre a câmera (testado abaixo)
        velha.close()
    ctxv = nav.new_context(viewport={"width": 390, "height": 844}, bypass_csp=True)
    ctxv.add_init_script(FAKE_SR)
    ctxv.add_init_script(ESPIA_CAM)
    pv = ctxv.new_page()
    pv.goto(URL + "#t=" + M.TOKEN)
    pv.wait_for_function("document.getElementById('lkt').textContent=='ONLINE'", timeout=5000)
    pv.wait_for_function("document.querySelectorAll('#sist li').length>=5", timeout=5000)
    time.sleep(2)
    ok(pv.evaluate("window.__camPedidos.length") == 0, "o painel aberto não liga a câmera sozinho")
    ok("Visão" in pv.inner_text("#sist"), "Sistemas mostra a visão (lobo occipital)")
    pv.evaluate("document.getElementById('boot').click()")
    pv.fill("#txt", "olhe")
    pv.click("#ctl button")
    pv.wait_for_function("document.getElementById('f').textContent.includes('notebook')", timeout=15000)
    ok("notebook" in pv.inner_text("#f"), f"ela olhou pela câmera do painel e contou: {pv.inner_text('#f')[:70]!r}")
    ok(len(visto) == 1 and visto[0][0][:3] == b"\xff\xd8\xff" and visto[0][1] == "image/jpeg" and len(visto[0][0]) > 500, "a foto chegou ao modelo de visão como JPEG de verdade")
    ok("DADO" in visto[0][2], "o modelo recebeu a regra de que o texto da imagem nunca é ordem")
    cam = pv.evaluate("window.__camPedidos.map(x=>JSON.parse(x))")
    ok(len(cam) == 1 and cam[0].get("audio") is False and "video" in cam[0], "abriu só a câmera, nunca o microfone, e uma única vez")
    time.sleep(0.5)
    ok(pv.evaluate("window.__cam.every(s=>s.getTracks().every(t=>t.readyState==='ended'))"), "a câmera foi fechada logo depois da foto")
    ok(M.VIS.coisas_conhecidas() and any("notebook" in c[0].lower() for c in M.VIS.coisas_conhecidas()), "ela aprendeu «notebook» (neurônio no lobo occipital)")
    ok("Visão" in pv.inner_text("#sist") and "olhada" in pv.inner_text("#sist"), f"Sistemas atualiza a visão: {pv.inner_text('#sist')[-80:]!r}")
    # foto que ninguém pediu é recusada pelo servidor
    st = pv.evaluate("fetch('/olhar',{method:'POST',headers:{'X-Friday-Token':T,'Content-Type':'image/jpeg'},body:new Blob([new Uint8Array([255,216,255,224,0,16,74,70,73,70,0,1,1,0,0,1,0,1])])}).then(r=>r.status)")
    ok(st == 409, f"imagem enviada sem pedido é recusada (HTTP {st})")
    # dois painéis abertos (celular + computador esquecido ligado): só UM abre a câmera para cada pedido
    ctxw = nav.new_context(viewport={"width": 1100, "height": 760}, bypass_csp=True)
    ctxw.add_init_script(FAKE_SR)
    ctxw.add_init_script(ESPIA_CAM)
    pw2 = ctxw.new_page()
    pw2.goto(URL + "#t=" + M.TOKEN)
    pw2.wait_for_function("document.getElementById('lkt').textContent=='ONLINE'", timeout=5000)
    total = lambda: pv.evaluate("window.__camPedidos.length") + pw2.evaluate("window.__camPedidos.length")
    antes = total()
    pv.wait_for_function("ocupado===false", timeout=8000)
    pv.fill("#txt", "olhe")
    pv.click("#ctl button")
    pv.wait_for_function("document.getElementById('f').textContent.includes('Nada de novo')", timeout=15000)
    time.sleep(1)
    ok(total() - antes == 1, f"com dois painéis abertos só um abriu a câmera ({total() - antes} abertura(s))")
    # câmera negada: uma tentativa por pedido, sem laço, e ela avisa
    pv.evaluate("window.__negar=true"); pw2.evaluate("window.__negar=true")
    antes = total()
    pv.wait_for_function("ocupado===false", timeout=8000)
    pv.fill("#txt", "olhe")
    pv.click("#ctl button")
    pv.wait_for_function("document.getElementById('f').textContent.includes('Não consegui enxergar')", timeout=15000)
    ok(total() - antes == 1, f"câmera negada: uma tentativa por pedido, sem ficar em laço ({total() - antes})")
    ok("câmera" in (pv.inner_text("#vm") + pw2.inner_text("#vm")), "avisa como liberar a câmera")
    M.VIS.ESPERA_NAVEGADOR = 25.0
    os.environ["VISAO_FONTE"] = "off"

    # 8. sem reconhecimento de voz no navegador: mensagem orientando
    ctx3 = nav.new_context(bypass_csp=True)
    p3 = ctx3.new_page()
    p3.add_init_script("delete window.webkitSpeechRecognition; delete window.SpeechRecognition;")
    p3.goto(URL + "#t=" + M.TOKEN)
    p3.wait_for_function("document.getElementById('lkt').textContent=='ONLINE'", timeout=5000)
    p3.evaluate("document.getElementById('boot').click()")
    p3.click("#bt")
    ok("não tem reconhecimento" in p3.inner_text("#vm"), "navegador sem voz: orienta a usar texto")
    ok(not erros, f"sem erros de JavaScript {erros}")
    # 8b. movimento reduzido: sem abertura e sem animações
    ctx4 = nav.new_context(viewport={"width": 1100, "height": 760}, reduced_motion="reduce", bypass_csp=True)
    p4 = ctx4.new_page()
    p4.goto(URL + "#t=" + M.TOKEN)
    p4.wait_for_function("document.getElementById('lkt').textContent=='ONLINE'", timeout=5000)
    ok(p4.evaluate("getComputedStyle(document.getElementById('boot')).display") == "none", "movimento reduzido: sem sequência de abertura")
    ok(p4.evaluate("getComputedStyle(document.querySelector('.gira')).animationName") == "none", "movimento reduzido: reator parado")
    # 9. com o CSP de verdade ligado (sem bypass): o painel funciona e o navegador não bloqueia nada
    desk_ctx = nav.new_context(viewport={"width": 1280, "height": 960})
    desk = desk_ctx.new_page()
    consola = []
    desk.on("console", lambda m: consola.append(m.text))
    desk.on("pageerror", lambda e: consola.append(str(e)))
    desk.goto(URL + "#t=" + M.TOKEN)
    desk.wait_for_selector("#lkt:text-is('ONLINE')", timeout=5000)   # (com o CSP real, wait_for_function de texto é bloqueado de propósito)
    desk.wait_for_selector("#boot", state="hidden", timeout=6000)
    desk.fill("#txt", "teste com CSP ligado")
    desk.click("#ctl button")
    desk.wait_for_selector("#f:text-is('Resposta para: teste com CSP ligado')", timeout=5000)
    ok(not [c for c in consola if "Content Security Policy" in c or "Refused" in c], f"nenhum bloqueio do CSP {consola}")
    ok(True, "painel funciona com o CSP ligado")
    time.sleep(1)
    desk.screenshot(path=os.path.join(SAIDA, "hud-desktop.png"))
    nav.close()

srv.shutdown(); srv.server_close()
print(f"\n{len(falhas)} falha(s)." if falhas else "\nTudo certo.")
sys.exit(1 if falhas else 0)
