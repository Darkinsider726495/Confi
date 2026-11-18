"""GPT próprio em NumPy puro: a mesma arquitetura dos GPTs (Transformer só-decodificador), com treino (retropropagação escrita à mão + AdamW)
e geração de texto. Sem PyTorch, sem bibliotecas de IA: roda no celular (Termux), no PC e no Colab.

  entrada   ids de tokens (do tokenizador BPE próprio)
  blocos    L × [LayerNorm → atenção causal multi-cabeça → soma] + [LayerNorm → MLP (GELU) → soma]
  saída     LayerNorm final → logits pelo embedding de tokens (pesos amarrados) → próxima palavra
  treino    entropia cruzada da próxima palavra, AdamW, corte de gradiente
O gradiente de cada peça é conferido por diferença finita nos testes (tests/test_modelo_proprio.py).
"""
import json, math
import numpy as np

DT = np.float32


def _ln_f(x, g, b, eps=1e-5):
    mu = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    inv = 1.0 / np.sqrt(var + eps)
    xh = (x - mu) * inv
    return xh * g + b, (xh, inv, g)


def _ln_b(dy, cache):
    xh, inv, g = cache
    dg = (dy * xh).reshape(-1, xh.shape[-1]).sum(0)
    db = dy.reshape(-1, xh.shape[-1]).sum(0)
    dxh = dy * g
    n = xh.shape[-1]
    dx = inv / n * (n * dxh - dxh.sum(-1, keepdims=True) - xh * (dxh * xh).sum(-1, keepdims=True))
    return dx, dg, db


_C = math.sqrt(2.0 / math.pi)


def _gelu_f(x):
    t = np.tanh(_C * (x + 0.044715 * x ** 3))
    return 0.5 * x * (1 + t), (x, t)


def _gelu_b(dy, cache):
    x, t = cache
    dt = (1 - t * t) * _C * (1 + 3 * 0.044715 * x * x)
    return dy * (0.5 * (1 + t) + 0.5 * x * dt)


