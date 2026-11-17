import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import memoria as M, neuronios as N, broker as B, cerebro as C, prefrontal as PFC, curiosidade as CUR, json
import catalogo
print("[processo novo] HIST em memória:", len(C.HIST))
print(M.lembrar("qual o nome do servidor"))
print("tratar:", M.tratar("o que você lembra sobre servidor"))
print("retomada:", M.retomada())
ok, n = B.verificar_auditoria(); print("auditoria íntegra:", ok, "eventos:", n)
print("metas:", [(m["titulo"], m["estado"], m["progresso"]) for m in PFC.ARQ.get()["metas"].values()])
print("interesse criptografia:", CUR._e()["temas"].get("criptografia"))
print("sinapses:", N.resumo().get("sinapses"), "neuronios:", N.resumo().get("neuronios"))
print("pendência do corretor sobrevive?", B.pendente_publico())
