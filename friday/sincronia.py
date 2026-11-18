"""Sincronia do cofre com o PC, DIRETO pelo Wi-Fi (sem nuvem). Só o dono liga: «liga a sincronização com o PC».

Lado do celular (este módulo): um servidor pequeno, SEPARADO do painel, que só responde
  - quando a sincronia está ligada;
  - para IPs da rede local (192.168.x, 10.x, 172.16–31.x);
  - com a chave de pareamento (32 bytes aleatórios, em friday/.sync_chave, chmod 600; nunca no git nem nos logs).
Ele lista o cofre (caminho, data, hash), entrega e recebe arquivos e ARQUIVA (nunca apaga). Conflito = as duas versões ficam.
Lado do PC: scripts/sincronizar_pc.py (só biblioteca padrão: Windows, Linux, Kali). O texto que vem do PC vira nota do dono.
Privado/ fica de fora (SYNC_PRIVADO=1 inclui).
"""
import hashlib, hmac, http.server, ipaddress, json, os, re, secrets, socket, threading, time, urllib.parse
from pathlib import Path, PurePosixPath
import memoria as M

PORTA = int(os.getenv("SYNC_PORTA", "8090") or 8090)
MAX_ARQ = 5 * 1024 * 1024
BASE = os.path.dirname(os.path.abspath(__file__))
ARQ_CHAVE = os.path.join(BASE, ".sync_chave")
ARQ_ESTADO = os.path.join(BASE, ".sync.json")
FORA = (".tmp", ".parcial", ".sync-tmp")
_srv = {"s": None}
_falhas = {"n": 0, "ate": 0.0}
_trava = threading.Lock()
_hash = {}                     # caminho -> (mtime, tamanho, sha)


# ---------------------------------------------------------------- ligado / chave
def ligada():
    try:
        with open(ARQ_ESTADO, encoding="utf-8") as f:
            return bool(json.load(f).get("ligada"))
    except (OSError, ValueError):
        return False


def _gravar_estado(v):
    tmp = ARQ_ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ligada": bool(v), "t": time.time()}, f)
    os.replace(tmp, ARQ_ESTADO)


