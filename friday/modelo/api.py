"""A API PRÓPRIA do modelo da FRIDAY (no formato de chat que todo mundo usa: POST /v1/chat/completions), sem nenhum serviço de terceiros.

    python scripts/api_modelo.py                    sobe a API só no próprio aparelho (127.0.0.1:8100)
    python scripts/api_modelo.py --rede             na rede local também (ex.: treina e roda no PC, o celular usa pelo Wi-Fi)

Chave: friday/.modelo_token (criada sozinha, chmod 600) — mande no cabeçalho «Authorization: Bearer <chave>». Sem chave = 401.
A FRIDAY usa este modelo com IA_PROVEDOR=propria no .env (dentro do próprio processo; ou PROPRIA_URL=http://IP:8100 para usar o do PC).
"""
import hmac, http.server, ipaddress, json, os, secrets, threading, time
from .tokenizador import BPETokenizer
from .gpt import GPT
from .treino import PASTA

BASE_FRIDAY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ_TOKEN = os.path.join(BASE_FRIDAY, ".modelo_token")
_m = {"modelo": None, "tok": None, "mtime": 0.0}
_trava = threading.Lock()


def disponivel():
    return (PASTA / "modelo.npz").exists() and (PASTA / "tokenizador.json").exists()


def carregar():
    """(modelo, tokenizador), recarregando se o arquivo mudou (treinou de novo)."""
    with _trava:
        mt = (PASTA / "modelo.npz").stat().st_mtime
        if _m["modelo"] is None or mt != _m["mtime"]:
            _m.update(modelo=GPT.carregar(PASTA / "modelo.npz"), tok=BPETokenizer.carregar(PASTA / "tokenizador.json"), mtime=mt)
        return _m["modelo"], _m["tok"]


def prompt_de(mensagens):
    """Mensagens no formato de chat → o formato com que ela foi treinada (Dono: … / FRIDAY: …). Só as últimas trocas cabem no contexto."""
    linhas = []
    for msg in mensagens[-8:]:
        conteudo = msg.get("content")
        if isinstance(conteudo, list):
            conteudo = " ".join(b.get("text", "") for b in conteudo if isinstance(b, dict))
        conteudo = " ".join(str(conteudo or "").split())[:600]
        if msg.get("role") == "user":
            linhas.append(f"Dono: {conteudo}")
        elif msg.get("role") == "assistant":
            linhas.append(f"FRIDAY: {conteudo}")
    return "\n".join(linhas) + "\nFRIDAY:"


def responder(mensagens, max_tokens=120, temperatura=0.7):
    modelo, tok = carregar()
    ids = tok.encode(prompt_de(mensagens))[-(modelo.cfg["ctx"] - 8):]

    def parar(novos):
        fim = tok.decode(novos[-12:])
        return "\nDono:" in fim or "\n\n" in fim

    texto = tok.decode(modelo.gerar(ids, n=max_tokens, temperatura=temperatura, top_k=40, parar=parar))
    return texto.split("\nDono:")[0].split("\n\n")[0].strip()


def token():
    try:
        with open(ARQ_TOKEN, encoding="utf-8") as f:
            t = f.read().strip()
        if len(t) >= 32:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(32)
    with os.fdopen(os.open(ARQ_TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(t)
    return t


class _H(http.server.BaseHTTPRequestHandler):
    timeout = 120

    def log_message(self, *a):
        pass

    def _resp(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _ok(self):
        try:
            if not ipaddress.ip_address(self.client_address[0]).is_private and not ipaddress.ip_address(self.client_address[0]).is_loopback:
                self._resp(403, {"error": "só rede local"})
                return False
        except ValueError:
            return False
        dada = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(dada.encode(), token().encode()):
            self._resp(401, {"error": "chave inválida"})
            return False
        return True

    def do_GET(self):
        if self.path == "/saude":
            return self._resp(200, {"ok": True, "modelo": disponivel()})
        self._resp(404, {"error": "não encontrado"})

    def do_POST(self):
        if not self._ok():
            return
        if self.path.split("?")[0] != "/v1/chat/completions":
            return self._resp(404, {"error": "não encontrado"})
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n > 200_000:
                return self._resp(413, {"error": "pedido grande demais"})
            d = json.loads(self.rfile.read(n) or b"{}")
            msgs = d.get("messages") or []
            assert isinstance(msgs, list) and msgs
        except (ValueError, AssertionError):
            return self._resp(400, {"error": "pedido inválido"})
        if not disponivel():
            return self._resp(503, {"error": "modelo ainda não treinado (python scripts/treinar_modelo.py)"})
        mx = max(1, min(int(d.get("max_tokens") or 120), 400))
        texto = responder(msgs, max_tokens=mx, temperatura=float(d.get("temperature", 0.7)))
        self._resp(200, {"id": f"friday-{int(time.time() * 1000)}", "object": "chat.completion", "model": "friday-gpt",
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": texto}, "finish_reason": "stop"}]})


def servir(host="127.0.0.1", porta=8100):
    s = http.server.ThreadingHTTPServer((host, porta), _H)
    token()
    return s
