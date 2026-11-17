# Pré-córtex distribuído (`friday/pre_cortex/`)

Nove módulos de software («neurônios») que colaboram por **mensagens JSON** para transformar um pedido em objetivo, levantar hipóteses, planejar, revisar, executar **pelo corretor**, conferir o efeito por fora e aprender com a diferença entre o previsto e o observado. Roda no mesmo processo (modo local) ou com neurônios em **processos separados** falando HTTP (modo distribuído). Tem uma tela no navegador (`/precortex`) que mostra o que acontece, com dados reais.

**O que isto não é.** Não é consciência, vontade própria nem inteligência humana: são regras, contagens e um currículo interno, escritos em código e auditáveis. A «confiança» de uma hipótese é uma contagem suavizada `(sucessos+1)/(n+2)`, **não** uma probabilidade calibrada. Não há punição nem recompensa: uma falha vira investigação e muda a ordem das estratégias; nenhum peso de modelo é treinado. Não substitui o pré-córtex de vontades (`prefrontal.py`, [PREFRONTAL.md](PREFRONTAL.md)): este aqui é o que planeja e confere **objetivos**.

## Arquitetura

```
                 pedido (voz «pré-córtex: …», painel /precortex, ou API)
                                       │
                                ┌──────▼──────┐  dossiê do objetivo (objetivos.json) + eventos (eventos.jsonl)
                                │     HUB     │  fases, limites, autorização, registro antes de agir
                                └──┬───┬───┬──┘
             mensagens precortex/1 │   │   │  (mesmo envelope nos dois modos; modo local também passa pelo JSON)
        ┌──────────────────────────┘   │   └───────────────────────────┐
┌───────▼─────────────┐   ┌────────────▼───────────┐   ┌───────────────▼──────────────┐
│ trabalhador «hub»   │   │ trabalhador «cognicao» │   │ trabalhador «revisao»        │
│ (sempre no processo │   │ 1 percepção            │   │ 5 crítica                    │
│  do FRIDAY)         │   │ 3 hipóteses            │   │ 7 verificação                │
│ 2 contexto          │   │ 4 planejamento         │   │                              │
│ 8 aprendizagem      │   │ (processo próprio no   │   │ (processo próprio no         │
│ 9 monitoramento     │   │  modo distribuído)     │   │  modo distribuído)           │
└───────┬─────────────┘   └────────────────────────┘   └──────────────────────────────┘
        │ só estes tocam o cofre, as experiências e o corretor
        ▼
  corretor (broker.py) ◄── 6 coordenação/execução: cria UMA tarefa (tarefas.py), registrada antes de agir
```

Os neurônios 2, 8 e 9 precisam do cofre, das experiências e das tarefas; por isso moram sempre no processo do FRIDAY. Os de fora (1, 3, 4, 5, 7) **não importam** o corretor, as tarefas nem o catálogo (teste estático `Pacote.test_neuronios_que_rodam_fora…` e checagem em tempo de execução: `/saude` de cada trabalhador traz `isolamento`). O neurônio 6 (coordenação) é o próprio hub: não é chamado por mensagem.

### Fluxo de um objetivo

```
interpretação ─► conhecimento ─────────────► hipóteses ─► plano ─► revisão ──────────────► autorização ─► execução ─► verificação ─► aprendizagem ─► decisão
  (percepção)    contexto ‖ conteúdo           (3)         (4)     crítica ‖ coerência       (hub)          (corretor)    (7, lê o      (8)            concluir │
                 (2)        (4)                                    (5)       (7)                                         armazenamento)              replanejar ──► volta ao conhecimento
                 em paralelo                                       em paralelo                                                                       pedir o dono
```

- Dependências explícitas: cada etapa vira um nó no grafo do dossiê (`grafo[]`, com `depende_de`). O que é independente roda em paralelo (contexto ‖ conteúdo; crítica ‖ coerência).
- Falha crítica não avança: sem percepção, planejamento, crítica ou verificação o objetivo fica **bloqueado** (recuperável; o vigia retoma sozinho quando o módulo volta, até 3 vezes).
- Contexto, hipóteses e aprendizagem podem faltar: o fluxo segue em **modo degradado** (catálogo puro, sem experiências) e então **toda execução passa a exigir o dono**.
- Limites configuráveis contra replanejamento infinito: `max_replanos`, `max_revisoes_critica`, `max_tempo_objetivo_s`, `max_nos_por_objetivo`; plano repetido (mesma assinatura) é **laço** e bloqueia; esgotadas as estratégias, o objetivo pede o dono (`sem_alternativas`).

