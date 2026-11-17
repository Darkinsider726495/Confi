# Experiências: aprender com o que aconteceu (`friday/experiencias.py`)

**Para que serve.** Cada vez que uma tarefa termina, a FRIDAY guarda o que tentou, o que esperava, o que viu de fato e o que isso quer dizer. Na vez seguinte, quem escolhe uma estratégia (o planejador, ver [PLANEJADOR.md](PLANEJADOR.md)) consulta esse registro e põe na frente o que já funcionou nas mesmas condições. Falha aqui é **informação**, não castigo: nenhum número de «prêmio» ou «punição» é somado a nada.

**O que isto NÃO é.** Não é treino do modelo de linguagem: nenhum peso, parâmetro ou prompt de modelo muda. O aprendizado é memória episódica estruturada + contagem honesta, e só reordena opções que o código já permite. Também não concede permissão: uma experiência boa não sobe o nível de nenhuma ferramenta, não tira a confirmação do dono e não faz o corretor aceitar o que recusou.

## As peças

| Peça | Onde | Papel |
|---|---|---|
| Registro | `friday/experiencias.py` | Transforma uma tarefa terminada em experiência (gancho `tarefas.GANCHOS_FIM`); consulta, contagens, padrões |
| Intenção | `experiencias.intencao()` | Grava **antes de agir** a hipótese, o resultado esperado, as alternativas e por que esta estratégia foi escolhida |
| Estado em disco | `.cerebro/experiencias.jsonl` | Só acrescenta (nada é apagado); linhas estragadas são contadas e ignoradas, não derrubam nada |
| Voz | «o que você aprendeu com as tarefas?», «minhas experiências» | Resumo falado, só contagens e a regra de leitura |
| Painel | `experiencias` em `/estado` | Só contagens |

## O que cada experiência guarda

objetivo e contexto · **hipótese inicial** (e quem a escreveu: `planejador`, ou `implicita` quando ninguém planejou, por exemplo uma ferramenta chamada pela IA) · estratégia · ações (descrição, ferramenta, nível, estado, resumo dos argumentos) · **esperado** · **observado** · evidências da conferência (veredito e força) · **diferença** entre esperado e observado · **causas prováveis com confiança** · o que foi **aprendido** · o que continua **desconhecido** · estratégias alternativas · **condições de reutilização** (quando vale, quando não vale, validade).

Cada afirmação tem um tipo, e eles nunca se misturam:

| Tipo | Significa | Exemplo |
|---|---|---|
| `fato` | foi observado (estado do passo, veredito da conferência, código do corretor) | «a ferramenta respondeu que deu certo e a conferência não achou o efeito» |
| `inferencia` | conclusão tirada dos fatos, com confiança menor que 1 | «a ferramenta não produziu o efeito (ou o produziu em outro lugar)» |
| `hipotese` | palpite a testar, com confiança baixa | «o ambiente atual contribuiu» |
| `desconhecido` | o que não dá para saber daqui | «por que a ferramenta disse "feito" sem produzir o efeito» |

As confianças são estimativas por regra, **não probabilidades calibradas**.

## Resultados

`sucesso` (efeito conferido) · `falha` com tipo `falso_sucesso` (disse que fez, o efeito não existe), `erro` (a ferramenta falhou) ou `recusa` (o corretor não deixou: o pedido estava errado, a estratégia não falhou) · `sem_conferencia` (executada, mas não há como conferir) · `interrompida` · `cancelada`.

## Como a experiência muda a escolha

`sinais(estrategia, condicoes)` conta, entre as experiências **compatíveis com as condições de agora** (`ambiente()`: cofre ativo, manutenção), só as de desfecho conhecido: sucesso e falha de tipo `erro` ou `falso_sucesso`. Recusa, sem conferência, interrompida e cancelada aparecem à parte e **não pesam**. A taxa é suavizada, `p = (sucessos + 1) / (n + 2)`: sem dados vale 0,5 e uma falha só baixa para 0,33, então **uma tentativa nunca zera uma estratégia nem vira regra universal**. Uma falha com o cofre desligado não pesa quando o cofre está ligado.

A justificativa é **verificável**: a escolha guarda o ranking, as contagens e os ids das experiências usadas, e `conferir_escolha()` recalcula tudo com as experiências feitas até o instante da escolha e aponta qualquer divergência. Uma frase bonita que não bate com o registro é detectada.

`padroes()` agrupa o que se repetiu nas mesmas condições (mesma estratégia, mesmas condições, desfecho conhecido). Não decide nada: é a matéria-prima de `objetivos.py`, que só **propõe** ao dono (ver [PLANEJADOR.md](PLANEJADOR.md)).

## Privacidade

Os registros usam o que `tarefas.py` já redigiu. O conteúdo pedido, a resposta da ferramenta e a trilha de auditoria **não entram**; o painel e a voz só trazem contagens. Há teste que procura o conteúdo nos arquivos de estado.

## Limites (ditos com franqueza)

- Registro é arquivo `.jsonl` do processo, ainda **não são neurônios** do cofre.
- `ambiente()` olha duas condições (cofre ativo, manutenção). Outras causas de falha (rede, bateria, horário) ainda não são condições.
- As causas e confianças são por regra. Com poucas observações, o texto diz «é indício, não regra».
- Só tarefas que terminam geram experiência; um processo que cai no meio da tarefa só gera a experiência quando a tarefa for retomada ou fechada.
- Não dá para verificar daqui: comportamento num celular real, e qualidade de um modelo de linguagem real.

## Testes

`tests/test_experiencias.py` (registro fiel, tipagem, ambiente, sinais, persistência, privacidade, robustez, voz, padrões), `tests/test_planejador.py` (aprendizado muda a escolha, com a justificativa conferida) e a mutação em `reports/evidencias/cenarios/fase3_4/`.
