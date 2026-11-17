"""Evidência da NECESSIDADE e do EFEITO da retomada depois de uma queda REAL de processo (Fase 6).

  python3 reports/evidencias/cenarios/fase5_6/necessidade_de_retomada.py            # ANTES: só mostra o estado preso depois da queda
  python3 reports/evidencias/cenarios/fase5_6/necessidade_de_retomada.py --depois   # DEPOIS: roda a retomada e mostra o que ela fez

Como funciona: cria um cofre temporário e roda TRÊS processos de verdade (subprocess), um depois do outro:
  1. «queda»:  uma tarefa cria um lembrete; o processo morre com os._exit(1) DEPOIS do efeito e ANTES de registrar o resultado (o pior momento);
  2. «queda sem efeito»: outra tarefa; o processo morre ANTES da ação chegar a acontecer;
  3. «inconferivel»: uma tarefa de ação que não dá para conferir (lanterna); o processo morre durante a execução.
Depois, um quarto processo (o «reinício») lê o que ficou no disco e, conforme o modo, tenta mexer nas tarefas.
Nada do cofre real é tocado (ambiente temporário). Roda da raiz do projeto."""
import json, os, subprocess, sys, tempfile

RAIZ = os.getcwd()
DEPOIS = "--depois" in sys.argv
FILHO = "--filho" in sys.argv

if not FILHO:
    base = tempfile.mkdtemp(prefix="friday-retomada-")
    env = dict(os.environ, RETOMADA_BASE=base)

    def filho(papel):
        r = subprocess.run([sys.executable, __file__, "--filho", papel] + (["--depois"] if DEPOIS else []), cwd=RAIZ, env=env, capture_output=True, text=True, timeout=120)
        return r

    for papel in ("queda_depois_do_efeito", "queda_antes_do_efeito", "queda_inconferivel"):
        r = filho(papel)
        print(f"processo «{papel}» terminou com código {r.returncode} (1 = morreu de propósito no meio da ação)")
    r = filho("reinicio")
    print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr[-1500:])
    sys.exit(r.returncode)

# ---------------------------------------------------------------- daqui para baixo: roda dentro de um processo filho
papel = sys.argv[sys.argv.index("--filho") + 1]
base = os.environ["RETOMADA_BASE"]
sys.path.insert(0, os.path.join(RAIZ, "tests"))
import _ambiente as E                      # noqa: E402,F401  (ambiente isolado; depois apontamos tudo para a pasta compartilhada)
for k, v in dict(FRIDAY_DB="t.db", FRIDAY_AUDITORIA="aud.jsonl", OBSIDIAN_VAULT="cofre").items():
    os.environ[k] = os.path.join(base, v)
os.makedirs(os.environ["OBSIDIAN_VAULT"], exist_ok=True)
import broker as B, catalogo, tarefas as T  # noqa: E402,F401
import ferramentas as F                      # noqa: E402

if papel == "queda_depois_do_efeito":
    real = B.FERRAMENTAS["criar_lembrete"]["fn"]

    def morre_depois(**kw):
        real(**kw)                           # o lembrete É criado...
        os._exit(1)                          # ...e o processo cai antes de qualquer registro do resultado

    B.FERRAMENTAS["criar_lembrete"]["fn"] = morre_depois
    tid = T.criar("lembrar de tomar água", passos=[{"descricao": "criar o lembrete", "ferramenta": "criar_lembrete", "args": {"minutos": 30, "texto": "tomar agua"}}])
    T.executar(tid)
elif papel == "queda_antes_do_efeito":
    B.FERRAMENTAS["criar_lembrete"]["fn"] = lambda **kw: os._exit(1)      # cai antes de a ação acontecer
    tid = T.criar("lembrar de ligar para o banco", passos=[{"descricao": "criar o lembrete", "ferramenta": "criar_lembrete", "args": {"minutos": 40, "texto": "ligar banco"}}])
    T.executar(tid)
elif papel == "queda_inconferivel":
    B.FERRAMENTAS["lanterna"]["fn"] = lambda **kw: os._exit(1)            # lanterna: a ação é do celular e não dá para conferir daqui
    tid = T.criar("acender a lanterna", passos=[{"descricao": "ligar", "ferramenta": "lanterna", "args": {"ligar": True}}])
    T.executar(tid)
else:                                         # o reinício: processo novo, só o disco sobrou
    T.reiniciar()
    lembretes_antes = [t for _, t in F.lembretes_lista() if "agua" in t or "banco" in t]
    print(f"\n--- estado no disco depois das quedas ({len(lembretes_antes)} lembretes já existentes) ---")
    for t in T.listar():
        print(f"{t['id']} {t['objetivo']!r}: {t['estado']} | passos: {[p['estado'] for p in t['passos']]}")
    print("\n--- o que o dono consegue fazer hoje ---")
    for t in T.listar():
        r = T.executar_proximo(t["id"])
        ok, msg = T.reabrir(t["id"])
        print(f"{t['id']}: executar_proximo → «{r['motivo']}»; reabrir → ({ok}, «{msg}»)")
    if DEPOIS:
        import coordenador, retomada as R     # noqa: E402,F401
        print("\n--- retomada ---")
        rel = R.retomar_pendentes()
        for x in rel["itens"]:
            print(f"{x['tarefa']}: {x['acao']} — {x['motivo']} → {x['estado']}")
        print("resumo:", rel["resumo"])
        print("\n--- estado depois ---")
        for t in T.listar():
            print(f"{t['id']} {t['objetivo']!r}: {t['estado']} | passos: {[p['estado'] for p in t['passos']]} | causa: {t['causa'] or '-'}")
    agua = [t for _, t in F.lembretes_lista() if "agua" in t]
    banco = [t for _, t in F.lembretes_lista() if "banco" in t]
    print(f"\nlembretes «tomar agua» no banco: {len(agua)} (esperado 1: criado antes da queda, nunca duplicado)")
    print(f"lembretes «ligar banco» no banco: {len(banco)} ({'1 = refeito porque a conferência provou que não existia' if DEPOIS else '0 = a tarefa ficou presa'})")