### Raciocínio observável

`explicar.py` responde às 12 perguntas (o que resolvo, fatos, o que falta, hipóteses, evidências, alternativas, resultado esperado de cada etapa, o que pode dar errado, por que esta estratégia, como vou verificar, o que aprendi, o que mudou no plano) **só com o dossiê**. Cada item tem tipo (fato, inferência, hipótese, incerteza, desconhecido) e a fonte. Fase que não rodou responde «ainda não sei». O painel e a voz («explique o objetivo pc3») usam a mesma função.

## Os nove neurônios

| # | Neurônio | Onde roda | Crítico? | Responsabilidade | NÃO faz |
|---|---|---|---|---|---|
| 1 | percepção (`percepcao.py`) | cognição | sim | pedido → objetivo estruturado: tipo, parâmetros, efeitos (externo?), o que falta, restrições, critérios de conclusão | não executa, não adivinha contato |
| 2 | contexto (`contexto.py`) | hub | não | fatos (com origem), inferências, desconhecidos, estratégias candidatas e as experiências relevantes por faixa de tamanho | não decide |
| 3 | hipóteses (`hipoteses.py`) | cognição | não | uma hipótese por estratégia, com evidências a favor/contra, incertezas, previsão verificável, condição de revisão; compara e escolhe | não promove hipótese a fato |
| 4 | planejamento (`planejamento.py`) | cognição | sim | gera o conteúdo (currículo interno determinístico) e o plano de 10 campos, assinado por hash | não inventa estratégia fora do catálogo |
| 5 | crítica (`critica.py`) | revisão | sim | regras R1–R14 (completude, hash, catálogo, nível 4, efeitos, sensível, limites, repetição, cobertura, verificação independente, dependências); aprova, devolve ou rejeita, preso ao hash | não autoriza, não executa; **nenhuma configuração a desliga** |
| 6 | coordenação (hub, `fases.py`/`execucao.py`) | hub | — | autorização (dispensada só em ação local de baixo impacto dentro do pedido), registro antes de agir, tarefa única pelo corretor, reanexar depois de queda | não repete ação que pode já ter acontecido |
| 7 | verificação (`verificador.py`) | revisão | sim | coerência do conteúdo antes; depois, **relê o armazenamento real** (banco de notas, pasta, cofre) e compara com cada critério | não aceita «a ferramenta disse ok»; sem leitor independente fica inconclusivo |
| 8 | aprendizagem (`aprendizagem.py`) | hub | não | previsão × observado, fatores tipados («coincide com», nunca «causou»), lições com `n` e condição de revisão, investigações, propostas de teste (não executadas) | não pune nem premia; só ajusta `ordem_de_estrategias`; revogável sem apagar |
| 9 | monitoramento (`monitor.py`) | hub | não | trabalhadores no ar/fora, tempos (médio, p95), taxa de falha, confiança por módulo (base **declarada**, não medida), modo normal/degradado/bloqueado, alertas | não age, não reinicia nada |

Exploração controlada (`exploracao.py`): benefício informacional, custo, impacto, reversibilidade, risco, autorização e critérios de parada para cada opção. Dentro do pedido executa; teste que o dono não pediu vira simulação ou pedido de autorização; o que sai do aparelho ou não se desfaz nunca é automático; ferramenta sem perfil é recusada.

## Mensagens (contrato `precortex/1`, `contrato.py`)

```json
{"contrato": "precortex/1", "id": "m-4a516da1ce3e4fd3", "tipo": "pedido", "correlacao": "pc0001", "plano": {"id": "pl-…", "versao": 2},
 "de": "hub", "para": "critica", "acao": "revisar", "criada_em": 1792870152.75, "expira_em": 1792870227.75, "timeout_s": 15.0,
 "tentativa": 2, "em_resposta_a": null, "estado": "enviada", "corpo": {"plano": {…}}}
```
Resposta: os mesmos campos + `ok`, `erro {codigo, mensagem}`, `processado_por {worker, pid, neuronio}`, `tempos {recebida_em, iniciada_em, concluida_em, duracao_ms}`, `duplicada`.

