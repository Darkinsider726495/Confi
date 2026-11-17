"""Rotina: uma rede neural RECORRENTE (GRU) que aprende o dia do dono pelo registro de atividades e prevê a próxima hora.

  entrada   as últimas 24 horas, hora a hora: o que aconteceu (fala com ela, câmera, mãos, os assuntos mais frequentes) + a hora
            do dia e o dia da semana (seno/cosseno). Só rótulos e assuntos do registro do pré-córtex — nunca frases.
  rede      GRU (memória temporal: a mesma família das «Temporal memory (GRU)» de visualizações de redes), NumPy puro, treinada
            no próprio celular com retropropagação no tempo e Adam.
  saída     a chance de cada coisa acontecer na PRÓXIMA hora.
  honesta   ela só confia na rede se, nos últimos dias (que a rede não viu no treino), ela errar menos que o jeito simples
            («o que costuma acontecer nesta hora»). Senão diz que ainda está aprendendo. Precisa de pelo menos 7 dias de registro.
  uso       «como é a minha rotina?», «o que você acha que eu vou fazer agora?»; e a conversa espontânea (se o dono ligou) pode se
            adiantar: «costuma falar de SQL por volta desta hora; quer que eu prepare algo?». Só sugere: não executa nada.
  treino    sozinha, uma vez por dia no tempo ocioso, ou `python scripts/treinar_rotina.py`. Modelo no cofre (.cerebro/rotina_gru.npz).
"""
import json, math, os, re, time, threading
import memoria as M

try:
    import numpy as np
except ImportError:
    np = None

JANELA = 24                 # horas que a rede olha para trás
OCULTO = 24                 # tamanho da memória da GRU
MAX_ROTULOS = 8             # fala + até 7 assuntos mais frequentes
MIN_DIAS = 7
DIAS_VALIDACAO = 2          # os últimos dias ficam fora do treino, para conferir se ela aprendeu de verdade
CONFIANCA_SUGERIR = 0.6     # chance mínima na próxima hora para ela se adiantar
_trava = threading.RLock()
_mod = {"v": None, "raiz": None}


def disponivel():
    return np is not None


# ---------------------------------------------------------------- dados: registro → horas
def _arq_registro():
    return M.base() / ".cerebro" / "atividades.jsonl" if M.ativo() else None


def _arq_modelo():
    return M.base() / ".cerebro" / "rotina_gru.npz" if M.ativo() else None


def ler_registro():
    """[(t, {rótulos})] do registro do pré-córtex: 'fala' quando o dono falou; 'visao'/'maos'; e cada assunto assimilado."""
    arq = _arq_registro()
    if not arq or not arq.exists():
        return []
    saida = []
    with open(arq, encoding="utf-8", errors="replace") as f:
        for linha in f:
            try:
                r = json.loads(linha)
                t = float(r["t"])
            except (ValueError, KeyError, TypeError):
                continue
            rot = set()
            origem = str(r.get("origem", ""))
            if origem in ("fala", "visao", "maos"):
                rot.add(origem)
            for a in r.get("assuntos") or []:
                a = " ".join(str(a).split())[:40]
                if a:
                    rot.add("assunto:" + a)
            if rot:
                saida.append((t, rot))
    return saida


