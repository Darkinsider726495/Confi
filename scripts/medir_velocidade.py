#!/usr/bin/env python3
"""Mede onde a FRIDAY demora para responder, no próprio aparelho, e compara modelos da Groq.

    python scripts/medir_velocidade.py                 mede a memória e o modelo atual
    python scripts/medir_velocidade.py --comparar      também testa os outros modelos de conversa da sua conta Groq

Não mostra a chave. Cada teste gasta uma pergunta curta do seu limite da Groq.
"""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PERGUNTA = "Oi, tudo bem? Responda em uma frase curta."


def cronometro(nome, f):
    t = time.time()
    try:
        r = f()
        print(f"  {nome:<38} {time.time() - t:6.2f} s")
        return r
    except Exception as e:
        print(f"  {nome:<38} {time.time() - t:6.2f} s  (erro: {type(e).__name__})")
        return None


def modelo_groq(modelo):
    import provedor_groq as G
    antes = os.environ.get("GROQ_MODEL")
    os.environ["GROQ_MODEL"] = modelo
    try:
        return G.responder([{"role": "user", "content": PERGUNTA}], sistema="Você é a FRIDAY. Português do Brasil.", max_tokens=80)
    finally:
        if antes is None:
            os.environ.pop("GROQ_MODEL", None)
        else:
            os.environ["GROQ_MODEL"] = antes


def main():
    import cerebro as C
    print("Onde ela gasta o tempo:")
    cronometro("memória + significado (contexto)", lambda: C._memoria_completa("como foi a prova de SQL?"))
    if (os.getenv("IA_PROVEDOR") or "").lower() != "groq" or not os.getenv("GROQ_API_KEY"):
        print("A Groq não está configurada (rode scripts/conectar_groq.py).")
        return 0
    import provedor_groq as G
    atual = os.getenv("GROQ_MODEL") or G.DEFAULT_MODEL
    cronometro(f"Groq · {atual}", lambda: modelo_groq(atual))
    if "--comparar" in sys.argv:
        import requests
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, timeout=20)
        ids = sorted(m["id"] for m in r.json().get("data", []) if not any(x in m["id"] for x in ("whisper", "tts", "guard", "playai", "orpheus", "prompt")))
        print("\nOutros modelos da sua conta (pergunta curta):")
        for m in ids:
            cronometro(m, lambda m=m: modelo_groq(m))
        print("\nPara trocar:  echo 'GROQ_MODEL=NOME' >> .env  e  bash termux/atualizar.sh --reiniciar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
