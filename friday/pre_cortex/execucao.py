"""Execução do pré-córtex — SÓ no processo do hub (é aqui, e só aqui, que alguma coisa chega ao corretor).

O pré-córtex nunca executa por conta própria: ele monta `tarefas.criar(...)` com passos que SÓ podem vir de `catalogo_pc.passos` (o catálogo de estratégias do planejador) e
a tarefa chama o corretor, que valida os argumentos, aplica o nível e pede a confirmação presa à ação. Nenhum neurônio importa este módulo, o corretor ou as tarefas.

Ação que não pode repetir (escrever uma nota, mandar uma mensagem) fica protegida por um REGISTRO ANTES DE AGIR no dossiê (gravado em disco antes de a tarefa existir):
  1. `execucoes[chave]` com o hash do plano, a tentativa e as marcas de leitura independente tiradas ANTES da ação;
  2. só então a tarefa é criada e o id dela é gravado no mesmo registro;
  3. só então a tarefa executa.
A chave é «hash-do-plano#tentativa»: a mesma chave nunca cria uma segunda tarefa. Depois de queda ou reinício o hub REANEXA à tarefa que já existe (e deixa `tarefas.recuperar`
olhar o mundo) em vez de executar de novo. Se a queda foi entre (1) e (2), nada chegou ao corretor, então criar a tarefa agora é seguro.
"""
import threading
import time

import experiencias as X
import tarefas as T

from . import catalogo_pc as CAT
from . import leitores as L

FINAIS_TAREFA = (T.CONCLUIDA, T.EXECUTADA_SEM_VERIFICACAO, T.FALHOU, T.PRECISA_INTERVENCAO, T.CANCELADA)


def chave(plano, tentativa):
    return f"{plano['hash']}#{int(tentativa)}"


def derivar_passos(plano, interp):
    """Os passos que o catálogo gera para a estratégia do plano. Levanta ValueError se a estratégia não existe ou faltam dados."""
    par = dict((interp or {}).get("parametros") or {})
    pe = plano.get("parametros_da_estrategia") or {}
    par["texto"], par["titulo"] = pe.get("texto"), pe.get("titulo") or ""
    for k in ("contato", "mensagem"):
        if pe.get(k) is not None:
            par[k] = pe[k]
    return CAT.passos(plano["tipo_objetivo"], plano["estrategia"], par)


def observar(reg):
    """Estado real da tarefa ligada a um registro de execução (lido do módulo de tarefas, não da memória do hub)."""
    tid = reg.get("tarefa")
    if not tid:
        return {"tarefa": None, "estado": None, "final": False, "aguardando_corretor": False, "causa": "", "passos": [], "codigo": "", "experiencia_tarefa": None}
    t = T.obter(tid)
    if t is None:
        return {"tarefa": tid, "estado": None, "final": False, "aguardando_corretor": False, "causa": "a tarefa não existe mais", "passos": [], "codigo": "", "experiencia_tarefa": None}
    passos = [{"id": p["id"], "ferramenta": p["ferramenta"], "estado": p["estado"], "codigo": p.get("codigo") or "", "tamanho": p.get("tam"),
               "verificacao": ({k: p["verificacao"].get(k) for k in ("veredito", "forca", "evidencia")} if p.get("verificacao") else None)} for p in t["passos"]]
    codigo = next((p["codigo"] for p in passos if p["codigo"]), "")
    xp = X.da_tarefa(tid, reg.get("plano_v_tarefa"))
    return {"tarefa": tid, "estado": t["estado"], "rotulo": T.ROTULO.get(t["estado"], t["estado"]), "final": t["estado"] in FINAIS_TAREFA, "aguardando_corretor": t["estado"] == T.BLOQUEADA,
            "causa": t.get("causa") or "", "proxima_acao": t.get("proxima_acao") or "", "passos": passos, "codigo": codigo, "experiencia_tarefa": xp["id"] if xp else None,
            "resultado_tarefa": xp["resultado"] if xp else None}


