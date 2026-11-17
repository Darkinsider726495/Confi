#!/usr/bin/env python3
"""Treina a rede de significado da FRIDAY nas três etapas (docs/SIGNIFICADO.md):

  python scripts/treinar_significado.py --base        1. pré-treino SÓ com as docs do projeto → friday/significado_base.npz (vai no pacote)
  python scripts/treinar_significado.py --pretreino   1. pré-treino com docs + o cofre dela → cofre/.cerebro/significado.npz (fica no aparelho)
  python scripts/treinar_significado.py --ajuste      2+3. ajuste fino com as sinapses e o feedback do dono (rode de vez em quando)

Mostra a perda caindo a cada época e exemplos do que ela aprendeu.
"""
import argparse, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
import significado as S

TESTES = ["treino", "memória", "sinapse", "corretor", "estudo", "câmera", "objetivo", "segurança"]


def docs():
    textos = []
    for f in list((ROOT / "docs").glob("*.md")) + list((ROOT / "reports").glob("*.md")) + [ROOT / "README.md", ROOT / "CLAUDE.md"]:
        try:
            textos.append(f.read_text(encoding="utf-8"))
        except OSError:
            pass
    return textos


def mostrar(vocab):
    for t in TESTES:
        viz = S.parecidos(t, vocab[:4000], n=5, minimo=0.0)
        if viz:
            print(f"  {t:>10} → " + ", ".join(f"{w} {s:.2f}" for w, s in viz))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--base", action="store_true")
    g.add_argument("--pretreino", action="store_true")
    g.add_argument("--ajuste", action="store_true")
    ap.add_argument("--epocas", type=int, default=0)
    a = ap.parse_args()
    if not S.disponivel():
        print("Precisa do NumPy. No Termux: pkg install python-numpy")
        return 1
    rel = lambda ep, perda: print(f"  época {ep:>2}: perda {perda:.4f}", flush=True)
    if a.base or a.pretreino:
        textos = docs() + (S.corpus_do_cofre() if a.pretreino else [])
        n = sum(len(S.palavras(t)) for t in textos)
        print(f"Etapa 1 · pré-treino autossupervisionado: {len(textos)} textos, {n} palavras")
        t0 = time.time()
        vocab, W = S.pretreinar(textos, epocas=a.epocas or 8, relatorio=rel)
        destino = S.BASE_NPZ if a.base else None
        S.salvar(vocab, W, destino)
        S.carregar(forcar=True)
        print(f"Pronto em {time.time() - t0:.0f}s: {len(vocab)} palavras × {W.shape[1]} dimensões = {W.size:,} parâmetros → {destino or 'cofre/.cerebro/significado.npz'}")
        print("O que ela aprendeu (vizinhos por significado):")
        mostrar(vocab)
    else:
        print("Etapas 2 e 3 · ajuste fino com as sinapses dela e o feedback do dono")
        n = S.ajustar(epocas=a.epocas or 30, relatorio=lambda ep, p: ep % 10 == 0 and rel(ep, p))
        print(f"Ajuste feito com {n} exemplos." if n else "Ainda não há sinapses entre assuntos nem feedback para ajustar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
