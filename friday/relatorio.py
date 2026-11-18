"""Relatório de evolução: todo dia ela anota os SEUS NÚMEROS e INVESTIGA o que deu errado, para você (e o Claude) acompanharem o treino dela.

  números       neurônios, sinapses, padrões, estudos (e fontes lidas por inteiro), rotina (GRU), significado, recompensa, chamadas de IA, backup
  comparação    o que mudou desde ontem e em 7 dias (+/−)
  investigação  problemas achados nos próprios dados: estudos que falharam, IA perto do limite, backup atrasado, rotina sem confiança, alertas do vigia
  onde fica     .cerebro/evolucao.jsonl (uma linha por dia, só números) e a nota «FRIDAY/Eu/Evolução.md» (tabela legível no Obsidian)
  quando        sozinha, uma vez por dia (gancho do laço proativo); na hora: «como você evoluiu?» / `python scripts/relatorio.py`
Nada de conteúdo pessoal: só contagens e nomes de partes dela.
"""
import json, os, re, time, datetime as dt
import memoria as M


def _arq():
    return M.base() / ".cerebro" / "evolucao.jsonl" if M.ativo() else None


def coletar():
    """Os números de agora (dict). Cada parte que falhar fica de fora, sem derrubar o resto."""
    n = {"dia": dt.date.today().isoformat(), "t": round(time.time())}
    def tenta(f):
        try:
            f()
        except Exception:
            pass
    def mem():
        import neuronios as N
        r = N.resumo()
        n.update(neuronios=r.get("neuronios", 0), sinapses=r.get("sinapses", 0), links=r.get("links", r.get("fortes", 0)))
    def estudos():
        b = M.base()
        n["estudos"] = len(list((b / "Estudos").glob("*.md"))) if (b / "Estudos").is_dir() else 0
        n["fontes_inteiras"] = len(list((b / "Estudos" / "Detalhes").glob("*.md"))) if (b / "Estudos" / "Detalhes").is_dir() else 0
        import curiosidade as CUR
        e = CUR._e()
        n.update(estudos_hoje=e["dia"]["n"], estudos_falhas=e.get("falhas", 0), curiosidade=bool(CUR.ativa()))
    def rotina():
        import rotina as R
        m = R.carregar()
        n["rotina"] = ("confiavel" if m[1].get("confiavel") else "aprendendo") if m else "juntando dados"
        if m:
            n["rotina_dias"] = m[1].get("dias")
    def sig():
        import significado as SIG
        n["significado"] = SIG.motor() or "desligado"
    def rec():
        import recompensa as RC
        n["votos_feedback"] = sum(sum(sum(v) for v in tab.values()) for tab in RC._ler().values())
    def ia():
        import ferramentas as F
        n["ia_hoje"] = F.usos_hoje()
        n["ia_limite"] = int(os.getenv("LIMITE_DIARIO", "200") or 200)
    def bk():
        import backup as BK
        t, _ = BK.ultimo()
        n["backup_dias"] = round((time.time() - t) / 86400, 1) if t else None
    def vig():
        import vigia as VIG
        n["vigia_alertas"] = len(VIG._ler().get("ult_avisos", []))
    for f in (mem, estudos, rotina, sig, rec, ia, bk, vig):
        tenta(f)
    return n


def historico():
    a = _arq()
    out = []
    try:
        for l in a.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    except (OSError, AttributeError):
        pass
    return out


def investigar(n):
    """Problemas que os números mostram (frases curtas, com o que fazer)."""
    p = []
    if n.get("estudos_falhas", 0) >= 2:
        p.append(f"{n['estudos_falhas']} estudos seguidos falharam: provavelmente sem internet ou com a busca bloqueada (bateria/dados em segundo plano).")
    if n.get("ia_limite") and n.get("ia_hoje", 0) >= 0.9 * n["ia_limite"]:
        p.append(f"Usei {n['ia_hoje']} de {n['ia_limite']} chamadas de IA hoje: perto do limite (LIMITE_DIARIO no .env).")
    if n.get("backup_dias") is None:
        p.append("Ainda não há cópia de segurança do cérebro: diga «faça um backup».")
    elif n["backup_dias"] > 9:
        p.append(f"A última cópia de segurança foi há {n['backup_dias']:.0f} dias.")
    if n.get("rotina") == "aprendendo":
        p.append("A rede da rotina ainda não vence o jeito simples: preciso de mais dias de uso regular.")
    if n.get("curiosidade") is False:
        p.append("A curiosidade está desligada: não estou estudando sozinha («ligue a curiosidade»).")
    if n.get("significado") == "desligado":
        p.append("A rede de significado está desligada (falta NumPy ou o modelo).")
    if n.get("vigia_alertas"):
        p.append(f"O vigia tem {n['vigia_alertas']} alerta(s) recente(s): «como está a minha segurança?».")
    return p


