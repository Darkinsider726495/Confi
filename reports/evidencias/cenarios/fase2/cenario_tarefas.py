"""Roteiro humano da Fase 2: roda no ambiente de teste (pasta temporária, comandos termux-* falsos) e mostra, cenário por cenário, o que a FRIDAY fez e o que ela
conferiu. uso: python3 reports/evidencias/cenarios/fase2/cenario_tarefas.py  (da raiz do projeto)"""
import json, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import _ambiente as E                      # noqa: E402  (precisa vir antes dos módulos da FRIDAY)
BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
from unittest import mock                  # noqa: E402
import broker as B, catalogo, ferramentas as F, tarefas as T, prefrontal as PFC   # noqa: E402,F401

os.makedirs(os.environ["OBSIDIAN_VAULT"], exist_ok=True)
SEG = "texto-particular-123"


def titulo(t):
    print(f"\n=== {t} ===")


def sms():
    return E.ler_log(LOG).count("CMD termux-sms-send")


def linha(tid):
    t = T.obter(tid)
    print(f"  tarefa {tid}: {t['estado']}  passos={[(p['id'], p['estado']) for p in t['passos']]}")
    for p in t["passos"]:
        if p["verificacao"]:
            print(f"    conferência de {p['id']}: {p['verificacao']['veredito']} ({p['verificacao']['forca']}): {p['verificacao']['evidencia']}")
    if t["causa"]:
        print("  causa:", t["causa"])
    print("  próxima ação:", t["proxima_acao"])


titulo("A — execução básica verificada")
tid = T.criar("lembrar de beber água", passos=[{"descricao": "criar lembrete", "ferramenta": "criar_lembrete", "args": {"minutos": 7, "texto": SEG}}])
T.executar(tid); linha(tid)

titulo("B — a ferramenta diz que fez e NÃO fez (falso sucesso)")
tid = T.criar("lembrar de ligar", passos=[{"descricao": "criar lembrete", "ferramenta": "criar_lembrete", "args": {"minutos": 9, "texto": SEG + "-b"}}])
with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Lembrete criado para daqui a 9 minutos."}):
    T.executar(tid)
linha(tid)
print("  pela conversa, a IA recebe:", T.executar_registrado.__name__, "->", end=" ")
with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Lembrete criado para daqui a 9 minutos."}):
    print(T.executar_registrado("criar_lembrete", {"minutos": 9, "texto": SEG + "-c"}))

titulo("F — ação sensível com confirmação ambígua")
tid = T.criar("avisar a mãe", passos=[{"descricao": "SMS", "ferramenta": "enviar_sms", "args": {"contato": "mae", "texto": SEG}}])
T.executar(tid); linha(tid)
for fala in ("sim", "pode", "isso mesmo"):
    print(f"  fala «{fala}» ->", B.confirmar_voz(fala), "| SMS enviados:", sms())
print("  fala «confirmo» ->", B.confirmar_voz("confirmo")[0], "| SMS enviados:", sms())
linha(tid)

titulo("G — privacidade: o que foi parar em disco")
achou = []
for raiz, _, nomes in os.walk(os.environ["OBSIDIAN_VAULT"]):
    for n in nomes:
        if n.endswith((".json", ".jsonl")):
            achou.append((n, SEG in open(os.path.join(raiz, n), encoding="utf-8").read()))
print("  arquivos com o texto particular:", [n for n, tem in achou if tem] or "nenhum")
for t in T.listar():
    print(f"    {t['id']} ({t['estado']}): argumentos no registro = {[p['args'] for p in t['passos']]}")
print("  (só tarefas que ainda podem ser retomadas guardam os argumentos de baixo risco; as terminadas e as de nível 2 não)")
print("  auditoria tem o texto:", SEG in open(B.AUDITORIA, encoding="utf-8").read(), "| cadeia íntegra:", B.verificar_auditoria())

titulo("H — meta e tarefa com textos diferentes")
ok, m = PFC.nova_meta("aprender", tema="sono")
tid = T.criar("entender como dormir bem ajuda a lembrar", meta=m["id"], conclui_meta=True,
              passos=[{"descricao": "registrar", "ferramenta": "guardar_memoria", "args": {"texto": "Dormir bem ajuda a lembrar", "titulo": "Dormir bem"}}])
T.executar(tid); linha(tid)
PFC.pensar()
meta = PFC.ARQ.get()["metas"][m["id"]]
print(f"  meta «{meta['titulo']}»: {meta['estado']}, progresso {meta['progresso']}, nota: {meta['nota']}")
