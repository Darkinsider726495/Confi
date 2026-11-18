#!/usr/bin/env python3
"""Treina o MODELO PRÓPRIO da FRIDAY (tokenizador BPE + GPT em NumPy) com o que ela sabe. Sem PyTorch, sem API de terceiros.

    python scripts/treinar_modelo.py                 tamanho padrão (celular: comece com --rapido)
    python scripts/treinar_modelo.py --rapido        teste rápido (minutos): modelo pequeno, poucos passos
    python scripts/treinar_modelo.py --grande        mais forte (use no PC ou no Colab: horas)
    python scripts/treinar_modelo.py --passos 5000 --camadas 6 --d 192
    python scripts/treinar_modelo.py --conversar     conversa com o modelo treinado (Ctrl+C sai)
"""
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
from modelo import treino as T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--grande", action="store_true")
    ap.add_argument("--conversar", action="store_true")
    ap.add_argument("--passos", type=int)
    ap.add_argument("--camadas", type=int)
    ap.add_argument("--d", type=int)
    ap.add_argument("--vocab", type=int)
    ap.add_argument("--ctx", type=int)
    a = ap.parse_args()
    if a.conversar:
        from modelo import api
        if not api.disponivel():
            print("Ainda não há modelo treinado: rode primeiro  python scripts/treinar_modelo.py --rapido")
            return 1
        hist = []
        print("Conversando com o modelo PRÓPRIO dela (Ctrl+C sai).")
        try:
            while True:
                t = input("você › ").strip()
                if not t:
                    continue
                hist.append({"role": "user", "content": t})
                r = api.responder(hist)
                hist.append({"role": "assistant", "content": r})
                print("friday-gpt ›", r or "(…)")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
    conf = dict(vocab=2048, ctx=128, d=128, cabecas=4, camadas=4, passos=2000, lote=16, lr=6e-4)
    if a.rapido:
        conf.update(vocab=768, ctx=64, d=64, cabecas=4, camadas=2, passos=300, lote=8, lr=1e-3)
    if a.grande:
        conf.update(vocab=4096, ctx=256, d=256, cabecas=8, camadas=6, passos=20000, lote=32)
    for k in ("passos", "camadas", "d", "vocab", "ctx"):
        if getattr(a, k):
            conf[k] = getattr(a, k)
    T.treinar(**conf)
    print("\nPronto. Converse com ele:  python scripts/treinar_modelo.py --conversar")
    print("Para a FRIDAY usar o modelo dela no lugar da Groq:  echo 'IA_PROVEDOR=propria' >> .env  e  bash termux/atualizar.sh --reiniciar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
