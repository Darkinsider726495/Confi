# Retomada depois de reinício ou queda (`friday/retomada.py`)

Quando o programa reinicia ou cai no meio de uma ação, ela precisa descobrir **o que ficou pela metade**, **conferir o que de fato aconteceu** e só então continuar — ou pedir você. A regra central: **ação que pode já ter acontecido e não dá para conferir nunca é repetida sozinha.**

## O problema (medido, não suposto)

`tarefas.py` grava o estado **antes** de chamar o corretor (ver [TAREFAS.md](TAREFAS.md)). Logo, uma queda deixa o disco com a tarefa `EXECUTANDO` e o passo `executando` — e o corretor pode ou não ter executado a ação. Antes da Fase 6 nada mexia nessa tarefa: nem `executar_proximo` («já está em execução») nem «retomar a tarefa N» («a tarefa está executando; não há o que retomar») aceitavam o estado. Ficava presa para sempre.

Prova com **queda real de processo** (`os._exit` no meio da ação), três processos de verdade e um quarto que reinicia: `reports/evidencias/cenarios/fase5_6/necessidade_de_retomada.py`.

| Queda | Antes (`necessidade_de_retomada.antes.log`) | Depois (`necessidade_de_retomada.depois.log`) |
|---|---|---|
| depois do efeito (lembrete criado) | tarefa presa em `EXECUTANDO` | efeito achado por fora → `CONCLUIDA`; lembrete **não** duplicado |
| antes do efeito | tarefa presa | conferência prova que não existe → refeito uma vez → `CONCLUIDA` |
| ação que não dá para conferir (lanterna) | tarefa presa | **não repetida** → `PRECISA_INTERVENCAO`, com o motivo |

## Como funciona

### 1. Recuperar o que parou no meio — `tarefas.recuperar(tid)`
Só age em tarefa `EXECUTANDO`/`VERIFICANDO` que **este processo não está executando** (`tarefas.ATIVAS`). Para cada passo que estava `executando`, olha o **mundo** (a conferência independente da Fase 2, com a marca tirada antes da ação), nunca a resposta da ferramenta:

| O que a conferência diz | O que acontece com o passo |
|---|---|
| efeito encontrado (independente) | `verificado`; **não repete** |
| efeito provadamente ausente, ou a ferramenta só lê (nível 0), e ainda não caiu `MAX_QUEDAS` (2) vezes | volta a `pendente` (pode repetir) |
| não dá para conferir / inconclusivo / caiu `MAX_QUEDAS` vezes | `intervencao` («interrompido»): **pode ter acontecido, não repete**, pede o dono |

Depois a tarefa é resolvida pelo mesmo `_resolver` de sempre (`CONCLUIDA`, `PRONTA`, `PRECISA_INTERVENCAO`…) e quem escuta o fim das tarefas (experiências, objetivos) é avisado. Um passo «interrompido» pode ser dado como feito por você («tarefa N está feita», registrado com força `dono`) ou repetido por você («retomar a tarefa N»): a decisão é sua.

`tarefas.confirmacao_perdida(tid)`: tarefa `BLOQUEADA` esperando uma confirmação que o corretor não tem mais (ela vive na memória do processo: some no reinício) → o passo vira `intervencao`, **nada é executado**, e você pede a ação de novo. Confirmação ainda viva não é tocada. «sim», «pode» e «confirmo» não ressuscitam a que se perdeu (teste `test_F_sim_ou_pode_depois_do_reinicio_nao_executam_o_que_se_perdeu`).

### 2. Retomar o que é seguro — `retomada.retomar_pendentes()`
Depois de recuperar, olha as tarefas `PRONTA` (e as `BLOQUEADA` só por dependência) e decide **na ordem e com as esperas do coordenador** ([COORDENADOR.md](COORDENADOR.md): `avaliar`). Só retoma sozinha o que passa por todas estas barreiras:

