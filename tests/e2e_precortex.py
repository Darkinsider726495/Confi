"""E2E no Chromium: a tela /precortex (dentro do painel da FRIDAY) acompanhando um objetivo de verdade — mapa dos neurônios com estados reais, objetivo e plano,
fluxo de eventos, hipóteses, planejamento, aprendizagem, as 12 perguntas, estado operacional e os controles (iniciar, autorizar/negar, interromper, limpar).
Rode:  python tests/e2e_precortex.py      (precisa do Playwright; salva precortex-*.png em E2E_SAIDA)"""
import os, sys, time
from unittest import mock
import _ambiente as E
os.environ["PRECORTEX_RITMO_DEMO_S"] = "0.15"            # só para dar tempo de ver; aparece nos eventos como «pausa_demo»
import main as M
import pre_cortex.fachada as PC
from pre_cortex.planejamento import Planejamento
from playwright.sync_api import sync_playwright

BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
M.TOKEN = "k" * 40
SAIDA = os.environ.get("E2E_SAIDA", E.TMP)
srv = M.iniciar_http("127.0.0.1", 0)
URL = f"http://127.0.0.1:{srv.server_address[1]}"
falhas = []
PEDIDO = "Monte um plano de estudos de Python para 4 semanas, com no máximo 90 minutos por dia, e guarde"

# o planejamento demora 1 s DE VERDADE (dorme dentro do neurônio): a tela tem de mostrar «processando» enquanto ele trabalha — o estado vem do trabalhador, não de um temporizador da página
_orig = Planejamento.acao_montar_plano


def _lento(self, corpo, ctx):
    time.sleep(1.0)
    return _orig(self, corpo, ctx)


Planejamento.acao_montar_plano = _lento


def ok(cond, msg):
    print(("✔ " if cond else "✖ ") + msg)
    if not cond:
        falhas.append(msg)


def espera(pg, expr, tempo=20.0):
    fim = time.time() + tempo
    while time.time() < fim:
        if pg.evaluate(expr):
            return True
        time.sleep(0.1)
    raise AssertionError("tempo esgotado: " + expr)


ESTADOS = "Array.from(document.querySelectorAll('#mapa .no')).map(g=>[g.dataset.n,g.dataset.estado])"

