import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1", extra={"ANTHROPIC_API_KEY": "chave-falsa-de-teste", "IA_MODO": "auto", "LIMITE_DIARIO": "50"})
import ferramentas as F, cerebro as C, os
print("modo:", C._modo(), "| chave:", bool(os.getenv("ANTHROPIC_API_KEY")))
try: print("contar_llm(50):", F.contar_llm(50))
except Exception as e: print("EXC", type(e).__name__, e)
