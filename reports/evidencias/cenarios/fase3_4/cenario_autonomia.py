"""Roteiro humano das Fases 3 e 4: roda no ambiente de teste (pasta temporária, comandos termux-* falsos) e mostra, cenário por cenário, o que a FRIDAY tentou,
o que esperava, o que viu, o que aprendeu e o que mudou na escolha seguinte. uso: python3 reports/evidencias/cenarios/fase3_4/cenario_autonomia.py  (da raiz do projeto)"""
import json, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import _ambiente as E                      # noqa: E402  (precisa vir antes dos módulos da FRIDAY)
BIN, LOG = E.termux_falso()
os.environ["PATH"] = BIN + os.pathsep + os.environ["PATH"]
os.environ["TERMUX_LOG"] = LOG
from unittest import mock                  # noqa: E402
import broker as B, catalogo, ferramentas as F, tarefas as T                     # noqa: E402,F401
import experiencias as X, objetivos as O, planejador as PL                       # noqa: E402

os.makedirs(os.environ["OBSIDIAN_VAULT"], exist_ok=True)
SEG = "texto-particular-123"
MENTE = lambda nome: mock.patch.dict(B.FERRAMENTAS[nome], {"fn": lambda **kw: "Feito, chefe."})   # a ferramenta diz «feito» e não faz


def titulo(t):
    print(f"\n=== {t} ===")


def ciclo(r):
    for l in r["ciclo"]:
        print("   ", l)
    print(f"  decisão: {r['decisao']} | estado da tarefa: {r['estado']} | {r['mensagem']}")


def xp(tid, v=None):
    x = X.da_tarefa(tid, v)
    print(f"  experiência {x['id']} ({x['estrategia']['id']}): {x['resultado']}{'/' + x['tipo_falha'] if x['tipo_falha'] else ''}; esperado: {x['esperado']}")
    print(f"    observado: {x['observado']}")
    for c in x["causas"]:
        print(f"    [{c['tipo']} {c['confianca']}] {c['texto']}")
    return x


titulo("A. execução simples, com o efeito conferido")
r = PL.executar_objetivo("registrar_informacao", {"texto": SEG + " A"}); ciclo(r); xp(r["tarefa"])

titulo("B. a ferramenta diz «feito» e não fez: a tarefa NÃO pode ser concluída (só uma estratégia permitida, sem alternativa a trocar)")
with MENTE("criar_lembrete"):
    r = PL.executar_objetivo("lembrar_depois", {"texto": SEG + " B", "minutos": 5}); ciclo(r); xp(r["tarefa"])
print("  tarefa concluída?", T.obter(r["tarefa"])["estado"] == T.CONCLUIDA)

titulo("C. a 1ª estratégia falha (falso sucesso), a experiência é registrada e a alternativa equivalente funciona")
X.reiniciar()
with MENTE("guardar_memoria"):
    r = PL.executar_objetivo("registrar_informacao", {"texto": SEG + " C"}); ciclo(r)
xp(r["tarefa"], 1); xp(r["tarefa"], 2)

titulo("E. a experiência muda a escolha seguinte, e a justificativa se confere contra o registro")
r = PL.executar_objetivo("registrar_informacao", {"texto": SEG + " E"}); ciclo(r)
esc = r["tentativas"][0]["escolha"]
print("  ranking:", [(i["id"], i["p"], i["sucessos"], i["falhas"]) for i in esc["ranking"]])
print("  conferir_escolha:", X.conferir_escolha(esc))
adulterada = json.loads(json.dumps(esc)); adulterada["ranking"][1]["falhas"] = 0          # apaga a falha de «guardar_memoria» do ranking
print("  conferir_escolha com um número inventado:", X.conferir_escolha(adulterada)[0], X.conferir_escolha(adulterada)[1])
print("  o que ela sabe:", X.falar())

titulo("F. ação sensível: nunca escolhida sozinha; «sim» não aprova nada")
tipo_sms = {"descricao": "avisar a mãe", "params": {"texto": ("str", 1, 200)}, "obrigatorios": ("texto",), "permite_proprio": True,
            "estrategias": [PL._E(("enviar_sms",), "mandar um SMS", "o SMS sai", "o SMS sai do celular", lambda p: [PL._passo("mandar um SMS", "enviar_sms", {"contato": "mae", "texto": p["texto"]})])], "parciais": []}
antes = E.ler_log(LOG).count("CMD termux-sms-send")
with mock.patch.dict(PL.OBJETIVOS, {"avisar_mae": tipo_sms}):
    r = PL.executar_objetivo("avisar_mae", {"texto": "oi"}); ciclo(r)
    r2 = PL.executar_objetivo("avisar_mae", {"texto": "oi"}, origem="propria", autorizado_por="dono", proposta="o99", nivel_max=3); print("  como objetivo próprio, mesmo aprovado:", r2["decisao"])
print("  SMS enviados:", E.ler_log(LOG).count("CMD termux-sms-send") - antes)

titulo("Propostas dela: duas falhas iguais viram UMA proposta; «sim» não aprova; «aprova o objetivo 1» executa e confere")
O.reiniciar()
print("  (a cena B já deixou 1 falha de «criar_lembrete» e nenhum acerto nas mesmas condições; a segunda falha, pedida por você, fecha o padrão)")
with MENTE("criar_lembrete"):
    t = T.criar("lembrar de uma coisa", passos=[{"descricao": "avisar", "ferramenta": "criar_lembrete", "args": {"minutos": 5, "texto": SEG + " P"}}]); T.executar(t)
print(" ", O.falar())
print("  «sim»  ->", O.tratar("sim"), "| estado:", O.obter("o01")["estado"])
print("  «aprova o objetivo 1»  ->", O.tratar("aprova o objetivo 1"))
p = O.obter("o01"); print("  estado:", p["estado"], "| decidida por:", p["decidida_por"], "| tarefa:", p["resultado"]["tarefa"], "| origem da tarefa:", T.obter(p["resultado"]["tarefa"])["contexto"]["origem"])

titulo("G. privacidade: o conteúdo do dono não aparece nos arquivos de objetivos e experiências nem na auditoria")
base = os.path.join(os.environ["OBSIDIAN_VAULT"], "FRIDAY", ".cerebro")
alvo = [os.path.join(base, n) for n in ("experiencias.jsonl", "objetivos_proprios.json", "objetivos_proprios_historico.jsonl")] + [B.AUDITORIA]
achou = [os.path.basename(a) for a in alvo if os.path.exists(a) and SEG in open(a, encoding="utf-8").read()]
print("  arquivos que contêm o conteúdo:", achou or "nenhum")
