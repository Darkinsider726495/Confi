import sys, time; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1")
import memoria as M, curiosidade as CUR, vida as V, ferramentas as F
import catalogo
e = CUR._e(); t = time.time()
print("ativa", CUR.ativa(), "| ativo", M.ativo(), "| MEMORIA_AUTO", __import__("os").getenv("MEMORIA_AUTO", "1"))
print("em_descanso", F.em_descanso(), "| bloq", e["bloq"], "t<bloq", t < e["bloq"], "| ult", e["ult"], "| t-ult<intervalo", t - e["ult"] < CUR.intervalo(), "intervalo", CUR.intervalo(), "| teto", CUR.passou_do_teto(e["dia"]["n"]))
print("seg desde conversa", V.segundos_desde_conversa(), "| ligada", V.ligada(), "| vontade", round(V.vontade_estudar(), 2), "LIMIAR", CUR.LIMIAR_ESTUDAR)
