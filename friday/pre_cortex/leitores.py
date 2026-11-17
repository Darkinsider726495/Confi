"""Leitores SOMENTE-LEITURA do estado real (banco de notas, pasta de arquivos, cofre de memória).

Servem à verificação independente: olham o mundo depois da execução, sem passar pelo corretor, pelas tarefas nem pela resposta da ferramenta. Este módulo não escreve em nada,
não importa o corretor e usa só biblioteca padrão e `memoria` (que também só usa a biblioteca padrão). As «marcas» tiradas ANTES da execução dizem o que já existia, para
só aceitar o que apareceu depois.
"""
import os
import sqlite3
import time
from contextlib import closing

FOLGA_MTIME = 0.25
_AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def caminho_db():
    return os.environ.get("FRIDAY_DB") or os.path.join(_AQUI, "friday.db")


def pasta_docs():
    return os.environ.get("FRIDAY_DOCS") or os.path.join(os.path.expanduser("~"), "friday-docs")


def _db():
    if not os.path.exists(caminho_db()):
        return None
    return sqlite3.connect(f"file:{caminho_db()}?mode=ro", uri=True)


def marca_notas():
    c = _db()
    if c is None:
        return 0
    with closing(c):
        try:
            return int(c.execute("select coalesce(max(id),0) from notas").fetchone()[0])
        except sqlite3.Error:
            return 0


def notas_depois(marca):
    c = _db()
    if c is None:
        return []
    with closing(c):
        try:
            return [r[0] for r in c.execute("select texto from notas where id>? order by id", (int(marca),)).fetchall()]
        except sqlite3.Error:
            return []


def arquivos(pasta=None):
    p = pasta or pasta_docs()
    try:
        return sorted(n for n in os.listdir(p) if os.path.isfile(os.path.join(p, n)))
    except OSError:
        return []


def ler_arquivo(nome, limite=200_000):
    with open(os.path.join(pasta_docs(), nome), encoding="utf-8") as f:
        return f.read(limite)


def memorias_alteradas_desde(t0):
    """Corpos das notas da pasta Memorias do cofre alteradas depois de `t0` (só leitura; nota privada é ignorada)."""
    import memoria as M
    if not M.ativo():
        raise RuntimeError("memória desligada: não há onde conferir")
    pasta = M.base() / "Memorias"
    saida = []
    try:
        nomes = [n for n in os.listdir(pasta) if n.endswith(".md")]
    except OSError:
        return saida
    for n in nomes:
        p = pasta / n
        try:
            if p.stat().st_mtime < t0 - FOLGA_MTIME:
                continue
        except OSError:
            continue
        nota = M._ler_nota(p)
        if nota and not nota["privado"]:
            saida.append(nota["corpo"])
    return saida


def marcar(ferramenta, args=None):
    """Tira, ANTES da execução, a marca de que cada leitor precisa. Serializável (vai numa mensagem)."""
    if ferramenta == "anotar":
        return {"tipo": "nota", "marca": marca_notas()}
    if ferramenta == "criar_arquivo":
        return {"tipo": "arquivo", "existentes": arquivos(), "nome": str((args or {}).get("nome", ""))}
    if ferramenta == "guardar_memoria":
        return {"tipo": "memoria", "t0": time.time()}
    return {"tipo": "nenhuma"}


def ler_depois(ferramenta, marca):
    """Lista de textos que apareceram depois da marca, ou levanta se o leitor não consegue olhar. `[]` = olhei e não havia nada."""
    t = (marca or {}).get("tipo")
    if ferramenta == "anotar" and t == "nota":
        return notas_depois(marca["marca"])
    if ferramenta == "criar_arquivo" and t == "arquivo":
        novos = [n for n in arquivos() if n not in set(marca.get("existentes") or [])]
        return [ler_arquivo(n) for n in novos]
    if ferramenta == "guardar_memoria" and t == "memoria":
        return memorias_alteradas_desde(marca["t0"])
    raise LookupError(f"não há leitor independente para «{ferramenta}»")
