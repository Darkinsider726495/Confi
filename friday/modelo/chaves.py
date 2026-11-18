"""Chaves da API PRÓPRIA da FRIDAY: uma por aparelho/uso, com nome. No disco fica só o HASH (sha256) — a chave aparece uma vez, na criação.
Revogar = marcar como revogada (fica no histórico, nada é apagado). Arquivo: friday/.modelo_chaves.json (chmod 600, fora do git).

    python scripts/chaves_api.py criar celular
    python scripts/chaves_api.py listar
    python scripts/chaves_api.py revogar celular
"""
import hashlib, hmac, json, os, re, secrets, threading, time

BASE_FRIDAY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = os.path.join(BASE_FRIDAY, ".modelo_chaves.json")
PREFIXO = "fri_"
_trava = threading.Lock()


def _hash(chave):
    return hashlib.sha256(chave.encode()).hexdigest()


def _ler():
    try:
        with open(ARQ, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(d):
    tmp = ARQ + ".tmp"
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARQ)


def criar(nome):
    """Cria uma chave nova e DEVOLVE ela (única vez em que aparece). Nome: letras, números, - e _."""
    nome = str(nome).strip()
    if not re.fullmatch(r"[\w-]{1,40}", nome):
        raise ValueError("nome inválido (use letras, números, - ou _)")
    with _trava:
        d = _ler()
        if nome in d and not d[nome].get("revogada"):
            raise ValueError(f"já existe uma chave ativa chamada «{nome}» (revogue antes)")
        chave = PREFIXO + secrets.token_urlsafe(32)
        d[nome] = {"hash": _hash(chave), "criada": time.time(), "fim": chave[-4:], "revogada": None, "usos": 0}
        _gravar(d)
    return chave


def revogar(nome):
    with _trava:
        d = _ler()
        if nome not in d or d[nome].get("revogada"):
            return False
        d[nome]["revogada"] = time.time()
        _gravar(d)
        return True


def listar():
    return [{"nome": n, "fim": v.get("fim"), "criada": v.get("criada"), "revogada": v.get("revogada"), "usos": v.get("usos", 0)} for n, v in _ler().items()]


def valida(chave):
    """Nome da chave se ela for válida e ativa (e conta o uso), senão None. Comparação em tempo constante."""
    if not isinstance(chave, str) or not chave:
        return None
    h = _hash(chave)
    with _trava:
        d = _ler()
        for nome, v in d.items():
            if not v.get("revogada") and hmac.compare_digest(v.get("hash", ""), h):
                v["usos"] = v.get("usos", 0) + 1
                _gravar(d)
                return nome
    return None
