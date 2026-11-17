import sys, os, time, random; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import memoria as M, neuronios as N
random.seed(7)
palavras = [f"palavra{i}" for i in range(3000)]
pasta = M.base() / "Memorias"; pasta.mkdir(parents=True, exist_ok=True)
def criar(n0, n1):
    for i in range(n0, n1):
        corpo = " ".join(random.choices(palavras, k=60))
        (pasta / f"Memoria {i}.md").write_text(f"---\ntipo: fato\ncriado: 2026-10-01T10:00:00-03:00\nimportancia: 3\norigem: usuario\ntags: [friday, memoria, fato]\n---\n# Memoria {i}\n\n{corpo}\n", encoding="utf-8")
print("MAX_ARQUIVOS (teto de varredura):", getattr(M, "MAX_ARQUIVOS", None))
n = 0
for alvo in (500, 2000, 5000):
    criar(n, alvo); n = alvo
    t = time.time(); M.buscar("palavra10 palavra200 palavra999"); frio = time.time() - t
    t = time.time(); M.buscar("palavra11 palavra201"); quente = time.time() - t
    t = time.time(); g = N.grafo(); tg = time.time() - t
    t = time.time(); M.contexto_completo("palavra42 palavra77"); tc = time.time() - t
    print(f"{alvo:5d} notas | buscar frio {frio*1000:7.0f} ms | buscar quente {quente*1000:7.0f} ms | contexto p/ prompt {tc*1000:7.0f} ms | grafo {tg*1000:7.0f} ms ({g['stats']['neuronios']} neurônios)")
