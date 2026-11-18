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


def dialogos_dos_estudos():
    """Perguntas e respostas tiradas dos estudos dela (cibersegurança etc.), no formato de conversa — para o AJUSTE FINO (aprender a responder)."""
    out = []
    try:
        import memoria as M
        d = M.base() / "Estudos" if M.ativo() else None
        for f in sorted(d.glob("*.md")) if d and d.is_dir() else []:
            nota = M._ler_nota(f)
            if not nota or nota.get("privado"):
                continue
            corpo = " ".join(re.sub(r"^#.*$|^_.*_$", "", nota["corpo"], flags=re.M).split())
            if len(corpo) > 60:
                t = f.stem
                out.append(f"Dono: o que é {t.lower()}?\nFRIDAY: {corpo[:600]}")
                out.append(f"Dono: me explica {t.lower()}\nFRIDAY: {corpo[:600]}")
    except Exception:
        pass
    return out


def texto_de_ajuste():
    """Só diálogo: as conversas guardadas (Dono/FRIDAY) + perguntas e respostas dos estudos."""
    partes = dialogos_dos_estudos()
    try:
        import memoria as M
        d = M.base() / "Conversas" if M.ativo() else None
        for f in sorted(d.glob("*.md")) if d and d.is_dir() else []:
            nota = M._ler_nota(f)
            if nota and not nota.get("privado"):
                corpo = re.sub(r"(?im)^\W*(?:voc[eê]|dono|usu[aá]rio)\W*[:\-]", "Dono:", nota["corpo"])
                partes.append(re.sub(r"(?im)^\W*friday\W*[:\-]", "FRIDAY:", corpo))
    except Exception:
        pass
    return "\n\n".join(partes)


def _salvar_ponto(m, opt, tok, passo, passos, hist, extra):
    """Ponto de restauração: modelo + otimizador + passo. Gravado com troca atômica (nunca fica pela metade)."""
    PASTA.mkdir(parents=True, exist_ok=True)
    tok.salvar(PASTA / "tokenizador.json")
    m.salvar(PASTA / "modelo.tmp.npz", {"treinado_em": time.time(), "passos": passo, "perda_final": float(np.mean(hist[-50:] or [0])), **extra})
    os.replace(PASTA / "modelo.tmp.npz", PASTA / "modelo.npz")
    np.savez(PASTA / "otimizador.tmp.npz", t=np.array(opt.t), passo=np.array(passo), passos=np.array(passos),
             **{"m:" + k: v for k, v in opt.m.items()}, **{"v:" + k: v for k, v in opt.v.items()})
    os.replace(PASTA / "otimizador.tmp.npz", PASTA / "otimizador.npz")


