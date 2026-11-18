#!/usr/bin/env python3
"""Sobe a API PRÓPRIA do modelo da FRIDAY (POST /v1/chat/completions, com a chave de friday/.modelo_token).

    python scripts/api_modelo.py           só no próprio aparelho (127.0.0.1:8100)
    python scripts/api_modelo.py --rede    também na rede local (ex.: no PC; no celular, PROPRIA_URL=http://IP-DO-PC:8100 e a mesma chave)
"""
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
from modelo import api

ap = argparse.ArgumentParser()
ap.add_argument("--rede", action="store_true")
ap.add_argument("--porta", type=int, default=8100)
a = ap.parse_args()
s = api.servir("0.0.0.0" if a.rede else "127.0.0.1", a.porta)
print(f"API do modelo próprio em http://{'0.0.0.0' if a.rede else '127.0.0.1'}:{a.porta}/v1/chat/completions  (chave em friday/.modelo_token)")
print("Modelo treinado:", "sim" if api.disponivel() else "ainda não (python scripts/treinar_modelo.py)")
try:
    s.serve_forever()
except KeyboardInterrupt:
    pass