- **Entrega «ao menos uma vez»**, nunca «exatamente uma vez»: o hub reenvia com o **mesmo id**; o trabalhador guarda as respostas (dedupe, inclusive de duplicata que chega enquanto o original roda); os neurônios cognitivos são idempotentes; a aprendizagem não registra a mesma tentativa duas vezes.
- Ação que não pode repetir (executar pelo corretor) não depende disso: o hub grava `execucoes[hash#versão]` **antes** de criar a tarefa e, depois de uma queda, reanexa à tarefa existente (ou deixa `tarefas.recuperar` olhar o mundo) — nunca repete sozinho.
- Mensagem vencida (`expira_em`) não é processada; objetivo cancelado é recusado (`cancelada`); códigos `timeout`/`indisponivel` são recuperáveis (reenvio); os outros não.
- Cancelamento é cooperativo: o hub avisa todos os trabalhadores; o que não começou é recusado; o que está rodando vê `ctx.cancelado()`.

## Instalar, configurar e iniciar

Nada novo para instalar: só biblioteca padrão (`http.server`, `urllib`, `threading`). Funciona no Termux.

Configuração (padrões do código < arquivo JSON em `PRECORTEX_CONFIG` < variáveis `PRECORTEX_*`); exemplo sem segredos em [`friday/pre_cortex/config.exemplo.json`](../friday/pre_cortex/config.exemplo.json). Valor fora da faixa volta ao padrão e aparece em `avisos` (tela e relatório). Variáveis:

| Variável | Para quê |
|---|---|
| `PRECORTEX_MODO` | `local` (padrão) ou `distribuido` |
| `PRECORTEX_WORKERS` | JSON `{"cognicao": {"url": "http://127.0.0.1:9101"}, "revisao": {"url": "http://127.0.0.1:9102"}}` |
| `PRECORTEX_TOKEN` | chave de sessão entre processos (≥ 16 caracteres). **Só no ambiente**; arquivo de configuração com «token» é ignorado |
| `PRECORTEX_PASTA` | onde guardar dossiês e eventos (padrão: `.cerebro/precortex` no cofre; sem cofre, só na memória) |
| `PRECORTEX_MAX_REPLANOS`, `…_MAX_TEMPO_OBJETIVO_S`, `…_TIMEOUT_MSG_S`, `…_TENTATIVAS_MSG`, `…_RITMO_DEMO_S` … | limites e tempos (`config.py`, `PADROES`/`FAIXAS`) |

**Dentro do FRIDAY** não há nada para iniciar: o hub nasce no primeiro uso (frase, tela ou objetivo gravado a recuperar na partida). Modo distribuído, com os trabalhadores em outros processos:

```bash
export PRECORTEX_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"
python3 -m friday.pre_cortex.worker --nome cognicao --neuronios percepcao,hipoteses,planejamento --porta 9101 &
python3 -m friday.pre_cortex.worker --nome revisao  --neuronios critica,verificador --porta 9102 &
export PRECORTEX_MODO=distribuido PRECORTEX_WORKERS='{"cognicao":{"url":"http://127.0.0.1:9101"},"revisao":{"url":"http://127.0.0.1:9102"}}'
python3 friday/main.py
```
A primeira linha que cada trabalhador imprime é um JSON com `pid`, `porta` e `url`. Por padrão escutam só em 127.0.0.1; outro `--host` expõe a porta na rede **sem cifra** (a chave é a única proteção).

