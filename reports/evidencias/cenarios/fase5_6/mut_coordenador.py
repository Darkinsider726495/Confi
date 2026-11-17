"""Mutação das defesas da Fase 5 (coordenador + reserva em tarefas). Uso (da pasta fase3_4):
   python3 mutar.py ../fase5_6/mut_coordenador.py <raiz do projeto>
Cada mutante vai numa CÓPIA do projeto; a suíte indicada TEM de falhar."""
CO, TA = "friday/coordenador.py", "friday/tarefas.py"
TC = ["test_coordenador", "test_tarefas_integracao"]
S = '                d.update(decisao="esperar", motivo=f"usa o mesmo recurso ({choque[0].split(\':\')[0]}) que {choque[1]}, que vem antes (nota maior)")'
MUTANTES = [
 # --- reserva
 ("reserva: exclusivo não conflita", CO, '    return a[0] == b[0] and "excl" in (a[1], b[1])', "    return False", TC),
 ("reserva: compartilhado também conflita (serializa o que se soma)", CO, '    return a[0] == b[0] and "excl" in (a[1], b[1])', "    return a[0] == b[0]", TC),
 ("reserva: conflito compara só o tipo (relé 1 trava relé 2)", CO, '    return a[0] == b[0] and "excl" in (a[1], b[1])', '    return a[0].split(":")[0] == b[0].split(":")[0] and "excl" in (a[1], b[1])', TC),
 ("reserva: o dono conflita com ele mesmo", CO, "            if outro == dono:\n                continue\n", "", TC),
 ("reserva: conflito não é detectado", CO, '                        return False, {"recurso": q[0], "dono": outro, "ferramenta": r["ferramenta"]}', "                        pass", TC),
 ("reserva: o perdedor fica com a reserva mesmo assim", CO, "    quer = recursos_de(ferramenta, args)\n    with _trava:", "    quer = recursos_de(ferramenta, args)\n    with _trava:\n        _reservas[dono] = {\"ferramenta\": ferramenta, \"recursos\": quer, \"desde\": _agora()}", TC),
 ("reserva: nome comparado com acento e caixa", CO, '    s = " ".join(M._fold(v).split())[:60] if isinstance(v, str) else ""', '    s = v[:60] if isinstance(v, str) else ""', TC),
 ("reserva: regra que quebra deixa o recurso livre", CO, '        return [(f"{ferramenta}:?", "excl")]', "        return []", TC),
 ("reserva: ligar não usa a linha telefônica", CO, '    "ligar": lambda a: _um("contato", "contato")(a) + [("linha_telefonica", "excl")],', '    "ligar": lambda a: _um("contato", "contato")(a),', TC),
 ("reserva: ferramenta de nível ≥ 1 sem declaração passa batida (anotar)", CO, '    "anotar": "cada nota é uma linha nova; duas juntas são duas notas",\n', "", TC),
 ("reserva: o coordenador não se liga ao importar", CO, "\n\n_ligar()\n", "\n", TC),
 # --- ligação em tarefas.py
 ("tarefas: não reserva antes de executar", TA, "        reservar = RESERVAS[\"reservar\"]\n        if reservar:", "        reservar = None\n        if reservar:", TC),
 ("tarefas: executa mesmo com o recurso ocupado", TA, "                return {\"ocupado\": quem}", "                pass", TC),
 ("tarefas: não libera ao terminar", TA, "    liberar = RESERVAS[\"liberar\"]\n    if liberar:\n        liberar(tid)", "    pass", TC),
 ("tarefas: não libera se a preparação falha", TA, "        except BaseException:                             # falhou depois de reservar (ex.: ao gravar): a reserva não pode ficar presa\n            _liberar_reserva(tid)\n            raise", "        except BaseException:\n            raise", TC),
 ("tarefas: espera para sempre pelo recurso (sem limite)", TA, "        if time.monotonic() >= limite:", "        if False:", TC),
 ("tarefas: ao desistir da espera não diz por quê", TA, "                    \"motivo\": f\"o recurso «{quem['recurso'].split(':')[0]}» está em uso por {quem['dono']}\"}", "                    \"motivo\": \"\"}", TC),
 ("tarefas: a tarefa esperando não registra a próxima ação", TA, "                t[\"proxima_acao\"] = f\"esperar o recurso «{quem['recurso'].split(':')[0]}», em uso por {quem['dono']}\"\n", "", TC),
 # --- avaliação
 ("avaliar: o que exige o dono sai por nota alta", CO, '        elif p.get("precisa_dono"):', "        elif False:", TC),
 ("avaliar: dependência ignorada", CO, "            if falta:\n", "            if False:\n", TC),
 ("avaliar: recurso em uso ignorado", CO, "            elif ocupado:\n", "            elif False:\n", TC),
 ("avaliar: conflito entre propostas ignorado", CO, "            elif choque:\n", "            elif False:\n", TC),
 ("avaliar: serializa o que não conflita", CO, '            choque = next(((q[0], u[2]) for q in quer for u in usados if u[2] != i["id"] and _conflita(q, (u[0], u[1]))), None)', '            choque = next(((q[0], u[2]) for q in quer for u in usados if u[2] != i["id"]), None)', TC),
 ("avaliar: quem espera segura o recurso dos outros", CO, S, S + '\n                usados += [(r, m, i["id"]) for r, m in quer]', TC),
 ("avaliar: ordem invertida", CO, '    itens.sort(key=lambda i: (-i["nota"], i["id"]))', '    itens.sort(key=lambda i: (i["nota"], i["id"]))', TC),
 ("avaliar: empate depende da ordem de entrada", CO, '    itens.sort(key=lambda i: (-i["nota"], i["id"]))', '    itens.sort(key=lambda i: -i["nota"])', TC),
 ("avaliar: booleano vira número", CO, "        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:", "        if not isinstance(v, (int, float)) or v != v:", TC),
 ("avaliar: NaN aceito", CO, "        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:", "        if isinstance(v, bool) or not isinstance(v, (int, float)):", TC),
 ("avaliar: componente fora da faixa não é limitado", CO, "    return max(0.0, min(1.0, float(x)))", "    return float(x)", TC),
 ("avaliar: peso do risco com sinal trocado", CO, '"risco": -0.15', '"risco": 0.15', TC),
 ("avaliar: proposta malformada é avaliada", CO, "        c = _componentes(p) if isinstance(p, dict) else None", "        c = (_componentes(p) or {k: 0.0 for k in PESOS}) if isinstance(p, dict) else None", TC),
 # --- proposta de tarefa
 ("proposta: nível 2 não pede o dono", CO, '"precisa_dono": nivel >= 2,', '"precisa_dono": nivel >= 3,', TC),
 ("proposta: argumento ausente deixa o recurso livre", CO, "recursos_de(p[\"ferramenta\"], args) if args is not None else [(f\"{p['ferramenta']}:?\", \"excl\")]", "recursos_de(p[\"ferramenta\"], args) if args is not None else []", TC),
 ("proposta: objetivo dela pesa igual ao pedido do dono", CO, 'RELEVANCIA_POR_ORIGEM = {"usuario": 1.0, "meta": 0.8, "ia": 0.6, "propria": 0.3}', 'RELEVANCIA_POR_ORIGEM = {"usuario": 1.0, "meta": 0.8, "ia": 0.6, "propria": 1.0}', TC),
 # --- registro
 ("registro: o nome do recurso vai em claro", CO, '    return f"{tipo}:{hashlib.sha256(nome.encode()).hexdigest()[:6]}" if nome else tipo', "    return str(recurso)", TC),
 ("registro: a decisão não é gravada", CO, '        with open(arq, "a", encoding="utf-8") as f:\n            f.write(json.dumps(reg, ensure_ascii=False) + "\\n")', "        pass", TC),
 ("registro: linha estragada derruba a leitura", CO, "        except ValueError:\n            continue\n        if isinstance(x, dict) and x.get(\"decisao\") in DECISOES:", "        except ValueError:\n            raise\n        if isinstance(x, dict) and x.get(\"decisao\") in DECISOES:", TC),
]
