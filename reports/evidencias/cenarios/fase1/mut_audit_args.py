T = ["test_auditoria_privada", "test_argumentos"]
B, P = "friday/broker.py", "friday/privacidade.py"
MUTANTES = [
 # 1.4 privacidade da trilha
 ("trilha deixa de passar pela redação final", B, "ev = {k: (P.redigir(v, 500) if isinstance(v, str) and k not in _CONTROLE else v) for k, v in ev.items()}", "ev = dict(ev)", T),
 ("resultado volta a ir em claro", B, "resultado=codigo, tam=len(r)", "resultado=r[:300], tam=len(r)", T),
 ("mensagem da exceção volta para a trilha", B, "codigo = f\"Erro: {erro}\" if erro", "codigo = r if erro", T),
 ("erro devolvido pela ferramenta vira ok", B, "(\"Erro\" if r.startswith(\"Erro\") else \"ok\")", "\"ok\"", T),
 ("argumentos de texto voltam em claro", P, "saida[k] = f\"‹texto: {len(v)} caracteres›\"", "saida[k] = v", T),
 ("link volta inteiro", P, "saida[k] = so_servidor(v)", "saida[k] = v", T),
 ("identificador declarado sem redação", P, "saida[k] = redigir(v, 40)", "saida[k] = v", T),
 ("pendência grava os argumentos crus", B, "args=P.resumir_args(args, f.get(\"audit_args\", ())), nivel=n, decisao=\"pendente\")", "args=json.dumps(args, ensure_ascii=False)[:500], nivel=n, decisao=\"pendente\")", T),
 ("redação deixa passar CPF", P, "    t = _CPF.sub(\"‹cpf›\", t)\n", "", T),
 ("redação deixa passar e-mail", P, "    t = _EMAIL.sub(\"‹email›\", t)\n", "", T),
 ("redação deixa passar telefone", P, "    t = _TEL_BR.sub(\"‹telefone›\", t)\n", "", T),
 ("redação deixa passar «senha é»", P, "    t = _SEGREDO_COM_ROTULO.sub(lambda m: f\"{m.group(1)}{m.group(2)}{m.group(3)} {OCULTO}\", t)\n", "", T),
 ("redação deixa passar chaves", P, "    for p in _TOKENS:\n        t = p.sub(\"‹token›\", t)\n", "", T),
 ("redação deixa passar link com chave", P, "    t = _URL.sub(lambda m: so_servidor(m.group(0)), t)\n", "", T),
 # 1.5 argumentos
 ("fora da faixa volta a ser ajustado em silêncio", B, "                    raise PedidoInvalido(f\"{k} deve {faixa} (recebi {_fmt(v)})\", f\"faixa:{k}\")", "                    saida[k] = novo", T),
 ("NaN/infinito passam", B, "if not math.isfinite(v):", "if False:", T),
 ("ajuste sem aviso", B, "return r + _aviso_ajustes(ajustes)", "return r", T),
 ("ajuste sem registro na trilha", B, "extra = {\"ajustes\": sorted(ajustes)} if ajustes else {}", "extra = {}", T),
 ("maxLength ignorado", B, "if len(v) > esq.get(\"maxLength\", 1000):", "if len(v) > 10 ** 9:", T),
 ("enum ignorado", B, "if \"enum\" in esq and v not in esq[\"enum\"]:", "if False:", T),
 ("recusa grava o texto da mensagem", B, "resultado=getattr(e, \"codigo\", \"invalido\"))", "resultado=str(e))", T),
 ("esquema público vaza ao_exceder", B, "if v.pop(\"ao_exceder\", None) == \"limitar\":", "if v.get(\"ao_exceder\") == \"limitar\":", T),
 ("pendência perde o ajuste", B, "ajustes=p.get(\"ajustes\"))\n\n\ndef confirmar_botao", "ajustes=None)\n\n\ndef confirmar_botao", T),
]
