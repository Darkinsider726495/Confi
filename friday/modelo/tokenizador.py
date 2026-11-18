"""Tokenizador BPE (byte-pair encoding) próprio, por bytes — a ideia do Karpathy, completa: treino, encode, decode, salvar e carregar.

Treino rápido: as fusões são feitas sobre as PALAVRAS ÚNICAS (com a contagem de cada uma), não sobre o texto inteiro, então treinar um vocabulário
de alguns milhares em megabytes de texto leva segundos/minutos em Python puro. Toda sequência de bytes é representável (nada vira «desconhecido»).
"""
import json, re
from collections import Counter

PADRAO = re.compile(r" ?[^\W\d_]+| ?\d{1,3}| ?[^\s\w]+|\s+(?!\S)|\s+", re.UNICODE)   # palavra, número, pontuação, espaços (estilo GPT-2)


class BPETokenizer:
    def __init__(self, vocab_size=2048):
        if vocab_size < 256:
            raise ValueError("vocab_size precisa ser pelo menos 256 (um token por byte)")
        self.vocab_size = vocab_size
        self.vocab = {i: bytes([i]) for i in range(256)}
        self.merges = {}                     # (a, b) -> novo id, na ordem em que foram aprendidas (ordem = prioridade)
        self._cache = {}

    # ------------------------------------------------------------ treino
    def train(self, text, relatorio=None):
        palavras = Counter(m.group(0).encode("utf-8") for m in PADRAO.finditer(text))
        seqs = {w: list(w) for w in palavras}
        while len(self.vocab) < self.vocab_size:
            pares = Counter()
            for w, n in palavras.items():
                s = seqs[w]
                for p in zip(s, s[1:]):
                    pares[p] += n
            if not pares:
                break                                       # texto curto demais para mais fusões
            melhor = max(pares, key=pares.get)
            if pares[melhor] < 2:
                break                                       # fundir par que aparece uma vez só não ensina nada
            novo = len(self.vocab)
            self.merges[melhor] = novo
            self.vocab[novo] = self.vocab[melhor[0]] + self.vocab[melhor[1]]
            for w in seqs:
                seqs[w] = self._merge(seqs[w], melhor, novo)
            if relatorio and novo % 200 == 0:
                relatorio(novo, self.vocab[novo])
        self.contagem = palavras                                     # guarda a contagem: o aprendizado contínuo continua daqui
        self._cache.clear()
        return self

    @staticmethod
    def _merge(tokens, pair, new_id):
        out, i, n = [], 0, len(tokens)
        while i < n:
            if i < n - 1 and tokens[i] == pair[0] and tokens[i + 1] == pair[1]:
                out.append(new_id)
                i += 2
            else:
                out.append(tokens[i])
                i += 1
        return out

    # ------------------------------------------------------------ aprendizado CONTÍNUO
    def atualizar(self, texto_novo, crescer=64, minimo=3, relatorio=None):
        """Continua aprendendo com texto novo, sem nunca mudar os tokens que já existem (os números ficam iguais: o modelo treinado continua
        valendo). Soma as palavras novas à contagem guardada e faz até `crescer` fusões novas com os pares que aparecem pelo menos `minimo`
        vezes. Devolve a lista de tokens novos (em texto)."""
        cont = getattr(self, "contagem", Counter())
        for m in PADRAO.finditer(texto_novo):
            cont[m.group(0).encode("utf-8")] += 1
        if len(cont) > 300_000:                                  # memória limitada: guarda só as palavras mais frequentes
            cont = Counter(dict(cont.most_common(200_000)))
        self.contagem = cont
        seqs = {w: list(self._encode_palavra(w)) for w in cont}   # o que já sabe (mesmo resultado de aplicar as fusões na ordem)
        novos = []
        for _ in range(max(0, crescer)):
            pares = Counter()
            for w, n in cont.items():
                s = seqs[w]
                for p in zip(s, s[1:]):
                    pares[p] += n
            if not pares:
                break
            melhor = max(pares, key=pares.get)
            if pares[melhor] < minimo:
                break
            nid = len(self.vocab)
            self.merges[melhor] = nid
            self.vocab[nid] = self.vocab[melhor[0]] + self.vocab[melhor[1]]
            for w in seqs:
                seqs[w] = self._merge(seqs[w], melhor, nid)
            novos.append(self.vocab[nid].decode("utf-8", errors="replace"))
            if relatorio:
                relatorio(nid, novos[-1], pares[melhor])
        self.vocab_size = max(self.vocab_size, len(self.vocab))
        self._cache.clear()
        return novos

    # ------------------------------------------------------------ uso
    def _encode_palavra(self, b):
        if b in self._cache:
            return self._cache[b]
        s = list(b)
        while len(s) > 1:
            par = min(zip(s, s[1:]), key=lambda p: self.merges.get(p, 1 << 30))
            if par not in self.merges:
                break
            s = self._merge(s, par, self.merges[par])
        if len(self._cache) < 200_000:
            self._cache[b] = s
        return s

    def encode(self, text):
        out = []
        for m in PADRAO.finditer(text):
            out.extend(self._encode_palavra(m.group(0).encode("utf-8")))
        return out

    def decode(self, ids):
        return b"".join(self.vocab.get(int(i), b"") for i in ids).decode("utf-8", errors="replace")

    # ------------------------------------------------------------ disco
    def salvar(self, caminho):
        cont = getattr(self, "contagem", None)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"vocab_size": self.vocab_size, "merges": [[a, b, n] for (a, b), n in self.merges.items()],
                       "contagem": [[w.hex(), n] for w, n in cont.most_common(200_000)] if cont else []}, f)

    @classmethod
    def carregar(cls, caminho):
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
        t = cls(d["vocab_size"])
        for a, b, n in d["merges"]:
            t.merges[(a, b)] = n
            t.vocab[n] = t.vocab[a] + t.vocab[b]
        if d.get("contagem"):
            t.contagem = Counter({bytes.fromhex(w): n for w, n in d["contagem"]})
        return t

    def __len__(self):
        return len(self.vocab)
