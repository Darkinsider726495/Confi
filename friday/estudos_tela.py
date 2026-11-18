"""Dados da tela /estudos: o que ela aprendeu na internet (resumo + fontes + detalhes). Só leitura; tudo é conteúdo de terceiros, rotulado."""
import re
import memoria as M


def lista():
    """[{titulo, data, fontes, frase, detalhes}] dos estudos, do mais recente ao mais antigo."""
    if not M.ativo():
        return []
    d = M.base() / "Estudos"
    det = d / "Detalhes"
    out = []
    for f in sorted(d.glob("*.md"), key=lambda x: -x.stat().st_mtime) if d.is_dir() else []:
        nota = M._ler_nota(f)
        if not nota or nota["meta"].get("origem") != "web":
            continue
        corpo = re.sub(r"^#.*$|^_.*_$", "", nota["corpo"], flags=re.M).strip()
        n_det = len(list(det.glob(f"{f.stem} — *.md"))) if det.is_dir() else 0
        out.append({"titulo": f.stem, "data": str(nota["meta"].get("atualizado") or nota["meta"].get("criado") or "")[:10],
                    "fontes": [h for h in str(nota["meta"].get("fonte", "")).split(", ") if h], "frase": " ".join(corpo.split())[:220], "detalhes": n_det})
    return out


def abrir(titulo):
    """{titulo, resumo, detalhes:[{fonte, texto}]} de um estudo, ou None."""
    if not M.ativo() or not isinstance(titulo, str) or not titulo.strip() or len(titulo) > 120 or re.search(r"[/\\\x00-\x1f]", titulo):
        return None
    f = M.base() / "Estudos" / (titulo + ".md")
    nota = M._ler_nota(f) if f.is_file() else None
    if not nota or nota["meta"].get("origem") != "web":
        return None
    dets = []
    d = M.base() / "Estudos" / "Detalhes"
    for g in sorted(d.glob(f"{titulo} — *.md")) if d.is_dir() else []:
        n = M._ler_nota(g)
        if n:
            dets.append({"fonte": n["meta"].get("fonte", g.stem.split(" — ")[-1]), "texto": re.sub(r"^#.*$|^_.*_$", "", n["corpo"], flags=re.M).strip()[:60000]})
    return {"titulo": titulo, "resumo": re.sub(r"^#.*$|^_.*_$", "", nota["corpo"], flags=re.M).strip(), "detalhes": dets}
