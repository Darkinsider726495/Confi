"""Acesso HTTP ao pré-córtex: o manipulador (neutro, sem servidor) e um servidor autônomo para a demonstração.

Rotas (todas sob /precortex; a página só confere o host, os dados exigem a chave `X-Friday-Token`, igual ao painel):
  GET  /precortex                       a página (friday/precortex.html)
  GET  /precortex/estado[?id=pcNNNN]    tudo que a tela mostra: neurônios, objetivos, detalhe do selecionado, estado operacional
  GET  /precortex/eventos?desde=N[&id=] eventos novos (fluxo em tempo real, por consulta periódica)
  GET  /precortex/objetivo?id=pcNNNN    o dossiê resumido + as 12 perguntas respondidas
  GET  /precortex/neuronios             a descrição dos nove neurônios
  POST /precortex/objetivo              {texto, so_planejar?, prioridade?}  → registra e inicia
  POST /precortex/controle              {acao: cancelar|limpar|autorizar|negar|aceitar|executar|retomar, id?, versao?, hash?}
NÃO existe rota que pare o FRIDAY, um trabalhador ou o hub. «Interromper a demonstração» = cancelar os objetivos (cooperativo); «limpar» = arquivar o cenário temporário. Nada apaga.
"""
import hmac
import http.server
import json
import os
import re
import threading
import urllib.parse

from . import catalogo_neuronios as K
from . import contrato as C

_ID = re.compile(r"pc\d{4,6}")
ACOES = ("cancelar", "limpar", "autorizar", "negar", "aceitar", "executar", "retomar")
PAGINA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "precortex.html")


class Api:
    """Recebe método, caminho e corpo já lidos; devolve (código, tipo, bytes). A autenticação é de quem chama (main.py ou o servidor autônomo)."""

    def __init__(self, obter_hub):
        self._hub = obter_hub

    @staticmethod
    def _json(o, codigo=200):
        return codigo, "application/json; charset=utf-8", json.dumps(o, ensure_ascii=False).encode("utf-8")

    def pagina(self):
        try:
            with open(PAGINA, "rb") as f:
                return 200, "text/html; charset=utf-8", f.read()
        except OSError:
            return self._json({"ok": False, "msg": "página não encontrada"}, 404)

    def get(self, caminho, query):
        h = self._hub()
        q = {k: v[0] for k, v in query.items()} if isinstance(query, dict) else {}
        if caminho == "/precortex/estado":
            sel = q.get("id") if _ID.fullmatch(q.get("id", "")) else None
            return self._json({"ok": True, **h.estado(sel)})
        if caminho == "/precortex/eventos":
            try:
                desde = max(0, int(q.get("desde", "0")))
            except ValueError:
                desde = 0
            oid = q.get("id") if _ID.fullmatch(q.get("id", "")) else None
            return self._json({"ok": True, "eventos": h.eventos(desde, oid, 400), "seq": h.arm.seq})
        if caminho == "/precortex/objetivo":
            d = h.detalhe(q.get("id", "")) if _ID.fullmatch(q.get("id", "")) else None
            return self._json({"ok": True, **d}) if d else self._json({"ok": False, "msg": "objetivo não encontrado"}, 404)
        if caminho == "/precortex/neuronios":
            return self._json({"ok": True, "contrato": C.VERSAO, "neuronios": K.descricoes()})
        return self._json({"ok": False}, 404)

    def post(self, caminho, d):
        h = self._hub()
        if not isinstance(d, dict):
            return self._json({"ok": False, "msg": "corpo inválido"}, 400)
        if caminho == "/precortex/objetivo":
            r = h.submeter(d.get("texto"), so_planejar=bool(d.get("so_planejar")), prioridade=d.get("prioridade") if d.get("prioridade") in ("baixa", "normal", "alta") else "normal")
            return self._json(r, 200 if r.get("ok") else 400)
        if caminho == "/precortex/controle":
            acao, oid = d.get("acao"), d.get("id")
            if acao not in ACOES:
                return self._json({"ok": False, "msg": "ação desconhecida"}, 400)
            if acao == "limpar":
                return self._json(h.limpar_cenario())
            if not (isinstance(oid, str) and _ID.fullmatch(oid)):
                return self._json({"ok": False, "msg": "falta o id do objetivo"}, 400)
            if acao == "autorizar":
                r = h.autorizar(oid, d.get("versao"), d.get("hash"), via="painel")
            elif acao == "negar":
                r = h.negar(oid, "negado pelo dono no painel")
            else:
                r = getattr(h, {"cancelar": "cancelar", "aceitar": "aceitar", "executar": "executar", "retomar": "retomar"}[acao])(oid)
            return self._json(r, 200 if r.get("ok") else 409)
        return self._json({"ok": False}, 404)


class ServidorApi:
    """Servidor HTTP autônomo (a demonstração e quem quiser usar a tela sem o painel inteiro). Mesma regra do painel: host conferido e chave em cabeçalho."""

    def __init__(self, hub, token, host="127.0.0.1", porta=0, hosts_extras=()):
        self.hub, self.token, self.host = hub, token, host
        self.api = Api(lambda: hub)
        self._extras = tuple(hosts_extras)
        srv_ref = self

        class H(http.server.BaseHTTPRequestHandler):
            timeout = 30

            def _enviar(self, codigo, tipo, b, pagina=False):
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(b)

            def _host_ok(self):
                return self.headers.get("Host", "") in srv_ref.hosts_permitidos()

            def _auth(self):
                return hmac.compare_digest(self.headers.get("X-Friday-Token", "").encode(), srv_ref.token.encode())

            def do_GET(self):
                if not self._host_ok():
                    return self._enviar(*srv_ref.api._json({"ok": False}, 421))
                u = urllib.parse.urlsplit(self.path)
                if u.path in ("/", "/precortex"):
                    return self._enviar(*srv_ref.api.pagina())
                if u.path == "/saude":
                    return self._enviar(*srv_ref.api._json({"ok": True}))
                if not u.path.startswith("/precortex/"):
                    return self._enviar(*srv_ref.api._json({"ok": False}, 404))
                if not self._auth():
                    return self._enviar(*srv_ref.api._json({"ok": False, "msg": "sem chave"}, 401))
                return self._enviar(*srv_ref.api.get(u.path, urllib.parse.parse_qs(u.query)))

            def do_POST(self):
                if not self._host_ok():
                    return self._enviar(*srv_ref.api._json({"ok": False}, 421))
                if not self._auth():
                    return self._enviar(*srv_ref.api._json({"ok": False, "msg": "sem chave"}, 401))
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n > 8192:
                    return self._enviar(*srv_ref.api._json({"ok": False, "msg": "grande demais"}, 413))
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._enviar(*srv_ref.api._json({"ok": False, "msg": "json inválido"}, 400))
                return self._enviar(*srv_ref.api.post(self.path.split("?")[0], d))

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
        return f"http://127.0.0.1:{self.porta}/precortex"

    def iniciar(self):
        self._thread = threading.Thread(target=self._srv.serve_forever, name="pc-api", daemon=True)
        self._thread.start()
        return self

    def parar(self):
        """Fecha o servidor DESTE objeto (testes e lançador da demonstração). Nenhuma rota chega aqui."""
        self._srv.shutdown()
        self._srv.server_close()
