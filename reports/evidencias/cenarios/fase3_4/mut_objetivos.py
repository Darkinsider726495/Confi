TO = ["test_objetivos", "test_experiencias"]
OB, XP = "friday/objetivos.py", "friday/experiencias.py"
MUTANTES = [
 # --- propor: o que uma proposta precisa para existir
 ("propor: tipo que o catálogo não permite como próprio", OB, '''    if not obj or not obj["permite_proprio"]:
        return False,''', '''    if not obj:
        return False,''', TO),
 ("propor: conteúdo sensível passa", OB, '''    if any(isinstance(v, str) and M.sensivel(v) for v in limpos.values()):
        return False, "o conteúdo parece sensível"''', '''    if False:
        return False, "o conteúdo parece sensível"''', TO),
 ("propor: evidência que não existe passa", OB, "    if any(r is None for r in reais):", "    if False:", TO),
 ("propor: sem nenhuma evidência passa", OB, "not 1 <= len(evidencias) <= 10", "not 0 <= len(evidencias) <= 10", TO),
 ("propor: vínculo com tarefa que ela mesma criou passa", OB, '''t["contexto"]["origem"] not in ("usuario", "meta", "ia"):''', '''t["contexto"]["origem"] not in ("usuario", "meta", "ia", "propria"):''', TO),
 ("propor: sem justificativa passa", OB, "    if not isinstance(justificativa, str) or not justificativa.strip():", "    if False:", TO),
 ("propor: duas propostas abertas sobre o mesmo assunto", OB, "        if any(p[\"estado\"] in ABERTAS for p in mesmas):", "        if False:", TO),
 ("propor: o que o dono recusou volta", OB, "        if any(p[\"estado\"] == \"cancelado\" for p in mesmas):", "        if False:", TO),
 ("propor: repete a proposta sem nada de novo", OB, "falhas_na_epoca < p[\"falhas_na_epoca\"] + 2", "falhas_na_epoca < p[\"falhas_na_epoca\"] + 0", TO),
 ("propor: sem limite de propostas esperando o dono", OB, ">= MAX_ABERTAS:", ">= MAX_ABERTAS + 100:", TO),
 ("padrão: um caso só já vira proposta", OB, "MIN_OBSERVACOES = 2 ", "MIN_OBSERVACOES = 1 ", TO),
 ("padrão: com um acerto ainda propõe", OB, 'if g["sucessos"] or g["falhas"] < MIN_OBSERVACOES:', 'if g["falhas"] < MIN_OBSERVACOES:', TO),
 # defesa em camadas: o que é dela não serve de base (1) no filtro do padrão e (2) na validação do vínculo em propor(); só quebrando as duas aparece
 ("padrão: o que ela fez por conta própria alimenta propostas (filtro do padrão + vínculo)", OB,
  ['''.get("origem") in ("usuario", "meta", "ia")]
        if not donas:''', '''t["contexto"]["origem"] not in ("usuario", "meta", "ia"):'''],
  ['''.get("origem") is not None]
        if not donas:''', '''t["contexto"]["origem"] not in ("usuario", "meta", "ia", "propria"):'''], TO),
 ("padrão: o que ela fez por conta própria alimenta propostas (só o filtro do padrão; coberto pela camada seguinte)", OB, '''.get("origem") in ("usuario", "meta", "ia")]
        if not donas:''', '''.get("origem") is not None]
        if not donas:''', TO),
 # --- aprovar: só o dono, só a frase explícita
 ("aprovar: qualquer estado pode ser aprovado", OB, '''        if p["estado"] != "proposto":
            return False, f"esse objetivo está''', '''        if False:
            return False, f"esse objetivo está''', TO),
 ("aprovar: o planejador não recebe a autorização do dono", OB, 'proposta=oid, nivel_max=lim["nivel_max"]', 'proposta=oid, nivel_max=lim["nivel_max"]', TO),  # placeholder trocado abaixo
 ("aprovar: nível máximo da proposta ignorado", OB, 'nivel_max=lim["nivel_max"], max_tentativas=lim["max_tentativas"]', 'nivel_max=3, max_tentativas=lim["max_tentativas"]', TO),
 ("aprovar: limite de tentativas da proposta ignorado", OB, 'max_tentativas=lim["max_tentativas"], turno=turno)', 'max_tentativas=6, turno=turno)', TO),
 ("aprovar: o dono não fica registrado como quem decidiu", OB, '_mudar(p, "executando", "aprovado pelo dono", por="dono")', '_mudar(p, "executando", "aprovado pelo dono")', TO),
 ("aprovar: falha vira concluída", OB, 'novo = "concluido" if r["decisao"] == "concluir" else "esperando" if r["decisao"] == "esperar_dono" else "falhou"', 'novo = "concluido"', TO),
 ("aprovar: cancelamento no meio da execução é ignorado", OB, '        if p["estado"] == "cancelado":                                   # o dono cancelou no meio', '        if False:                                   # o dono cancelou no meio', TO),
 ("aprovar: a conciliação mexe na proposta que está sendo executada", OB, "        _EM_EXECUCAO.add(oid)\n", "", TO),
 ("voz: frase solta no meio do texto aprova", OB, "        m = rx.fullmatch(f)", "        m = rx.search(f)", TO),
 ("voz: erro na execução fica escondido", OB, '''                _ERROS["n"] += 1
                _ERROS["ultimo"] = f"{type(e).__name__}: {e}"[:200]
                conciliar()''', '''                conciliar()''', TO),
 ("gancho: erro ao propor fica escondido", OB, '''        _ERROS["n"] += 1
        _ERROS["ultimo"] = f"{type(e).__name__}: {e}"[:200]


def _registrar_gancho''', '''        pass


def _registrar_gancho''', TO),
 # --- cancelar / conciliar
 ("cancelar: cancela também tarefa de outra origem", OB, 'achadas = [t for t in T.listar() if t["contexto"]["origem"] == "propria" and marca in t["contexto"]["restricoes"]]', 'achadas = [t for t in T.listar() if marca in t["contexto"]["restricoes"]]', TO),
 ("cancelar: a tarefa da proposta continua rodando", OB, '    if t and t["estado"] not in T.FINAIS:                      # só a tarefa', '    if False:                      # só a tarefa', TO),
 ("conciliar: proposta sem tarefa fica presa em «executando»", OB, '''novo, motivo = ("proposto", "reinício antes de começar: nada foi feito, volta a esperar o dono") if vivo["estado"] == "executando" else (None, "")''', '''novo, motivo = (None, "")''', TO),
 ("conciliar: tarefa concluída não conclui a proposta", OB, 'T.CONCLUIDA: ("concluido", "a tarefa terminou com o efeito conferido")', 'T.CONCLUIDA: ("esperando", "a tarefa terminou com o efeito conferido")', TO),
 ("conciliar: sem conferência conclui a proposta", OB, 'T.EXECUTADA_SEM_VERIFICACAO: ("esperando",', 'T.EXECUTADA_SEM_VERIFICACAO: ("concluido",', TO),
 # --- arquivo adulterado
 ("ler: o limite vem do arquivo", OB, '"limites": dict(LIMITES),', '"limites": x.get("limites") or dict(LIMITES),', TO),
 ("ler: conteúdo sensível no arquivo é aceito", OB, "    if erro or any(isinstance(v, str) and M.sensivel(v) for v in params.values()):", "    if erro:", TO),
 ("ler: tipo não permitido no arquivo é aceito", OB, '''    if not obj or not obj["permite_proprio"]:
        return None''', '''    if not obj:
        return None''', TO),
 ("ler: proposta sem evidência no arquivo é aceita", OB, "    if not evid:\n        return None", "    if False:\n        return None", TO),
 ("ler: quem decidiu pode ser qualquer um", OB, '"decidida_por": "dono" if x.get("decidida_por") == "dono" else None', '"decidida_por": x.get("decidida_por")', TO),
 ("ler: estado desconhecido vira «proposto» (aprovável)", OB, 'x["estado"] if x.get("estado") in ESTADOS else "pausado"', 'x["estado"] if x.get("estado") in ESTADOS else "proposto"', TO),
 # --- experiencias.padroes
 ("padroes: recusa do corretor conta como falha", XP, '''if x["resultado"] == SUCESSO or (x["resultado"] == FALHA and x["tipo_falha"] in ("erro", "falso_sucesso")):
            g = grupos''', '''if x["resultado"] in (SUCESSO, FALHA):
            g = grupos''', TO),
 ("padroes: condições diferentes se somam", XP, 'grupos.setdefault((x["estrategia"]["id"], tuple(sorted(x["condicoes"].items()))),', 'grupos.setdefault((x["estrategia"]["id"],),', TO),
 ("padroes: o mais falhado não vem primeiro", XP, "saida.sort(key=lambda g: (-g[\"falhas\"], g[\"estrategia\"]))", "saida.sort(key=lambda g: (g[\"falhas\"], g[\"estrategia\"]))", TO),
 ("padroes: mínimo ignorado", XP, 'if g["sucessos"] + g["falhas"] >= minimo]', 'if g["sucessos"] + g["falhas"] >= 1]', TO),
]
# o mutante «sem a autorização do dono» é do planejador (já coberto em test_planejador); aqui o equivalente é a aprovação que não passa autorizado_por:
MUTANTES = [m for m in MUTANTES if not m[0].startswith("aprovar: o planejador não recebe")] + [
 ("aprovar: o planejador não recebe a autorização do dono", OB, 'origem="propria", autorizado_por="dono", proposta=oid', 'origem="propria", autorizado_por=None, proposta=oid', TO)]