**Tela:** no painel, botão «Neurônios em rede» (ou abra `/precortex` com o mesmo link `#t=…` do painel). Painéis: A mapa dos nove neurônios (ocioso, recebendo, processando, aguardando, concluído, bloqueado, erro — vindos da saúde dos trabalhadores e do grafo do objetivo), B objetivo/plano/etapas/dependências, C fluxo de eventos, D hipóteses, E planejamento (versões, revisão, riscos, alternativas, crítica, coerência, execução), F aprendizagem, 12 perguntas, G estado operacional, H entrada e controles (iniciar, só planejar, autorizar/negar o plano exato, interromper a demonstração = cancelar objetivos, limpar estado temporário = arquivar dossiês e eventos; experiências e memórias não são tocadas). Atualização por consulta periódica (1 s o estado, 0,6 s os eventos). «Concluído»/«erro» ficam visíveis por 3 s (`PERSISTE_S`); como cada neurônio responde em milissegundos, «processando» só aparece em trabalho lento — a demonstração tem `ritmo_demo_s` (pausa **entre** fases, registrada como evento `pausa_demo`, fora do orçamento de tempo) para dar tempo de ver; nenhum estado é inventado pela página.

**Voz:** «pré-córtex: <objetivo>», «pré-córtex planejar: <objetivo>», «autorizo o plano do objetivo pc3» (opcional «versão 2»), «nego o plano do objetivo pc3», «cancele o objetivo pc3», «explique o objetivo pc3», «como está o pré-córtex?». «Sim», «pode», «ok» nunca autorizam.

**API** (mesma chave `X-Friday-Token` do painel; a página só confere o host): `GET /precortex/estado[?id=]`, `GET /precortex/eventos?desde=N[&id=]`, `GET /precortex/objetivo?id=`, `GET /precortex/neuronios`, `POST /precortex/objetivo {texto, so_planejar?, prioridade?}`, `POST /precortex/controle {acao: cancelar|limpar|autorizar|negar|aceitar|executar|retomar, id, versao?, hash?}`. Não existe rota que pare o FRIDAY, o hub ou um trabalhador.

## Demonstração

```bash
python3 -m friday.pre_cortex.demo                     # distribuído: 2 processos trabalhadores + autoconferência (código de saída 0/1)
python3 -m friday.pre_cortex.demo --modo local
python3 -m friday.pre_cortex.demo --ui                # imprime o link da tela e roda devagar (Ctrl-C termina)
python3 -m friday.pre_cortex.demo --ui --sem-cenario  # só a tela
```
Sem credenciais, sem internet, sem API paga; tudo numa pasta temporária (banco, auditoria, cofre, estado), que fica para inspeção. Cenário: (1) plano de estudos de Python, 4 semanas, 90 min/dia — a primeira estratégia («anotar», uma nota só) é **recusada pelo corretor** porque o texto passa de 1000 caracteres; a verificação independente não acha nada, a aprendizagem registra a discrepância e o plano é revisado para «anotar_em_partes», que funciona e é conferido; (2) o mesmo pedido de novo: a experiência já põe «anotar_em_partes» na frente, sem replanejar; (3) SMS: o plano para pedindo a autorização do dono; a demonstração nega e nada é enviado (um `termux-sms-send` de mentira anota qualquer tentativa). Backend: «deterministico»; um modelo de linguagem opcional **não está incluído** (ponto de extensão: `Config["backend"]` só aceita `deterministico` nesta versão).

