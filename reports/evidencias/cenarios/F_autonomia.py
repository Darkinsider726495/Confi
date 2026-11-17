import sys, json, os, datetime as dt; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1")
import memoria as M, broker as B, autonomia as AUT, protocolos as P, vida as V, main as MAIN
import catalogo
base = sys.argv[1]
print("constantes: DIAS_ASSISTENTE", AUT.DIAS_ASSISTENTE, "DIAS_PILOTO", AUT.DIAS_PILOTO, "JANELA_MIN", AUT.JANELA_MIN, "MAX_EXEC_DIA", AUT.MAX_EXEC_DIA, "ATRASO_MAX_MIN", AUT.ATRASO_MAX_MIN, "MAX_AVISOS_DIA", AUT.MAX_AVISOS_DIA)
print("protocolos e nível de risco para virar rotina:", {n: AUT.nivel_rotina(n) for n in P.carregar()})
alvo = next(n for n in P.carregar() if AUT.nivel_rotina(n) == 0)
print("protocolo escolhido (só leitura):", alvo)
ditas = []
falar = lambda t: ditas.append(t)
print("modo inicial:", AUT.modo())
print("pedido de modo:", AUT.tratar("modo piloto automático"))
print("modo agora:", AUT.modo())
# o usuário pede o protocolo ~08:00 em 5 dias diferentes: ela aprende o hábito
hoje = dt.datetime(2026, 10, 24, 8, 3)
msgs = []
for i in range(6):
    dia = hoje - dt.timedelta(days=5 - i) + dt.timedelta(minutes=(i * 2) % 7)
    msgs.append(AUT.observar(alvo, agora=dia))
print("frases dela durante o aprendizado:", [m for m in msgs if m])
print("resposta ao «sim»:", AUT.tratar("sim"))
print("rotinas criadas:", AUT.resumo()["lista"], "| modo:", AUT.modo())
# no dia seguinte, na hora: o relógio dispara sozinho (sem nenhum comando)
amanha = dt.datetime(2026, 10, 25, 8, 4)
ant = len(open(f"{base}/aud.jsonl").read().splitlines()) if os.path.exists(f"{base}/aud.jsonl") else 0
AUT.tick(falar, agora=amanha)
novos = [json.loads(l) for l in open(f"{base}/aud.jsonl").read().splitlines()[ant:]]
print("tick às 08:04 -> falas:", ditas, "\n   trilha:", [(x.get("ferramenta"), x.get("decisao")) for x in novos])
ditas.clear(); AUT.tick(falar, agora=amanha + dt.timedelta(minutes=1))
print("tick de novo no mesmo dia (não repete):", ditas)
# pausar/cancelar
print("cancelar:", AUT.tratar(f"cancele a rotina {alvo}")); print("rotinas:", AUT.resumo()["lista"])
print("o que você fez sozinha?:", AUT.tratar("o que você fez sozinha"))
print("desligar autonomia:", AUT.tratar("desligue a autonomia")); print("modo:", AUT.modo())
# rotina com ferramenta de nível alto nunca vira rotina
print("pode virar rotina um protocolo com relé de portão (nível 3)?", AUT.pode_ser_rotina("sair"))
print("auditoria íntegra:", B.verificar_auditoria())
# vigília: sem novidade nenhuma, não inventa conversa
ditas.clear(); AUT.tick(falar, agora=amanha + dt.timedelta(hours=3)); print("vigília sem novidade ->", ditas)
