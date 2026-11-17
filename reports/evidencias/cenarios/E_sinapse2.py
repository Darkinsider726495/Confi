import sys, json, os; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import memoria as M, neuronios as N
M.guardar("Gato Mimi", "o gato Mimi gosta de dormir no sofá", "fato", 3)
M.guardar("Lua cheia", "a lua cheia aparece no céu da varanda", "fato", 3)
def top(q): return [(x["titulo"], x["score"]) for x in M.buscar(q, 5)]
for n in (1, 2, 1, 5):
    for i in range(n):
        N._ult['t'] = 0     # pula a trava de 30 s (o mesmo disparo repetido conta uma vez só)
        M.lembrar("gato lua")
    e = json.load(open(f"{sys.argv[1]}/cofre/FRIDAY/.cerebro/estado.json"))
    sin = e.get("sin", {})
    nota = open(f"{sys.argv[1]}/cofre/FRIDAY/Memorias/Gato Mimi.md", encoding="utf-8").read()
    print(f"após +{n}: sinapses={ {k: v for k, v in sin.items()} } | link promovido na nota? {'[[' in nota} | busca 'lua' -> {top('lua')} | busca 'varanda' -> {top('varanda')}")
