"""Privacidade da trilha de auditoria: guardar o FATO, não o conteúdo.

Duas camadas (só biblioteca padrão; o corretor importa este arquivo, então ele não pode importar nada da FRIDAY):
  1. Minimização — resumir_args(): argumentos de texto viram «‹texto: N caracteres›»; só ficam em claro os identificadores que a própria
     ferramenta declara (relé, alias de contato), depois da redação, e links ficam só com o servidor. O resultado nunca vai: só um código e o tamanho.
  2. Redação — redigir(): rede de segurança para QUALQUER texto que algum módulo grave. Mascara cartão, CPF/CNPJ, telefone, e-mail, chaves e tokens
     conhecidos, «senha é …» e links (reduzidos ao servidor). Não é à prova de tudo — um endereço escrito por extenso passa —, por isso a regra
     principal é a primeira: não gravar o conteúdo.
"""
import json
import re
from urllib.parse import urlsplit

OCULTO = "‹oculto›"
_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
_SEGREDO_COM_ROTULO = re.compile(
    r"(\b(?:senha|password|passwd|pwd|pin|cvv|token|chave|secret|segredo|api[_ -]?key|c[oó]digo de acesso)\b)([^\n]{0,25}?)(:|=|\b(?:é|eh)\b|\bsão\b|\bsao\b|\bis\b)\s*\S+", re.I)
_SENHA_NUMERICA = re.compile(r"(\b(?:senha|password|passwd|pwd|pin|cvv)\b)\s*\d{4,}", re.I)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.I)
_TOKENS = [re.compile(p) for p in (
    r"\bsk-[A-Za-z0-9_-]{16,}", r"\bgh[pousr]_[A-Za-z0-9]{20,}", r"\bxox[baprs]-[A-Za-z0-9-]{10,}", r"\bAKIA[0-9A-Z]{12,}",
    r"\beyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+){0,2}",
    r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{32,}\b")]            # sequência longa com letras e números
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TEL_INTERNACIONAL = re.compile(r"(?<![\w+])\+\d[\d\s().-]{7,}\d")
_TEL_BR = re.compile(r"(?<!\d)(?:55[\s-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\d)")
_CNPJ = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d)")                  # só o formato com pontuação; 14 dígitos soltos caem em _CARTAO
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_CARTAO = re.compile(r"(?<!\d)\d(?:[ .-]?\d){12,18}(?!\d)")


def so_servidor(url):
    """«https://u:p@Exemplo.org:8443/a/b?c=d#e» -> «https://exemplo.org:8443/…». O caminho e a consulta podem ter nomes, chaves e ids."""
    try:
        u = urlsplit(str(url).strip())
        host = (u.hostname or "").lower()
        porta = f":{u.port}" if u.port else ""
    except ValueError:
        return "‹link›"
    if u.scheme.lower() not in ("http", "https") or not host:
        return "‹link›"
    resto = "/…" if (u.path not in ("", "/") or u.query or u.fragment) else ""
    return f"{u.scheme.lower()}://{host}{porta}{resto}"


def redigir(texto, limite=300):
    """Mascara dados pessoais e segredos e corta no limite. Idempotente: redigir(redigir(x)) == redigir(x)."""
    t = str(texto)
    t = _URL.sub(lambda m: so_servidor(m.group(0)), t)
    t = _SEGREDO_COM_ROTULO.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)} {OCULTO}", t)
    t = _SENHA_NUMERICA.sub(lambda m: f"{m.group(1)} {OCULTO}", t)
    t = _BEARER.sub(f"Bearer {OCULTO}", t)
    for p in _TOKENS:
        t = p.sub("‹token›", t)
    t = _EMAIL.sub("‹email›", t)
    t = _TEL_INTERNACIONAL.sub("‹telefone›", t)
    t = _TEL_BR.sub("‹telefone›", t)
    t = _CNPJ.sub("‹cnpj›", t)
    t = _CPF.sub("‹cpf›", t)
    t = _CARTAO.sub("‹número›", t)
    return t if len(t) <= limite else t[:limite].rstrip() + "…"


def resumir_args(args, claros=()):
    """JSON dos argumentos SEM o conteúdo: números e verdadeiro/falso ficam; texto vira só o tamanho, salvo os nomes em `claros`
    (identificadores curtos que a ferramenta declara, como o relé ou o alias do contato) e os links, que ficam só com o servidor."""
    saida = {}
    for k, v in (args or {}).items():
        if isinstance(v, (bool, int, float)):
            saida[k] = v
        elif isinstance(v, str):
            if k == "url":
                saida[k] = so_servidor(v)
            elif k in claros and len(v) <= 40:
                saida[k] = redigir(v, 40)
            else:
                saida[k] = f"‹texto: {len(v)} caracteres›"
        else:
            saida[k] = f"‹{type(v).__name__}›"
    return json.dumps(saida, ensure_ascii=False)
