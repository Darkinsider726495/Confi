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

## O que ainda guarda frase inteira
O diário `Conversas/AAAA-MM-DD.md` (`memoria.registrar_conversa`, ligado por `MEMORIA_AUTO`, padrão 1) continua registrando as conversas que vão para a IA, como antes desta mudança. Desligar ou trocar por assuntos é decisão do dono.

## Limites
A qualidade dos assuntos depende do modelo (no celular, o Ollama pequeno erra mais que o da nuvem). Com a nuvem, a frase vai para o provedor de IA para extrair os assuntos — o mesmo caminho que a resposta já faz.
