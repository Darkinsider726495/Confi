import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import broker as B, catalogo
def nv(f): return f["nivel"] if isinstance(f["nivel"], int) else "var"
por = {}
for n, f in B.FERRAMENTAS.items(): por.setdefault(nv(f), []).append(n + ("*" if f["externo"] or f.get("externo_dyn") else ""))
print("total:", len(B.FERRAMENTAS), "(sem Termux:API; no celular entram +7 do Android)")
for k in sorted(por, key=str): print(f"nível {k}: {len(por[k])} -> {', '.join(por[k])}")
