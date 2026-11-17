import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1])
import memoria as M, neuronios as N, broker as B, cerebro as C, prefrontal as PFC, curiosidade as CUR
import catalogo  # registra ferramentas
print(M.guardar("Servidor de casa", "o servidor de casa se chama Hermes e fica no escritório", "fato", 5))
print(M.guardar("Projeto Inviktus", "o projeto Inviktus é um site de cibersegurança com formulário", "projeto", 4))
print(M.lembrar("servidor Hermes"))                         # acende neurônios (Hebb)
print(M.lembrar("Hermes escritório projeto Inviktus"))      # acende os dois juntos -> sinapse
M.registrar_conversa("qual o nome do servidor?", "Hermes, chefe.", False)
print(B.executar("criar_lembrete", {"minutos": 5, "texto": "teste de persistência"}))
ok, n = B.verificar_auditoria(); print("auditoria íntegra:", ok, "eventos:", n)
okm, meta = PFC.nova_meta("aprender", "criptografia"); print("meta:", okm, meta["titulo"] if okm else meta)
CUR.interesse("criptografia", 2.0)
print("sinapses:", N.resumo().get("sinapses"), "neuronios:", N.resumo().get("neuronios"))
print("HIST em memória:", len(C.HIST))
