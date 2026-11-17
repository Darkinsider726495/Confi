# Tarefas e conferência do efeito (`friday/tarefas.py`, `friday/verificacao.py`)

**Para que serve.** Antes da Fase 2, uma ferramenta que respondia «Lembrete criado» era tratada como lembrete criado. Agora a FRIDAY registra o que está tentando fazer (a **tarefa**, com passos), manda cada passo ao corretor como sempre e **confere por fora se o efeito existe**. «A ferramenta disse que fez» não é «o objetivo foi atingido».

O que isto **não** é: não é um agente que decide sozinho o que fazer, não executa nada fora do corretor, não aprende com os resultados (isso é a Fase 3: [EXPERIENCIAS.md](EXPERIENCIAS.md)) e não retoma sozinho depois de um reinício (isso é a Fase 6: [RETOMADA.md](RETOMADA.md)). É a base para essas três coisas.

## As peças

| Peça | Arquivo | Papel |
|---|---|---|
| Resultado estruturado e eventos | `friday/broker.py` | `executar_estruturado()` devolve `{estado, texto, codigo, nivel, pendencia, erro, ajustes}`; `executar()` continua devolvendo o mesmo texto de sempre. `OBSERVADORES` recebem um evento quando uma ação é executada, cancelada, expira ou é substituída |
| Conferência do efeito | `friday/verificacao.py` | Olha o estado real (banco, pasta de arquivos, cofre) e diz `confirmado`, `refutado`, `nao_verificavel` ou `inconclusivo`. Só lê |
| Tarefas | `friday/tarefas.py` | Registro, máquina de estados, execução passo a passo **pelo corretor**, ligação com as metas, comandos de voz |
| Estado em disco | `.cerebro/tarefas.json`, `.cerebro/tarefas_historico.jsonl` | Estado vivo (validado ao ler) e histórico que só acrescenta |

## Máquina de estados

`TRANSICOES` em `tarefas.py` é a única regra; qualquer outra mudança levanta `TransicaoInvalida` e não altera nada.

```
CRIADA → PLANEJANDO → PRONTA → EXECUTANDO → VERIFICANDO → CONCLUIDA
                                   │              ├→ PRONTA (falta passo)
                                   │              ├→ EXECUTADA_SEM_VERIFICACAO
                                   │              ├→ FALHOU
                                   │              └→ PRECISA_INTERVENCAO
                                   ├→ BLOQUEADA   (espera a confirmação do dono, outra tarefa ou o fim da manutenção)
                                   └→ FALHOU / PRECISA_INTERVENCAO
qualquer estado não final → CANCELADA
```

- **Ninguém chega a `CONCLUIDA` sem passar por `VERIFICANDO`** (há teste que confere cada estado).
- `CONCLUIDA` e `CANCELADA` são finais. `FALHOU` e `PRECISA_INTERVENCAO` podem voltar a `PRONTA` (retomar) ou a `PLANEJANDO` (refazer o plano).
- `EXECUTADA_SEM_VERIFICACAO`: a ação rodou, mas **não há como conferir daqui** (SMS, ligação, relé…). Só o dono muda isso, dizendo «a tarefa N está feita». Nunca vira `CONCLUIDA` sozinha.

## O que «verificado» quer dizer

| Veredito | Significado | O passo fica |
|---|---|---|
| `confirmado` | o efeito está lá | `verificado` |
| `refutado` | a ferramenta respondeu que fez e o efeito **não** está lá (falso sucesso) | `refutado` → a tarefa `FALHOU` |
| `nao_verificavel` | não há como conferir | `sem_verificacao` → `EXECUTADA_SEM_VERIFICACAO` |
| `inconclusivo` | dava para conferir, mas a conferência falhou (cofre desligado, erro de leitura, marca perdida) | `sem_verificacao` |

Cada veredito `confirmado`/`refutado` diz a **força** da prova: `independente` (olhou o estado) ou `da_resposta` (leitura pura: só temos a resposta da ferramenta, e a evidência diz isso).

Conferências por estado (`verificacao.VERIFICADORES`): `criar_lembrete` (lembrete novo no banco, com o texto e o horário), `anotar` (nota nova), `criar_arquivo` (arquivo novo com o conteúdo exato; vale o `-2` do «nunca sobrescreve»), `guardar_memoria` (nota do cofre alterada depois do pedido que contém o texto), `silenciar`/`voltar_a_falar` (estado do modo foco), `pedir_evolucao` (pedido em aberto com o texto).
Sem como conferir (motivo fica na evidência): `enviar_sms`, `ligar`, `rele`, `lanterna`, `vibrar`, `notificar`, `preparar_whatsapp`, `localizacao`, `compartilhar_arquivo`, `esquecer_memoria`, `consolidar_memoria`, `exportar_cerebro`. Ferramenta nova sem conferência cai em `nao_verificavel`; nunca em `confirmado`.

