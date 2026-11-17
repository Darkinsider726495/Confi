#!/usr/bin/env python3
"""Teste manual da integração Groq: python scripts/perguntar_groq.py 'pergunta'."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from provedor_groq import responder, GroqError


def main() -> int:
    pergunta = " ".join(sys.argv[1:]).strip()
    if not pergunta:
        print("Uso: python scripts/perguntar_groq.py 'Sua pergunta'")
        return 2
    try:
        resposta = responder([{"role": "user", "content": pergunta}], sistema=(
            "Você é a FRIDAY, assistente pessoal. Responda em português do Brasil, com clareza e concisão. "
            "Não afirme que executou ações no aparelho; este script só conversa com o modelo."
        ), max_tokens=500)
    except GroqError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(resposta or "A API retornou uma resposta vazia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
