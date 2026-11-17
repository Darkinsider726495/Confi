import sys, json, os, random; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1")
import memoria as M, broker as B, curiosidade as CUR, prefrontal as PFC, internet as I, vida as V
import catalogo
P = {"https://a.example/x": ("a.example", "A criptografia protege dados com chaves e algoritmos matemáticos. " * 8)}
I.resultados = lambda q: [{"t": "Cripto", "u": u, "s": ""} for u in P]; I.texto_pagina = lambda u, limite=2500: P[u]
V._atualizar()["ult_conversa"] -= 600   # harness: o estado interno nasce neste processo (cópia sem vida.json); finge que a última conversa foi há 10 min
print("[processo novo] metas:", [(m["titulo"], m["estado"], m["progresso"]) for m in PFC.ARQ.get()["metas"].values()], "| curiosidade ligada?", CUR.ativa())
print("pedido do dono:", CUR.tratar("ligue a curiosidade"), "| ligada?", CUR.ativa())
for i in range(3):
    r = PFC.pensar(); print(f"pensar #{i+1}: agir={r['decisao']['agir']} feitos={r['feitos']}")
vez = CUR.vez_de_estudar(); print("vez_de_estudar():", vez, "| vontade:", round(V.vontade_estudar(), 2), "| candidatos:", CUR.candidatos()[:3])
if vez:
    r = CUR.estudar(); print("estudo autônomo:", {k: v for k, v in r.items() if k != "frase"})
print("notas de estudo:", [p.name for p in (M.base() / "Estudos").glob("*.md")])
r = PFC.pensar(); print("pensar depois:", r["decisao"]["agir"], r["feitos"], "| metas:", [(m["titulo"], m["estado"], m["progresso"]) for m in PFC.ARQ.get()["metas"].values()])
