"""Treino do modelo próprio: monta o texto de treino, treina o tokenizador BPE e o GPT em NumPy, e salva tudo em modelos_ia/friday-gpt/.

Texto de treino (só o que é seu ou público, nada de serviço de IA):
  - as conversas guardadas (Conversas/), no formato «Dono: …» / «FRIDAY: …» — é daqui que ela aprende a CONVERSAR;
  - as memórias, tópicos e lembranças do cofre (o que ela sabe de você);
  - os estudos e os textos inteiros das fontes (Estudos/, Estudos/Detalhes/) — a especialidade em cibersegurança;
  - a documentação do projeto e qualquer .txt que você puser em modelos_ia/corpus/ (livros de domínio público, por exemplo).
Privado/ e notas marcadas como privadas NUNCA entram.
"""
import os, re, time
from pathlib import Path
import numpy as np
from .tokenizador import BPETokenizer
from .gpt import GPT, AdamW

RAIZ = Path(__file__).resolve().parents[2]
PASTA = Path(os.getenv("MODELO_PROPRIO_DIR", str(RAIZ / "modelos_ia" / "friday-gpt")))


def montar_corpus(incluir_cofre=True):
    """O texto de treino (str) e um resumo de onde veio (dict)."""
    partes, origem = [], {}

    def add(nome, txt):
        txt = txt.strip()
        if len(txt) > 40:
            partes.append(txt)
            origem[nome] = origem.get(nome, 0) + len(txt)

    if incluir_cofre:
        try:
            import memoria as M
            if M.ativo():
                b = M.base()
                for pasta in ("Conversas", "Memorias", "Topicos", "Lembrancas", "Estudos", "Estudos/Detalhes", "Eu"):
                    d = b / pasta
                    for f in sorted(d.glob("*.md")) if d.is_dir() else []:
                        nota = M._ler_nota(f)
                        if not nota or nota.get("privado"):
                            continue
                        corpo = re.sub(r"^#.*$|^_.*_$|\[\[|\]\]", "", nota["corpo"], flags=re.M)
                        if pasta == "Conversas":            # vira diálogo: «Dono: …» / «FRIDAY: …»
                            corpo = re.sub(r"(?im)^\W*(?:voc[eê]|dono|usu[aá]rio)\W*[:\-]", "Dono:", corpo)
                            corpo = re.sub(r"(?im)^\W*friday\W*[:\-]", "FRIDAY:", corpo)
                        add(pasta.split("/")[0], corpo)
        except Exception:
            pass
    for f in sorted((RAIZ / "docs").glob("*.md")):
        add("docs", f.read_text(encoding="utf-8", errors="replace"))
    extra = RAIZ / "modelos_ia" / "corpus"
    for f in sorted(extra.glob("*.txt")) if extra.is_dir() else []:
        add("corpus", f.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(partes), origem


def treinar(vocab=2048, ctx=128, d=128, cabecas=4, camadas=4, passos=2000, lote=16, lr=3e-4, relatorio=print, texto=None, semente=1337):
    """Treina do zero e salva. Devolve (modelo, tokenizador, histórico de perdas)."""
    t0 = time.time()
    if texto is None:
        texto, origem = montar_corpus()
        relatorio(f"Texto de treino: {len(texto):,} caracteres · " + ", ".join(f"{k} {v:,}" for k, v in origem.items()))
    if len(texto) < 2000:
        raise ValueError("pouco texto para treinar (menos de 2.000 caracteres): converse mais com ela ou ponha .txt em modelos_ia/corpus/")
    tok = BPETokenizer(vocab).train(texto)
    dados = np.array(tok.encode(texto), dtype=np.int32)
    relatorio(f"Tokenizador: {len(tok)} tokens · texto vira {len(dados):,} tokens ({len(texto) / max(1, len(dados)):.1f} caracteres por token)")
    corte = int(len(dados) * 0.95)
    treino, val = dados[:corte], dados[corte:]
    ctx = min(ctx, max(8, len(val) - 2))
    m = GPT(len(tok), ctx=ctx, d=d, cabecas=cabecas, camadas=camadas, semente=semente)
    relatorio(f"Modelo: {m.n_parametros():,} parâmetros ({camadas} camadas, {cabecas} cabeças, d={d}, contexto {ctx})")
    opt = AdamW(m.p, lr=lr)
    rng = np.random.default_rng(semente)

    def lote_de(arr):
        i = rng.integers(0, len(arr) - ctx - 1, lote)
        x = np.stack([arr[j:j + ctx] for j in i])
        y = np.stack([arr[j + 1:j + ctx + 1] for j in i])
        return x, y

    hist = []
    aquec = max(1, passos // 20)
    for passo in range(1, passos + 1):
        taxa = lr * min(1.0, passo / aquec) * (0.1 + 0.9 * 0.5 * (1 + np.cos(np.pi * passo / passos)))   # aquecimento + cosseno
        x, y = lote_de(treino)
        perda, g = m.perda_e_gradientes(x, y)
        opt.passo(m.p, g, taxa)
        hist.append(perda)
        if passo % max(1, passos // 20) == 0 or passo == passos:
            xv, yv = lote_de(val) if len(val) > ctx + 2 else (x, y)
            pv, _ = m.perda_e_gradientes(xv, yv)
            relatorio(f"passo {passo:>5}/{passos} · perda treino {np.mean(hist[-50:]):.3f} · validação {pv:.3f} · {time.time() - t0:.0f}s")
    PASTA.mkdir(parents=True, exist_ok=True)
    tok.salvar(PASTA / "tokenizador.json")
    m.salvar(PASTA / "modelo.npz", {"treinado_em": time.time(), "passos": passos, "perda_final": float(np.mean(hist[-50:]))})
    relatorio(f"Salvo em {PASTA} ({time.time() - t0:.0f}s).")
    return m, tok, hist
