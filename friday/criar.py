"""Criar arquivos: só dentro da pasta FRIDAY_DOCS (padrão ~/friday-docs), com nome simples, tipo permitido e tamanho limitado."""
import os, re

EXT = {".md", ".txt", ".csv", ".html", ".json"}
MAX_ARQ, MAX_PASTA = 100_000, 20_000_000


def pasta():
    p = os.environ.get("FRIDAY_DOCS") or os.path.join(os.path.expanduser("~"), "friday-docs")
    os.makedirs(p, exist_ok=True)
    return p


def _tamanho(p):
    return sum(os.path.getsize(os.path.join(p, f)) for f in os.listdir(p) if os.path.isfile(os.path.join(p, f)))


def caminho(nome):
    nome = str(nome).strip()
    if not re.fullmatch(r"[\w\-. ]{1,60}", nome) or nome.startswith(".") or ".." in nome:
        raise ValueError("Nome inválido: use letras, números, espaço, hífen e ponto, sem pastas.")
    if os.path.splitext(nome)[1].lower() not in EXT:
        raise ValueError(f"Tipo não permitido. Use: {', '.join(sorted(EXT))}.")
    return os.path.join(pasta(), nome)


def criar_arquivo(nome, conteudo):
    c = str(conteudo)
    if len(c.encode()) > MAX_ARQ:
        raise ValueError("Conteúdo grande demais (máximo 100 KB).")
    p = caminho(nome)
    if _tamanho(pasta()) + len(c.encode()) > MAX_PASTA:
        raise ValueError("A pasta da FRIDAY está cheia.")
    base, ext = os.path.splitext(p)
    n = 1
    while os.path.lexists(p):  # nunca sobrescreve (nem através de link simbólico)
        n += 1
        p = f"{base}-{n}{ext}"
    with open(p, "x", encoding="utf-8") as f:
        f.write(c)
    return f"Arquivo {os.path.basename(p)} criado."


def listar_arquivos():
    f = sorted(os.listdir(pasta()))
    return ", ".join(f[:30]) or "Nenhum arquivo ainda."
