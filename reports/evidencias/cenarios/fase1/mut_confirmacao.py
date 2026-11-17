T = ["test_confirmacao", "test_http", "test_core"]
MUTANTES = [
 ("sim/pode/isso passam a executar", "friday/broker.py", "forte = bool(palavras & CONSENTE)  ", "forte = bool(palavras & (CONSENTE | {'sim', 'pode', 'isso'}))  ", T),
 ("confirmo solto vale depois de outra conversa", "friday/broker.py", "or (forte_sozinho and imediata):", "or forte_sozinho:", T),
 ("vaga logo após o anúncio executa", "friday/broker.py", "elif forte_sozinho or vaga:\n            executar = False", "elif forte_sozinho or vaga:\n            executar = True", T),
 ("botão ignora o id", "friday/broker.py", "if not isinstance(id_pendencia, str) or not hmac.compare_digest(id_pendencia, p[\"id\"]):", "if False:", T),
 ("pendência trocada não é registrada", "friday/broker.py", "_audit(ferramenta=PEND[\"nome\"], decisao=\"substituido\")", "pass", T),
 ("negativa deixa de cancelar", "friday/broker.py", "(palavras & NEGA and (cita or forte) and len(t.split()) <= 8)", "False", T),
 ("nível 3 aceita voz", "friday/broker.py", "        if p[\"tipo\"] != \"voz\":\n            return True, \"Essa ação crítica exige o PIN no HUD ou no celular.\"\n        if not executar:", "        if not executar:", T),
 ("fala citando outra ação executa", "friday/broker.py", "cita = bool(p[\"chave\"]) and all(w in palavras for w in p[\"chave\"])", "cita = True", T),
 ("rota do painel volta a ignorar o id", "friday/main.py", "B.confirmar_botao(d.get(\"id\"))", "B.confirmar_voz(\"confirmo\")", T),
 ("notificação permanente volta a ter Confirmo solto", "friday/main.py", "botoes=[(\"Falar\", f\"sh {acao} ouvir\"), (\"Cancelar\", f\"sh {acao} cancelar\")])\n\n\ndef _notificar_pendencia", "botoes=[(\"Falar\", f\"sh {acao} ouvir\"), (\"Confirmo\", f\"sh {acao} confirmar_voz\"), (\"Cancelar\", f\"sh {acao} cancelar\")])\n\n\ndef _notificar_pendencia", T),
 ("corretor não anuncia a pendência real", "friday/main.py", "if p and p[\"id\"] != antes:", "if False:", T),
]
