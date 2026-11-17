"""Transporte de mensagens entre neurônios: modo local (threads, mesmo processo) e modo distribuído (HTTP entre processos).

Peças:
  Worker         hospeda neurônios, recebe mensagens, recusa as vencidas/canceladas, reconhece duplicatas pelo id e responde. É a MESMA classe nos dois modos.
  DestinoLocal   entrega a um Worker do mesmo processo (passando pelo JSON, como na rede).
  DestinoHTTP    entrega a um Worker em outro processo (ou outra máquina) por HTTP, com chave de sessão.
  ServidorHTTP   põe um Worker na rede local (por padrão só 127.0.0.1).
  Roteador       escolhe o destino pelo nome do neurônio e junta saúde e cancelamento de todos.

Sem dependências: só biblioteca padrão (http.server, urllib, threading). Nenhuma infraestrutura de mensageria é necessária.
Garantias, ditas com cuidado: entrega «ao menos uma vez» (o hub reenvia com o mesmo id) + dedupe no trabalhador + neurônios cognitivos idempotentes. Não há
«exatamente uma vez», e processo separado no mesmo computador prova distribuição entre processos, não entre máquinas.
"""
import collections
import copy
import hmac
import http.server
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

from . import contrato as C


class Indisponivel(Exception):
    """Não consegui falar com o destinatário (processo parado, porta fechada, rede)."""


class Recusado(Exception):
    """O destinatário respondeu, mas recusou a conversa (chave errada, host não permitido)."""


class _Reg:
    __slots__ = ("evento", "resposta", "criada", "correlacao")

    def __init__(self, correlacao):
        self.evento, self.resposta, self.criada, self.correlacao = threading.Event(), None, time.time(), correlacao


class _EstadoNeuronio:
    def __init__(self):
        self.em_andamento = self.recebidas = self.concluidas = self.falhas = self.duplicadas = 0
        self.ultimo_erro, self.ultima_acao, self.ultima_atividade, self.ultimo_resultado = "", "", 0.0, ""
        self.duracoes = collections.deque(maxlen=100)


PERSISTE_S = 3.0      # por quanto tempo «concluído»/«com erro» continua aparecendo antes de voltar a «ocioso»


