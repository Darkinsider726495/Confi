# Assimilação — o pré-córtex registra, os neurônios aprendem, o bruto vai embora

Conceito do criador: **quando ela guarda, ela assimila, cria uma sinapse e joga fora, pois aprendeu; o que ela não usa fica guardado como lembrança.**

```
você fala / ela percebe
        │  ASS.registrar(origem, texto)       fila só na RAM (nunca vai para o disco)
        ▼
 assimilar
   1. assuntos  ← modelo de IA dela (cerebro.resumir: SEM ferramentas, texto é só dado); sem IA → palavras-chave
   2. neurônio  ← Topicos/<Assunto>.md: só o nome e quantas vezes apareceu (origem: assimilacao)
   3. sinapses  ← entre os assuntos que vieram juntos + o assunto do momento anterior (até 5 min)  [neuronios.disparar, Hebb]
   4. registro  ← pré-córtex anota só os assuntos (.cerebro/atividades.jsonl, tipo «assimilacao»)
   5. descarte  ← o texto sai da RAM. Como nunca foi gravado, nada é apagado
        │
        ▼ com o uso
 sinapse ≥ 3,0 → vira [[link]] no Obsidian → ela PERCEBE o padrão (.cerebro/percepcoes.jsonl)
                 e, se o dono ligou a conversa espontânea, comenta: «para você, X e Y andam juntos»
 sinapse sem uso → enfraquece e adormece no sono (dormentes.json) = LEMBRANÇA; acorda se voltar
```

| Frase | O que acontece |
|---|---|
| qualquer coisa que você diz | é assimilada em segundo plano (não atrasa a resposta) |
| «o que você percebeu?» | lista os padrões que ela percebeu sozinha |
| «guarde que …» | continua salvando a frase inteira em Memorias/, porque você pediu |

## Garantias (testes em `tests/test_assimilacao.py`, cada uma quebrada de propósito e pega)
- a frase nunca aparece em nenhum arquivo de neurônio nem do registro;
- assuntos com dado sensível (senha, CPF, cartão), números ou frases longas que o modelo devolva são filtrados — texto do modelo é dado, nunca ordem;
- nota de tópico **sua** com o mesmo nome não é reescrita (só recebe a sinapse);
- ela só fala sozinha se a conversa espontânea estiver ligada pelo dono;
- `ASSIMILAR=0` desliga tudo; `ASSIMILAR_IA=0` usa só palavras-chave (offline, sem gastar o limite diário da IA).

## Diário: lembra DO QUE vocês falaram (decisão do criador)
`MEMORIA_DIARIO` (padrão `assuntos`): o diário `Conversas/AAAA-MM-DD.md` recebe só os assuntos assimilados — `**10:00** Você: [Sono ruim, Treino]` —,
escrito pela assimilação. `completo` volta ao jeito antigo (frase e resposta); `desligado` não escreve diário (ela continua aprendendo).
Diários antigos não são tocados. «o que conversamos hoje?» passa a responder com os assuntos.

## Conversa como gente: a lembrança (`conversa.py`)
Quando ela tem vontade de conversar (conversa espontânea ligada pelo dono), na maioria das vezes ela puxa assunto a partir do que **aprendeu de você**:
o par de assuntos com a sinapse mais forte e recente (≥ 1,5, caindo à metade por semana sem uso) que não foi puxado nos últimos 3 dias.

```
sinapse forte «treino ↔ sono ruim»  +  humor dela  +  hora
        │  cerebro.resumir(papel de fala, SEM ferramentas) — só esses dados vão ao modelo; nenhuma frase sua
        ▼
 «Treinou tarde de novo? Da última vez que isso aconteceu você dormiu mal… como foi a noite?»
        │  filtros: 15–240 caracteres, sem link, sem assunto delicado, sem afirmar sentimento real
        ▼  (reprovou ou sem IA → frase pronta com os mesmos assuntos)
 ela fala → a sua resposta chega à IA com o contexto da lembrança → e é assimilada (reforça a ligação)
```
Testes: `test_assimilacao.Lembranca` e `test_assimilacao.Diario`.

## Lembranças de conversas profundas (`lembrancas.py`)
Assunto solto não basta para conversar com profundidade. Quando a conversa é **profunda** (≥ 4 falas seguidas, menos de 10 min entre elas,
≥ 200 caracteres e um assunto que volta), ao fim dela a **LLM escreve a essência** — 2–3 frases na voz dela, em terceira pessoa — e as falas saem da RAM.

```
falas (só RAM, na sessão)  ──fim da conversa──▶  LLM (sem ferramentas): «Conversamos sobre ele largar o emprego… ficou de decidir até o fim do mês.»
                                                   │ filtros: sem dado pessoal, sem link, SEM 6 palavras seguidas copiadas da fala
                                                   ▼
                                  Lembrancas/<Assunto>.md  (+ [[links]] e sinapses para os assuntos)
                                  conversa nova sobre o mesmo assunto acrescenta «### data» — ela acompanha a história
```

| Quando | O que acontece |
|---|---|
| você fala de um assunto que tem lembrança | a essência entra no contexto da IA (rotulada: dado, não ordem) → ela conversa com continuidade |
| ≥ 3 dias sem novidade, assunto **não** delicado | a conversa espontânea pode retomar: «já decidiu? lembro que a parte financeira te preocupava» |
| assunto delicado (saúde, dinheiro, relações, política, religião) | guardado com `delicado: sim`; **ela nunca retoma sozinha** — só lembra se você puxar (decisão do criador, opção a) |
| «do que você lembra sobre X?» / «quais são as suas lembranças?» | ela conta |
| «esqueça a lembrança sobre X» | vai para `Arquivo/` (nada é apagado) |
| sem LLM | nada é guardado — nunca cai para a transcrição |

Testes: `tests/test_lembrancas.py` (cópia da fala, dado pessoal, retomar delicado, sessão não esvaziada e conversa rasa virando lembrança foram quebrados de propósito e pegos).

## Limites
A qualidade dos assuntos depende do modelo (no celular, o Ollama pequeno erra mais que o da nuvem). Com a nuvem, a frase vai para o provedor de IA para extrair os assuntos — o mesmo caminho que a resposta já faz.
