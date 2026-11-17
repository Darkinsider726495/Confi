T = ["test_prefrontal_progresso"]
PF, CU = "friday/prefrontal.py", "friday/curiosidade.py"
MUTANTES = [
 ("parecido passa a concluir a meta", PF, "return 1.0 if _evidencia(m, q) else 0.0", "return 1.0 if (_evidencia(m, q) or _candidatos(m, q)) else 0.0", T),
 ("candidato passa a contar como «assunto ligado»", PF, "        if chave_tema(ligado) in estudados:", "        if True:", T),
 ("candidato zera o contador de empacada", PF, "        m[\"candidatos\"] = _candidatos(m, q)\n", "        m[\"candidatos\"] = _candidatos(m, q)\n        if m[\"candidatos\"]:\n            m[\"sem_avanco\"] = 0\n", T),
 ("crédito por id vale para qualquer meta", PF, "    feitos = q.get(\"estudos_por_meta\", {}).get(m[\"id\"], [])", "    feitos = [x for v in q.get(\"estudos_por_meta\", {}).values() for x in v]", T),
 ("observar credita estudo que não aconteceu (n=0)", PF, "            if v.get(\"n\", 0) > 0:\n                for mid in v.get(\"m\", []):", "            if True:\n                for mid in v.get(\"m\", []):", T),
 ("chave ignora a palavra a mais (prefixo)", PF, "    return \" \".join(toks) if toks else", "    return \" \".join(toks[:1]) if toks else", T),
 ("ligar aceita meta ambígua no chute", PF, "    if len(achadas) == 1:\n        return achadas[0], None", "    if achadas:\n        return achadas[0], None", T),
 ("ligar não passa pelo filtro de assunto", PF, "    t = _tema_ok(tema)\n    if not t:\n        return False, \"esse assunto não serve (muito curto, longo ou com dados que não busco)\"\n    with _trava:\n        m, motivo = _achar_ativa(ref)", "    t = \" \".join(str(tema).lower().split())\n    with _trava:\n        m, motivo = _achar_ativa(ref)", T),
 ("ligar sem limite", PF, "        if len(m[\"ligados\"]) >= MAX_LIGADOS:", "        if False:", T),
 ("ligar em meta que não é de aprender", PF, "        if m[\"tipo\"] != \"aprender\":\n            return False, f\"só metas", "        if False:\n            return False, f\"só metas", T),
 ("estado aceita lixo em ligados", PF, "\"ligados\": _temas_sanos(m.get(\"ligados\"), MAX_LIGADOS)", "\"ligados\": list(m.get(\"ligados\") or [])", T),
 ("meta cumprida sem registrar a evidência", PF, "(evidência: {motivo}, estudo «{assunto}»)", "", T),
 ("id malformado é aceito", CU, "if isinstance(x, str) and _ID_META.fullmatch(x) and x not in saida:", "if isinstance(x, str) and x not in saida:", T),
 ("estudo falho também registra o id", CU, "        e[\"dia\"][\"n\"] += 1\n        e[\"ult\"] = time.time()\n", "        e[\"dia\"][\"n\"] += 1\n        e[\"ult\"] = time.time()\n        e[\"temas\"].setdefault(tema, {\"p\": 0.0, \"n\": 0, \"u\": \"\"})[\"m\"] = _ids_de_meta(None, meta)\n", T),
 ("estudo com id registra antes de dar certo", CU, "        ids = _ids_de_meta(d.get(\"m\"), meta)\n        if ids:\n            d[\"m\"] = ids\n        for s in _seguir", "        for s in _seguir", T),
 ("estado da curiosidade perde os ids", CU, "                if ids:\n                    base[\"temas\"][k][\"m\"] = ids", "                pass", T),
 ("despejo de assunto ligado a meta (evicção)", CU, "key=lambda k: (bool(e[\"temas\"][k].get(\"m\")), e[\"temas\"][k][\"p\"])", "key=lambda k: e[\"temas\"][k][\"p\"]", ["test_prefrontal_progresso", "test_curiosidade"]),
]
