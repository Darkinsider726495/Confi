#!/usr/bin/env python3
"""Chaves da API própria da FRIDAY (uma por aparelho). A chave só aparece na hora em que é criada: guarde-a.

    python scripts/chaves_api.py criar celular      cria a chave «celular» e mostra uma vez
    python scripts/chaves_api.py listar             mostra os nomes, o fim de cada chave e quantas vezes foi usada
    python scripts/chaves_api.py revogar celular    desativa a chave «celular» (as outras continuam)
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "friday"))
from modelo import chaves as K

if len(sys.argv) < 2 or sys.argv[1] not in ("criar", "listar", "revogar"):
    print(__doc__)
    raise SystemExit(2)
acao = sys.argv[1]
if acao == "listar":
    for c in K.listar():
        estado = "REVOGADA" if c["revogada"] else "ativa"
        print(f"  {c['nome']:<16} …{c['fim']}  {estado:<9} {c['usos']} uso(s)  criada {time.strftime('%d/%m/%Y', time.localtime(c['criada']))}")
    raise SystemExit(0)
if len(sys.argv) < 3:
    print("Diga o nome. Ex.: python scripts/chaves_api.py criar celular")
    raise SystemExit(2)
if acao == "criar":
    try:
        chave = K.criar(sys.argv[2])
    except ValueError as e:
        print(e)
        raise SystemExit(1)
    print(f"Chave «{sys.argv[2]}» criada. Ela aparece SÓ AGORA — guarde (não mande em chat nem print):\n\n  {chave}\n")
    print("No aparelho que vai usar:  echo 'PROPRIA_CHAVE=<a chave>' >> .env")
else:
    print("Revogada." if K.revogar(sys.argv[2]) else "Não achei uma chave ativa com esse nome.")