def montar_series(eventos, agora=None, rotulos=None):
    """(rotulos, X, horas_inicio): matriz hora × rótulo (0/1) cobrindo do primeiro evento até a hora atual."""
    if not eventos:
        return [], None, None
    agora = time.time() if agora is None else agora
    if rotulos is None:
        cont = {}
        for _, rs in eventos:
            for r in rs:
                cont[r] = cont.get(r, 0) + 1
        assuntos = sorted((r for r in cont if r.startswith("assunto:")), key=lambda r: -cont[r])[:MAX_ROTULOS - 1]
        rotulos = (["fala"] if "fala" in cont else []) + assuntos
    idx = {r: i for i, r in enumerate(rotulos)}
    h0 = int(min(t for t, _ in eventos) // 3600)
    h1 = int(agora // 3600)
    X = np.zeros((h1 - h0 + 1, max(1, len(rotulos))), dtype=np.float32)
    for t, rs in eventos:
        h = int(t // 3600) - h0
        if 0 <= h < len(X):
            for r in rs:
                if r in idx:
                    X[h, idx[r]] = 1.0
    return rotulos, X, h0


def _tempo(hora_abs):
    """Hora do dia e dia da semana (hora local) em seno/cosseno + fim de semana."""
    lt = time.localtime(hora_abs * 3600)
    h, d = lt.tm_hour + lt.tm_min / 60, lt.tm_wday
    return [math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24), math.sin(2 * math.pi * d / 7), math.cos(2 * math.pi * d / 7),
            1.0 if d >= 5 else 0.0]


def exemplos(X, h0, inicio=JANELA, fim=None):
    """Janelas de 24 h → alvo da hora seguinte. Entrada de cada passo = rótulos da hora + tempo da PRÓXIMA hora (o que ela quer prever)."""
    fim = len(X) - 1 if fim is None else fim
    T = np.array([_tempo(h0 + i) for i in range(len(X) + 1)], dtype=np.float32)
    E = np.concatenate([X, T[1:len(X) + 1]], axis=1)
    xs, ys = [], []
    for k in range(inicio, fim + 1):
        if k >= len(X):
            break
        xs.append(E[k - JANELA:k])
        ys.append(X[k])
    if not xs:
        return None, None
    return np.stack(xs), np.stack(ys)


# ---------------------------------------------------------------- a GRU (para frente e para trás no tempo)
def _sig(x):
    return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def nova_rede(n_ent, n_saida, oculto=OCULTO, semente=5):
    rng = np.random.default_rng(semente)
    s = 1 / math.sqrt(oculto)
    p = {}
    for g in ("z", "r", "n"):
        p["W" + g] = rng.uniform(-s, s, (oculto, n_ent))
        p["U" + g] = rng.uniform(-s, s, (oculto, oculto))
        p["b" + g] = np.zeros(oculto)
    p["Wo"] = rng.uniform(-s, s, (n_saida, oculto))
    p["bo"] = np.zeros(n_saida)
    return p


def frente(p, xs):
    """xs: (lote, tempo, entrada). Devolve (probabilidades da próxima hora, cache)."""
    B, T, _ = xs.shape
    H = p["bz"].shape[0]
    h = np.zeros((B, H))
    cache = []
    for t in range(T):
        x = xs[:, t]
        z = _sig(x @ p["Wz"].T + h @ p["Uz"].T + p["bz"])
        r = _sig(x @ p["Wr"].T + h @ p["Ur"].T + p["br"])
        n = np.tanh(x @ p["Wn"].T + (r * h) @ p["Un"].T + p["bn"])
        hn = (1 - z) * n + z * h
        cache.append((x, h, z, r, n))
        h = hn
    y = _sig(h @ p["Wo"].T + p["bo"])
    return y, (cache, h)


def perda_e_gradientes(p, xs, ys, pesos=None):
    """Entropia cruzada binária média + gradientes (retropropagação no tempo)."""
    y, (cache, hT) = frente(p, xs)
    B = len(xs)
    w = np.ones_like(ys) if pesos is None else pesos
    perda = float(-(w * (ys * np.log(y + 1e-9) + (1 - ys) * np.log(1 - y + 1e-9))).sum() / B)
    g = {k: np.zeros_like(v) for k, v in p.items()}
    dlog = w * (y - ys) / B
    g["Wo"] = dlog.T @ hT
    g["bo"] = dlog.sum(0)
    dh = dlog @ p["Wo"]
    for x, h, z, r, n in reversed(cache):
        dn = dh * (1 - z)
        dz = dh * (h - n)
        dhp = dh * z
        dan = dn * (1 - n * n)
        g["Wn"] += dan.T @ x
        g["bn"] += dan.sum(0)
        g["Un"] += dan.T @ (r * h)
        drh = dan @ p["Un"]
        dr = drh * h
        dhp += drh * r
        daz = dz * z * (1 - z)
        dar = dr * r * (1 - r)
        g["Wz"] += daz.T @ x
        g["Uz"] += daz.T @ h
        g["bz"] += daz.sum(0)
        g["Wr"] += dar.T @ x
        g["Ur"] += dar.T @ h
        g["br"] += dar.sum(0)
        dhp += daz @ p["Uz"] + dar @ p["Ur"]
        dh = dhp
    return perda, g


def treinar_rede(p, xs, ys, epocas=80, lr=0.02, lote=32, semente=3, relatorio=None):
    """Adam com corte de gradiente. Sem pesos artificiais: a chance que ela diz tem que ser uma chance de verdade (calibrada)."""
    rng = np.random.default_rng(semente)
    m = {k: np.zeros_like(v) for k, v in p.items()}
    v2 = {k: np.zeros_like(v) for k, v in p.items()}
    passo = 0
    for ep in range(epocas):
        ordem = rng.permutation(len(xs))
        total = 0.0
        for a in range(0, len(xs), lote):
            i = ordem[a:a + lote]
            perda, g = perda_e_gradientes(p, xs[i], ys[i])
            total += perda * len(i)
            norma = math.sqrt(sum(float((x * x).sum()) for x in g.values()))
            if norma > 5:
                g = {k: x * 5 / norma for k, x in g.items()}
            passo += 1
            for k in p:
                m[k] = 0.9 * m[k] + 0.1 * g[k]
                v2[k] = 0.999 * v2[k] + 0.001 * g[k] * g[k]
                p[k] -= lr * (m[k] / (1 - 0.9 ** passo)) / (np.sqrt(v2[k] / (1 - 0.999 ** passo)) + 1e-8)
        if relatorio:
            relatorio(ep + 1, total / len(xs))
    return p


def _bce(y, ys):
    return float(-(ys * np.log(y + 1e-9) + (1 - ys) * np.log(1 - y + 1e-9)).mean())


# ---------------------------------------------------------------- treinar com o registro dela
def treinar(agora=None, epocas=80, relatorio=None):
    """Treina com o registro; valida nos últimos dias contra o jeito simples. Salva no cofre. Devolve o resumo (dict)."""
    if np is None:
        return {"ok": False, "motivo": "precisa do NumPy (no Termux: pkg install python-numpy)"}
    eventos = ler_registro()
    rotulos, X, h0 = montar_series(eventos, agora)
    if X is None or not rotulos:
        return {"ok": False, "motivo": "ainda não há atividades registradas"}
    dias = len(X) / 24
    if dias < MIN_DIAS:
        return {"ok": False, "motivo": f"preciso de pelo menos {MIN_DIAS} dias de registro; tenho {dias:.1f}", "dias": round(dias, 1)}
    corte = len(X) - DIAS_VALIDACAO * 24
    xs, ys = exemplos(X, h0, fim=corte - 1)
    xv, yv = exemplos(X, h0, inicio=corte, fim=len(X) - 1)
    if xs is None or xv is None:
        return {"ok": False, "motivo": "dados insuficientes para treinar e conferir"}
    p = treinar_rede(nova_rede(xs.shape[2], len(rotulos)), xs, ys, epocas=epocas, relatorio=relatorio)
    yv_rede, _ = frente(p, xv)
    # jeito simples: a frequência de cada rótulo naquela hora do dia, no período de treino
    por_hora = np.zeros((24, len(rotulos)))
    cont_h = np.zeros(24)
    for i in range(corte):
        hd = time.localtime((h0 + i) * 3600).tm_hour
        por_hora[hd] += X[i]
        cont_h[hd] += 1
    por_hora = (por_hora + 0.1) / (cont_h[:, None] + 0.2)
    yv_simples = np.stack([por_hora[time.localtime((h0 + corte + k) * 3600).tm_hour] for k in range(len(yv))])
    perda_rede, perda_simples = _bce(yv_rede, yv), _bce(yv_simples, yv)
    confiavel = perda_rede < perda_simples
    resumo = {"ok": True, "dias": round(dias, 1), "rotulos": rotulos, "exemplos": len(xs), "perda_validacao": round(perda_rede, 4),
              "perda_jeito_simples": round(perda_simples, 4), "confiavel": bool(confiavel), "treinado_em": time.time()}
    arq = _arq_modelo()
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(arq) + ".tmp.npz"
    np.savez_compressed(tmp, meta=np.array(json.dumps(resumo, ensure_ascii=False)), **{k: v.astype(np.float32) for k, v in p.items()})
    os.replace(tmp, str(arq))
    with _trava:
        _mod.update(v=None)
    return resumo


def carregar():
    if np is None or not M.ativo():
        return None
    raiz = str(M.base())
    with _trava:
        if _mod["v"] is not None and _mod["raiz"] == raiz:
            return _mod["v"]
        arq = _arq_modelo()
        try:
            d = np.load(str(arq), allow_pickle=False)
            meta = json.loads(str(d["meta"]))
            p = {k: d[k].astype(np.float64) for k in d.files if k != "meta"}
            _mod.update(v=(p, meta), raiz=raiz)
            return _mod["v"]
        except (OSError, ValueError, KeyError):
            return None


def previsao(agora=None):
    """[(rótulo, chance)] da próxima hora, do mais provável ao menos. Vazio se não houver rede treinada."""
    m = carregar()
    if not m:
        return []
    p, meta = m
    agora = time.time() if agora is None else agora
    rotulos, X, h0 = montar_series(ler_registro(), agora, rotulos=meta["rotulos"])
    if X is None:
        return []
    if len(X) < JANELA:
        falta = JANELA - len(X)
        X = np.concatenate([np.zeros((falta, X.shape[1]), dtype=np.float32), X])
        h0 -= falta
    xs, _ = exemplos(np.concatenate([X, np.zeros((1, X.shape[1]), dtype=np.float32)]), h0, inicio=len(X), fim=len(X))
    if xs is None:
        return []
    y, _ = frente(p, xs.astype(np.float64))
    return sorted(zip(rotulos, (round(float(v), 3) for v in y[0])), key=lambda x: -x[1])


def _nome(r):
    return "falar comigo" if r == "fala" else "usar a câmera" if r == "visao" else "usar as mãos" if r == "maos" else r.split(":", 1)[-1].lower()


def sugestao(agora=None):
    """Uma frase para ela se adiantar, ou None: só com a rede confiável e um ASSUNTO com chance alta na próxima hora."""
    m = carregar()
    if not m or not m[1].get("confiavel"):
        return None
    for r, c in previsao(agora):
        if r.startswith("assunto:") and c >= CONFIANCA_SUGERIR:
            return {"chave": r, "texto": f"Pelo que aprendi da sua rotina, por volta desta hora você costuma falar de {_nome(r)}. Quer que eu prepare alguma coisa?"}
    return None


# ---------------------------------------------------------------- voz
_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_ROTINA = re.compile(_P + r"(?:como e a minha rotina|o que voce sabe da minha rotina|o que voce aprendeu da minha rotina)[ ?!.]*$")
_AGORA = re.compile(_P + r"(?:o que voce acha que eu vou fazer(?: agora)?|o que eu costumo fazer (?:agora|a esta hora|nesta hora)|o que vem agora)[ ?!.]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if not (_ROTINA.match(f) or _AGORA.match(f)):
        return None
    if np is None:
        return "Minha rede de rotina precisa do NumPy (no Termux: pkg install python-numpy)."
    m = carregar()
    if not m:
        r = treinar_status()
        return f"Ainda estou juntando dados da sua rotina: {r}. Sigo anotando, e treino sozinha quando tiver o bastante."
    p, meta = m
    if not meta.get("confiavel"):
        return (f"Treinei com {meta['dias']} dias, mas ainda não acerto melhor que o óbvio (erro {meta['perda_validacao']} contra "
                f"{meta['perda_jeito_simples']} do jeito simples). Preciso de mais dias para entender a sua rotina.")
    prev = [x for x in previsao() if x[1] >= 0.3][:3]
    if not prev:
        return "Pelo que aprendi, a próxima hora costuma ser tranquila para você."
    return ("Pelo que aprendi da sua rotina, na próxima hora o mais provável é: " + ", ".join(f"{_nome(r)} ({round(c * 100)}%)" for r, c in prev)
            + ". É uma previsão da minha rede, não uma certeza.")


TREINO_A_CADA_S = 24 * 3600
_treino = {"t": 0.0}


def treinar_se_for_hora(agora=None):
    """Chamado no tempo ocioso da assimilação: no máximo uma vez por dia. Devolve o resumo ou None."""
    agora = time.time() if agora is None else agora
    if np is None or not M.ativo() or agora - _treino["t"] < TREINO_A_CADA_S:
        return None
    _treino["t"] = agora
    return treinar(agora)


def treinar_status():
    eventos = ler_registro()
    if not eventos:
        return "ainda não há atividades registradas"
    dias = (time.time() - min(t for t, _ in eventos)) / 86400
    return f"tenho {dias:.1f} de {MIN_DIAS} dias"