def chave():
    """Chave de pareamento (criada uma vez). Só o dono a vê, pelo Termux (scripts/parear_pc.py)."""
    try:
        with open(ARQ_CHAVE, encoding="utf-8") as f:
            c = f.read().strip()
        if len(c) >= 32:
            return c
    except OSError:
        pass
    c = secrets.token_urlsafe(32)
    with os.fdopen(os.open(ARQ_CHAVE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(c)
    return c


def ip_local():
    """IP do celular no Wi-Fi (não envia nada: só pergunta ao sistema qual interface sairia)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def rede_local(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback


# ---------------------------------------------------------------- o cofre
def _raiz():
    r = M.raiz()
    return Path(r) if r else None


def _incluir(rel):
    p = PurePosixPath(rel)
    if not p.parts or any(x.startswith(".sync") for x in p.parts) or rel.endswith(FORA):
        return False
    if p.parts[0] == "Privado" or (len(p.parts) > 1 and p.parts[0] == M.PASTA and p.parts[1] == "Privado"):
        return os.getenv("SYNC_PRIVADO", "0") == "1"
    if p.parts[0] == ".obsidian" and p.name.startswith("workspace"):
        return False                                     # layout das janelas: muda a cada toque, não é memória
    return True


def caminho_seguro(rel):
    """Caminho dentro do cofre, ou None. Sem «..», sem caminho absoluto, sem barra invertida, sem controle, sem link simbólico."""
    r = _raiz()
    if r is None or not isinstance(rel, str) or not rel or len(rel) > 300 or "\\" in rel or re.search(r"[\x00-\x1f]", rel):
        return None
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or not _incluir(rel):
        return None
    alvo = r.joinpath(*p.parts)
    atual = r
    for parte in p.parts:
        atual = atual / parte
        if atual.is_symlink():
            return None
    try:
        alvo.resolve().relative_to(r.resolve())
    except (ValueError, OSError):
        return None
    return alvo


def _sha(f):
    st = f.stat()
    k = str(f)
    c = _hash.get(k)
    if c and c[0] == st.st_mtime and c[1] == st.st_size:
        return c[2]
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    _hash[k] = (st.st_mtime, st.st_size, h)
    return h


def lista():
    """{rel: [mtime, tamanho, sha256]} de tudo que sincroniza."""
    r = _raiz()
    out = {}
    if r is None or not r.is_dir():
        return out
    for f in r.rglob("*"):
        if not f.is_file() or f.is_symlink():
            continue
        rel = f.relative_to(r).as_posix()
        if _incluir(rel):
            try:
                out[rel] = [f.stat().st_mtime, f.stat().st_size, _sha(f)]
            except OSError:
                pass
    return out


def receber(rel, dados, base_sha, mtime=None):
    """Grava o arquivo que veio do PC. Se mudou aqui também desde a última vez (base diferente), guarda as DUAS versões."""
    alvo = caminho_seguro(rel)
    if alvo is None:
        raise ValueError("caminho recusado")
    if len(dados) > MAX_ARQ:
        raise ValueError("arquivo grande demais")
    conflito = None
    if alvo.exists() and base_sha and _sha(alvo) != base_sha:
        conflito = alvo.with_name(f"{alvo.stem} (conflito PC {time.strftime('%Y-%m-%d %H%M')}){alvo.suffix}")
        alvo = conflito
    alvo.parent.mkdir(parents=True, exist_ok=True)
    tmp = alvo.with_name(alvo.name + ".sync-tmp")
    tmp.write_bytes(dados)
    os.replace(tmp, alvo)
    if mtime:
        try:
            os.utime(alvo, (float(mtime), float(mtime)))
        except (OSError, ValueError):
            pass
    M._cache.clear()
    return {"ok": True, "conflito": alvo.relative_to(_raiz()).as_posix() if conflito else None}


def arquivar(rel):
    """O dono tirou a nota do PC: aqui ela vai para Arquivo/sincronia/ (nada é apagado)."""
    alvo = caminho_seguro(rel)
    if alvo is None or not alvo.exists():
        return {"ok": False}
    destino = _raiz() / M.PASTA / "Arquivo" / "sincronia" / PurePosixPath(rel).as_posix().replace("/", " - ")
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino = destino.with_name(f"{destino.stem} ({int(time.time())}){destino.suffix}")
    os.replace(alvo, destino)                            # mover (nunca apagar)
    M._cache.clear()
    return {"ok": True}


# ---------------------------------------------------------------- consulta para o MCP do PC (só leitura)
def api_estado():
    """Números e estado, sem conteúdo pessoal nem chave."""
    out = {"ok": True}
    try:
        import neuronios as N
        out["memoria"] = N.resumo()
    except Exception:
        pass
    try:
        import mente as MENTE
        m = MENTE.resumo()
        out.update(significado=m["significado"], rotina=m["rotina"], llm=m["llm"])
    except Exception:
        pass
    try:
        import vida as V
        v = V.painel()
        out["vida"] = {k: v.get(k) for k in ("humor", "energia") if isinstance(v, dict)}
    except Exception:
        pass
    return out


def api_buscar(consulta):
    """Busca por palavra (+ por significado). O que veio da internet ou da câmera vem marcado como «externo»."""
    if not isinstance(consulta, str) or not consulta.strip() or len(consulta) > 300:
        return {"ok": False, "msg": "consulta inválida"}
    achados = [{k: x[k] for k in ("titulo", "origem", "trecho", "externo")} for x in M.buscar(consulta, limite=8, estudos=True)]
    try:
        import significado as SIG
        ja = {a["titulo"] for a in achados}
        for o, t, sc, tr in SIG.buscar_por_significado(consulta, n=3):
            if t not in ja:
                achados.append({"titulo": t, "origem": o, "trecho": tr, "externo": False, "por_significado": sc})
    except Exception:
        pass
    return {"ok": True, "resultados": achados}


def api_nota(titulo):
    """O texto de uma nota pelo título (nunca Privado/ nem nota marcada privada)."""
    b = M.base()
    if b is None or not isinstance(titulo, str) or not titulo.strip() or len(titulo) > 120 or re.search(r"[/\\\x00-\x1f]", titulo):
        return {"ok": False, "msg": "título inválido"}
    for f in sorted(b.rglob("*.md")):
        rel = f.relative_to(b)
        if f.stem != titulo or rel.parts[0] == "Privado" or f.is_symlink():
            continue
        nota = M._ler_nota(f)
        if not nota or nota["privado"]:
            continue
        return {"ok": True, "titulo": f.stem, "pasta": rel.parts[0], "externo": rel.parts[0] in ("Estudos", "Visao"),
                "texto": nota["corpo"][:20000]}
    return {"ok": False, "msg": "nota não encontrada"}


def api_pedidos():
    """Os pedidos de evolução que ela abriu (o que ela gostaria de saber fazer)."""
    b = M.base()
    out = []
    for f in sorted((b / "Pedidos").glob("*.md")) if b and (b / "Pedidos").is_dir() else []:
        nota = M._ler_nota(f)
        if nota and nota["meta"].get("status", "aberto") == "aberto":
            out.append({"titulo": f.stem, "texto": " ".join(nota["corpo"].split())[:600]})
    return {"ok": True, "pedidos": out}


# ---------------------------------------------------------------- servidor (só na rede local, só com a chave)
class _H(http.server.BaseHTTPRequestHandler):
    timeout = 30

    def log_message(self, *a):
        pass

    def _resp(self, code, corpo, tipo="application/json"):
        b = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(code)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _ok(self):
        if not ligada() or not rede_local(self.client_address[0]):
            self._resp(403, {"ok": False})
            return False
        if time.time() < _falhas["ate"]:
            self._resp(429, {"ok": False, "msg": "muitas tentativas"})
            return False
        if not hmac.compare_digest(self.headers.get("X-Sync-Chave", "").encode(), chave().encode()):
            _falhas["n"] += 1
            try:
                import vigia as VIG
                VIG.tentativa_errada("sync")
            except Exception:
                pass
            if _falhas["n"] >= 5:
                _falhas.update(n=0, ate=time.time() + 60)
            self._resp(401, {"ok": False})
            return False
        _falhas["n"] = 0
        return True

    def _q(self):
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

    def do_GET(self):
        if not self._ok():
            return
        p = self.path.split("?")[0]
        if p == "/sync/lista":
            return self._resp(200, {"ok": True, "arquivos": lista()})
        if p == "/sync/arquivo":
            alvo = caminho_seguro(self._q().get("rel", [""])[0])
            if alvo is None or not alvo.is_file():
                return self._resp(404, {"ok": False})
            return self._resp(200, alvo.read_bytes(), "application/octet-stream")
        q = self._q()
        if p == "/api/estado":
            return self._resp(200, api_estado())
        if p == "/api/buscar":
            return self._resp(200, api_buscar(q.get("q", [""])[0]))
        if p == "/api/nota":
            return self._resp(200, api_nota(q.get("titulo", [""])[0]))
        if p == "/api/pedidos":
            return self._resp(200, api_pedidos())
        self._resp(404, {"ok": False})

    def do_POST(self):
        if not self._ok():
            return
        p, q = self.path.split("?")[0], self._q()
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n > MAX_ARQ:
            return self._resp(413, {"ok": False})
        dados = self.rfile.read(n) if n else b""
        try:
            if p == "/sync/arquivo":
                return self._resp(200, receber(q.get("rel", [""])[0], dados, q.get("base", [""])[0], q.get("mtime", [None])[0]))
            if p == "/sync/arquivar":
                return self._resp(200, arquivar(q.get("rel", [""])[0]))
        except ValueError as e:
            return self._resp(400, {"ok": False, "msg": str(e)})
        self._resp(404, {"ok": False})


def iniciar():
    """Sobe o servidor (uma vez). Ele recusa tudo enquanto a sincronia estiver desligada."""
    with _trava:
        if _srv["s"] is not None:
            return True
        try:
            s = http.server.ThreadingHTTPServer(("0.0.0.0", PORTA), _H)
        except OSError:
            return False
        _srv["s"] = s
        threading.Thread(target=s.serve_forever, daemon=True).start()
        return True


# ---------------------------------------------------------------- voz (só o dono)
_P = r"^(?:(?:friday|jarvis|fraide)[ ,]+)?"
_LIGA = re.compile(_P + r"(?:liga|ligue|ative|ativa) a sincroniza(?:cao|r)(?: do cofre)?(?: com o (?:pc|computador))?[ .!]*$")
_DESLIGA = re.compile(_P + r"(?:desliga|desligue|desative|desativa) a sincroniza(?:cao|r)(?: do cofre)?(?: com o (?:pc|computador))?[ .!]*$")
_STATUS = re.compile(_P + r"(?:como esta a sincronizacao|a sincronizacao esta ligada)[ ?!.]*$")


def tratar(texto):
    f = M._fold(" ".join(str(texto).split())).strip()
    if _LIGA.match(f):
        if not M.ativo():
            return "A memória está desligada: não há cofre para sincronizar."
        chave()
        _gravar_estado(True)
        if not iniciar():
            return f"Não consegui abrir a porta {PORTA} no celular. Outra coisa está usando?"
        return ("Sincronização ligada, só na sua rede Wi-Fi e só com a chave de pareamento. No Termux, rode "
                "«python scripts/parear_pc.py»: ele mostra o comando para colar no seu PC.")
    if _DESLIGA.match(f):
        _gravar_estado(False)
        return "Sincronização desligada. Ninguém mais lê nem grava o cofre pela rede."
    if _STATUS.match(f):
        return (f"Ligada, em {ip_local()}:{PORTA}, só na rede local." if ligada() else "Desligada. Diga «liga a sincronização com o PC».")
    return None
