#!/usr/bin/env python3
"""Relatório de evolução da FRIDAY no Termux (números do dia, comparação e investigação). Bom para mandar ao Claude: não tem nada pessoal.

    python scripts/relatorio.py            o relatório de hoje
    python scripts/relatorio.py --tabela   também a tabela dos últimos dias
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
import relatorio as R

n = R.registrar()
if n is None:
    print("A memória está desligada (OBSIDIAN_VAULT=off).")
    raise SystemExit(1)
print(R.relatorio(n))
if "--tabela" in sys.argv:
    print("\ndia         neurônios sinapses estudos fontes feedback IA  rotina")
    for x in R.historico()[-14:]:
        print(f"{x.get('dia', ''):<11} {x.get('neuronios', ''):>9} {x.get('sinapses', ''):>8} {x.get('estudos', ''):>7} {x.get('fontes_inteiras', ''):>6} "
              f"{x.get('votos_feedback', ''):>8} {x.get('ia_hoje', ''):>3}  {x.get('rotina', '')}")
