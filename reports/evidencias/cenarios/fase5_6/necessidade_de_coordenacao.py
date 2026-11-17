"""Evidência da NECESSIDADE e do EFEITO da coordenação (a missão pede provar antes de criar).
Registra uma ferramenta de teste lenta (nível 1) e roda duas tarefas em threads pelo caminho normal (tarefas → corretor). Mede quantas ficam dentro da ferramenta juntas.

  python3 reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py            # ANTES: sem coordenador (pico de 2 no mesmo recurso = se pisam)
  python3 reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py --depois   # DEPOIS: com o coordenador ligado (pico de 1 no mesmo recurso; 2 em recursos diferentes)
(da raiz do projeto; usa o ambiente temporário dos testes, não toca no cofre real)"""
import os, sys, threading, time
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import _ambiente as E                      # noqa: E402
import broker as B, catalogo, tarefas as T  # noqa: E402,F401
os.makedirs(os.environ["OBSIDIAN_VAULT"], exist_ok=True)
DEPOIS = "--depois" in sys.argv
if DEPOIS:
    import coordenador as CO               # noqa: E402  (ao importar, liga T.RESERVAS)
    CO.RECURSOS["recurso_unico_demo"] = lambda a: [("rele:" + a["nome"], "excl")]

dentro, pico, trava = [0], [0], threading.Lock()


def lenta(**kw):
    with trava:
        dentro[0] += 1
        pico[0] = max(pico[0], dentro[0])
    time.sleep(0.3)
    with trava:
        dentro[0] -= 1
    return "Feito."


B.registrar("recurso_unico_demo", "demonstração: mexe em UM recurso físico", {"nome": {"type": "string", "maxLength": 20}}, ["nome"], lenta, 1)


def rodar(titulo, nomes):
    dentro[0] = pico[0] = 0
    tids = [T.criar(f"pedido {i}", passos=[{"descricao": "usar o recurso", "ferramenta": "recurso_unico_demo", "args": {"nome": n}}]) for i, n in enumerate(nomes)]
    ts = [threading.Thread(target=T.executar, args=(t,)) for t in tids]
    [t.start() for t in ts]
    [t.join() for t in ts]
    print(f"{titulo}: pico de {pico[0]} dentro da ferramenta (1 = uma esperou a outra; 2 = ao mesmo tempo)")
    print("   estados:", [T.obter(t)["estado"] for t in tids])


print("MODO:", "DEPOIS (coordenador ligado)" if DEPOIS else "ANTES (sem coordenador)")
rodar("duas tarefas, MESMO recurso, ao mesmo tempo", ["rele1", "rele1"])
if DEPOIS:
    rodar("duas tarefas, recursos DIFERENTES, ao mesmo tempo", ["rele1", "rele2"])
    print("reservas que sobraram:", CO.ocupados())