**A marca de antes.** «Existe um lembrete com esse texto» não prova que **esta** ação o criou. Por isso `verificacao.antes()` tira uma marca (maior id, arquivos parecidos, hora) e `depois()` só aceita o que apareceu depois dela. A marca é pequena e vai para o disco junto com o passo.

## Como uma ação anda

1. `tarefas.criar(objetivo, passos=[…])` registra e planeja (`CRIADA → PLANEJANDO → PRONTA`). Passo = `{ferramenta, args, descricao, depende_de}`; ferramenta desconhecida, nível 4 ou dependência para frente são recusados antes de mexer no estado.
2. `executar_proximo()` escolhe o passo cujas dependências estão **verificadas**, tira a marca, **grava no disco que o passo está executando** e só então chama `broker.executar_estruturado()`. O corretor continua decidindo tudo: validação, nível, contaminação, confirmação, PIN, manutenção, auditoria.
3. Resultado do corretor:
   - `executada` → confere o efeito → passo `verificado` / `refutado` / `sem_verificacao` / `falhou` → a tarefa avança ou termina;
   - `pendente` → o passo fica `aguardando` e a tarefa `BLOQUEADA`. A tarefa **não confirma nada**: quem confirma é o dono («confirmo …», ou o botão com o id daquela pendência). «Sim», «pode» e «isso» continuam sem executar;
   - `recusada`/`negada` → o passo `falhou` (ou a tarefa fica `BLOQUEADA` se for o modo manutenção).
4. Quando a confirmação chega (ou é cancelada, expira ou é substituída), o corretor avisa os observadores e `tarefas._ouvir` fecha o passo: executada → confere o efeito; **cancelada → tarefa `CANCELADA`**; **expirada ou substituída → `PRECISA_INTERVENCAO`** (a ação antiga nunca roda).

## Pela conversa (a IA propõe, a tarefa confere)

As duas chamadas de ferramenta da IA em `cerebro.py` (nuvem e Ollama) passam por `tarefas.executar_registrado()`. As ferramentas que **mudam algo** viram uma tarefa de um passo; as leituras puras não. O texto devolvido à IA é o mesmo de sempre, com uma única exceção: se o efeito **não foi encontrado**, o texto ganha «(Conferi o efeito e NÃO encontrei: não diga ao usuário que foi feito…)». Se o registro falhar antes da chamada, segue o caminho antigo; depois da chamada nunca repete.

**A IA não tem ferramenta para criar, planejar, executar, cancelar ou confirmar tarefas** (há teste que varre os nomes e as definições). Quem cria tarefas hoje: o código (a Fase 4 terá o planejador) e o caminho da conversa acima.

Não passam por aqui, e portanto não são conferidas: os protocolos (`protocolos.py`), as rotinas da autonomia e os atalhos de voz da memória, que chamam o corretor direto. Continuam protegidos pelo corretor, só não geram tarefa.

## Por voz

| Fala | Efeito |
|---|---|
| «quais são as minhas tarefas?», «minhas tarefas», «o que você está fazendo?» | lista as 5 mais recentes que não terminaram |
| «cancela a tarefa 3» | cancela (e derruba só a confirmação **dela**, nunca a de outra origem) |
| «retomar a tarefa 3» | tenta de novo; antes de repetir um passo, confere se o efeito já existe; ação de nível 2 pede confirmação outra vez |
| «retoma o que ficou pendente» / «continua de onde parou» | depois de reinício ou queda: confere o que ficou pela metade e retoma só o seguro ([RETOMADA.md](RETOMADA.md)) |
| «o que ficou interrompido?» | só lê |
| «a tarefa 3 está feita» | o dono confirma o que ela não consegue conferir |

## Metas do pré-córtex

A ligação é por **id** (`criar(…, meta="m01", conclui_meta=True)`), nunca por parecer com o texto. Uma meta de **aprender** é cumprida quando uma tarefa marcada com `conclui_meta` termina `CONCLUIDA` com o efeito conferido (evidência «tarefa conferida» na nota). Falha, falso sucesso, tarefa «sem verificação», tarefa de outra meta ou tarefa sem a marca **não concluem**: só mostram andamento, no máximo 90%. O pré-córtex só lê (`resumo_por_meta`); não cria nem executa tarefas (há teste).

## Privacidade