class Worker:
    def __init__(self, nome, neuronios, *, max_paralelo=8, relogio=time.time, dedupe_max=4000):
        self.nome = nome
        self.neuronios = {n.nome: n for n in neuronios}
        self._rel = relogio
        self._trava = threading.RLock()
        self._vistos = collections.OrderedDict()
        self._eventos_vistos = collections.OrderedDict()  # dedupe separado: eventos nunca ocupam a cache de pedidos
        self._dedupe_max = dedupe_max
        self._cancelados = collections.OrderedDict()
        self._estados = {n: _EstadoNeuronio() for n in self.neuronios}
        self._emandamento = {}                       # id da mensagem -> correlacao (para cancelar o que está rodando)
        self._pool = None
        self._max_paralelo = max_paralelo
        self.iniciado_em = relogio()
        self.duplicatas = 0
        self.pid = os.getpid()

    # ------------------------------------------------------------------ receber
    def _pool_(self):
        if self._pool is None:
            import concurrent.futures
            self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=self._max_paralelo, thread_name_prefix=f"pc-{self.nome}")
        return self._pool

    def _falha(self, pedido, codigo, motivo, estado=None, neuronio=None, tempos=None):
        return C.resposta(pedido if isinstance(pedido, dict) else {}, de=neuronio or self.nome, ok=False, erro=(codigo, motivo), estado=estado,
                          processado_por={"worker": self.nome, "pid": self.pid, "neuronio": neuronio or ""}, tempos=tempos or {}, agora=self._rel())

    def processar(self, msg):
        """Recebe um pedido e devolve a resposta (bloqueia até terminar ou até o timeout do pedido). Nunca levanta."""
        recebida = self._rel()
        try:
            ok, motivo = C.validar(msg)
            if not ok:
                return self._falha(msg, "contrato_invalido", motivo)
            if msg["tipo"] == "cancelar":
                n = self.cancelar(msg["correlacao"])
                return C.resposta(msg, de=self.nome, ok=True, corpo={"cancelado": True, "em_andamento": n}, processado_por={"worker": self.nome, "pid": self.pid}, agora=self._rel())
            if msg["tipo"] == "evento":
                return self._receber_evento(msg, recebida)
            if msg["tipo"] != "pedido":
                return self._falha(msg, "contrato_invalido", f"tipo «{msg['tipo']}» não é tratado aqui")
            neuronio = self.neuronios.get(msg["para"])
            if neuronio is None:
                return self._falha(msg, "neuronio_desconhecido", f"este trabalhador ({self.nome}) não hospeda «{msg['para']}»")
            with self._trava:
                reg = self._vistos.get(msg["id"])
                novo = reg is None
                if novo:
                    if recebida > msg["expira_em"]:
                        return self._falha(msg, "expirada", "o prazo de validade da mensagem já passou", estado="expirada", neuronio=neuronio.nome)
                    if msg["correlacao"] in self._cancelados:
                        return self._falha(msg, "cancelada", "o objetivo foi cancelado", estado="cancelada", neuronio=neuronio.nome)
                    reg = _Reg(msg["correlacao"])
                    self._vistos[msg["id"]] = reg
                    while len(self._vistos) > self._dedupe_max:
                        self._vistos.popitem(last=False)
                    self._estados[neuronio.nome].recebidas += 1
                    self._emandamento[msg["id"]] = msg["correlacao"]
                else:
                    self.duplicatas += 1
                    self._estados[neuronio.nome].duplicadas += 1
            if novo:
                self._pool_().submit(self._rodar, msg, reg, neuronio, recebida)
            espera = max(0.0, min(msg["timeout_s"], msg["expira_em"] - recebida))
            reg.evento.wait(espera)
            if reg.resposta is None:
                return self._falha(msg, "timeout", f"«{neuronio.nome}.{msg['acao']}» ainda não terminou em {espera:.1f}s; reenvie com o mesmo id para pegar o resultado", estado="processando", neuronio=neuronio.nome)
            r = copy.deepcopy(reg.resposta)
            if not novo:
                r["duplicada"] = True
            return r
        except Exception as e:                                  # o trabalhador nunca cai por causa de uma mensagem
            return self._falha(msg, "erro_interno", f"{type(e).__name__}: {e}")

    def _receber_evento(self, msg, recebida):
        """Aceita evento em fan-out, agenda o hook em paralelo e responde sem esperar o neurônio.

        A deduplicação é independente da dos pedidos; um evento repetido não dispara
        novamente o hook. O evento não pode executar ferramentas nem avançar fases.
        """
        neuronio = self.neuronios.get(msg["para"])
        if neuronio is None:
            return self._falha(msg, "neuronio_desconhecido", f"este trabalhador ({self.nome}) não hospeda «{msg['para']}»")
        with self._trava:
            duplicada = msg["id"] in self._eventos_vistos
            if not duplicada:
                if recebida > msg["expira_em"]:
                    return self._falha(msg, "expirada", "o prazo de validade do evento já passou", estado="expirada", neuronio=neuronio.nome)
                self._eventos_vistos[msg["id"]] = recebida
                while len(self._eventos_vistos) > self._dedupe_max:
                    self._eventos_vistos.popitem(last=False)
        if not duplicada:
            self._pool_().submit(self._rodar_evento, msg, neuronio)
        return C.resposta(msg, de=self.nome, ok=True, corpo={"aceito": True, "duplicado": duplicada},
                          processado_por={"worker": self.nome, "pid": self.pid, "neuronio": neuronio.nome}, duplicada=duplicada, agora=self._rel())

    def _rodar_evento(self, msg, neuronio):
        try:
            from .neuronio import Contexto
            neuronio.receber_evento(C.ida_e_volta(msg["corpo"]), Contexto(msg, lambda: False, self.nome, neuronio.nome))
        except Exception:
            # Um assinante defeituoso não derruba o worker nem interfere nos pedidos.
            return

    def _rodar(self, msg, reg, neuronio, recebida):
        est = self._estados[neuronio.nome]
        with self._trava:
            est.em_andamento += 1
            est.ultima_acao = msg["acao"]
            est.ultima_atividade = self._rel()
        iniciada = self._rel()
        pp = {"worker": self.nome, "pid": self.pid, "neuronio": neuronio.nome}
        cancelado = lambda: msg["correlacao"] in self._cancelados            # noqa: E731
        try:
            if cancelado():
                raise C.ErroNeuronio("cancelada", "o objetivo foi cancelado antes de começar")
            from .neuronio import Contexto
            corpo = neuronio.tratar(msg["acao"], copy.deepcopy(msg["corpo"]), Contexto(msg, cancelado, self.nome, neuronio.nome))
            corpo = C.ida_e_volta(corpo)
            ok, erro, estado = True, None, "concluida"
        except C.ErroNeuronio as e:
            corpo, ok, erro = None, False, (e.codigo, e.mensagem)
            estado = "cancelada" if e.codigo == "cancelada" else "falhou"
        except Exception as e:
            corpo, ok, erro, estado = None, False, ("erro_interno", f"{type(e).__name__}: {str(e)[:200]}"), "falhou"
        fim = self._rel()
        tempos = {"recebida_em": recebida, "iniciada_em": iniciada, "concluida_em": fim, "duracao_ms": round((fim - iniciada) * 1000, 2)}
        resp = C.resposta(msg, de=neuronio.nome, ok=ok, corpo=corpo, erro=erro, estado=estado, processado_por=pp, tempos=tempos, agora=fim)
        with self._trava:
            est.em_andamento -= 1
            est.ultima_atividade = fim
            est.duracoes.append(tempos["duracao_ms"])
            if ok:
                est.concluidas += 1
                est.ultimo_resultado = "concluida"
            else:
                est.falhas += 1
                est.ultimo_erro = f"{erro[0]}: {erro[1]}"[:200]
                est.ultimo_resultado = "cancelada" if estado == "cancelada" else "erro"
            self._emandamento.pop(msg["id"], None)
            reg.resposta = resp
        reg.evento.set()

    # ------------------------------------------------------------------ cancelar e observar
    def cancelar(self, correlacao):
        """Marca o objetivo como cancelado: o que ainda não começou é recusado; o que está rodando vê `ctx.cancelado()`. Devolve quantas mensagens estavam em andamento."""
        with self._trava:
            self._cancelados[correlacao] = self._rel()
            while len(self._cancelados) > 1000:
                self._cancelados.popitem(last=False)
            return sum(1 for c in self._emandamento.values() if c == correlacao)

    def estado_de(self, nome, agora=None):
        t = self._rel() if agora is None else agora
        e = self._estados[nome]
        if e.em_andamento > 0:
            return "processando"
        if e.ultima_atividade and t - e.ultima_atividade < PERSISTE_S and e.ultimo_resultado:
            return {"concluida": "concluido", "erro": "erro", "cancelada": "bloqueado"}.get(e.ultimo_resultado, "ocioso")
        return "ocioso"

    def saude(self):
        t = self._rel()
        neur = {}
        for nome, e in self._estados.items():
            d = sorted(e.duracoes)
            neur[nome] = {"estado": self.estado_de(nome, t), "em_andamento": e.em_andamento, "recebidas": e.recebidas, "concluidas": e.concluidas, "falhas": e.falhas,
                          "duplicadas": e.duplicadas, "ultima_acao": e.ultima_acao, "ultimo_erro": e.ultimo_erro, "ultima_atividade": e.ultima_atividade,
                          "tempo_medio_ms": round(sum(d) / len(d), 2) if d else None, "tempo_p95_ms": d[min(len(d) - 1, int(len(d) * 0.95))] if d else None}
        return {"worker": self.nome, "pid": self.pid, "contrato": C.VERSAO, "iniciado_em": self.iniciado_em, "agora": t, "neuronios": neur,
                "dedupe": {"guardadas": len(self._vistos), "eventos_guardados": len(self._eventos_vistos), "duplicatas": self.duplicatas}, "cancelados": len(self._cancelados),
                "isolamento": {"corretor_carregado": "broker" in sys.modules, "tarefas_carregado": "tarefas" in sys.modules, "catalogo_carregado": "catalogo" in sys.modules}}

    def encerrar_pool(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------- destinos
class Destino:
    tipo = "?"
    nome = ""

    def enviar(self, msg, timeout_s):
        raise NotImplementedError

    def cancelar(self, correlacao):
        raise NotImplementedError

    def saude(self):
        raise NotImplementedError


class DestinoLocal(Destino):
    tipo = "local"

    def __init__(self, worker):
        self.worker, self.nome = worker, worker.nome
        self.derrubado = False                       # para testes: simula o trabalhador fora do ar
        self.atraso_s = 0.0

    def enviar(self, msg, timeout_s):
        if self.derrubado:
            raise Indisponivel(f"o trabalhador «{self.nome}» está fora do ar")
        if self.atraso_s:
            time.sleep(self.atraso_s)
        return C.ida_e_volta(self.worker.processar(C.ida_e_volta(msg)))

    def cancelar(self, correlacao):
        if self.derrubado:
            raise Indisponivel(self.nome)
        return self.worker.cancelar(correlacao)

    def saude(self):
        if self.derrubado:
            raise Indisponivel(self.nome)
        return C.ida_e_volta(self.worker.saude())


_SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # 127.0.0.1 nunca passa por proxy do ambiente


class DestinoHTTP(Destino):
    tipo = "http"

    def __init__(self, nome, url, token):
        self.nome, self.url, self.token = nome, url.rstrip("/"), token

    def _req(self, caminho, dados, timeout_s, metodo="POST"):
        corpo = json.dumps(dados).encode("utf-8") if dados is not None else None
        req = urllib.request.Request(self.url + caminho, data=corpo, method=metodo, headers={"Content-Type": "application/json", "X-Precortex-Token": self.token})
        try:
            with _SEM_PROXY.open(req, timeout=timeout_s) as r:
                return json.loads(r.read(C.TAMANHO_MAX * 2) or b"{}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 421):
                raise Recusado(f"{self.nome}: HTTP {e.code}") from None
            raise Indisponivel(f"{self.nome}: HTTP {e.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as e:                  # recusa de conexão, timeout, reset, corpo que não é JSON
            raise Indisponivel(f"{self.nome}: {type(e).__name__}: {e}") from None

    def enviar(self, msg, timeout_s):
        return self._req("/msg", msg, float(timeout_s) + 3.0)

    def cancelar(self, correlacao):
        return self._req("/cancelar", {"correlacao": correlacao}, 3.0).get("em_andamento", 0)

    def saude(self):
        return self._req("/saude", None, 2.5, metodo="GET")


class Roteador:
    """Escolhe o destino pelo neurônio de destino da mensagem. Os mesmos objetos servem aos dois modos."""

    def __init__(self):
        self.rotas = {}                              # neurônio -> Destino
        self.destinos = {}                           # nome do trabalhador -> Destino

    def registrar(self, destino, neuronios):
        self.destinos[destino.nome] = destino
        for n in neuronios:
            self.rotas[n] = destino

    def destino_de(self, neuronio):
        d = self.rotas.get(neuronio)
        if d is None:
            raise Indisponivel(f"nenhum trabalhador conhecido hospeda «{neuronio}»")
        return d

    def enviar(self, msg, timeout_s):
        return self.destino_de(msg["para"]).enviar(msg, timeout_s)

    def cancelar(self, correlacao):
        n = 0
        for d in list(self.destinos.values()):
            try:
                n += int(d.cancelar(correlacao) or 0)
            except (Indisponivel, Recusado):
                pass
        return n

    def saude(self):
        saida = {}
        for nome, d in self.destinos.items():
            t0 = time.time()
            try:
                s = d.saude()
                saida[nome] = {"disponivel": True, "tipo": d.tipo, "resposta_ms": round((time.time() - t0) * 1000, 2), **s}
            except (Indisponivel, Recusado) as e:
                saida[nome] = {"disponivel": False, "tipo": d.tipo, "erro": str(e)[:200]}
        return saida


# ---------------------------------------------------------------------- servidor HTTP de um trabalhador
class ServidorHTTP:
    def __init__(self, worker, token, host="127.0.0.1", porta=0, hosts_extras=()):
        self.worker, self.token, self.host = worker, token, host
        self._extras = tuple(hosts_extras)
        w, tok, ext = worker, token, self._extras
        srv_ref = self

        class H(http.server.BaseHTTPRequestHandler):
            timeout = 60

            def _json(self, o, codigo=200):
                b = json.dumps(o, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)

            def _ok(self):
                host = self.headers.get("Host", "")
                if host not in srv_ref.hosts_permitidos():
                    self._json({"ok": False, "motivo": "host"}, 421)
                    return False
                if not hmac.compare_digest(self.headers.get("X-Precortex-Token", "").encode(), tok.encode()):
                    self._json({"ok": False, "motivo": "chave"}, 401)
                    return False
                return True

            def do_GET(self):
                if not self._ok():
                    return
                if self.path.split("?")[0] == "/saude":
                    return self._json(w.saude())
                self._json({"ok": False}, 404)

            def do_POST(self):
                if not self._ok():
                    return
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n > C.TAMANHO_MAX + 4096:
                    return self._json({"ok": False, "motivo": "grande demais"}, 413)
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json({"ok": False, "motivo": "json inválido"}, 400)
                p = self.path.split("?")[0]
                if p == "/msg":
                    return self._json(w.processar(d))
                if p == "/cancelar" and isinstance(d, dict) and isinstance(d.get("correlacao"), str):
                    return self._json({"ok": True, "em_andamento": w.cancelar(d["correlacao"])})
                self._json({"ok": False}, 404)

            def log_message(self, *a):
                pass

        self._srv = http.server.ThreadingHTTPServer((host, porta), H)
        self._srv.daemon_threads = True
        self.porta = self._srv.server_address[1]
        self._thread = None

    def hosts_permitidos(self):
        return {f"127.0.0.1:{self.porta}", f"localhost:{self.porta}", f"{self.host}:{self.porta}", *self._extras}

    @property
    def url(self):
        return f"http://127.0.0.1:{self.porta}"

    def iniciar(self):
        self._thread = threading.Thread(target=self._srv.serve_forever, name=f"pc-http-{self.worker.nome}", daemon=True)
        self._thread.start()
        return self

    def parar(self):
        """Fecha o servidor DESTE objeto (usado por quem o criou: testes e o lançador da demonstração)."""
        self._srv.shutdown()
        self._srv.server_close()
        self.worker.encerrar_pool()
