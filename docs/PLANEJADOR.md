# Planejador e objetivos próprios (`friday/planejador.py`, `friday/objetivos.py`)

**Para que serve.** Dado um objetivo permitido, a FRIDAY avalia o contexto, escolhe uma estratégia, executa **pelo corretor**, observa, confere se o efeito existe, registra a experiência e, se a estratégia falhou, tenta uma alternativa equivalente e permitida, ou pergunta, ou para. Ela também pode **propor** objetivos com base no que aprendeu, mas só executa o que o dono aprovar.

**O que isto NÃO é.** Não é um agente solto. As estratégias vêm de um **catálogo escrito em código**; nem a experiência, nem a IA, nem texto da internet acrescentam ferramentas ou sobem de nível. Quem executa é o corretor, que continua validando argumentos, pedindo confirmação presa à ação no nível 2 e gravando a auditoria.

## Três coisas diferentes (de propósito)

| Verbo | Quem faz | O que significa |
|---|---|---|
| **Propor** | ela (`objetivos.propor`) | grava uma proposta com justificativa e evidências. Não cria tarefa, não chama ferramenta |
| **Planejar** | `planejador.executar_objetivo` | monta o plano e escolhe a estratégia |
| **Ser autorizada a executar** | só o dono, por frase explícita | «aprova o objetivo 2». «sim», «pode», «faz aí» **nunca** aprovam |

## O ciclo (11 passos, todos em `resultado["ciclo"]`)

1 receber um objetivo permitido · 2 avaliar contexto e recursos (`ambiente()`, estratégias disponíveis) · 3 separar o que sabe do que precisa descobrir · 4 dividir em etapas · 5 escolher a estratégia (`escolher`) · 6 executar um passo (pelo corretor) · 7 observar · 8 verificar se cumpriu o propósito (`verificacao.py`) · 9 registrar a experiência · 10 atualizar o plano · 11 continuar, tentar alternativa, pedir esclarecimento ou parar.

Não é rígido: se a estratégia falha, as evidências decidem a próxima; o ambiente é **reavaliado a cada tentativa** (cofre desligado, manutenção). Decisões possíveis: `concluir` (efeito conferido), `esperar_dono` (há confirmação pendente), `pedir_esclarecimento`, `interromper`, `recusar` (nada foi tentado).

## O catálogo

| Objetivo | Estratégias equivalentes, em ordem de preferência | Próprio? |
|---|---|---|
| `registrar_informacao` | `guardar_memoria` · `anotar` · `criar_arquivo` | sim (nível 1, nada sai do aparelho) |
| `registrar_e_avisar` | `anotar`+`criar_lembrete` · `guardar_memoria`+`criar_lembrete` | não |
| `lembrar_depois` | `criar_lembrete` (oferece `anotar` só como sugestão, porque não cumpre o pedido inteiro) | não |

`REGRA_DE_ESCOLHA`: ordem pela taxa suavizada das experiências compatíveis com as condições de agora; sem experiência vale 0,5; empate pela ordem do catálogo; o que está fora do nível permitido ou indisponível não entra. A escolha guarda por que cada candidata ficou onde ficou, e [EXPERIENCIAS.md](EXPERIENCIAS.md) explica como conferir.

## Regras que não mudam

- Estratégia de nível ≥ 2 **nunca é escolhida sozinha**: vira sugestão («posso fazer assim se você confirmar»).
- Uma **recusa do corretor** encerra a tentativa. Não se contorna trocando de ferramenta.
- Conteúdo que parece sensível (senha, cartão, documento) é recusado **antes** de planejar.
- O planejador não importa nada do corretor além do catálogo de ferramentas; um teste confere.
- A IA ganha só uma **dica** quando uma ação dela falha ou o efeito não aparece: o que as experiências dizem e quais alternativas equivalentes existem. Ela continua só propondo.

## Objetivos propostos por ela (`objetivos.py`)

Hoje ela olha `experiencias.padroes()`: a mesma estratégia **falhou duas vezes ou mais, sem nenhum acerto, nas mesmas condições**, em tarefas que **você** pediu. Aí propõe anotar a observação («indício, não regra»).

Uma proposta só existe se:
- o tipo está no catálogo com `permite_proprio` (hoje só `registrar_informacao`);
- tem **evidência**: ids de experiências reais; e **vínculo**: uma tarefa do dono (o que ela fez por conta própria não alimenta novas propostas, para não criar laço);
- o conteúdo é limpo e a justificativa existe;
- não há outra aberta sobre o mesmo assunto, nem uma que você já recusou; no máximo 5 esperam você ao mesmo tempo.

Limites fixos no código, não no arquivo: nível máximo 1, 2 tentativas, nenhuma ação externa. Ela não consegue alterar as próprias regras de segurança: corretor, protocolos, autonomia e curiosidade não são tipos de objetivo.

**Por voz (só o dono):** «quais objetivos você propõe?» · «aprova o objetivo N» · «pausa o objetivo N» · «retoma o objetivo N» · «cancela (ou recusa) o objetivo N». Nenhuma ferramenta da IA toca nisso (teste varre o código e os nomes). Cancelar cancela só a tarefa que a própria proposta criou.

**Reinício no meio:** `conciliar()` põe a proposta de acordo com a tarefa que ela criou (a verdade está na tarefa). Sem tarefa, nada foi começado e a proposta volta a esperar você; **nada é repetido**.

## Estado e privacidade

`.cerebro/objetivos_proprios.json` (validado ao ler: o limite, quem decidiu e o estado não vêm do arquivo) e `.cerebro/objetivos_proprios_historico.jsonl` (só acrescenta). O texto da proposta é montado de metadados (nome da estratégia, condições, contagens); o conteúdo que você pediu não entra.

## Limites (ditos com franqueza)

- **Não há entrada por fala livre.** «anota que…» ainda não vira um objetivo do planejador; hoje os pedidos chegam por código ou por proposta aprovada. Ligar a fala livre exige decidir quais frases viram objetivo (decisão sua).
- São 3 tipos de objetivo e as alternativas são escritas em código; ela não inventa estratégias novas.
- Efeitos parciais de uma estratégia que falhou no meio (por exemplo uma nota salva antes de o lembrete falhar) ficam no mundo; a experiência registra, mas nada desfaz sozinho.
- Retomar sozinha uma tarefa depois de reiniciar é a Fase 6; hoje o dono reabre.
- Não dá para verificar daqui: telefone real, Termux:API, modelo de linguagem real.

## Testes

`tests/test_planejador.py`, `tests/test_objetivos.py`, integração em `tests/test_tarefas_integracao.py`; mutação em `reports/evidencias/cenarios/fase3_4/` (log em `reports/evidencias/logs/fase3_4/`).