| Barreira | Motivo |
|---|---|
| origem: pedido seu, meta ou objetivo que você aprovou (**não** `ia`) | o contexto da conversa se perdeu, e o turno em que o corretor tratava o pedido como mais perigoso (contaminação) não existe mais |
| parada há no máximo `IDADE_MAX_S` (30 min) | pode já não valer; mais velha espera você («retomar a tarefa N») |
| nível ≤ 1 (duas camadas: elegibilidade e coordenador) | nível 2 pede a confirmação presa à ação, como sempre |
| argumentos guardados | ação sensível e reinício não deixam os dados no disco; não se inventa a ação |
| dependência e recurso livres | decisão do coordenador; quem espera é reavaliado até `MAX_RODADAS` (4) |

Quem executa é `tarefas.executar` → **corretor** (nada de atalho): auditoria, validação de argumentos e conferência do efeito valem como sempre. A retomada roda **em sequência**, sem threads nem agentes; a coordenação continua protegendo contra outras execuções simultâneas (reserva de recursos). No máximo `MAX_TAREFAS` (20) por rodada, e só **uma rodada de cada vez**.

Cada item do relatório é `{tarefa, acao, motivo, estado}`, com `acao` em `conferiu` · `retomou` · `esperou` · `pediu_dono`. Os motivos nunca levam o conteúdo do que foi pedido.

## Quando roda

- **Ao ligar**, uma vez, numa thread (`main._retomar_ao_iniciar`): retoma, depois reconcilia os objetivos dela com o que as tarefas dizem (`objetivos.conciliar`). Só **fala** se retomou/conferiu algo ou se algo precisa de você. Para desligar a parte automática, ponha `FRIDAY_RETOMADA=0` no seu `.env` (o comando de voz continua valendo).
- **Por voz:** «retoma o que ficou pendente» / «continua de onde parou» (confere e retoma o seguro) · «o que ficou interrompido?» (**só lê**).
- **Painel:** só contagens (`retomada: {interrompidas, ultima, erros}`).

## Privacidade e registro
`.cerebro/retomada.jsonl`: uma linha por rodada **que fez alguma coisa** (rodada vazia não escreve), com ids, ação, motivo curto e estado. As decisões do coordenador vão para `.cerebro/coordenacao.jsonl` (recursos como tipo + código curto).

## O que ela NÃO faz
- Não repete ação não conferível (SMS, ligação, relé, lanterna…) que pode já ter acontecido. Nem repete passo que já derrubou o programa `MAX_QUEDAS` vezes (laço de queda).
- Não retoma sozinha pedido da conversa, nível 2 ou mais, nem o que passou de 30 min.
- Não tem ferramenta da IA e não importa o corretor (teste varre o código).
- Não mexe em tarefa que este processo está executando (nem entre dois passos).

## Limites honestos
- Quedas foram simuladas (exceção no meio da ferramenta) e **exercitadas de verdade com `os._exit`** num processo separado, no Linux. Reinício real no celular, `kill` do Android e Termux **não foram exercitados aqui**.
- Só as ferramentas com conferência independente (lembrete, nota, arquivo, memória, silêncio, pedido de evolução) têm o caminho «efeito encontrado → não repete». As demais caem em «pede o dono», que é conservador.
- A conferência de um efeito ausente assume que o efeito é imediato (ferramentas locais). Efeito assíncrono poderia ser dado como ausente cedo demais; hoje nenhuma ferramenta conferível é assim.
- A fila do coordenador é por processo; dois processos da FRIDAY no mesmo cofre não se coordenam.
- Tarefas de nível ≥ 2 perdem os argumentos no reinício (decisão de privacidade da Fase 2): o dono pede de novo.

## Como validar
```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_retomada.py'
python3 reports/evidencias/cenarios/fase5_6/necessidade_de_retomada.py --depois
```
Mutação (33 mutantes, todos detectados; 2 camadas redundantes sobrevivem de propósito e estão marcadas): `reports/evidencias/cenarios/fase5_6/mut_retomada.py`, resultado em `reports/evidencias/logs/fase5_6/mut_retomada.log`; roda com `mutar.py` da pasta `fase3_4`.

Relatório da fase (decisões, números, limites): [FASE_5_6_ENTREGA.md](../reports/FASE_5_6_ENTREGA.md).
