# Núcleo (`friday/nucleo.py`) — camada observacional integrada

O núcleo está integrado ao `main.py` e **não é um escalonador**: nada nele é fila. Ele registra sinais de atenção sem armazenar o texto integral do usuário e mantém um foco observacional. **O sistema distribuído mora dentro dele:** `NC.iniciar()` sobe, na partida, o pré-córtex distribuído (hub + nove neurônios, cada objetivo na sua linha) e o ciclo da **autonomia total**.

## Limites de responsabilidade

| Camada | Responsabilidade | O que não faz |
|---|---|---|
| Núcleo (`nucleo.py`) | Atenção, habituação e observabilidade | Não bloqueia impulsos, tarefas ou workers |
| Pré-córtex (`pre_cortex/`) | Planejamento distribuído entre neurônios/processos, revisão e execução conforme o fluxo aprovado | Não é substituído pelo núcleo |
| Coordenador (`coordenador.py`) | Reserva exclusiva apenas de recursos conflitantes e avaliação de propostas | Não serializa ações independentes |
| Broker (`broker.py`) | Validação, autorização e execução de ferramentas | Não recebe autoridade do núcleo |

## Autonomia total (pedido do dono)

| | Desligada (padrão) | Ligada |
|---|---|---|
| Objetivos que ela mesma propõe, nível ≤ 1, nada fora do aparelho | esperam «aprova o objetivo N» | o núcleo aprova sozinho e executa **em paralelo** (até 4 ao mesmo tempo), sem esperar ordem |
| Ação de nível 2+ (mensagem, ligação, arquivo do dono, dinheiro) | o corretor pede o dono | **continua pedindo o dono** |
| Plano do pré-córtex distribuído que a crítica marca como de risco | espera «autorizo o plano…» | continua esperando |
| Ação local de baixo impacto no pré-córtex distribuído | já roda sem esperar | igual |

- **Só o dono liga e desliga, por voz:** «liga a autonomia total» / «desliga a autonomia total»; «como está a autonomia total?». «sim», «pode», «liga a autonomia» (sem «total») não ligam. Fica gravado em `.cerebro/nucleo_autonomia.json`.
- Caminho único: `nucleo.ciclo_autonomo()` → `objetivos.aprovar_pela_autonomia()` → `planejador.executar_objetivo(autorizado_por="autonomia_do_dono", nivel_max ≤ 1)` → corretor. A função recusa se o modo estiver desligado, se a proposta tiver `nivel_max > 1` ou `acao_externa`. O planejador recusa qualquer outro `autorizado_por`.
- Tudo o que ela notar fica no registro de atividades do pré-córtex (`.cerebro/atividades.jsonl`); a proposta guarda `decidida_por: autonomia_total`.
- Testes: `test_objetivos.AutonomiaTotal` (desligada não executa; só a frase explícita liga; limite de nível e de ação externa; planejador recusa outros; três objetivos rodando ao mesmo tempo) e `test_nucleo_concorrencia.SistemaDistribuidoDentroDoNucleo`.

## Integração

- `main.processar()` registra `fala:pedido` com resumo fixo; o conteúdo integral da fala não é enviado ao núcleo.
- `NC.tratar()` responde consultas sobre a arquitetura. As perguntas de foco são do pré-córtex, que roda antes em `processar()` e assimila cada sinal notado (`NC.assinar(ao_entrar=PFC.assimilar)`), guardando-o como registro de atividade em `.cerebro/atividades.jsonl` (ver `docs/PREFRONTAL.md`).
- `estado_completo()` expõe `nucleo` no painel sem criar o hub do pré-córtex.
- `agir()` e `ocupado()` são métricas de atividade. `liberar()` permanece permissivo por compatibilidade e **nunca deve ser usado como trava**.
- `NC.iniciar()` (na partida) sobe o hub do pré-córtex distribuído e o ciclo autônomo; erro no hub não derruba a partida e aparece em `painel()["distribuido"]`.
- `NUCLEO=0` desliga o cálculo de atenção, não o pré-córtex, os workers, o coordenador ou a FRIDAY.

## Garantias e testes

`tests/test_nucleo_concorrencia.py` verifica que impulsos simultâneos não se bloqueiam e que a observação não captura o texto do usuário. `tests/test_coordenador.py` continua verificando a exclusão mútua por recurso: ações que disputam o mesmo recurso esperam; ações independentes seguem em paralelo.

O pré-córtex distribuído permanece controlado por `PRECORTEX_MODO` e `PRECORTEX_WORKERS`, sem dependência do núcleo. Não desligue nem altere essas configurações para usar a camada de atenção.
