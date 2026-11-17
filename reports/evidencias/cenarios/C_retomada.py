import sys, json, os, random; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1")
import memoria as M, broker as B, curiosidade as CUR, prefrontal as PFC, internet as I, vida as V
import catalogo
P = {"https://a.example/x": ("a.example", "A criptografia protege dados com chaves e algoritmos matemáticos. " * 8)}
I.resultados = lambda q: [{"t": "Cripto", "u": u, "s": ""} for u in P]; I.texto_pagina = lambda u, limite=2500: P[u]
print("[processo novo] metas persistidas:", [(m["titulo"], m["estado"], m["progresso"]) for m in PFC.ARQ.get()["metas"].values()])
print("notas de estudo antes:", len(list((M.base() / "Estudos").glob("*.md"))))
for i in range(4):
    r = PFC.pensar()
    print(f"pensar #{i+1}: agir={r['decisao']['agir']} feitos={r['feitos']} alertas={r['alertas']}")
print("notas de estudo depois:", len(list((M.base() / "Estudos").glob("*.md"))), "| metas:", [(m["titulo"], m["estado"], m["progresso"]) for m in PFC.ARQ.get()["metas"].values()])
print("vez_de_estudar():", CUR.vez_de_estudar())
