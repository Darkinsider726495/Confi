"""Treinador diário: todo dia ela se ESTIMULA sozinha, como o Claude faria se estivesse no celular.

Roteiro (uma vez por dia, a partir de TREINO_HORA, padrão 14:00; ou na hora com «treine agora»):
  1. aprofunda os assuntos NOVOS do dia (os neurônios de Topicos/ criados ou mexidos hoje): estuda cada um na internet, com profundidade;
  2. revisa o estudo mais antigo (relê as fontes: a informação pode ter mudado);
  3. reajusta a rede de significado com as sinapses e as suas correções;
  4. treina a GRU da rotina (se já tiver dias suficientes);
  5. anota o relatório de evolução e o resumo do treino.
Respeita as suas escolhas: os estudos só acontecem com a curiosidade LIGADA (só você liga/desliga a curiosidade). Tudo o que vem da internet
continua em quarentena. Sem teto de assuntos por padrão (TREINO_MAX_ESTUDOS no .env põe um). «desliga o treino diário» desliga.
"""
import json, os, re, threading, time, datetime as dt
import memoria as M

BASE = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(BASE, ".treino.json")
_rodando = threading.Lock()


def _ler():
    try:
        with open(ARQ, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(d):
    tmp = ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, ARQ)


def ligado():
    v = _ler().get("ligado")
    return (os.getenv("TREINO", "1") != "0") if v is None else bool(v)


def _hora():
    h = os.getenv("TREINO_HORA", "14:00")
    return h if re.fullmatch(r"\d{2}:\d{2}", h) else "14:00"


def _teto():
    try:
        return max(0, int(os.getenv("TREINO_MAX_ESTUDOS", "0") or 0))
    except ValueError:
        return 0


def assuntos_do_dia(agora=None):
    """Neurônios de assunto (Topicos/) criados ou mexidos hoje, do mais recente ao mais antigo."""
    if not M.ativo():
        return []
    d = M.base() / "Topicos"
    hoje = dt.date.fromtimestamp(time.time() if agora is None else agora)
    out = []
    for f in d.glob("*.md") if d.is_dir() else []:
        try:
            if dt.date.fromtimestamp(f.stat().st_mtime) == hoje:
                out.append((f.stat().st_mtime, f.stem))
        except OSError:
            pass
    return [t for _, t in sorted(out, reverse=True)]


def estudo_mais_antigo():
    if not M.ativo():
        return None
    d = M.base() / "Estudos"
    arqs = sorted(d.glob("*.md"), key=lambda f: f.stat().st_mtime) if d.is_dir() else []
    return arqs[0].stem if arqs else None


def treinar(agora=None, estudar=None):
    """Um treino completo. Devolve o resumo (dict). `estudar` só para testes."""
    if not _rodando.acquire(blocking=False):
        return {"ok": False, "motivo": "já estou treinando"}
    try:
        import curiosidade as CUR
        estudar = estudar or (lambda t: CUR.estudar(t))
        r = {"ok": True, "dia": dt.date.today().isoformat(), "estudados": [], "falhas": 0, "revisado": None, "significado": None, "rotina": None}
        if CUR.ativa():
            temas = assuntos_do_dia(agora)
            if _teto():
                temas = temas[:_teto()]
            for t in temas:
                x = estudar(t)
                if isinstance(x, dict) and x.get("ok"):
                    r["estudados"].append(t)
                else:
                    r["falhas"] += 1
            try:
                import especialidade as ES             # a trilha de cibersegurança: os próximos temas, em ordem, todo dia
                if ES.ativa():
                    for t in ES.proximos(ES.por_dia()):
                        x = estudar(t)
                        if isinstance(x, dict) and x.get("ok"):
                            r.setdefault("trilha", []).append(t)
                        else:
                            r["falhas"] += 1
            except Exception:
                pass
            velho = estudo_mais_antigo()
            if velho and velho not in r["estudados"]:
                x = estudar(velho)
                r["revisado"] = velho if isinstance(x, dict) and x.get("ok") else None
        else:
            r["sem_curiosidade"] = True
        try:
            import significado as SIG
            r["significado"] = SIG.ajustar(epocas=15)
        except Exception:
            pass
        try:
            import rotina as R
            t = R.treinar()
            r["rotina"] = ("confiável" if t.get("confiavel") else "aprendendo") if t.get("ok") else t.get("motivo")
        except Exception:
            pass
        try:
            import relatorio as REL
            REL.registrar()
        except Exception:
            pass
        d = _ler()
        d["ultimo"] = r
        d["dia"] = r["dia"]
        d.setdefault("historico", []).append({"dia": r["dia"], "estudados": len(r["estudados"]), "falhas": r["falhas"]})
        _gravar(d)
        return r
    finally:
        _rodando.release()


