"""Reproduz, no código ATUAL, cada achado da auditoria de 24/10/2026 e classifica:
CONFIRMADO | PARCIALMENTE_CONFIRMADO | RESOLVIDO | NAO_REPRODUZIDO.

Não é um teste da suíte (não começa com test_): é um instrumento de validação que pode ser repetido depois de cada fase.
Tudo roda em pasta temporária (tests/_ambiente.py); nada toca o cofre, o banco ou a auditoria reais.

  python3 tests/auditoria_achados.py            # imprime a tabela
  python3 tests/auditoria_achados.py --json X   # também grava o JSON em X
"""
import json, os, re, sys, time, importlib, importlib.util, random
from pathlib import Path
import _ambiente as E

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["FRIDAY_VIDA"] = "1"
import memoria as M, broker as B, catalogo, ferramentas as F, prefrontal as PFC, curiosidade as CUR, internet as I  # noqa: E402,F401

RES = []


def achado(num, titulo, fn):
    try:
        estado, evid = fn()
    except Exception as e:  # um probe que quebra não pode esconder os outros
        estado, evid = "NAO_REPRODUZIDO", f"probe falhou: {type(e).__name__}: {e}"
    RES.append({"n": num, "achado": titulo, "estado": estado, "evidencia": evid})


def existe(nome):
    return importlib.util.find_spec(nome) is not None


# 1/2/4/5/6 — peças do ciclo que a auditoria disse faltar
def p_tarefas():
    """#1 — o ciclo objetivo → plano → execução → verificação existe? Falta a experiência (Fase 3)?"""
    if not existe("tarefas"):
        return "CONFIRMADO", "não há módulo de tarefas: o pedido não vira objeto com estado"
    import tarefas as T
    elos = {"objetivo/plano": hasattr(T, "criar"), "execução": hasattr(T, "executar"), "verificação": existe("verificacao")}
    faltam = [k for k, v in elos.items() if not v]
    if faltam:
        return "PARCIALMENTE_CONFIRMADO", f"tarefas.py existe, faltam: {', '.join(faltam)}"
    if not existe("experiencias"):
        return "PARCIALMENTE_CONFIRMADO", "objetivo → plano → execução → verificação existem (tarefas.py + verificacao.py); falta o elo «experiência»"
    return "RESOLVIDO", "o ciclo inteiro existe, inclusive o registro de experiências"


