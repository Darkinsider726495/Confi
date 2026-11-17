---
name: friday-testar
description: Rodar e escrever testes da FRIDAY (unitários, painel no Chromium e checagem de mutação das defesas). Use ao mudar qualquer código em friday/.
---
# Testar a FRIDAY

1. Ambiente: `pip install -r requirements-test.txt`. Unitários (sem rede, ~50 s): `python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'`. Um arquivo só: `-p 'test_vida.py'`.
2. Painel no Chromium (precisa do Playwright): `python3 tests/e2e_hud.py`, `tests/e2e_voz_memoria.py`, `tests/e2e_cerebro.py`, `tests/e2e_maos.py`, `tests/e2e_prefrontal.py`. O CSP proíbe `eval`: espere com `evaluate` + polling (função `espera`).
3. Ambiente: `import _ambiente as E` antes dos módulos (pasta temporária, `FRIDAY_VIDA=0`). Cérebro isolado: herde `Cerebro` de `test_neuronios`. Tempo: `mock.patch.object(V, "agora", ...)`. Internet e IA: simule `internet.resultados`, `internet.texto_pagina` e `cerebro.resumir`.
4. Mudou uma defesa (limpar, consulta_segura, quarentena, teto de IA, silêncio/descanso, confirmação)? Faça a **checagem de mutação**: quebre a linha de propósito, rode o arquivo de teste e confirme que falha; restaure. Se passar, falta um teste. Em lote: `reports/evidencias/cenarios/fase2/mutar.py <lista.py> <projeto>` aplica cada mutante numa CÓPIA do projeto (veja `mut_*.py` ao lado; a Fase 1 está em `fase1/`).
5. Não afirme que algo funciona no celular: os testes usam comandos Termux simulados.
