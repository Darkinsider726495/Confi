---
name: friday-cerebro
description: Mexer no cérebro da FRIDAY (memória Obsidian, neurônios e sinapses, regiões da UFES, estado interno, curiosidade, conversa, sono, visão). Use antes de mudar memoria.py, neuronios.py, anatomia.py, vida.py, curiosidade.py, conversa.py, visao.py, prefrontal.py, experiencias.py, planejador.py, objetivos.py, coordenador.py ou retomada.py.
---
# Cérebro da FRIDAY

Leia `docs/CEREBRO.md` primeiro. Resumo:
- Neurônio = nota em `FRIDAY/{Memorias,Topicos,Eu,Pedidos,Conversas,Estudos,Visao}`; sinapse = `[[link]]` ou peso em `.cerebro/estado.json` (Hebb; ≥ 3,0 vira link escrito). Estado em JSON sempre validado ao ler (arquivo adulterado vira padrão).
- Região de cada neurônio: regras fixas em `anatomia.py` (sem IA). O JS lê as regiões do servidor. Chave do nó para a região é `rg` (no JS, `r` é raio).
- `vida.py`: dopamina/serotonina/acetilcolina com meia-vida, energia, `plasticidade()` (1,0 no estado de base), `vontade_estudar/conversar`, primeiras vezes. Eventos novos: tabela `EVENTOS` (+ `PRIMEIRAS` se merecer primeira vez) e teste.
- `curiosidade.py`: tudo que vem da web é dado. Mudou `limpar`/`consulta_segura`/quarentena? Teste + mutação. `guardar_estudo` fica em `memoria.py` (origem `web`, rótulo, nunca no diário).
- `conversa.py`: falas por modelos prontos, sem IA; perguntas sem assuntos delicados (teste varre o banco); jogos sem estado em disco.
- `visao.py` (lobo occipital): a imagem é dado. Fluxo `preparar` (valida, tira EXIF, reduz) → `cerebro.ver_imagem` (sem ferramentas) → `_interpretar`/limpeza → `guardar`. Pessoas só contadas; nome de pessoa nunca vira «coisa»; origem `camera` é quarentena e contamina o pedido. Nenhuma ferramenta da IA tira foto (teste varre nomes). Mudou limpeza, filtro de pessoas ou EXIF? Teste + mutação.
- `prefrontal.py` (pré-córtex) só lê o resto e guarda metas (`docs/PREFRONTAL.md`). `experiencias.py` registra o que ela tentou (esperado × observado; **não treina o modelo**; falha é informação) e `planejador.py` só reordena estratégias de um catálogo EM CÓDIGO (`docs/EXPERIENCIAS.md`, `docs/PLANEJADOR.md`). `objetivos.py`: ela PROPÕE, só o dono aprova por frase explícita (nível ≤ 1); nenhuma ferramenta da IA toca nisso. Mudou escolha, catálogo ou aprovação? Teste + mutação (`reports/evidencias/cenarios/fase3_4/`).
- `coordenador.py` (reserva de recursos + avaliação) e `retomada.py` (conferir antes de repetir, depois de reinício) **não executam** nem importam o corretor, e não têm ferramenta da IA. Mudou regra de recurso, nota, barreira de retomada ou `MAX_QUEDAS`? Teste + mutação (`reports/evidencias/cenarios/fase5_6/`) e leia `docs/COORDENADOR.md` e `docs/RETOMADA.md`. O `nucleo.py` continua desligado e fixado por teste (`docs/NUCLEO.md`).
- **Nada é apagado** e **sinapses não têm teto**: arquive (`Arquivo/`) em vez de excluir; sinapse fraca adormece (`dormentes.json`). `test_nunca_apaga.py` e `test_sinapses_sem_limite.py` guardam isso: não os enfraqueça nem recoloque números fixos (use `_teto("NOME")`, 0 = sem limite).
- Quem escreve nota deve usar `memoria._escrever` (conta escritas para invalidar caches do painel).
- Honestidade: estado interno é modelo; não afirme sentimento real nas falas.