- A **trilha de auditoria** continua sendo só do corretor e continua sem conteúdo. Nada mudou ali.
- O **objetivo** da tarefa passa por `privacidade.redigir` (telefone, e-mail, «senha é …» saem).
- Os **argumentos** de um passo só vão para o disco se ele for de nível ≤ 1, a tarefa não for da conversa e nenhum texto parecer dado sensível (`memoria.sensivel`), e **saem do registro quando a tarefa termina** (`CONCLUIDA` ou `CANCELADA`; enquanto ela puder ser retomada eles ficam, porque sem eles não há como repetir o passo). Ação de nível ≥ 2 e tarefas da conversa guardam só o resumo («‹texto: 40 caracteres›»); os argumentos ficam na memória do processo e, se ele reiniciar, a tarefa vai para `PRECISA_INTERVENCAO` e pede ao dono que peça de novo.
- A **resposta** da ferramenta não é guardada, só o código e o tamanho. A **evidência** da conferência é uma frase sem o conteúdo.
- O estado vive no cofre (`.cerebro/`), que já é onde ficam as memórias dela: é um registro **local e privado**, diferente da trilha.

## Persistência e falhas

- Estado em `.cerebro/tarefas.json` (escrita atômica; campo desconhecido, estado inventado, id fora do formato ou ferramenta com nome estranho são descartados ou corrigidos ao ler; arquivo corrompido vira estado limpo).
- `.cerebro/tarefas_historico.jsonl` só acrescenta: cada mudança de estado e uma foto (sem argumentos) de cada tarefa terminada. Passam de `MAX_FINAIS` (100) concluídas/canceladas, as mais antigas saem do estado vivo e ficam só no histórico. Nada é apagado.
- Os ids (`t0001`…) nunca voltam, nem depois de reiniciar.
- **Gravar antes de executar**: se o processo cair depois de chamar o corretor e antes de registrar o resultado, o disco mostra a tarefa `EXECUTANDO` e o passo `executando` com a marca. **Desde a Fase 6** a retomada usa isso para conferir, por fora, se a ação chegou a acontecer — e nunca repete a que não dá para conferir ([RETOMADA.md](RETOMADA.md)). Antes dela a tarefa ficava presa nesse estado (nem «retomar» aceitava).
- Erro inesperado do corretor depois da chamada: `PRECISA_INTERVENCAO` («não sei se o passo chegou a acontecer»); a ação **não** é repetida.
- Cancelar durante a execução: a tarefa fica `CANCELADA`, o passo registra o que de fato aconteceu e uma confirmação que tenha nascido nesse meio-tempo é derrubada.

## Travas

`tarefas._trava` (a mesma do arquivo de estado) **nunca fica presa durante uma chamada ao corretor**. O corretor avisa os observadores com a trava dele presa; se as duas se esperassem haveria impasse. `_ouvir` só mexe no registro e na conferência e nunca chama o corretor. Os `GANCHOS_FIM` (quem quiser ser avisado de que uma tarefa terminou) são chamados fora da trava, com uma cópia.

## Limites

- Sete ferramentas são conferidas por estado; o resto é `nao_verificavel` ou leitura (as leituras puras só têm a resposta da própria ferramenta). Tudo o que sai do celular (SMS, ligação, relé, lanterna) fica «executada, mas não consegui conferir».
- A conferência de `guardar_memoria` e `pedir_evolucao` procura o **texto**; se a ferramenta o gravar de outro jeito (normalização), pode dar `refutado` por engano. Nesse caso a tarefa pede o dono, não repete sozinha.
- O vínculo entre tarefa e meta é explícito: tarefa sem `meta` não conta para nenhuma.
- Tetos de operação (não de conhecimento): `MAX_PASSOS` 12, `MAX_ABERTAS` 200, `MAX_FINAIS` 100, `MAX_HIST` 40 por tarefa.
- Nada disto foi observado no celular real (Termux:API, notificação com botão); os testes usam o corretor de verdade com comandos `termux-*` falsos.

## Testes

`tests/test_broker_estruturado.py` (22: resultado estruturado e eventos), `tests/test_verificacao.py` (37: cada conferência de verdade e «mentindo»), `tests/test_tarefas.py` (88: estados, plano, execução verificada **A**, falso sucesso **B**, confirmação ambígua **F**, privacidade **G**, persistência, concorrência, voz), `tests/test_tarefas_integracao.py` (8: laço da IA na nuvem e local, `main.processar`, painel), `tests/test_tarefas_metas.py` (11: metas com texto diferente **H**). Rodar: `python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_tarefas*.py'` (e `test_verificacao.py`, `test_broker_estruturado.py`).
Os testes de aprendizado (**E**, **C**) estão em [EXPERIENCIAS.md](EXPERIENCIAS.md) e [PLANEJADOR.md](PLANEJADOR.md); os de coordenação (**I**) em [COORDENADOR.md](COORDENADOR.md); os de retomada depois de reinício (**D**) em [RETOMADA.md](RETOMADA.md).
