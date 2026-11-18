#!/usr/bin/env python3
"""Treina o MODELO PRÓPRIO da FRIDAY (tokenizador BPE + GPT em NumPy) com o que ela sabe. Sem PyTorch, sem API de terceiros.

    python scripts/treinar_modelo.py                 tamanho padrão (celular: comece com --rapido)
    python scripts/treinar_modelo.py --rapido        teste rápido (minutos): modelo pequeno, poucos passos
    python scripts/treinar_modelo.py --grande        mais forte (use no PC ou no Colab: horas)
    python scripts/treinar_modelo.py --passos 5000 --camadas 6 --d 192
    python scripts/treinar_modelo.py --continuar     retoma de onde parou (o treino salva sozinho a cada 200 passos; Ctrl+C salva e para)
    python scripts/treinar_modelo.py --ajuste        ajuste fino: depois do pré-treino, ensina a CONVERSAR como assistente
    python scripts/treinar_modelo.py --hibrido 3     modelo HÍBRIDO: passa 3 vezes pelas mesmas camadas (pensa mais fundo, mesmos parâmetros)
    python scripts/treinar_modelo.py --conversar     conversa com o modelo treinado, o texto aparece ao vivo (Ctrl+C sai)
    python scripts/treinar_modelo.py --infinito "texto"   escreve SEM PARAR a partir do texto, sem limite (Ctrl+C para)
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
    ap.add_argument("--infinito", nargs="?", const="A FRIDAY", metavar="TEXTO", help="escreve SEM PARAR a partir do texto (Ctrl+C para)")
    ap.add_argument("--passos", type=int)
    ap.add_argument("--camadas", type=int)
    ap.add_argument("--d", type=int)
    ap.add_argument("--vocab", type=int)
    ap.add_argument("--ctx", type=int)
    ap.add_argument("--continuar", action="store_true", help="retoma do último ponto salvo (modelo + otimizador + passo)")
    ap.add_argument("--ajuste", action="store_true", help="ajuste fino: ensina a CONVERSAR (conversas + perguntas e respostas dos estudos)")
    ap.add_argument("--hibrido", type=int, metavar="R", help="modelo híbrido: passa R vezes pelas mesmas camadas (profundidade recorrente, BPTT)")
    a = ap.parse_args()
    if a.conversar or a.infinito:
        from modelo import api
        if not api.disponivel():
            print("Ainda não há modelo treinado: rode primeiro  python scripts/treinar_modelo.py --rapido")
            return 1
        if a.infinito:
            import numpy as np, codecs
            modelo, tok = api.carregar()
            dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
            print(f"Modelo próprio escrevendo SEM LIMITE a partir de «{a.infinito}» (Ctrl+C para):\n")
            print(a.infinito, end="", flush=True)
            n = 0
            try:
                for t in modelo.fluxo(tok.encode(a.infinito), temperatura=0.8, top_k=40):
                    print(dec.decode(tok.vocab.get(t, b"")), end="", flush=True)
                    n += 1
            except KeyboardInterrupt:
                print(f"\n\n[parado por você depois de {n:,} tokens]")
            return 0
        hist = []
        print("Conversando com o modelo PRÓPRIO dela, sem limite de uso (Ctrl+C sai).")
        try:
            while True:
                t = input("você › ").strip()
                if not t:
                    continue
                hist.append({"role": "user", "content": t})
                print("friday-gpt › ", end="", flush=True)
                partes = []
                try:
                    for pedaco in api.responder_fluxo(hist):           # o texto vai aparecendo enquanto ela escreve
                        partes.append(pedaco)
                        print(pedaco, end="", flush=True)
                except KeyboardInterrupt:
                    print(" [interrompido]", end="")
                print()
                hist.append({"role": "assistant", "content": "".join(partes).strip()})
                del hist[:-12]
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
    if a.hibrido:
        conf["repeticoes"] = a.hibrido
    if a.continuar:
        conf["continuar"] = True
    if a.ajuste:
        conf.update(ajuste=True, passos=a.passos or 600)
    try:
        T.treinar(**conf)
    except KeyboardInterrupt:
        print("\nParado. Para continuar de onde parou:  python scripts/treinar_modelo.py --continuar")
        return 0
    print("\nPronto. Converse com ele:  python scripts/treinar_modelo.py --conversar")
    print("Para a FRIDAY usar o modelo dela no lugar da Groq:  echo 'IA_PROVEDOR=propria' >> .env  e  bash termux/atualizar.sh --reiniciar")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