def treinar(vocab=2048, ctx=128, d=128, cabecas=4, camadas=4, passos=2000, lote=16, lr=3e-4, relatorio=print, texto=None, semente=1337,
            repeticoes=1, continuar=False, ajuste=False, salvar_cada=200, amostra="Dono: o que é injeção de SQL?\nFRIDAY:"):
    """Treina e salva. `continuar=True` retoma do último ponto salvo (modelo + otimizador + passo); `ajuste=True` é o AJUSTE FINO: parte do modelo
    já treinado e treina só em diálogo (conversas + perguntas e respostas dos estudos), com taxa menor. Devolve (modelo, tokenizador, perdas)."""
    t0 = time.time()
    existe = (PASTA / "modelo.npz").exists() and (PASTA / "tokenizador.json").exists()
    if (continuar or ajuste) and not existe:
        raise ValueError("não há modelo salvo para continuar/ajustar: treine primeiro (python scripts/treinar_modelo.py)")
    if ajuste and texto is None:
        texto = texto_de_ajuste()
        relatorio(f"Ajuste fino: {len(texto):,} caracteres de diálogo (conversas + perguntas e respostas dos estudos)")
    elif texto is None:
        texto, origem = montar_corpus()
        relatorio(f"Texto de treino: {len(texto):,} caracteres · " + ", ".join(f"{k} {v:,}" for k, v in origem.items()))
    if len(texto) < 2000:
        raise ValueError("pouco texto para treinar (menos de 2.000 caracteres): converse mais com ela ou ponha .txt em modelos_ia/corpus/")
    if continuar or ajuste:
        tok = BPETokenizer.carregar(PASTA / "tokenizador.json")
        m = GPT.carregar(PASTA / "modelo.npz")
        if m.cfg["vocab"] < len(tok):
            m.expandir_vocab(len(tok))
    else:
        tok = BPETokenizer(vocab).train(texto)
    dados = np.array(tok.encode(texto), dtype=np.int32)
    relatorio(f"Tokenizador: {len(tok)} tokens · texto vira {len(dados):,} tokens ({len(texto) / max(1, len(dados)):.1f} caracteres por token)")
    corte = int(len(dados) * 0.95)
    treino, val = dados[:corte], dados[corte:]
    if not (continuar or ajuste):
        ctx = min(ctx, max(8, len(val) - 2))
        m = GPT(len(tok), ctx=ctx, d=d, cabecas=cabecas, camadas=camadas, semente=semente, repeticoes=repeticoes)
    ctx = m.cfg["ctx"]
    if len(treino) < ctx + 2:
        raise ValueError("pouco texto para o contexto deste modelo")
    if len(val) < ctx + 2:
        val = treino
    c = m.cfg
    relatorio(f"Modelo: {m.n_parametros():,} parâmetros ({c['camadas']} camadas, {c['cabecas']} cabeças, d={c['d']}, contexto {ctx})"
              + (f" · HÍBRIDO: {c['repeticoes']} passadas pelas mesmas camadas (BPTT na profundidade)" if c.get("repeticoes", 1) > 1 else ""))
    lr = lr / 3 if ajuste else lr
    opt = AdamW(m.p, lr=lr)
    inicio = 0
    if continuar and (PASTA / "otimizador.npz").exists():
        o = np.load(PASTA / "otimizador.npz")
        if all(("m:" + k) in o.files for k in m.p) and all(o["m:" + k].shape == m.p[k].shape for k in m.p):
            opt.m = {k: o["m:" + k] for k in m.p}
            opt.v = {k: o["v:" + k] for k in m.p}
            opt.t = int(o["t"])
            inicio = int(o["passo"])
            passos = max(passos, int(o["passos"]))
            relatorio(f"Continuando do passo {inicio} de {passos}.")
    rng = np.random.default_rng(semente + inicio)

    def lote_de(arr):
        i = rng.integers(0, len(arr) - ctx - 1, lote)
        x = np.stack([arr[j:j + ctx] for j in i])
        y = np.stack([arr[j + 1:j + ctx + 1] for j in i])
        return x, y

    hist = []
    aquec = max(1, passos // 20)
    extra = {"fase": "ajuste" if ajuste else "pretreino"}
    try:
        for passo in range(inicio + 1, passos + 1):
            taxa = lr * min(1.0, passo / aquec) * (0.1 + 0.9 * 0.5 * (1 + np.cos(np.pi * passo / passos)))   # aquecimento + cosseno
            x, y = lote_de(treino)
            perda, g = m.perda_e_gradientes(x, y)
            opt.passo(m.p, g, taxa)
            hist.append(perda)
            if passo % max(1, passos // 20) == 0 or passo == passos:
                xv, yv = lote_de(val)
                pv, _ = m.perda_e_gradientes(xv, yv)
                relatorio(f"passo {passo:>5}/{passos} · perda treino {np.mean(hist[-50:]):.3f} · validação {pv:.3f} · {time.time() - t0:.0f}s")
            if salvar_cada and passo % salvar_cada == 0:
                _salvar_ponto(m, opt, tok, passo, passos, hist, extra)
    except KeyboardInterrupt:
        relatorio("Interrompido: salvando o ponto atual (continue depois com --continuar).")
        _salvar_ponto(m, opt, tok, passo - 1, passos, hist, extra)
        raise
    _salvar_ponto(m, opt, tok, passos, passos, hist, extra)
    if amostra:
        try:
            ids = tok.encode(amostra)
            relatorio("Amostra: " + amostra.replace("\n", " ") + tok.decode(m.gerar(ids, n=40, temperatura=0.7, rng=np.random.default_rng(1))).split("\nDono:")[0])
        except Exception:
            pass
    relatorio(f"Salvo em {PASTA} ({time.time() - t0:.0f}s).")
    return m, tok, hist