with sync_playwright() as pw:
    nav = pw.chromium.launch()
    ctx = nav.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    erros, consola = [], []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: consola.append((m.type, m.text)))

    pg.goto(URL + "/precortex")
    ok(pg.is_visible("#sc") and not pg.is_visible("#app"), "sem a chave, a tela não mostra dados")
    pg.goto("about:blank")
    pg.goto(URL + "/precortex#t=" + M.TOKEN)
    pg.wait_for_load_state()
    espera(pg, "document.getElementById('contxt').textContent.startsWith('ao vivo')")
    ok(len(pg.evaluate(ESTADOS)) == 9, "o mapa tem os nove neurônios")
    ok(all(e == "ocioso" for n, e in pg.evaluate(ESTADOS) if n != "monitor"), "antes de qualquer objetivo, todos ociosos (o monitor trabalha sempre: avalia a saúde a cada volta do vigia)")
    ok("local" in pg.inner_text("#tags") and "deterministico" in pg.inner_text("#tags"), "a tela diz o modo e o backend")

    # --- um objetivo pela tela
    pg.fill("#txt", PEDIDO)
    pg.click("#bIniciar")
    vistos = {}
    fim = time.time() + 60
    while time.time() < fim:
        for n, e in pg.evaluate(ESTADOS):
            vistos.setdefault(n, set()).add(e)
        if pg.evaluate("(document.getElementById('bEstado')||{}).dataset && document.getElementById('bEstado').dataset.estado==='concluido'"):
            break
        time.sleep(0.1)
    print("   estados vistos:", {k: sorted(v) for k, v in vistos.items()})
    ok("processando" in vistos.get("planejamento", set()), "enquanto o planejamento trabalha, o mapa mostra «processando»")
    ok(all("concluido" in vistos.get(n, set()) for n in ("percepcao", "contexto", "hipoteses", "planejamento", "critica", "verificador", "aprendizagem")),
       "cada neurônio que trabalhou passou por «concluído»")
    ok(pg.evaluate("document.getElementById('bEstado').dataset.estado") == "concluido", "o objetivo terminou concluído")
    acesos = pg.evaluate("(()=>{const c=document.getElementById('c3');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=16)if(d[i]>0)n++;return n})()")
    ok(acesos > 500, f"o cérebro em 3D está desenhado ({acesos} pontos acesos na amostra)")
    ok(pg.inner_text("#c3info").startswith("#"), f"o 3D mostra a última mensagem real: «{pg.inner_text('#c3info')[:60]}»")
    pg.screenshot(path=os.path.join(SAIDA, "precortex-concluido.png"), full_page=True)
    tipos = pg.evaluate("Array.from(document.querySelectorAll('#fluxo li')).map(li=>li.dataset.tipo)")
    for t in ("objetivo_recebido", "interpretacao", "hipoteses", "plano", "critica", "verificacao", "aprendizagem", "replanejamento", "concluido"):
        ok(t in tipos, f"o fluxo de eventos mostra «{t}»")
    ok(pg.evaluate("document.querySelectorAll('#versoes tr').length") == 3, "o planejamento mostra as duas versões do plano (v1 falhou, v2 funcionou)")
    ok("falha_total" in pg.inner_text("#versoes") and "sucesso" in pg.inner_text("#versoes"), "a tabela de versões traz o resultado de cada uma")
    ok(pg.evaluate("document.querySelectorAll('#hip .hip').length") >= 3, "o painel de hipóteses mostra as hipóteses comparadas")
    ok("não calibrada" in pg.inner_text("#hip"), "a confiança aparece como não calibrada")
    ok(pg.evaluate("document.querySelectorAll('#aprendizados li').length") == 2, "a aprendizagem mostra os dois registros (falha e sucesso)")
    ok(pg.inner_text("#fVeredito") == "sucesso", "a verificação independente aparece com o veredito")
    ok(pg.evaluate("document.querySelectorAll('#perg details').length") == 12, "as 12 perguntas aparecem")
    ok("anotar_em_partes" in pg.inner_text("#perg"), "as respostas citam a estratégia real")
    ok(pg.inner_text("#modoOp") in ("normal", "degradado", "bloqueado"), f"estado operacional: modo «{pg.inner_text('#modoOp')}»")
    ok(pg.evaluate("document.querySelectorAll('#trabalhadores tr[data-w]').length") == 3, "três trabalhadores no estado operacional (hub, cognição, revisão)")

    # --- ação externa: a tela pede a autorização; o dono nega; nada é enviado
    pg.fill("#txt", "Mande um SMS para mae dizendo que chego tarde")
    pg.click("#bIniciar")
    espera(pg, "!!document.getElementById('pedidoAut')", 30)
    ok("Preciso da sua autorização" in pg.inner_text("#pedidoAut"), "a tela mostra o pedido de autorização do plano exato")
    pg.screenshot(path=os.path.join(SAIDA, "precortex-autorizacao.png"), full_page=False)
    pg.click("#bNegar")
    espera(pg, "document.getElementById('bEstado').dataset.estado==='bloqueado'")
    ok("CMD termux-sms-send" not in E.ler_log(LOG), "negado: nenhum SMS saiu")

    # --- interromper a demonstração (cooperativo) com um objetivo rodando
    pg.fill("#txt", PEDIDO)
    pg.click("#bIniciar")
    espera(pg, "document.getElementById('bEstado') && document.getElementById('bEstado').dataset.estado==='em_andamento'")
    pg.click("#bInterromper")
    espera(pg, "document.getElementById('bEstado').dataset.estado==='cancelado'", 30)
    ok(True, "«Interromper a demonstração» cancelou o objetivo em andamento")
    ok(pg.evaluate("fetch('/saude').then(r=>r.ok)"), "o servidor continua no ar depois de interromper")

    # --- limpar o estado temporário
    pg.click("#bLimpar")
    espera(pg, "document.querySelectorAll('#objs .obj').length===0")
    ok("memórias permanentes não foram tocadas" in pg.inner_text("#msg"), "limpar arquiva só o cenário e diz isso")
    textos = [b.lower() for b in pg.evaluate("Array.from(document.querySelectorAll('button')).map(b=>b.textContent)")]
    ok(not any(w in t for t in textos for w in ("desligar", "pausar", "encerrar", "apagar")), f"nenhum botão de desligar ({textos})")
    ok(not erros, f"nenhum erro de JavaScript ({erros[:2]})")
    ok(not [m for m in consola if m[0] == "error"], f"nenhum erro no console ({[m for m in consola if m[0] == 'error'][:2]})")
    # --- o atalho no painel principal
    pg.goto(URL + "/#t=" + M.TOKEN)
    ok(pg.locator("#bpc").count() == 1, "o painel principal tem o atalho para a tela dos neurônios")
    nav.close()

print()
print("FALHAS:" if falhas else "TUDO OK", *falhas, sep="\n  " if falhas else " ")
sys.exit(1 if falhas else 0)
