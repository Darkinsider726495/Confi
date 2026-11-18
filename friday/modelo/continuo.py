"""BPE CONTÍNUO: o tokenizador da FRIDAY fica aprendendo sem parar com o texto novo (conversas, estudos, livros novos em modelos_ia/corpus/).

A cada rodada: junta o texto que mudou desde a última vez → soma as palavras → cria até BPE_CRESCER tokens novos (padrão 64) com os pares que
apareceram pelo menos 3 vezes → salva. Os tokens antigos NUNCA mudam de número; se já existe modelo treinado, o embedding dele ganha as linhas
novas (o que ele sabia continua igual; os tokens novos ele aprende no próximo treino).
Roda sozinho no treino diário (treinador.py) ou em laço: `python scripts/bpe_continuo.py`.
"""
import json, os, time
from .tokenizador import BPETokenizer
from .treino import PASTA, RAIZ

ESTADO = PASTA / "bpe_continuo.json"
PASTAS = ("Conversas", "Memorias", "Topicos", "Lembrancas", "Estudos", "Estudos/Detalhes", "Eu")


def _ler_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"desde": 0.0, "rodadas": 0, "novos": []}


def texto_novo(desde):
    """O texto que mudou depois de `desde` (só o que é seu ou público; nunca Privado/)."""
    partes = []
    try:
        import memoria as M
        if M.ativo():
            for pasta in PASTAS:
                d = M.base() / pasta
                for f in d.glob("*.md") if d.is_dir() else []:
                    if f.stat().st_mtime > desde:
                        nota = M._ler_nota(f)
                        if nota and not nota.get("privado"):
                            partes.append(nota["corpo"])
    except Exception:
        pass
    corpus = RAIZ / "modelos_ia" / "corpus"
    for f in corpus.glob("*.txt") if corpus.is_dir() else []:
        if f.stat().st_mtime > desde:
            partes.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(partes)


def rodada(crescer=None, relatorio=None, agora=None):
    """Uma rodada de aprendizado contínuo. Devolve {'novos': [...], 'vocab': n, 'texto': caracteres}."""
    agora = time.time() if agora is None else agora
    crescer = int(os.getenv("BPE_CRESCER", "64")) if crescer is None else crescer
    est = _ler_estado()
    txt = texto_novo(est.get("desde", 0.0))
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = PASTA / "tokenizador.json"
    if arq.exists():
        tok = BPETokenizer.carregar(arq)
        novos = tok.atualizar(txt, crescer=crescer, relatorio=relatorio) if txt else []
    else:
        if len(txt) < 2000:
            return {"novos": [], "vocab": 256, "texto": len(txt), "motivo": "pouco texto ainda"}
        tok = BPETokenizer(256 + crescer).train(txt)
        novos = [tok.vocab[i].decode("utf-8", errors="replace") for i in range(256, len(tok))]
    tok.salvar(arq)
    if novos and (PASTA / "modelo.npz").exists():
        from .gpt import GPT
        m = GPT.carregar(PASTA / "modelo.npz")
        if m.expandir_vocab(len(tok)):
            m.salvar(PASTA / "modelo.npz", {k: v for k, v in getattr(m, "meta", {}).items() if k != "cfg"})
    est.update(desde=agora, rodadas=est.get("rodadas", 0) + 1, vocab=len(tok), ultima=agora)
    est["novos"] = (est.get("novos", []) + novos)[-200:]
    ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    return {"novos": novos, "vocab": len(tok), "texto": len(txt)}


def laco(intervalo=600, relatorio=print, dormir=time.sleep, vezes=None):
    """Laço contínuo: uma rodada a cada `intervalo` segundos (padrão 10 min). `vezes` só para testes."""
    n = 0
    while vezes is None or n < vezes:
        r = rodada(relatorio=lambda i, t, c: relatorio(f"  token novo #{i}: {t!r} (apareceu {c}x)"))
        relatorio(f"rodada {n + 1}: {len(r['novos'])} token(s) novo(s), vocabulário {r['vocab']}, {r['texto']:,} caracteres novos lidos")
        n += 1
        if vezes is None or n < vezes:
            dormir(intervalo)
