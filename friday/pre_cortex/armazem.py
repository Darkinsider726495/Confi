"""Armazenamento do pré-córtex: dossiês dos objetivos (JSON atômico) e histórico de eventos (JSONL que só acrescenta).

Nada aqui apaga: «limpar o cenário» MOVE os dois arquivos para `arquivo/<data>/` (os.replace) e recomeça vazio. As experiências (`experiencias.jsonl`) e as notas do
cofre não ficam aqui e não são tocadas. Sem pasta configurada o armazém vive só na memória do processo (e diz isso em `persistente`).
"""
import collections
import copy
import json
import os
import threading
import time


class Armazem:
    def __init__(self, pasta=None, relogio=time.time, eventos_em_memoria=3000):
        self.pasta = pasta
        self._rel = relogio
        self.trava = threading.RLock()
        self._objetivos = {"v": 1, "proximo": 1, "objetivos": {}}
        self._eventos = collections.deque(maxlen=eventos_em_memoria)
        self._seq = 0
        self.erros = 0
        self.ultimo_erro = ""
        if pasta:
            os.makedirs(pasta, exist_ok=True)
            self._carregar()

    @property
    def persistente(self):
        return bool(self.pasta)

    def _arq(self, nome):
        return os.path.join(self.pasta, nome)

    def _carregar(self):
        try:
            with open(self._arq("objetivos.json"), encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("objetivos"), dict) and isinstance(d.get("proximo"), int):
                self._objetivos = d
        except (OSError, ValueError):
            pass
        try:
            with open(self._arq("eventos.jsonl"), encoding="utf-8") as f:
                for linha in f:
                    try:
                        e = json.loads(linha)
                    except ValueError:
                        self.erros += 1
                        continue
                    if isinstance(e, dict) and isinstance(e.get("seq"), int):
                        self._eventos.append(e)
                        self._seq = max(self._seq, e["seq"])
        except OSError:
            pass

    # ------------------------------------------------------------------ objetivos
    def proximo_id(self):
        with self.trava:
            n = self._objetivos["proximo"]
            self._objetivos["proximo"] = n + 1
            return f"pc{n:04d}"

    def obter(self, oid):
        with self.trava:
            d = self._objetivos["objetivos"].get(oid)
            return d          # o mesmo objeto: quem altera segura `trava` e chama `salvar`

    def copia(self, oid):
        with self.trava:
            d = self._objetivos["objetivos"].get(oid)
            return copy.deepcopy(d) if d is not None else None

    def ids(self):
        with self.trava:
            return list(self._objetivos["objetivos"])

    def colocar(self, dossie):
        with self.trava:
            self._objetivos["objetivos"][dossie["id"]] = dossie

    def salvar(self):
        if not self.pasta:
            return
        with self.trava:
            try:
                tmp = self._arq("objetivos.json.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._objetivos, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self._arq("objetivos.json"))
            except OSError as e:
                self.erros += 1
                self.ultimo_erro = f"{type(e).__name__}: {e}"[:200]

    # ------------------------------------------------------------------ eventos
    def evento(self, objetivo, tipo, **campos):
        with self.trava:
            self._seq += 1
            e = {"seq": self._seq, "em": self._rel(), "objetivo": objetivo, "tipo": tipo, **campos}
            self._eventos.append(e)
            if self.pasta:
                try:
                    with open(self._arq("eventos.jsonl"), "a", encoding="utf-8") as f:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                except (OSError, TypeError, ValueError) as ex:
                    self.erros += 1
                    self.ultimo_erro = f"{type(ex).__name__}: {ex}"[:200]
            return e

    def eventos(self, desde=0, objetivo=None, limite=500):
        with self.trava:
            saida = [e for e in self._eventos if e["seq"] > desde and (objetivo is None or e.get("objetivo") == objetivo)]
            return copy.deepcopy(saida[-limite:])

    @property
    def seq(self):
        return self._seq

    # ------------------------------------------------------------------ limpar o cenário (arquiva, não apaga)
    def arquivar_cenario(self):
        """Move dossiês e eventos para arquivo/<data>/ e começa vazio. Devolve a pasta onde ficaram (ou None se nada havia / sem pasta)."""
        with self.trava:
            vazio = not self._objetivos["objetivos"] and not self._eventos
            destino = None
            if self.pasta and not vazio:
                destino = os.path.join(self.pasta, "arquivo", time.strftime("%Y%m%d-%H%M%S", time.localtime(self._rel())))
                base, n = destino, 1
                while os.path.exists(destino):
                    n += 1
                    destino = f"{base}-{n}"
                os.makedirs(destino, exist_ok=True)
                for nome in ("objetivos.json", "eventos.jsonl"):
                    if os.path.exists(self._arq(nome)):
                        os.replace(self._arq(nome), os.path.join(destino, nome))
            proximo = self._objetivos["proximo"]                 # os números não voltam: pc0001 nunca é reaproveitado
            self._objetivos = {"v": 1, "proximo": proximo, "objetivos": {}}
            self._eventos.clear()
            self.salvar()
            return destino
