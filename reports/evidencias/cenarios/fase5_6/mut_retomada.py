"""Mutação das defesas da Fase 6 (retomada + recuperar/confirmacao_perdida em tarefas + ligação no main). Uso (da pasta fase3_4):
   python3 mutar.py ../fase5_6/mut_retomada.py <raiz do projeto>
Cada mutante vai numa CÓPIA do projeto; a suíte indicada TEM de falhar. Antes, a mesma suíte roda SEM mutação e tem de passar (linha de base)."""
RE, TA, MA, CO = "friday/retomada.py", "friday/tarefas.py", "friday/main.py", "friday/coordenador.py"
TR = ["test_retomada", "test_tarefas_integracao"]
TC = ["test_retomada", "test_coordenador"]
MUTANTES = [
 # --- tarefas.recuperar: o que fazer com um passo que estava executando
 ("recuperar: não confere o mundo (assume dúvida)", TA, "            ver = _conferir_de_novo(t, p)\n            if ver and ver[\"veredito\"] == V.CONFIRMADO:\n                p[\"estado\"], p[\"verificacao\"] = \"verificado\", ver\n                achados.append",
  "            ver = None\n            if ver and ver[\"veredito\"] == V.CONFIRMADO:\n                p[\"estado\"], p[\"verificacao\"] = \"verificado\", ver\n                achados.append", TR),
 ("recuperar: o que não dá para conferir é repetido", TA, "                p[\"estado\"], p[\"codigo\"] = \"intervencao\", \"interrompido\"\n                duvida.append(p[\"id\"])",
  "                p[\"estado\"], p[\"verificacao\"] = \"pendente\", None\n                ausentes.append(p[\"id\"])", TR),
 ("recuperar: sem limite de quedas (laço de queda)", TA, "                if p[\"tentativas\"] >= MAX_QUEDAS:", "                if False:", TR),
 ("recuperar: leitura pura não é repetida", TA, " or V.classe(p[\"ferramenta\"]) == \"leitura\":", ":", TR),
 ("recuperar: mexe em tarefa que este processo executa", TA, "        if t is None or ATIVAS.get(tid) or t[\"estado\"] not in (EXECUTANDO, VERIFICANDO):\n            return None\n        achados", "        if t is None or t[\"estado\"] not in (EXECUTANDO, VERIFICANDO):\n            return None\n        achados", TR),
 ("recuperar: age em tarefa em qualquer estado", TA, "        if t is None or ATIVAS.get(tid) or t[\"estado\"] not in (EXECUTANDO, VERIFICANDO):\n            return None\n        achados", "        if t is None or ATIVAS.get(tid):\n            return None\n        achados", TR),
 ("recuperar: não resolve o estado da tarefa", TA, "        _resolver(t)\n        _historico({\"tarefa\": tid, \"recuperada\"", "        _historico({\"tarefa\": tid, \"recuperada\"", TR),
 ("recuperar: não avisa quem escuta o fim das tarefas", TA, "    _despachar()\n    return saida", "    return saida", TR),
 ("recuperar: dúvida não deixa a causa escrita", TA, "            t[\"causa\"] = f\"o programa parou durante o passo {', '.join(duvida)} e não dá para conferir daqui se a ação aconteceu; por segurança não repeti\"", "            t[\"causa\"] = \"\"", TR),
 ("confirmação perdida: mexe na confirmação que ainda está viva", TA, "        if atual and any(p[\"pendencia\"] == atual.get(\"id\") for p in esperando):\n            return False\n", "", TR),
 ("confirmação perdida: não é tratada (tarefa fica bloqueada para sempre)", TA, "        for p in esperando:\n            p[\"estado\"] = \"intervencao\"\n        t[\"causa\"] = \"a confirmação", "        t[\"causa\"] = \"a confirmação", TR),
 ("confirmar_manual: o dono não consegue dizer que o passo interrompido aconteceu", TA, " or (p[\"estado\"] == \"intervencao\" and p.get(\"codigo\") == \"interrompido\"))", ")", TR),
 # --- retomada: o que é seguro retomar
 ("retomada: pedido da conversa (ia) é retomado sozinho", RE, 'ORIGENS_RETOMAVEIS = ("usuario", "meta", "propria")', 'ORIGENS_RETOMAVEIS = ("usuario", "meta", "propria", "ia")', TR),
 ("retomada: idade da tarefa ignorada", RE, "    if parada > idade_max_s:", "    if False:", TR),
 ("retomada: argumentos que não ficaram guardados não barram", RE, "        if T.argumentos_guardados(t[\"id\"], p[\"id\"]) is None:", "        if False:", TR),
 ("retomada: camada 1 deixa passar nível ≥ 2 (a 2ª, do coordenador, ainda barra)", RE, "        if nivel >= 2:\n            return False", "        if False:\n            return False", TR),
 ("[redundante] retomada: nível ilegível tratado como seguro só na camada 1 (o coordenador ainda barra)", RE, "else 2          # nível ilegível = sensível", "else 0          # nível ilegível = sensível", TR),
 ("retomada: nível ilegível passa nas duas camadas (elegibilidade e coordenador)", RE, ["else 2          # nível ilegível = sensível", "            props.append(CO.proposta_de_tarefa(t, agora=agora))"],
  ["else 0          # nível ilegível = sensível", "            props.append({**CO.proposta_de_tarefa(t, agora=agora), \"precisa_dono\": False})"], TR),
 ("retomada: o coordenador não decide (executa tudo na ordem)", RE, "        for d in CO.avaliar(props, concluidas=concluidas, agora=agora):", "        for d in [{\"id\": p[\"id\"], \"decisao\": \"executar_agora\", \"motivo\": \"\"} for p in props]:", TR),
 ("retomada: uma rodada só (dependência não chega a rodar)", RE, "MAX_RODADAS = 4 ", "MAX_RODADAS = 1 ", TR),
 ("retomada: BLOQUEADA esperando confirmação viva é tratada como candidata", RE, "    return t[\"estado\"] == T.BLOQUEADA and not any(p[\"estado\"] == \"aguardando\" for p in t[\"passos\"])", "    return t[\"estado\"] == T.BLOQUEADA", TR),
 ("retomada: mexe em tarefa PRONTA que este processo está executando entre dois passos", RE, "            if tid in feitas or T.ATIVAS.get(tid) or (t[\"estado\"] == T.BLOQUEADA and not _so_depende(t)):", "            if tid in feitas or (t[\"estado\"] == T.BLOQUEADA and not _so_depende(t)):", TR),
 ("[redundante] retomada: recupera tarefa que este processo executa (tarefas.recuperar também barra)", RE, "        if T.ATIVAS.get(tid):\n            continue                                     # este processo", "        if False:\n            continue                                     # este processo", TR),
 ("retomada: erro ao executar fica escondido", RE, "    except Exception as e:\n        _erro(e)\n        itens.append(_item(tid, \"pediu_dono\", f\"erro inesperado", "    except Exception as e:\n        itens.append(_item(tid, \"pediu_dono\", f\"erro inesperado", TR),
 ("retomada: duas rodadas ao mesmo tempo", RE, "    if not _trava.acquire(blocking=False):", "    if False:", TR),
 ("retomada: o registro leva o objetivo das tarefas", RE, "f.write(json.dumps({\"em\": rel[\"em\"], \"itens\": rel[\"itens\"], \"resumo\": rel[\"resumo\"]}, ensure_ascii=False) + \"\\n\")", "f.write(json.dumps({\"em\": rel[\"em\"], \"itens\": rel[\"itens\"], \"resumo\": rel[\"resumo\"], \"o\": [t[\"objetivo\"] for t in T.listar()]}, ensure_ascii=False) + \"\\n\")", TR),
 ("retomada: perguntar o que ficou interrompido também retoma", RE, "    if f in _PERG:\n        n = interrompidas()", "    if f in _PERG:\n        retomar_pendentes()\n        n = interrompidas()", TR),
 ("retomada: ao ligar fala mesmo sem nada a contar", RE, "        if falar_fn and (rel[\"resumo\"][\"retomou\"] or rel[\"resumo\"][\"conferiu\"] or rel[\"resumo\"][\"pediu_dono\"]):", "        if falar_fn:", TR),
 ("retomada: ao ligar uma exceção derruba o programa", RE, "    except Exception as e:\n        _erro(e)\n        return None\n\n\n_RETOMAR", "    except ZeroDivisionError as e:\n        _erro(e)\n        return None\n\n\n_RETOMAR", TR),
 ("retomada: rodada vazia escreve no registro", RE, "    if not rel[\"itens\"] or not M.ativo():", "    if not M.ativo():", TR),
 ("retomada: falar não aguenta um relatório vazio", RE, "    if not rel:\n        return \"Não achei nada interrompido", "    if False:\n        return \"Não achei nada interrompido", TR),
 # --- ligação no programa
 ("main: a voz não chega na retomada", MA, "            r = RET.tratar(t)  #", "            r = None  #", TR),
 ("main: ao ligar não reconcilia os objetivos", MA, "    try:\n        OBJ.conciliar()\n    except Exception as e:\n        print(\"objetivos", "    try:\n        pass\n    except Exception as e:\n        print(\"objetivos", TR),
 ("main: o painel não mostra a retomada", MA, ", \"retomada\": RET.resumo()}", "}", TR),
 # --- coordenador usado pela retomada
 ("coordenador: nível ilegível passa por baixo", CO, "else 2 for p in faltam]", "else 0 for p in faltam]", TC),
]
