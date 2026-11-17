# Rotina — a GRU que aprende o seu dia

`friday/rotina.py` é uma **rede neural recorrente (GRU)** escrita em NumPy puro, treinada no próprio celular. Ela lê o registro de
atividades que o pré-córtex já guarda (`.cerebro/atividades.jsonl`), aprende o ritmo do seu dia e prevê o que deve acontecer na
**próxima hora**.

## O que entra e o que sai
| | |
|---|---|
| Entrada | as últimas 24 h, hora a hora: se você falou com ela, se usou a câmera/as mãos, e os até 7 assuntos mais frequentes; mais a hora do dia e o dia da semana (seno/cosseno) e se é fim de semana |
| Rede | GRU com 24 neurônios de memória (portas *update* `z`, *reset* `r` e candidato `n`): `h' = (1−z)·n + z·h` |
| Saída | a chance (0–100%) de cada rótulo acontecer na hora seguinte |
| Treino | entropia cruzada binária, retropropagação no tempo (BPTT), Adam, corte de gradiente; 80 épocas por padrão (segundos no celular) |
| Modelo | `cofre/.cerebro/rotina_gru.npz` (fica no aparelho, junto do cérebro dela) |

**Privacidade:** a rede só vê rótulos e nomes de assuntos que o pré-córtex já tinha registrado. Nenhuma frase sua entra no treino.

## Honestidade: quando ela confia na rede
- Precisa de **pelo menos 7 dias** de registro. Antes disso ela diz quanto já juntou.
- Os **2 últimos dias ficam fora do treino**. Neles ela compara o erro da GRU com o «jeito simples» (a frequência de cada coisa naquela hora do dia).
- Ela só **confia** (e só se adianta) se a GRU errar **menos** que o jeito simples. A vantagem real da GRU é a sequência do dia: por exemplo, «nos dias em que você treina de manhã, à noite fala de SQL». Uma rotina que depende só da hora o jeito simples já acerta, e ela diz isso.

## Como ela usa
- Voz: «como é a minha rotina?», «o que você acha que eu vou fazer agora?» → mostra as previsões com a porcentagem e lembra que é previsão, não certeza.
- Conversa espontânea (só se **você** ligou a conversa): com a rede confiável e um assunto com chance ≥ 60% na próxima hora, ela se adianta **uma vez por dia por assunto**: «por volta desta hora você costuma falar de SQL. Quer que eu prepare alguma coisa?». Passa pelos filtros da conversa (`fala_ok`).
- **Só sugere.** Não há ferramenta da IA para a rotina, ela não cria tarefa nem executa nada sozinha; qualquer ação continua passando pelo corretor.

## Treino
- Sozinha: no tempo ocioso da assimilação, no máximo uma vez por dia (`treinar_se_for_hora`).
- Na mão: `python scripts/treinar_rotina.py` (mostra a perda caindo, o resultado da validação e a previsão) ou `--ver` para só ver a previsão.

## Testes
`tests/test_rotina.py`: gradiente conferido por diferença finita; aprende uma rotina sintética em que a hora sozinha dá 50% e a GRU passa de 70%; recusa com menos de 7 dias; sem confiança não sugere (checagem de mutação feita); treino automático no máximo 1×/dia; conversa se adianta uma vez só; sem NumPy tudo desliga sem erro.

## O que não dá para verificar aqui
A qualidade com a sua rotina real (depende dos seus dias) e o tempo exato de treino no seu aparelho.