class GPT:
    def __init__(self, vocab, ctx=128, d=128, cabecas=4, camadas=4, semente=1337, dtype=DT, repeticoes=1):
        """`repeticoes` > 1 = modelo HÍBRIDO (profundidade recorrente): o texto passa R vezes pelas MESMAS camadas antes da resposta — pensa
        «mais fundo» sem ganhar parâmetros. O treino vira retropropagação através das repetições (BPTT na profundidade): o gradiente de cada
        passada se soma nos mesmos pesos."""
        assert d % cabecas == 0
        self.cfg = {"vocab": int(vocab), "ctx": int(ctx), "d": int(d), "cabecas": int(cabecas), "camadas": int(camadas),
                    "repeticoes": max(1, int(repeticoes))}
        self.dtype = dtype
        r = np.random.default_rng(semente)
        n = lambda *s, e=0.02: (r.standard_normal(s) * e).astype(dtype)
        z = lambda *s: np.zeros(s, dtype)
        o = lambda *s: np.ones(s, dtype)
        p = {"wte": n(vocab, d), "wpe": n(ctx, d), "lnf_g": o(d), "lnf_b": z(d)}
        ep = 0.02 / math.sqrt(2 * camadas)                     # projeções de saída menores (estabilidade, como no GPT-2)
        for l in range(camadas):
            p.update({f"{l}.ln1_g": o(d), f"{l}.ln1_b": z(d), f"{l}.wqkv": n(d, 3 * d), f"{l}.bqkv": z(3 * d),
                      f"{l}.wo": n(d, d, e=ep), f"{l}.bo": z(d), f"{l}.ln2_g": o(d), f"{l}.ln2_b": z(d),
                      f"{l}.wfc": n(d, 4 * d), f"{l}.bfc": z(4 * d), f"{l}.wpr": n(4 * d, d, e=ep), f"{l}.bpr": z(d)})
        self.p = p

    def expandir_vocab(self, novo_vocab, semente=7):
        """O tokenizador contínuo criou tokens novos: acrescenta linhas no embedding (as antigas ficam iguais; o modelo continua sabendo tudo
        o que sabia e aprende os novos no próximo treino)."""
        atual = self.p["wte"].shape[0]
        if novo_vocab <= atual:
            return 0
        r = np.random.default_rng(semente)
        extra = (r.standard_normal((novo_vocab - atual, self.cfg["d"])) * 0.02).astype(self.p["wte"].dtype)
        self.p["wte"] = np.concatenate([self.p["wte"], extra])
        self.cfg["vocab"] = int(novo_vocab)
        return novo_vocab - atual

    def n_parametros(self):
        return int(sum(v.size for v in self.p.values()))

    # ------------------------------------------------------------ para frente
    def _frente(self, idx, guardar=True):
        c, p = self.cfg, self.p
        B, T = idx.shape
        if T > c["ctx"]:
            raise ValueError("sequência maior que o contexto")
        H, D = c["cabecas"], c["d"]
        hd = D // H
        x = p["wte"][idx] + p["wpe"][:T]
        mascara = np.triu(np.ones((T, T), bool), 1)
        caches = []
        passadas = [l for _ in range(c.get("repeticoes", 1)) for l in range(c["camadas"])]   # híbrido: as mesmas camadas, R vezes
        for l in passadas:
            a, cl1 = _ln_f(x, p[f"{l}.ln1_g"], p[f"{l}.ln1_b"])
            qkv = a @ p[f"{l}.wqkv"] + p[f"{l}.bqkv"]
            q, k, v = (qkv[..., i * D:(i + 1) * D].reshape(B, T, H, hd).transpose(0, 2, 1, 3) for i in range(3))
            s = (q @ k.transpose(0, 1, 3, 2)) / math.sqrt(hd)
            s = np.where(mascara, -1e9, s)
            s = s - s.max(-1, keepdims=True)
            att = np.exp(s)
            att /= att.sum(-1, keepdims=True)
            y = (att @ v).transpose(0, 2, 1, 3).reshape(B, T, D)
            x = x + (y @ p[f"{l}.wo"] + p[f"{l}.bo"])
            m, cl2 = _ln_f(x, p[f"{l}.ln2_g"], p[f"{l}.ln2_b"])
            h = m @ p[f"{l}.wfc"] + p[f"{l}.bfc"]
            g, cg = _gelu_f(h)
            x = x + (g @ p[f"{l}.wpr"] + p[f"{l}.bpr"])
            if guardar:
                caches.append((l, a, cl1, q, k, v, att, y, m, cl2, g, cg))
        xf, clf = _ln_f(x, p["lnf_g"], p["lnf_b"])
        logits = xf @ p["wte"].T
        return logits, (idx, caches, xf, clf)

    def logits(self, idx):
        return self._frente(np.asarray(idx), guardar=False)[0]

    # ------------------------------------------------------------ perda e gradientes
    def perda_e_gradientes(self, idx, alvo):
        c, p = self.cfg, self.p
        logits, (idx, caches, xf, clf) = self._frente(idx)
        B, T, V = logits.shape
        z = logits - logits.max(-1, keepdims=True)
        pr = np.exp(z)
        pr /= pr.sum(-1, keepdims=True)
        n = B * T
        perda = float(-np.log(pr.reshape(n, V)[np.arange(n), alvo.reshape(-1)] + 1e-12).mean())
        dlog = pr
        dlog.reshape(n, V)[np.arange(n), alvo.reshape(-1)] -= 1
        dlog /= n
        g = {k: np.zeros_like(v) for k, v in p.items()}
        g["wte"] += dlog.reshape(n, V).T @ xf.reshape(n, -1)
        dx, g["lnf_g"], g["lnf_b"] = _ln_b(dlog @ p["wte"], clf)
        H, D = c["cabecas"], c["d"]
        hd = D // H
        for l, a, cl1, q, k, v, att, y, m, cl2, gg, cg in reversed(caches):    # BPTT: volta passada por passada, somando nos mesmos pesos
            # MLP
            g[f"{l}.wpr"] += gg.reshape(n, -1).T @ dx.reshape(n, -1)
            g[f"{l}.bpr"] += dx.reshape(n, -1).sum(0)
            dh = _gelu_b(dx @ p[f"{l}.wpr"].T, cg)
            g[f"{l}.wfc"] += m.reshape(n, -1).T @ dh.reshape(n, -1)
            g[f"{l}.bfc"] += dh.reshape(n, -1).sum(0)
            dm, dg2, db2 = _ln_b(dh @ p[f"{l}.wfc"].T, cl2)
            g[f"{l}.ln2_g"] += dg2
            g[f"{l}.ln2_b"] += db2
            dx = dx + dm
            # atenção
            g[f"{l}.wo"] += y.reshape(n, -1).T @ dx.reshape(n, -1)
            g[f"{l}.bo"] += dx.reshape(n, -1).sum(0)
            dy = (dx @ p[f"{l}.wo"].T).reshape(B, T, H, hd).transpose(0, 2, 1, 3)
            datt = dy @ v.transpose(0, 1, 3, 2)
            dv = att.transpose(0, 1, 3, 2) @ dy
            ds = att * (datt - (datt * att).sum(-1, keepdims=True)) / math.sqrt(hd)
            dq = ds @ k
            dk = ds.transpose(0, 1, 3, 2) @ q
            dqkv = np.concatenate([t.transpose(0, 2, 1, 3).reshape(B, T, D) for t in (dq, dk, dv)], -1)
            g[f"{l}.wqkv"] += a.reshape(n, -1).T @ dqkv.reshape(n, -1)
            g[f"{l}.bqkv"] += dqkv.reshape(n, -1).sum(0)
            da, dg1, db1 = _ln_b(dqkv @ p[f"{l}.wqkv"].T, cl1)
            g[f"{l}.ln1_g"] += dg1
            g[f"{l}.ln1_b"] += db1
            dx = dx + da
        np.add.at(g["wte"], idx, dx)
        g["wpe"][:T] += dx.sum(0)
        return perda, g

    # ------------------------------------------------------------ geração
    def gerar(self, ids, n=100, temperatura=0.8, top_k=40, parar=None, rng=None):
        """Continua a sequência `ids` por até `n` tokens. `parar(ids_novos)` → True interrompe (ex.: chegou «\\nDono:»)."""
        rng = rng or np.random.default_rng()
        ids = list(ids)
        novos = []
        for _ in range(n):
            ctx = np.array([ids[-self.cfg["ctx"]:]])
            z = self.logits(ctx)[0, -1].astype(np.float64)
            if temperatura <= 0:
                prox = int(z.argmax())
            else:
                z = z / temperatura
                if top_k and top_k < z.size:
                    corte = np.partition(z, -top_k)[-top_k]
                    z = np.where(z < corte, -np.inf, z)
                pz = np.exp(z - z.max())
                pz /= pz.sum()
                prox = int(rng.choice(z.size, p=pz))
            ids.append(prox)
            novos.append(prox)
            if parar and parar(novos):
                break
        return novos

    # ------------------------------------------------------------ disco
    def salvar(self, caminho, extra=None):
        meta = json.dumps({"cfg": self.cfg, **(extra or {})})
        np.savez_compressed(caminho, __meta__=np.array(meta), **{k: v.astype(DT) for k, v in self.p.items()})

    @classmethod
    def carregar(cls, caminho):
        d = np.load(caminho, allow_pickle=False)
        meta = json.loads(str(d["__meta__"]))
        m = cls(**meta["cfg"])
        m.p = {k: d[k].astype(DT) for k in d.files if k != "__meta__"}
        m.meta = meta
        return m


class AdamW:
    def __init__(self, params, lr=3e-4, betas=(0.9, 0.95), wd=0.1, corte=1.0):
        self.lr, self.b1, self.b2, self.wd, self.corte = lr, betas[0], betas[1], wd, corte
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def passo(self, params, grads, lr=None):
        lr = self.lr if lr is None else lr
        norma = math.sqrt(sum(float((g * g).sum()) for g in grads.values()))
        f = min(1.0, self.corte / (norma + 1e-6))
        self.t += 1
        for k, w in params.items():
            g = grads[k] * f
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * g
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * g * g
            mh = self.m[k] / (1 - self.b1 ** self.t)
            vh = self.v[k] / (1 - self.b2 ** self.t)
            decai = self.wd if w.ndim >= 2 else 0.0           # weight decay só nas matrizes (não em vieses nem LayerNorm)
            w -= lr * (mh / (np.sqrt(vh) + 1e-8) + decai * w)
        return norma