def gancho(agora=None):
    """Laço proativo: uma vez por dia, depois de TREINO_HORA, roda o treino em segundo plano. Não fala: o resumo sai quando você pede."""
    if not ligado() or not M.ativo():
        return []
    agora_dt = dt.datetime.fromtimestamp(time.time() if agora is None else agora)
    if _ler().get("dia") == agora_dt.date().isoformat() or agora_dt.strftime("%H:%M") < _hora():
        return []
    d = _ler(); d["dia"] = agora_dt.date().isoformat(); _gravar(d)          # marca já: não dispara duas vezes no mesmo dia
    threading.Thread(target=treinar, daemon=True).start()
    return []


def resumo_falado():
    u = _ler().get("ultimo")
    if not u:
        return f"Ainda não treinei. Eu treino sozinha todo dia depois das {_hora()}, ou agora se você disser «treine agora»."
    partes = [f"No treino de {u['dia']}"]
    if u.get("sem_curiosidade"):
        partes.append("não estudei porque a curiosidade está desligada")
    else:
        partes.append(f"aprofundei {len(u['estudados'])} assunto(s) do dia" + (f" ({', '.join(u['estudados'][:5])})" if u["estudados"] else ""))
        if u.get("trilha"):
            partes.append(f"avancei na trilha de cibersegurança com {len(u['trilha'])} tema(s) ({', '.join(u['trilha'])})")
        if u.get("revisado"):
            partes.append(f"revisei o estudo «{u['revisado']}»")
        if u.get("falhas"):
            partes.append(f"{u['falhas']} estudo(s) falharam")
    if u.get("significado"):
        partes.append(f"reajustei a rede de significado com {u['significado']} exemplos")
    if u.get("rotina"):
        partes.append(f"rotina: {u['rotina']}")
    return ", ".join(partes) + "."


_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_AGORA = re.compile(_P + r"(?:treine agora|faca (?:o )?(?:seu )?treino agora|vai treinar|pode treinar agora)[ .!]*$")
_VER = re.compile(_P + r"(?:como foi (?:o )?(?:seu )?treino|o que voce treinou(?: hoje)?|como esta (?:o )?(?:seu )?treino diario)[ ?!.]*$")
_LIGA = re.compile(_P + r"(?:liga|ligue|ative) o treino(?: diario)?[ .!]*$")
_DESLIGA = re.compile(_P + r"(?:desliga|desligue|desative) o treino(?: diario)?[ .!]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if _AGORA.match(f):
        if _rodando.locked():
            return "Já estou treinando."
        threading.Thread(target=treinar, daemon=True).start()
        return "Começando o treino: vou aprofundar os assuntos de hoje, revisar um estudo antigo e reajustar as minhas redes. Depois pergunte «como foi o seu treino?»."
    if _VER.match(f):
        return resumo_falado()
    if _LIGA.match(f):
        d = _ler(); d["ligado"] = True; _gravar(d)
        return f"Treino diário ligado: todo dia depois das {_hora()} eu me treino sozinha."
    if _DESLIGA.match(f):
        d = _ler(); d["ligado"] = False; _gravar(d)
        return "Treino diário desligado. Continuo aprendendo nas conversas e nos estudos normais."
    return None
