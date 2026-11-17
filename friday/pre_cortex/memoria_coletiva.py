"""Memória coletiva derivada de eventos operacionais seguros.

Não armazena texto livre, planos, argumentos, credenciais ou conteúdo de conversa.
Aprendizagem é descritiva: contagens e transições, nunca alteração de políticas.
"""
import copy
import json
import os
import threading
from collections import Counter, deque

CAMPOS_SEGUROS = {"estado", "modulo", "recuperavel", "tipo_objetivo", "suportado",
                  "neuronio", "acao", "ok", "codigo", "worker", "de", "para", "fase_origem", "fase_destino"}
TIPOS_IGNORADOS = {"objetivo_recebido", "mensagem_enviada", "mensagem_recebida",
                   "autorizacao_concedida", "autorizacao_negada", "corretor_respondeu"}


def projetar_evento(evento):
    """Retorna apenas metadados explicitamente permitidos para replay/contexto."""
    if not isinstance(evento, dict):
        return None
    tipo = evento.get("tipo") or evento.get("evento")
    if not isinstance(tipo, str) or not tipo or len(tipo) > 48:
        return None
    dados = evento.get("dados") if isinstance(evento.get("dados"), dict) else evento
    seguros = {k: v for k, v in dados.items() if k in CAMPOS_SEGUROS and isinstance(v, (str, int, float, bool, type(None)))}
    return {"evento": tipo, "fase": str(evento.get("fase", ""))[:40],
            "ciclo": int(evento.get("ciclo", 0) or 0), "dados": seguros,
            "emitido_em": float(evento.get("emitido_em", evento.get("em", 0)) or 0)}