## Testes

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_pre_cortex_*.py'   # ~20 s; abre processos trabalhadores de verdade
python3 tests/e2e_precortex.py                                                              # Chromium (Playwright)
```
`test_pre_cortex_fluxo` (modo local, fluxo inteiro), `…_neuronios` (cada neurônio isolado), `…_distribuido` (contrato, transporte, processos reais, trabalhador que cai e volta), `…_painel` (API, painel, voz, varreduras do pacote, demonstração nos dois modos). Mutação das defesas novas: `reports/evidencias/logs/fase7/mutacoes.log`.

## Adicionar um neurônio

1. Crie `friday/pre_cortex/<nome>.py` com uma classe `Neuronio` (`nome`, `numero`, `papel`, `responsabilidade`, `entradas`, `saidas`, `confianca`, `critico`, `no_hub`) e métodos `acao_<verbo>(self, corpo, ctx)` que devolvem um objeto JSON e usam `ctx.conferir_cancelamento()` em trabalho longo. Erro esperado: `raise C.ErroNeuronio(codigo, mensagem)`.
2. Registre em `catalogo_neuronios.CLASSES` (e num grupo de `GRUPOS_PADRAO` ou em `NO_HUB` se precisar do cofre/corretor). Neurônio que roda fora **não** pode importar `broker`, `tarefas`, `catalogo` (teste).
3. Chame-o de uma fase (`fases.py`) com `self._no(...)` + `self._chamar_no(...)`, declarando `depende_de`. Se puder faltar, escreva o substituto degradado e exija o dono depois dele.
4. Escreva o teste do neurônio e um do fluxo; para defesa nova, quebre-a de propósito e confira que um teste falha.

## Diagnosticar falhas

- **Objetivo «bloqueado»**: o dossiê diz o tipo (`modulo_indisponivel`, `falha_de_modulo`, `limite_de_*`, `laco_de_replanejamento`, `critica_rejeitou`, `execucao_barrada`, `autorizacao_negada`) e o módulo. Na tela: painel B e «Erros» em G. `retomar` só vale para bloqueio recuperável.
- **Módulo fora**: G mostra o trabalhador «fora do ar» com o erro; `curl -H "X-Precortex-Token: $PRECORTEX_TOKEN" http://127.0.0.1:9101/saude`. HTTP 401 = chave diferente; 421 = host não permitido.
- **«Recusada»**: a chave de sessão do hub não é a dos trabalhadores.
- **Eventos**: `eventos.jsonl` na pasta do pré-córtex (append-only); `objetivos.json` tem o dossiê inteiro.
- **Gravação falhou**: `operacional.armazem.erros` na tela.

## Desligar

O pré-córtex não tem botão de desligar e não para o FRIDAY. Os trabalhadores externos são processos comuns do dono: Ctrl-C ou o gerenciador de processos. Com um trabalhador parado, os objetivos que precisam dele ficam bloqueados (nada executa sem crítica e verificação) e retomam quando ele volta. A parada do FRIDAY continua sendo a do dono (`termux/parar.sh`).

## Local × distribuído

| | local | distribuído |
|---|---|---|
| Onde rodam 1, 3, 4, 5, 7 | threads do processo do FRIDAY | processos `friday.pre_cortex.worker` (HTTP 127.0.0.1) |
| Contrato | o mesmo, passando pelo JSON | o mesmo, pela rede |
| Prova de separação | — | `pid` em cada resposta e evento; `isolamento` na saúde |
| Falhas possíveis | só as do código | processo cai, porta fecha, chave errada, demora de rede |
| Custo | nenhum | 2 processos Python a mais (~poucos MB cada) |

**Mesma máquina ≠ várias máquinas.** Os testes e a demonstração provam comunicação entre **processos** no mesmo computador. Outra máquina exigiria `--host` na rede local, e o tráfego não é cifrado (só a chave) — não foi testado.

## Limitações conhecidas (honestas)

- **Limite do corretor que o pré-córtex não lê.** O corretor recusa qualquer argumento de texto acima de 1000 caracteres quando a ferramenta não declara `maxLength`. Isso vale para `anotar`, `criar_arquivo` (que no código aceita até 100 KB) e `guardar_memoria` (2000): por esse limite, só «anotar_em_partes» guarda um plano de estudo inteiro. O pré-córtex **não** consulta essa validação interna (o corretor é outra autoridade); por isso a primeira tentativa falha de verdade e é aprendida. `catalogo_pc.LIMITES_DECLARADOS` não conhece esse limite. Uma correção possível é declarar `maxLength` nas ferramentas — mexe em `catalogo.py`/corretor e fica para o dono decidir.
- Uma crença anterior, «anotar corta o texto calado», estava errada: o corretor recusa (`tamanho:texto`) e nada é gravado.
- O currículo de estudo é interno e não foi conferido com fonte externa.
- Confianças são contagens pequenas; as confianças-base do monitor são suposições de projeto.
- Sem modelo de linguagem: interpretação por regras cobre só as frases conhecidas (o resto pede esclarecimento).
- Falha parcial natural não acontece neste ambiente; os testes a produzem por injeção (a 2ª parte é recusada).
- Não verificado aqui: celular e Termux reais, reinício real do Android, desempenho em aparelho fraco, várias máquinas.
- `nucleo.py` observa a atenção no processo principal, mas não substitui nem bloqueia este pacote distribuído ([NUCLEO.md](NUCLEO.md)).
