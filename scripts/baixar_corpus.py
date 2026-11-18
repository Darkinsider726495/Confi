#!/usr/bin/env python3
"""Baixa livros em PORTUGUÊS de domínio público do Projeto Gutenberg para treinar o modelo próprio (modelos_ia/corpus/).

    python scripts/baixar_corpus.py                 até 50 livros em português (os mais conhecidos primeiro, pelo catálogo)
    python scripts/baixar_corpus.py --livros 200    mais livros (mais texto = modelo melhor)
    python scripts/baixar_corpus.py --listar        só mostra quais baixaria

Usa só o catálogo oficial (pg_catalog.csv) e os arquivos .txt oficiais; tira o cabeçalho e o rodapé de licença do Gutenberg; espera 2 s entre
um livro e outro (educação com o site) e não baixa de novo o que já tem. Nada de IA de terceiros: é só texto público.
Depois:  python scripts/treinar_modelo.py
"""
import argparse, csv, io, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINO = ROOT / "modelos_ia" / "corpus"
CATALOGO = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
LIVRO = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"
UA = {"User-Agent": "friday-corpus/1.0 (download educacional de textos de dominio publico)"}


def baixar(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def livros_em_portugues(csv_texto):
    """[(id, título, autor)] dos livros de texto em português, na ordem do catálogo."""
    out = []
    for linha in csv.DictReader(io.StringIO(csv_texto)):
        if (linha.get("Type") or "").strip() != "Text":
            continue
        idiomas = [x.strip().lower() for x in (linha.get("Language") or "").split(";")]
        if "pt" in idiomas and (linha.get("Text#") or "").strip().isdigit():
            out.append((int(linha["Text#"]), (linha.get("Title") or "").strip().replace("\n", " "), (linha.get("Authors") or "").strip()))
    return out


def limpar(txt):
    """Só o livro: tira o cabeçalho e o rodapé de licença do Gutenberg."""
    ini = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\n", txt, re.I)
    fim = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", txt, re.I)
    corpo = txt[ini.end() if ini else 0: fim.start() if fim else len(txt)]
    return re.sub(r"\r\n?", "\n", corpo).strip()


def nome_arquivo(i, titulo):
    t = re.sub(r"[^\w\- ]", "", titulo, flags=re.U)[:60].strip().replace(" ", "_") or "livro"
    return f"pg{i}_{t}.txt"


def main(argv=None, baixar=baixar, dormir=time.sleep):
    ap = argparse.ArgumentParser()
    ap.add_argument("--livros", type=int, default=50)
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args(argv)
    print("Lendo o catálogo do Projeto Gutenberg…")
    lista = livros_em_portugues(baixar(CATALOGO, timeout=120))
    print(f"{len(lista)} livros em português no catálogo.")
    escolhidos = lista[:max(0, a.livros)]
    if a.listar:
        for i, t, au in escolhidos:
            print(f"  {i:>6}  {t[:60]}  — {au[:40]}")
        return 0
    DESTINO.mkdir(parents=True, exist_ok=True)
    total, feitos = 0, 0
    for n, (i, t, au) in enumerate(escolhidos, 1):
        arq = DESTINO / nome_arquivo(i, t)
        if arq.exists():
            continue
        try:
            corpo = limpar(baixar(LIVRO.format(id=i)))
        except Exception as e:
            print(f"  [{n}/{len(escolhidos)}] {t[:50]}: não consegui ({type(e).__name__})")
            continue
        if len(corpo) < 2000:
            continue
        arq.write_text(corpo, encoding="utf-8")
        total += len(corpo)
        feitos += 1
        print(f"  [{n}/{len(escolhidos)}] {t[:50]} — {len(corpo):,} caracteres")
        dormir(2)
    tem = sum(f.stat().st_size for f in DESTINO.glob("*.txt"))
    print(f"\nBaixei {feitos} livro(s) agora ({total:,} caracteres). Em {DESTINO}: {tem / 1e6:.1f} MB de texto.")
    print("Agora treine:  python scripts/treinar_modelo.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
