import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1")
import broker as B, vida as V, catalogo
B.executar("anotar", {"texto": "um"}); V.vigiar()      # marca onde está
n0 = {k: round(V.nivel(k), 3) for k in ("dopamina", "serotonina", "acetilcolina")}
for _ in range(3): B.executar("criar_arquivo", {"nome": "../x.md", "conteudo": "a"})   # três falhas de verdade
print("achou:", V.vigiar(), "| níveis antes:", n0, "| depois:", {k: round(V.nivel(k), 3) for k in n0})
print("contadores do dia:", V.hoje())