def registrar_antes(d, plano, passos, tentativa, *, salvar, evento):
    """Passo 1: grava no dossiê, em disco, que esta execução vai acontecer — antes de existir tarefa. Idempotente: a mesma chave devolve o mesmo registro."""
    k = chave(plano, tentativa)
    reg = d["execucoes"].get(k)
    if reg is not None:
        return reg, False
    marcas = {}
    for p in passos:
        marcas[p["ferramenta"]] = L.marcar(p["ferramenta"], p["args"])
    reg = {"chave": k, "plano_hash": plano["hash"], "plano_versao": plano["versao"], "tentativa": int(tentativa), "estado": "registrada", "registrada_em": time.time(),
           "ferramentas": [p["ferramenta"] for p in passos], "marcas": marcas, "tarefa": None, "plano_v_tarefa": None, "iniciada_em": None, "terminada_em": None, "intencao": None}
    d["execucoes"][k] = reg
    salvar()
    evento("execucao_registrada", chave=k, ferramentas=reg["ferramentas"], plano_hash=plano["hash"], tentativa=int(tentativa),
           texto="registrei no dossiê, antes de agir, que esta execução vai acontecer (protege contra repetir depois de uma queda)")
    return reg, True


def criar_tarefa(d, reg, plano, passos, *, origem_tarefa, salvar, evento):
    """Passo 2: cria a tarefa (ainda sem executar) e grava o id dela no registro. Se o registro já tem tarefa, NÃO cria outra."""
    if reg["tarefa"]:
        return reg["tarefa"]
    objetivo = f"{d['descricao'][:200]} [pré-córtex {d['id']} plano v{plano['versao']}]"
    tid = T.criar(objetivo, passos=passos, origem=origem_tarefa)
    t = T.obter(tid)
    reg["tarefa"], reg["plano_v_tarefa"], reg["estado"] = tid, t["plano_v"], "tarefa_criada"
    salvar()
    evento("tarefa_criada", tarefa=tid, texto=f"a tarefa {tid} foi criada para o corretor (ainda não executou)")
    return tid


def gravar_intencao(d, reg, plano, escolha):
    """Antes de agir, a expectativa fica gravada no módulo de experiências (mesma tabela do planejador), marcada com a origem «precortex»."""
    tid = reg["tarefa"]
    try:
        esc = plano.get("escolha") or {}
        ranking = esc.get("ranking") or []
        prev = (plano.get("previsao") or {}).get("texto") or plano.get("resultado_esperado") or ""
        hip = next((h for h in (escolha or []) if h.get("id") == plano.get("hipotese_testada")), None)
        X.intencao(tid, reg["plano_v_tarefa"], tipo=plano["tipo_objetivo"], estrategia=plano["estrategia"], descricao=f"pré-córtex {d['id']} plano v{plano['versao']}",
                   hipotese=(hip or {}).get("texto") or f"«{plano['estrategia']}» cumpre o objetivo por inteiro", esperado=prev,
                   alternativas=[r["id"] for r in ranking if r["id"] != plano["estrategia"]], condicoes=esc.get("condicoes"), escolha=None, origem="precortex")
        reg["intencao"] = True
        return True
    except Exception as e:
        reg["intencao"] = f"não gravada: {type(e).__name__}"
        return False


def executar_em_segundo_plano(reg, *, evento):
    """Passo 3: executa a tarefa numa linha própria (o corretor pode demorar). Devolve a linha; quem chama espera com `join(timeout)` e depois consulta `observar`."""
    tid = reg["tarefa"]
    reg["iniciada_em"], reg["estado"] = time.time(), "executando"
    evento("execucao_iniciada", tarefa=tid, texto=f"a tarefa {tid} foi entregue ao corretor")

    def corre():
        try:
            T.executar(tid)
        except Exception as e:                                      # a tarefa já guarda o estado; aqui só não deixamos a linha morrer calada
            evento("execucao_erro", tarefa=tid, erro=f"{type(e).__name__}: {str(e)[:160]}")

    th = threading.Thread(target=corre, name=f"pc-exec-{tid}", daemon=True)
    th.start()
    return th


def recuperar(reg):
    """Depois de queda/reinício: deixa o módulo de tarefas olhar o mundo (nunca repete) e devolve o que ele achou."""
    tid = reg.get("tarefa")
    if not tid:
        return None
    r = T.recuperar(tid)
    c = T.confirmacao_perdida(tid)
    return {"recuperacao": r, "confirmacao_perdida": c}


def cancelar_tarefa(reg, motivo):
    tid = reg.get("tarefa")
    if not tid:
        return False
    try:
        T.cancelar(tid, motivo)
        return True
    except Exception:
        return False