def _delta(n, antes, chave):
    if not antes or chave not in n or chave not in antes or not isinstance(n[chave], (int, float)) or not isinstance(antes[chave], (int, float)):
        return ""
    d = n[chave] - antes[chave]
    return f" ({'+' if d >= 0 else ''}{d:g})" if d else " (=)"


def relatorio(n=None):
    """Texto do relatório de hoje, comparando com ontem e com 7 dias atrás."""
    n = n or coletar()
    h = [x for x in historico() if x.get("dia") != n["dia"]]
    ontem = h[-1] if h else None
    semana = next((x for x in reversed(h) if x.get("dia", "") <= (dt.date.today() - dt.timedelta(days=7)).isoformat()), None)
    linhas = [f"Relatório de evolução de {n['dia']} (entre parênteses: desde {'ontem' if ontem else 'o começo'}; em 7 dias quando houver)."]
    def item(rot, chave, sufixo=""):
        if chave in n and n[chave] is not None:
            s = f"{rot}: {n[chave]}{sufixo}{_delta(n, ontem, chave)}"
            if semana and _delta(n, semana, chave):
                s += f", em 7 dias{_delta(n, semana, chave)}"
            linhas.append(s)
    item("Neurônios", "neuronios"); item("Sinapses", "sinapses"); item("Padrões fortes", "links")
    item("Estudos", "estudos"); item("Fontes lidas por inteiro", "fontes_inteiras"); item("Estudos hoje", "estudos_hoje")
    item("Votos de feedback", "votos_feedback"); item("Chamadas de IA hoje", "ia_hoje")
    if "rotina" in n:
        linhas.append(f"Rotina (GRU): {n['rotina']}" + (f", {n['rotina_dias']} dias" if n.get("rotina_dias") else ""))
    if "significado" in n:
        linhas.append(f"Significado: {n['significado']}")
    if n.get("backup_dias") is not None:
        linhas.append(f"Último backup: há {n['backup_dias']:.0f} dia(s)")
    probs = investigar(n)
    linhas.append("Investigação: " + (" ".join(probs) if probs else "nenhum problema encontrado nos meus dados."))
    return "\n".join(linhas)


def registrar(agora=None):
    """Anota o dia (uma linha por dia; se já anotou hoje, troca pela versão mais nova) e reescreve a nota Eu/Evolução.md."""
    if not M.ativo():
        return None
    n = coletar()
    h = [x for x in historico() if x.get("dia") != n["dia"]] + [n]
    a = _arq()
    a.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in h), encoding="utf-8")
    os.replace(tmp, a)
    cab = "| dia | neurônios | sinapses | estudos | fontes inteiras | feedback | IA | rotina |\n|---|---|---|---|---|---|---|---|\n"
    tab = "".join(f"| {x.get('dia')} | {x.get('neuronios', '')} | {x.get('sinapses', '')} | {x.get('estudos', '')} | {x.get('fontes_inteiras', '')} | "
                  f"{x.get('votos_feedback', '')} | {x.get('ia_hoje', '')} | {x.get('rotina', '')} |\n" for x in reversed(h[-60:]))
    nota = (f"---\ntipo: eu\norigem: friday\n---\n# Evolução\n\nAnotado por mim todo dia: só números (nada pessoal).\n\n## Hoje\n\n"
            + relatorio(n).replace("\n", "\n\n") + "\n\n## Últimos dias\n\n" + cab + tab)
    eu = M.base() / "Eu"
    eu.mkdir(parents=True, exist_ok=True)
    t2 = eu / "Evolução.md.tmp"
    t2.write_text(nota, encoding="utf-8")
    os.replace(t2, eu / "Evolução.md")
    return n


_feito = {"dia": ""}


def gancho(agora=None):
    """Uma vez por dia (laço proativo). Não fala nada: só anota (o relatório sai quando você pede ou no bom dia)."""
    hoje = dt.date.today().isoformat()
    if _feito["dia"] == hoje or not M.ativo():
        return []
    _feito["dia"] = hoje
    try:
        registrar(agora)
    except Exception:
        pass
    return []


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_VER = re.compile(_P + r"(?:como voce evoluiu|como (?:esta|anda) (?:o )?seu treino|relatorio de evolucao|seus numeros|me (?:de|da|mostra) (?:o )?(?:seu )?relatorio)(?: hoje| essa semana)?[ ?!.]*$")


def tratar(texto):
    if not _VER.match(M._fold(" ".join(str(texto).split())).strip()):
        return None
    if not M.ativo():
        return "A memória está desligada: não tenho números para mostrar."
    registrar()
    return relatorio().replace("\n", " ")
