# Núcleo (`friday/nucleo.py`) — camada observacional integrada

O núcleo está integrado ao `main.py`, mas **não é um escalonador**. Ele registra sinais de atenção sem armazenar o texto integral do usuário, mantém um foco observacional e oferece consultas sobre atenção/arquitetura. A integração não cria o hub do pré-córtex e não interfere na execução.

## Limites de responsabilidade

| Camada | Responsabilidade | O que não faz |
|---|---|---|
| Núcleo (`nucleo.py`) | Atenção, habituação e observabilidade | Não bloqueia impulsos, tarefas ou workers |
| Pré-córtex (`pre_cortex/`) | Planejamento distribuído entre neurônios/processos, revisão e execução conforme o fluxo aprovado | Não é substituído pelo núcleo |
| Coordenador (`coordenador.py`) | Reserva exclusiva apenas de recursos conflitantes e avaliação de propostas | Não serializa ações independentes |
| Broker (`broker.py`) | Validação, autorização e execução de ferramentas | Não recebe autoridade do núcleo |

## Integração

- `main.processar()` registra `fala:pedido` com resumo fixo; o conteúdo integral da fala não é enviado ao núcleo.
- `NC.tratar()` responde consultas sobre foco e arquitetura.
- `estado_completo()` expõe `nucleo` no painel sem criar o hub do pré-córtex.
- `agir()` e `ocupado()` são métricas de atividade. `liberar()` permanece permissivo por compatibilidade e **nunca deve ser usado como trava**.
- `NUCLEO=0` desliga o cálculo de atenção, não o pré-córtex, os workers, o coordenador ou a FRIDAY.

## Garantias e testes

`tests/test_nucleo_concorrencia.py` verifica que impulsos simultâneos não se bloqueiam e que a observação não captura o texto do usuário. `tests/test_coordenador.py` continua verificando a exclusão mútua por recurso: ações que disputam o mesmo recurso esperam; ações independentes seguem em paralelo.

O pré-córtex distribuído permanece controlado por `PRECORTEX_MODO` e `PRECORTEX_WORKERS`, sem dependência do núcleo. Não desligue nem altere essas configurações para usar a camada de atenção.
