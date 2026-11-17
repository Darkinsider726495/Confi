"""Demonstração executável do pré-córtex — sem credenciais, sem API paga, sem internet.

    python -m friday.pre_cortex.demo                       # modo distribuído (2 processos trabalhadores) e autoconferência no fim
    python -m friday.pre_cortex.demo --modo local          # tudo neste processo (mesmo contrato, mesmas mensagens em JSON)
    python -m friday.pre_cortex.demo --ui                  # abre a tela /precortex (link impresso) e roda o cenário devagar para acompanhar
    python -m friday.pre_cortex.demo --ui --sem-cenario    # só a tela: escreva o objetivo nela

Cenário (o MESMO fluxo, contratos e módulos do aplicativo):
  1. «Monte um plano de estudos de Python para 4 semanas, com no máximo 90 minutos por dia, e guarde.»
     O conteúdo passa de 1000 caracteres. A primeira estratégia («anotar», uma nota só) é recusada pelo corretor (limite de tamanho do argumento) — uma falha que o
     sistema não fabricou: a verificação independente relê o banco, não acha nada, a aprendizagem registra a discrepância e o plano é revisado («anotar_em_partes»).
  2. O mesmo pedido de novo: a experiência registrada reordena as estratégias e o primeiro plano já usa a que funcionou (sem replanejar).
  3. «Mande um SMS para a mãe dizendo que chego tarde»: efeito fora do aparelho → o plano para e pede a autorização do dono. A demonstração NEGA (nada é enviado).
Tudo roda numa pasta temporária (banco, auditoria, cofre e estado do pré-córtex); nada do seu FRIDAY real é tocado e nada é apagado no fim (a pasta fica para você olhar).
Backend: «deterministico» (regras e currículo interno). Modelo de linguagem: não incluído (ponto de extensão; docs/PRE_CORTEX.md).
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PEDIDO_ESTUDO = "Monte um plano de estudos de Python para 4 semanas, com no máximo 90 minutos por dia, e guarde"
PEDIDO_SMS = "Mande um SMS para mae dizendo que chego tarde"
SEGREDOS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "NTFY_URL", "NTFY_TOKEN", "SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "BRAVE_API_KEY")
MOSTRAR = ("objetivo_recebido", "interpretacao", "contexto", "hipoteses", "plano", "critica", "coerencia", "autorizacao_pedida", "autorizacao_dispensada", "autorizacao_negada",
           "execucao_registrada", "tarefa_criada", "execucao_concluida", "verificacao", "aprendizagem", "replanejamento", "concluido", "precisa_do_dono", "bloqueado", "modo_degradado",
           "modulo_indisponivel", "limite_atingido", "laco_detectado", "cancelado")


def preparar_ambiente(pasta):
    """Isola tudo ANTES de importar os módulos da FRIDAY (eles leem o ambiente ao carregar)."""
    os.environ.update(
        FRIDAY_DB=os.path.join(pasta, "friday.db"), FRIDAY_AUDITORIA=os.path.join(pasta, "auditoria.jsonl"), FRIDAY_DOCS=os.path.join(pasta, "docs"),
        FRIDAY_TOKEN_ARQ=os.path.join(pasta, "token"), FRIDAY_AUTONOMIA_ARQ=os.path.join(pasta, "autonomia.json"), FRIDAY_DIAG_ARQ=os.path.join(pasta, "diagnostico.txt"),
        FRIDAY_HEARTBEAT=os.path.join(pasta, "hb"), OBSIDIAN_VAULT=os.path.join(pasta, "cofre"), FRIDAY_PIN=str(secrets.randbelow(900000) + 100000),
        FRIDAY_VIDA="0", VISAO_FONTE="off", FRIDAY_PLATAFORMA="android", CONTATOS="mae:+5500000000000", SILENCIO="", DESCANSO="", PRECORTEX_PASTA=os.path.join(pasta, "precortex"),
        PATH=os.path.join(pasta, "bin") + os.pathsep + os.environ.get("PATH", ""))
    for k in SEGREDOS:
        os.environ.pop(k, None)
    # FRIDAY_PLATAFORMA=android registra as ferramentas do celular; os comandos termux-* abaixo são de mentira: se algo tentar enviar, fica anotado aqui (a demonstração confere que NÃO foi chamado)
    b = os.path.join(pasta, "bin")
    os.makedirs(b, exist_ok=True)
    log = os.path.join(pasta, "termux.log")
    for n in ("sms-send", "notification", "tts-speak", "vibrate"):
        p = os.path.join(b, "termux-" + n)
        with open(p, "w") as f:
            f.write('#!/bin/sh\necho "CMD $(basename "$0") $*" >> "%s"\n' % log)
        os.chmod(p, 0o755)
    open(log, "a").close()
    return log


def iniciar_trabalhadores(token):
    procs, workers = [], {}
    env = dict(os.environ, PRECORTEX_TOKEN=token)
    from . import catalogo_neuronios as K
    for nome, neur in K.GRUPOS_PADRAO.items():
        p = subprocess.Popen([sys.executable, "-m", "friday.pre_cortex.worker", "--nome", nome, "--neuronios", ",".join(neur)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env, cwd=RAIZ)
        linha = p.stdout.readline()
        try:
            info = json.loads(linha)
        except ValueError:
            info = {"erro": (linha or p.stderr.read())[:300]}
        if "url" not in info:
            raise RuntimeError(f"trabalhador {nome} não subiu: {info}")
        procs.append(p)
        workers[nome] = {"url": info["url"], "pid": info["pid"], "neuronios": info["neuronios"]}
    return procs, workers


def mostrar(h, pcid, desde):
    ult = desde
    for e in h.eventos(desde, pcid, 2000):
        ult = max(ult, e["seq"])
        if e["tipo"] in MOSTRAR:
            quem = f" [{e['worker']}·pid {e['pid']}]" if e.get("worker") else ""
            print(f"   #{e['seq']:<4} {e['tipo']:<24} {e.get('texto', '')[:150]}{quem}")
    return ult


def quem_respondeu(h, pcid):
    r = {}
    for e in h.eventos(0, pcid, 5000):
        if e["tipo"] == "mensagem_recebida" and e.get("ok"):
            r.setdefault(e["de"], set()).add((e.get("worker"), e.get("pid")))
    return r


def cenario(h, ritmo, checar, log_termux):
    from . import explicar as EXPL
    print("\n== 1) primeiro pedido (sem experiência anterior) ==")
    r1 = h.submeter(PEDIDO_ESTUDO)
    est = h.esperar(r1["id"], 120 + 40 * ritmo)
    mostrar(h, r1["id"], 0)
    d1 = h.dossie(r1["id"])
    planos1 = [(p["versao"], p["plano"].get("estrategia"), (p.get("verificacao") or {}).get("veredito")) for p in d1["planos"]]
    print(f"   → estado final: {est}; planos: {planos1}")
    checar("objetivo 1 concluído", est == "concluido", est)
    checar("a primeira estratégia falhou e a falha foi DETECTADA pela verificação independente", len(planos1) >= 2 and planos1[0][2] in ("falha_total", "parcial"), planos1)
    checar("o plano foi revisado depois da experiência e a revisão funcionou", len(planos1) >= 2 and planos1[-1][2] == "sucesso", planos1)
    checar("aprendizado registrado para cada tentativa (esperado × observado)", len(d1["aprendizados"]) == len(planos1), [a["id"] for a in d1["aprendizados"]])
    q = {p["n"]: p for p in EXPL.perguntas(d1)}
    checar("as 12 perguntas têm resposta tirada do dossiê", all(q[n]["disponivel"] for n in range(1, 13)), [n for n in range(1, 13) if not q[n]["disponivel"]])
    print("   Por que esta estratégia? " + q[9]["resposta"])
    print("   O que aprendi? " + q[11]["resposta"])
    print("   O que mudou no plano? " + q[12]["resposta"])

    print("\n== 2) o mesmo pedido de novo (agora com experiência) ==")
    r2 = h.submeter(PEDIDO_ESTUDO)
    est2 = h.esperar(r2["id"], 120 + 40 * ritmo)
    mostrar(h, r2["id"], 0)
    d2 = h.dossie(r2["id"])
    planos2 = [(p["versao"], p["plano"].get("estrategia"), (p.get("verificacao") or {}).get("veredito")) for p in d2["planos"]]
    print(f"   → estado final: {est2}; planos: {planos2}")
    checar("objetivo 2 concluído", est2 == "concluido", est2)
    checar("a experiência mudou a escolha: o primeiro plano já usa a estratégia que funcionou", bool(planos2) and planos2[0][1] == planos1[-1][1] and len(planos2) == 1, planos2)

    print("\n== 3) pedido com efeito fora do aparelho (SMS) ==")
    r3 = h.submeter(PEDIDO_SMS)
    est3 = h.esperar(r3["id"], 60 + 20 * ritmo, ate=("aguardando_autorizacao",))
    mostrar(h, r3["id"], 0)
    checar("o plano parou esperando a autorização do dono", est3 == "aguardando_autorizacao", est3)
    with open(log_termux, encoding="utf-8") as f:
        enviado = "sms-send" in f.read()
    checar("nada foi enviado antes da autorização", not enviado, "termux-sms-send chamado" if enviado else "nenhuma chamada")
    return r1["id"], r2["id"], r3["id"]


def principal(argv=None):
    ap = argparse.ArgumentParser(prog="python -m friday.pre_cortex.demo", description="demonstração do pré-córtex (sem internet, sem credenciais)")
    ap.add_argument("--modo", choices=("distribuido", "local"), default="distribuido")
    ap.add_argument("--ui", action="store_true", help="sobe a tela /precortex e espera Ctrl-C no fim")
    ap.add_argument("--porta", type=int, default=0, help="porta da tela (0 = qualquer livre)")
    ap.add_argument("--ritmo", type=float, default=None, help="pausa entre fases em segundos (padrão: 0 sem --ui, 0,7 com --ui)")
    ap.add_argument("--sem-cenario", action="store_true", help="com --ui: não roda o cenário; você escreve o objetivo na tela")
    ap.add_argument("--relatorio", help="grava o resultado da autoconferência em JSON neste arquivo")
    a = ap.parse_args(argv)
    ritmo = a.ritmo if a.ritmo is not None else (0.7 if a.ui else 0.0)

    pasta = tempfile.mkdtemp(prefix="friday-precortex-demo-")
    log_termux = preparar_ambiente(pasta)
    sys.path.insert(0, os.path.join(RAIZ, "friday"))
    import catalogo  # noqa: F401  (registra as ferramentas no corretor, como o main.py faz)

    from . import api as API
    from . import config as CF
    from . import hub as HB

    token = secrets.token_urlsafe(24)
    procs, workers = [], {}
    cfg = CF.Config.carregar()
    cfg.aplicar({"modo": a.modo, "ritmo_demo_s": ritmo, "saude_intervalo_s": 1.0}, "demonstração")
    print(f"pasta temporária da demonstração: {pasta}")
    print(f"processo do hub: pid {os.getpid()}  ·  modo {a.modo}  ·  backend {cfg['backend']}  ·  ritmo {ritmo}s")
    resultados = []

    def checar(nome, ok, detalhe=""):
        resultados.append({"verificacao": nome, "ok": bool(ok), "detalhe": str(detalhe)[:300]})
        print(f"   [{'OK' if ok else 'FALHOU'}] {nome}" + ("" if ok else f" — {str(detalhe)[:200]}"))

    srv = h = None
    try:
        if a.modo == "distribuido":
            procs, workers = iniciar_trabalhadores(token)
            for n, w in workers.items():
                print(f"trabalhador «{n}»: processo separado pid {w['pid']} em {w['url']} → {', '.join(w['neuronios'])}")
            cfg.aplicar({"workers": {n: {"url": w["url"]} for n, w in workers.items()}}, "demonstração")
        h = HB.Hub(cfg, os.environ["PRECORTEX_PASTA"], token=token)
        if a.ui:
            srv = API.ServidorApi(h, token, porta=a.porta).iniciar()
            print(f"\nTELA: {srv.url}#t={token}\n(a chave vale só para esta demonstração; abra o link no navegador desta máquina)\n")
            time.sleep(0.5)
        if not (a.ui and a.sem_cenario):
            ids = cenario(h, ritmo, checar, log_termux)
            if a.modo == "distribuido":
                resp = quem_respondeu(h, ids[0])
                fora = {n: sorted(v) for n, v in resp.items() if any(pid and pid != os.getpid() for _, pid in v)}
                print("\n   quem respondeu (neurônio → trabalhador, processo):", {n: sorted(v) for n, v in resp.items()})
                checar("neurônios responderam de OUTROS processos (comunicação entre processos de verdade)", {"percepcao", "planejamento", "critica", "verificador"} <= set(fora), fora)
                h.atualizar_saude()
                iso = {w: s.get("isolamento") for w, s in h.ultima_saude["workers"].items() if s.get("tipo") == "http"}
                checar("os trabalhadores não carregaram o corretor, as tarefas nem o catálogo", all(v and not any(v.values()) for v in iso.values()) and len(iso) == len(workers), iso)
            if not a.ui:
                r = h.negar(ids[2], "a demonstração nega por padrão")
                checar("o dono negou e o objetivo ficou bloqueado sem executar", r.get("ok") and h.dossie(ids[2])["estado"] == "bloqueado", h.dossie(ids[2])["estado"])
            else:
                print(f"\n   O objetivo {ids[2]} está esperando a SUA decisão na tela (Autorizar / Negar). Autorizar ainda passa pelo corretor, que pede a confirmação da ação.")
        ok = all(r["ok"] for r in resultados)
        print(f"\nAUTOCONFERÊNCIA: {sum(r['ok'] for r in resultados)}/{len(resultados)} verificações ok" + ("" if ok else " — HÁ FALHAS"))
        if a.relatorio:
            with open(a.relatorio, "w", encoding="utf-8") as f:
                json.dump({"modo": a.modo, "pasta": pasta, "pid_hub": os.getpid(), "trabalhadores": workers, "resultados": resultados, "ok": ok}, f, ensure_ascii=False, indent=1)
        if a.ui:
            print("A tela continua no ar. Ctrl-C aqui termina a demonstração (o FRIDAY real não é afetado).")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nfim da demonstração")
        return 0 if ok else 1
    finally:
        if srv is not None:
            srv.parar()
        if h is not None:
            h.encerrar(2.0)
        for p in procs:                       # só os trabalhadores QUE ESTA demonstração abriu
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(principal())
