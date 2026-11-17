#!/usr/bin/env python3
"""Treina a GRU da rotina da FRIDAY com o registro de atividades do cofre (docs/ROTINA.md) e mostra o que ela aprendeu.

  python scripts/treinar_rotina.py            treina agora (ela também treina sozinha, 1x por dia)
  python scripts/treinar_rotina.py --ver      só mostra a previsão da próxima hora com o modelo salvo
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
import rotina as R


def mostrar():
    prev = R.previsao()
    if not prev:
        print("Ainda não há modelo treinado.")
        return
    print(f"Próxima hora ({time.strftime('%H:%M')} → {(time.localtime().tm_hour + 1) % 24:02d}h):")
    for r, c in prev:
        print(f"  {R._nome(r):<30} {c * 100:5.1f}%  " + "█" * round(c * 30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ver", action="store_true")
    ap.add_argument("--epocas", type=int, default=0)
    a = ap.parse_args()
    if not R.disponivel():
        print("Precisa do NumPy. No Termux: pkg install python-numpy")
        return 1
    if not a.ver:
        print("GRU da rotina · treinando com o registro de atividades (só rótulos e assuntos, nunca frases)")
        t0 = time.time()
        r = R.treinar(epocas=a.epocas or 80, relatorio=lambda ep, p: ep % 10 == 0 and print(f"  época {ep:>3}: perda {p:.4f}", flush=True))
        if not r["ok"]:
            print("Não treinei:", r["motivo"])
            return 0
        print(f"Pronto em {time.time() - t0:.0f}s · {r['dias']} dias · {r['exemplos']} exemplos · rótulos: {', '.join(R._nome(x) for x in r['rotulos'])}")
        print(f"Erro nos 2 últimos dias (que a rede não viu): GRU {r['perda_validacao']} × jeito simples {r['perda_jeito_simples']}")
        print("→ Confiável: ela vai usar a previsão." if r["confiavel"] else "→ Ainda não vence o jeito simples: ela não vai se adiantar até aprender mais.")
    mostrar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