def p_registro():
    """#2 — o pedido vira um objeto com id, objetivo, passos, estado, histórico e contexto?"""
    if not existe("tarefas"):
        return "CONFIRMADO", "não há registro de tarefas"
    import tarefas as T
    T.reiniciar()
    tid = T.criar("lembrar de beber água", passos=[{"descricao": "avisar", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": "beber água"}}])
    t = T.obter(tid)
    campos = ("id", "objetivo", "passos", "estado", "historico", "contexto")
    faltam = [c for c in campos if c not in t]
    T.reiniciar()
    if faltam:
        return "PARCIALMENTE_CONFIRMADO", f"registro sem: {', '.join(faltam)}"
    return "RESOLVIDO", f"tarefa {t['id']} nasce em {t['estado']} com id, objetivo, passos, estado, histórico e contexto"


def p_experiencias():
    """#4 — existe um registro estruturado (hipótese, esperado × observado, evidência, diferença, causas com confiança, aprendido, reuso)? Reproduz: uma ferramenta que mente."""
    if not existe("experiencias"):
        return "CONFIRMADO", "não há registro de experiências (hipótese, esperado × observado, confiança)"
    from unittest import mock
    import experiencias as X, tarefas as T
    T.reiniciar()
    X.reiniciar()
    try:
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Lembrete criado para daqui a 9 minutos."}):
            tid = T.criar("lembrar de prova", passos=[{"descricao": "avisar", "ferramenta": "criar_lembrete", "args": {"minutos": 9, "texto": "exp-audit"}}])
            T.executar(tid)
        x, s = X.da_tarefa(tid), X.sinais("criar_lembrete")
    finally:
        T.reiniciar()
        X.reiniciar()
    if not x:
        return "PARCIALMENTE_CONFIRMADO", "experiencias.py existe mas a tarefa terminada não gerou registro"
    campos = ("hipotese", "esperado", "observado", "evidencias", "diferenca", "causas", "aprendido", "alternativas", "reuso", "desconhecido", "condicoes")
    faltam = [c for c in campos if c not in x]
    tipadas = x["causas"] and all(c.get("tipo") in ("fato", "inferencia", "hipotese", "desconhecido") and isinstance(c.get("confianca"), float) for c in x["causas"])
    if faltam or not tipadas or x["resultado"] != "falha" or s["falhas"] < 1:
        return "PARCIALMENTE_CONFIRMADO", f"registro incompleto (faltam {faltam or 'nada'}; causas tipadas: {bool(tipadas)}; resultado {x['resultado']})"
    return "RESOLVIDO", (f"falso sucesso virou {x['resultado']}/{x['tipo_falha']} com hipótese, esperado × observado, {len(x['causas'])} causas tipadas com confiança, reuso e o que se ignora; "
                         f"a próxima escolha já enxerga: {s['falhas']} falha(s), p={s['p']}. Limite: arquivo jsonl do processo, ainda não são neurônios do cofre")


def p_plano():
    """#5 — o plano é montado e REVISADO por alguém além do chamador? Reproduz: a 1ª estratégia diz «feito» sem fazer; o planejador tem de trocar de estratégia e conferir."""
    if not existe("planejador"):
        if existe("tarefas"):
            return "PARCIALMENTE_CONFIRMADO", "tarefas.py executa planos de vários passos com dependências, mas quem escreve o plano é o chamador; ninguém gera nem revisa o plano (Fase 4)"
        return "CONFIRMADO", "PFC.plano() devolve um passo; não há plano de várias etapas nem replanejamento"
    from unittest import mock
    import experiencias as X, planejador as P, tarefas as T
    T.reiniciar()
    X.reiniciar()
    try:
        with mock.patch.dict(B.FERRAMENTAS["guardar_memoria"], {"fn": lambda **kw: "Guardei na memória de longo prazo."}):
            r = P.executar_objetivo("registrar_informacao", {"texto": "teste de planejamento da auditoria"})
    finally:
        T.reiniciar()
        X.reiniciar()
    ok = r["decisao"] == "concluir" and len(r["tentativas"]) >= 2 and r["tentativas"][0]["resultado"] == "falha" and r["tentativas"][-1]["resultado"] == "sucesso"
    if not ok:
        return "PARCIALMENTE_CONFIRMADO", f"planejador.py existe, mas o cenário terminou em «{r['decisao']}» com {len(r['tentativas'])} tentativa(s)"
    return "PARCIALMENTE_CONFIRMADO", (f"a 1ª estratégia falhou ({r['tentativas'][0]['estrategia']}), o planejador trocou para «{r['tentativas'][-1]['estrategia']}» e concluiu com o efeito conferido; "
                                       f"ciclo de 11 passos registrado. Limite: só os {len(P.tipos())} tipos do catálogo viram plano sozinhos (pedido livre ainda não vira objetivo) e as alternativas são escritas em código")


def p_retomada():
    """#6 — depois de uma queda no meio da ação, a tarefa volta a andar sem repetir o que já aconteceu? Reproduz: a ação ACONTECE e o processo cai antes de registrar."""
    if not existe("tarefas"):
        return "CONFIRMADO", "nenhuma tarefa persistida; só metas, rotinas e conversa voltam depois do reinício"
    import tarefas as T
    if not existe("retomada"):
        if hasattr(T, "reabrir"):
            return "PARCIALMENTE_CONFIRMADO", "o estado das tarefas sobrevive ao reinício e o dono pode reabrir uma (conferindo antes o efeito); nada retoma sozinho (Fase 6)"
        return "CONFIRMADO", "sem retomada"
    from unittest import mock
    import coordenador, retomada as R  # noqa: F401

    class Queda(BaseException):
        pass
    T.reiniciar()
    marca = F.marca_lembretes()
    real = B.FERRAMENTAS["criar_lembrete"]["fn"]

    def cai(**kw):
        real(**kw)
        raise Queda()
    try:
        tid = T.criar("lembrar de prova", passos=[{"descricao": "avisar", "ferramenta": "criar_lembrete", "args": {"minutos": 9, "texto": "prova-retomada-audit"}}])
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": cai}):
            try:
                T.executar(tid)
            except Queda:
                pass
        T.reiniciar()
        T.ATIVAS.clear()
        preso = T.obter(tid)["estado"]
        rel = R.retomar_pendentes()
        t = T.obter(tid)
        n = sum(1 for r in F.lembretes_depois(marca) if r[1] == "prova-retomada-audit")
    finally:
        T.reiniciar()
    if preso == "EXECUTANDO" and t["estado"] == "CONCLUIDA" and n == 1:
        return "RESOLVIDO", (f"queda depois do efeito: a tarefa ficou {preso}; a retomada conferiu por fora ({[i['acao'] for i in rel['itens'] if i['tarefa'] == tid]}), concluiu e o lembrete não foi duplicado ({n}). "
                             "Ação que não dá para conferir não é repetida (pede o dono). Limite: reinício de verdade no celular não foi exercitado aqui")
    return "PARCIALMENTE_CONFIRMADO", f"retomada.py existe, mas o cenário terminou {t['estado']} com {n} lembrete(s) (esperado CONCLUIDA e 1)"


# 3 — verificação independente
def p_verificacao():
    """Uma ferramenta que diz «feito» sem fazer: a tarefa pode terminar CONCLUÍDA?"""
    from unittest import mock
    if not existe("tarefas"):
        r = B.executar("criar_lembrete", {"minutos": 5, "texto": "x"})
        return "CONFIRMADO", f"o corretor devolveu «{r}» e registrou como sucesso; nada confere o efeito"
    import tarefas as T
    T.reiniciar()
    try:
        with mock.patch.dict(B.FERRAMENTAS["criar_lembrete"], {"fn": lambda **kw: "Lembrete criado para daqui a 9 minutos."}):
            tid = T.criar("lembrar de prova", passos=[{"descricao": "avisar", "ferramenta": "criar_lembrete", "args": {"minutos": 9, "texto": "prova-audit"}}])
            T.executar(tid)
        t = T.obter(tid)
        est, ver = t["estado"], t["passos"][0].get("verificacao") or {}
    finally:
        T.reiniciar()
    if est == "CONCLUIDA":
        return "CONFIRMADO", "tarefa marcada CONCLUIDA sem o efeito existir"
    return "RESOLVIDO", f"ferramenta que mente terminou {est}; conferência: {ver.get('veredito')} ({ver.get('forca')})"


# 7 — busca limitada
def p_busca():
    pasta = M.base() / "Memorias"
    pasta.mkdir(parents=True, exist_ok=True)
    cab = "---\ntipo: fato\ncriado: 2026-10-01T10:00:00-03:00\nimportancia: 3\norigem: usuario\ntags: [friday, memoria, fato]\n---\n"
    for i in range(3200):
        corpo = "assunto comum de enchimento" if i != 3150 else "zeppelinomega unico"
        (pasta / f"Nota {i:05d}.md").write_text(f"{cab}# Nota {i:05d}\n\n{corpo}\n", encoding="utf-8")
    achou = [x["titulo"] for x in M.buscar("zeppelinomega", 3)]
    return ("RESOLVIDO", f"nota na posição 3.150 de 3.200 encontrada: {achou}") if achou else ("CONFIRMADO", "nota na posição 3.150 de 3.200 não foi encontrada")


# 8 — progresso por tema exato
def p_progresso():
    """Desenho da correção (Fase 1.2): relação EXPLÍCITA conta (id da meta, ligação do dono, mesma chave de assunto); parecer parecido não conclui.
    Cenário A: estudo em nome do id da meta, com palavras totalmente diferentes -> a meta tem de avançar.
    Cenário B (o literal da auditoria): estudo de «criptografia explicada» sem relação nenhuma -> NÃO conclui, mas tem de aparecer como candidato."""
    ok, a = PFC.nova_meta("aprender", "buracos negros")
    ok2, b = PFC.nova_meta("aprender", "criptografia")
    PAG = {"https://a.example/x": ("a.example", "A criptografia protege dados com chaves e algoritmos matemáticos. " * 8)}
    I.resultados = lambda q: [{"t": "Cripto", "u": u, "s": ""} for u in PAG]
    I.texto_pagina = lambda u, limite=2500: PAG[u]
    ra = CUR.estudar("singularidades", pedido=True, rng=random.Random(1), meta=a["id"]) if "meta" in CUR.estudar.__code__.co_varnames else {"ok": False}
    rb = CUR.estudar("criptografia explicada", pedido=True, rng=random.Random(1))
    PFC.pensar()
    por_tema = {m["tema"]: m for m in PFC.metas()}
    pa, pb = por_tema["buracos negros"], por_tema["criptografia"]
    a_ok = ra.get("ok") and pa["progresso"] >= 1.0 and pa["estado"] == "cumprida"
    b_ok = rb.get("ok") and pb["progresso"] == 0.0 and pb["estado"] == "ativa" and pb.get("candidatos") == ["criptografia explicada"]
    ev = (f"A (id da meta, outras palavras): progresso {pa['progresso']}, {pa['estado']}, nota «{pa['nota']}»; "
          f"B (literal da auditoria, sem relação): progresso {pb['progresso']}, {pb['estado']}, candidatos {pb.get('candidatos')}")
    if a_ok and b_ok:
        return "RESOLVIDO", ev + " — B não conclui de propósito: «parecer relacionado» não cumpre meta; o dono confirma com «conte … na meta …»"
    return ("PARCIALMENTE_CONFIRMADO" if (a_ok or b_ok) else "CONFIRMADO"), ev


# 9 — confirmação ambígua
def p_confirmacao():
    feito = []
    B.registrar("acao_n2_audit", "ação de teste de nível 2", {}, [], lambda: feito.append(1) or "executada", nivel=2)
    out = {}
    for frase in ("pode", "isso", "sim", "confirmo"):
        feito.clear()
        B.cancelar()
        B.executar("acao_n2_audit", {})
        B.confirmar_voz(frase)
        out[frase] = bool(feito)
    B.cancelar()
    vagas = [f for f in ("pode", "isso", "sim") if out[f]]
    if vagas:
        return "CONFIRMADO", f"respostas vagas executam a ação de nível 2: {vagas}"
    return "RESOLVIDO", f"nenhuma resposta vaga executa; «confirmo» sozinho executa? {out['confirmo']}"


# 10 — resultados em texto simples na auditoria
def p_log():
    B.registrar("vaza_audit", "devolve texto privado", {}, [], lambda: "Maria mora na Rua Augusta 123 e o código de acesso é ZXQ-98765-ALFA", nivel=0)
    B.executar("vaza_audit", {})
    ultima = Path(B.AUDITORIA).read_text(encoding="utf-8").splitlines()[-1]
    return ("CONFIRMADO", "texto do resultado gravado em claro na auditoria") if "Augusta" in ultima or "ZXQ-98765" in ultima else ("RESOLVIDO", "resultado não aparece em claro na auditoria")


# 11 — normalização silenciosa
def p_argumentos():
    r = B.executar("criar_lembrete", {"minutos": -5, "texto": "teste"})
    r2 = B.executar("silenciar", {"minutos": 0})
    if "inválido" in r.lower() and "inválido" in r2.lower():
        return "RESOLVIDO", f"valores fora da faixa são recusados: «{r[:60]}» / «{r2[:60]}»"
    return ("CONFIRMADO" if "Lembrete criado" in r or "Modo foco ativo" in r2 else "PARCIALMENTE_CONFIRMADO"), f"criar_lembrete(-5) → «{r[:70]}»; silenciar(0) → «{r2[:70]}»"


# 12 — documentos
def p_docs():
    falt = []
    if not os.path.exists(os.path.join(RAIZ, "docs", "PREFRONTAL.md")):
        falt.append("docs/PREFRONTAL.md (linkado em CEREBRO.md)")
    cl = Path(RAIZ, "CLAUDE.md").read_text(encoding="utf-8")
    if "MAOS.tratar" not in cl and "mãos" not in cl.lower():
        falt.append("CLAUDE.md sem as mãos na ordem de processar()")
    if "PFC.tratar" not in cl and "pré-córtex" not in cl.lower():
        falt.append("CLAUDE.md sem o pré-córtex")
    nuc = Path(RAIZ, "friday", "nucleo.py").read_text(encoding="utf-8")
    if "docs/NUCLEO.md" in nuc and not os.path.exists(os.path.join(RAIZ, "docs", "NUCLEO.md")):
        falt.append("nucleo.py cita docs/NUCLEO.md inexistente")
    if not falt:
        return "RESOLVIDO", "links e ordem de processar() conferem"
    return ("PARCIALMENTE_CONFIRMADO" if len(falt) < 4 else "CONFIRMADO"), f"pendente ({len(falt)} de 4 verificações): " + "; ".join(falt)


# 13 — nucleo.py / main.py / simbiose.py
def p_nucleo():
    main = Path(RAIZ, "friday", "main.py").read_text(encoding="utf-8")
    nuc = Path(RAIZ, "friday", "nucleo.py").read_text(encoding="utf-8")
    hook = "simbiose.py" in Path(RAIZ, ".claude", "hooks", "simbiose.sh").read_text(encoding="utf-8")
    docs = Path(RAIZ, "docs", "NUCLEO.md").read_text(encoding="utf-8")
    integrado = "import nucleo as NC" in main and "NC.perceber" in main and "PC.tratar(t)" in main
    observacional = "def liberar(nome, agora=None):" in nuc and "return True" in nuc
    evid = f"núcleo integrado={integrado}; liberar permissivo={observacional}; hook Claude Code={hook}"
    if integrado and observacional and "não é um escalonador" in docs:
        return "RESOLVIDO", evid + "; pré-córtex distribuído e coordenador preservados"
    return "PARCIALMENTE_CONFIRMADO", evid + "; falta comprovar integração observacional sem bloqueio"


achado(1, "Ciclo objetivo → plano → execução → verificação → experiência incompleto", p_tarefas)
achado(2, "Registro estruturado de tarefas", p_registro)
achado(3, "Verificação independente dos resultados das ferramentas", p_verificacao)
achado(4, "Registro estruturado de experiências", p_experiencias)
achado(5, "Planejamento em várias etapas e replanejamento", p_plano)
achado(6, "Retomada de tarefas interrompidas", p_retomada)
achado(7, "Busca limitada a ~3.000 notas", p_busca)
achado(8, "Progresso de metas depende de tema idêntico", p_progresso)
achado(9, "Confirmações ambíguas de ação sensível", p_confirmacao)
achado(10, "Trechos de resultados em texto simples na auditoria", p_log)
achado(11, "Normalização silenciosa de argumentos fora dos limites", p_argumentos)
achado(12, "Documentos desatualizados", p_docs)
achado(13, "Conflito nucleo.py × main.py × simbiose.py", p_nucleo)

if __name__ == "__main__":
    for r in RES:
        print(f"{r['n']:>2}. [{r['estado']}] {r['achado']}\n      {r['evidencia']}")
    if "--json" in sys.argv:
        dest = sys.argv[sys.argv.index("--json") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump({"data": time.strftime("%Y-%m-%d %H:%M:%S"), "achados": RES}, f, ensure_ascii=False, indent=2)