class MemoriaColetiva:
    """Índice persistente de padrões operacionais, reconstruível a partir do JSONL."""
    def __init__(self, pasta=None, max_transicoes=10000):
        self.pasta = pasta
        self.max_transicoes = max(100, int(max_transicoes))
        self._lock = threading.RLock()
        self._tipos = Counter()
        self._transicoes = Counter()
        self._conexoes = Counter()
        self._ultimos = {}
        self._ultimo_neuronio = {}
        self._seq = 0
        self._historico = deque(maxlen=256)
        self.erros = 0
        self._suja = False
        self._parar = threading.Event()
        self._despertar = threading.Event()
        self._thread = None
        if pasta:
            os.makedirs(pasta, exist_ok=True)
            self._carregar()
            self._thread = threading.Thread(target=self._laco_gravacao, name="pc-memoria-coletiva", daemon=True)
            self._thread.start()

    @property
    def seq(self):
        return self._seq

    def _arquivo(self):
        return os.path.join(self.pasta, "memoria_coletiva.json")

    def _carregar(self):
        try:
            with open(self._arquivo(), encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get("v") == 1:
                self._tipos.update({str(k): int(v) for k, v in d.get("tipos", {}).items() if int(v) >= 0})
                self._transicoes.update({str(k): int(v) for k, v in d.get("transicoes", {}).items() if int(v) >= 0})
                self._conexoes.update({str(k): int(v) for k, v in d.get("conexoes", {}).items() if int(v) >= 0})
                self._ultimo_neuronio = {str(k): str(v) for k, v in d.get("ultimo_neuronio", {}).items()}
                self._ultimos = {str(k): str(v) for k, v in d.get("ultimos", {}).items()}
                self._seq = int(d.get("seq", 0))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.erros += 1

    def registrar(self, registro):
        """Incorpora evento sem texto livre. Chamado pelo processo proprietário do hub."""
        e = projetar_evento(registro)
        if not e:
            return None
        objetivo = str(registro.get("objetivo", ""))[:64]
        tipo = e["evento"]
        with self._lock:
            self._seq = max(self._seq + 1, int(registro.get("seq", 0) or 0))
            alvo = e["dados"].get("para") or e["dados"].get("neuronio")
            if objetivo and isinstance(alvo, str) and alvo and tipo in ("mensagem_enviada", "mensagem_recebida"):
                anterior_no = self._ultimo_neuronio.get(objetivo)
                if anterior_no and anterior_no != alvo:
                    self._conexoes[anterior_no + "->" + alvo] += 1
                self._ultimo_neuronio[objetivo] = alvo
            if tipo not in TIPOS_IGNORADOS:
                self._tipos[tipo] += 1
                anterior = self._ultimos.get(objetivo) if objetivo else None
                if anterior and anterior != tipo:
                    chave = anterior + "->" + tipo
                    self._transicoes[chave] += 1
                    if len(self._transicoes) > self.max_transicoes:
                        menor = min(self._transicoes, key=self._transicoes.get)
                        del self._transicoes[menor]
                if objetivo:
                    self._ultimos[objetivo] = tipo
            self._historico.append(e)
            self._suja = True
            self._despertar.set()
        return e

    def reconstruir(self, registros):
        """Reconstrói agregados do log de eventos quando o índice ainda não existe."""
        with self._lock:
            alterou = False
            for r in registros:
                e = projetar_evento(r)
                if not e:
                    continue
                self._historico.append(e)
                seq = int(r.get("seq", 0) or 0)
                if seq <= self._seq:
                    continue
                objetivo, tipo = str(r.get("objetivo", ""))[:64], e["evento"]
                self._seq = max(self._seq, seq)
                alterou = True
                alvo = e["dados"].get("para") or e["dados"].get("neuronio")
                if objetivo and isinstance(alvo, str) and alvo and tipo in ("mensagem_enviada", "mensagem_recebida"):
                    anterior_no = self._ultimo_neuronio.get(objetivo)
                    if anterior_no and anterior_no != alvo:
                        self._conexoes[anterior_no + "->" + alvo] += 1
                    self._ultimo_neuronio[objetivo] = alvo
                if tipo not in TIPOS_IGNORADOS:
                    self._tipos[tipo] += 1
                    anterior = self._ultimos.get(objetivo) if objetivo else None
                    if anterior and anterior != tipo:
                        self._transicoes[anterior + "->" + tipo] += 1
                    if objetivo:
                        self._ultimos[objetivo] = tipo
            if alterou:
                self._suja = True
                self._despertar.set()
            return alterou

    def _snapshot(self):
        return {"v": 1, "seq": self._seq, "tipos": dict(self._tipos),
                "transicoes": dict(self._transicoes), "conexoes": dict(self._conexoes),
                "ultimos": dict(self._ultimos), "ultimo_neuronio": dict(self._ultimo_neuronio)}

    def flush(self):
        """Grava o índice em lote; não é chamado no caminho síncrono de cada evento."""
        if not self.pasta:
            return True
        with self._lock:
            if not self._suja:
                return True
            d = self._snapshot()
        tmp = self._arquivo() + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, sort_keys=True)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self._arquivo())
            with self._lock:
                if self._seq == d["seq"]:
                    self._suja = False
            return True
        except OSError:
            with self._lock:
                self.erros += 1
            try: os.unlink(tmp)
            except OSError: pass
            return False

    def _laco_gravacao(self):
        while not self._parar.is_set():
            self._despertar.wait(0.5)
            self._despertar.clear()
            self.flush()
        self.flush()

    def encerrar(self):
        """Fecha o gravador e força a persistência do último lote."""
        if self._thread is None:
            return
        self._parar.set()
        self._despertar.set()
        self._thread.join(timeout=3.0)

    def resumo(self, limite=20):
        with self._lock:
            top_tipos = sorted(self._tipos.items(), key=lambda x: (-x[1], x[0]))[:limite]
            top_trans = sorted(self._transicoes.items(), key=lambda x: (-x[1], x[0]))[:limite]
            top_conex = sorted(self._conexoes.items(), key=lambda x: (-x[1], x[0]))[:limite]
            return {"persistente": bool(self.pasta), "seq": self._seq, "tipos": dict(top_tipos),
                    "transicoes": dict(top_trans), "conexoes_neuronios": dict(top_conex),
                    "eventos_contexto": copy.deepcopy(list(self._historico)),
                    "erros": self.erros}
