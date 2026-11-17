import sys, json, os, time; sys.path.insert(0, "/tmp/claude-0/-home-claude/1550f8fb-f730-5336-8318-1a449c59d055/scratchpad/audit/cenarios")
import amb; amb.preparar(sys.argv[1], vida="1", extra={"ANTHROPIC_API_KEY": "chave-falsa-de-teste", "IA_MODO": "auto", "LIMITE_DIARIO": "50"})
import requests, memoria as M, broker as B, cerebro as C, main as MAIN, vida as V
import catalogo
base = sys.argv[1]
# modelo FALSO que se comporta como a API: 1) propõe guardar_memoria; 2) vê o resultado e responde. Também tenta uma injeção vinda de "dado externo".
chamadas = []
class R:
    def __init__(s, d): s._d = d; s.status_code = 200
    def raise_for_status(s): pass
    def json(s): return s._d
def falso(url, **kw):
    msgs = kw["json"]["messages"]; chamadas.append({"url": url, "n_tools": len(kw["json"].get("tools", [])), "msgs": len(msgs), "sistema_tem_memoria": "MEMÓRIA" in kw["json"]["system"]})
    ultimo = msgs[-1]
    if isinstance(ultimo["content"], str) and "meu cachorro" in ultimo["content"]:
        return R({"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "t1", "name": "guardar_memoria", "input": {"texto": "o cachorro do usuário se chama Thor", "tipo": "fato", "importancia": 4}}]})
    if isinstance(ultimo["content"], str) and "envie" in ultimo["content"]:
        return R({"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "t2", "name": "shell", "input": {"cmd": "rm -rf /"}}, {"type": "tool_use", "id": "t3", "name": "criar_arquivo", "input": {"nome": "a.md", "conteudo": "oi"}}]})
    res = [b for b in ultimo["content"] if b.get("type") == "tool_result"]
    return R({"stop_reason": "end_turn", "content": [{"type": "text", "text": "Anotei. Resultado do corretor: " + " | ".join(str(b["content"])[:60] for b in res)}]})
requests.post = falso
print("1) pedido simples ->", MAIN.processar("meu cachorro se chama Thor"))
print("   memória gravou?", (M.base() / "Memorias").exists() and [p.name for p in (M.base() / "Memorias").glob("*.md")])
print("   chamadas ao modelo:", chamadas)
print("   HIST:", len(C.HIST), "| conversa no diário:", bool(list((M.base() / "Conversas").glob("*.md"))) if (M.base() / "Conversas").exists() else False)
print("2) pergunta seguinte usa a memória?", MAIN.processar("qual o nome do meu cachorro?")); print("   o prompt desta chamada trazia o bloco MEMÓRIA:", chamadas[-1]["sistema_tem_memoria"])
print("3) modelo propõe ferramenta inexistente + ferramenta real ->", MAIN.processar("envie algo perigoso"))
print("   trilha:", [(x.get("ferramenta"), x.get("decisao")) for x in map(json.loads, open(f"{base}/aud.jsonl").read().splitlines()[-4:])])
# sem rede: cai para o modelo local (Ollama inexistente) e responde honestamente
def sem_rede(*a, **k): raise requests.ConnectionError("sem rede")
requests.post = sem_rede
print("4) sem nuvem e sem Ollama ->", MAIN.processar("bom dia, tudo bem?")[:140], "| modo:", MAIN.T.MODO_IA["v"])
print("5) limite diário:", [F for F in [MAIN.F.contar_llm]][0](1), "(contador de chamadas de IA no dia)")
