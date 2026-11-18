#!/usr/bin/env python3
"""BPE em loop contínuo: o tokenizador da FRIDAY aprende sem parar com o texto novo (Ctrl+C para).

    python scripts/bpe_continuo.py                 uma rodada a cada 10 min, para sempre
    python scripts/bpe_continuo.py --intervalo 60  a cada 1 min
    python scripts/bpe_continuo.py --uma-vez       só uma rodada
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
from modelo import continuo as C

ap = argparse.ArgumentParser()
ap.add_argument("--intervalo", type=int, default=600)
ap.add_argument("--uma-vez", action="store_true")
a = ap.parse_args()
print("BPE contínuo da FRIDAY: aprendendo tokens novos com o texto que chega (Ctrl+C para).")
try:
    C.laco(intervalo=a.intervalo, vezes=1 if a.uma_vez else None)
except KeyboardInterrupt:
    print("\nParado. O que ela aprendeu ficou salvo.")
