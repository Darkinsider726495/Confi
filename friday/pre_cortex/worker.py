"""Trabalhador do pré-córtex: um PROCESSO separado que hospeda alguns neurônios e fala HTTP local com o hub.

    python -m friday.pre_cortex.worker --nome cognicao --neuronios percepcao,hipoteses,planejamento [--porta 0] [--host 127.0.0.1]

A chave de sessão vem de PRECORTEX_TOKEN (obrigatória; nunca de argumento de linha de comando, que aparece na lista de processos). A primeira linha do que ele imprime é um JSON
{"worker","pid","porta","url","neuronios"}: o lançador (a demonstração, ou você) lê essa linha para saber onde ele está. A parada é do dono, de fora (Ctrl-C ou o gerenciador de
processos); o trabalhador não tem rota nem comando que o pare.

Este processo NÃO importa o corretor, as tarefas nem o cofre: só neurônios puros e leitores somente-leitura (um teste confere). Os neurônios que precisam deles (`no_hub`) são recusados.
"""
import argparse
import json
import os
import time

from . import catalogo_neuronios as K
from . import transporte as TR


def principal(argv=None):
    ap = argparse.ArgumentParser(prog="python -m friday.pre_cortex.worker", description=__doc__.split("\n")[0])
    ap.add_argument("--nome", required=True)
    ap.add_argument("--neuronios", required=True, help="lista separada por vírgulas")
    ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--host", default="127.0.0.1", help="só 127.0.0.1 por padrão; outro endereço expõe a porta na rede (a chave é a única proteção e o tráfego não é cifrado)")
    ap.add_argument("--max-paralelo", type=int, default=4)
    a = ap.parse_args(argv)
    token = os.environ.get("PRECORTEX_TOKEN", "")
    if len(token) < 16:
        print(json.dumps({"erro": "defina PRECORTEX_TOKEN (pelo menos 16 caracteres) no ambiente"}), flush=True)
        return 2
    nomes = [n.strip() for n in a.neuronios.split(",") if n.strip()]
    instancias = K.novos(nomes)
    achados = {n.nome for n in instancias}
    faltam = [n for n in nomes if n not in achados]
    proibidos = [n.nome for n in instancias if n.no_hub]
    if faltam or proibidos or not instancias:
        print(json.dumps({"erro": "neurônios inválidos", "desconhecidos": faltam, "so_no_hub": proibidos}), flush=True)
        return 2
    w = TR.Worker(a.nome, instancias, max_paralelo=a.max_paralelo)
    extras = ()
    srv = TR.ServidorHTTP(w, token, host=a.host, porta=a.porta, hosts_extras=extras).iniciar()
    print(json.dumps({"worker": a.nome, "pid": os.getpid(), "porta": srv.porta, "url": srv.url, "neuronios": sorted(achados), "host": a.host}), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        srv.parar()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
