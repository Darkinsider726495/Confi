import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import memoria as M, neuronios as N, json, re
M.guardar("Gato Mimi", "o gato Mimi gosta de dormir no sofá", "fato", 3)
M.guardar("Lua cheia", "a lua cheia aparece no céu da varanda", "fato", 3)
def top(q): return [(x["titulo"], x["score"]) for x in M.buscar(q, 5)]
print("antes  | busca 'gato':", top("gato"), "| busca 'lua':", top("lua"))
# o que a rede faz com o uso: lembrar os dois juntos várias vezes
for i in range(12):
    M.lembrar("gato lua")
sin = json.loads(open(f"{sys.argv[1]}/cofre/FRIDAY/.cerebro/sinapses.json").read()) if __import__("os").path.exists(f"{sys.argv[1]}/cofre/FRIDAY/.cerebro/sinapses.json") else None
print("arquivos .cerebro:", sorted(__import__("os").listdir(f"{sys.argv[1]}/cofre/FRIDAY/.cerebro")))
print("depois | busca 'gato':", top("gato"), "| busca 'lua':", top("lua"))
nota = open(f"{sys.argv[1]}/cofre/FRIDAY/Memorias/Gato Mimi.md", encoding="utf-8").read()
print("nota Gato Mimi agora termina com:", repr(nota[-120:]))
print("resumo:", N.resumo().get("sinapses"), "sinapses")
# o peso da sinapse é usado na recuperação? procurar quem lê o peso fora do módulo de visualização
import subprocess
print(subprocess.run(["grep", "-n", "-E", r"_peso\(|\.get\(\"sin\"|\[\"sin\"\]", COPIA := amb.COPIA + "/friday/memoria.py", amb.COPIA + "/friday/cerebro.py", amb.COPIA + "/friday/curiosidade.py"], capture_output=True, text=True).stdout or "nenhum uso do peso em memoria/cerebro/curiosidade")
