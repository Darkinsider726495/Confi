# FRIDAY — melhorias arquiteturais (17/11/2026)

## Objetivo

Integrar atenção/observabilidade sem desligar, substituir ou serializar o pré-córtex distribuído.

## Mudanças

1. `friday/nucleo.py` agora é uma camada observacional. `liberar()` é sempre permissiva e existe apenas por compatibilidade; não deve ser usada como mecanismo de execução.
2. `friday/main.py` registra a chegada de cada pedido com uma chave única e um resumo fixo. O texto integral da fala não é enviado ao núcleo. O registro não é uma condição para responder.
3. `NC.tratar()` é consultado no fluxo determinístico para perguntas sobre foco/arquitetura.
4. `estado_completo()` expõe `nucleo` no painel, sem instanciar o hub distribuído.
5. `pre_cortex.fachada` permanece integrado e independente. `PRECORTEX_MODO` e `PRECORTEX_WORKERS` não foram alterados.
6. `coordenador.py` continua reservando somente recursos que entram em conflito; ações independentes continuam paralelas.
7. Atualizados `docs/NUCLEO.md`, `docs/ARQUITETURA.md`, `docs/COORDENADOR.md`, `docs/PRE_CORTEX.md` e a auditoria correspondente.

## Segurança e limites

- Núcleo não executa ferramentas, não autoriza operações e não controla workers.
- `NUCLEO=0` desativa o registro no foco; não desliga a FRIDAY nem o pré-córtex.
- A confirmação de ações sensíveis continua no broker/corretor.
- O pacote não inclui `.env`, token local, banco de dados pessoal, cache ou `.venv`.

## Verificações realizadas

| Suíte | Resultado |
|---|---:|
| `test_nucleo_concorrencia.py` | 4 passaram |
| `test_coordenador.py` | 43 passaram |
| `test_pre_cortex_neuronios.py` | 26 passaram |
| `test_pre_cortex_fluxo.py` | 30 passaram |
| `test_pre_cortex_distribuido.py` | 18 passaram |
| `test_pre_cortex_painel.py` | 15 passaram |
| `test_docs.py` | 5 passaram |
| `auditoria_achados.py` | achado 13 resolvido |

Os testes do pré-córtex distribuído foram executados com processos trabalhadores reais e passaram, incluindo queda/retorno de worker e execução completa entre processos. A suíte global de todos os testes ultrapassou o limite de execução do ambiente; não é reportada como integralmente aprovada.

## Como validar no seu Linux/Termux

```bash
python -m py_compile friday/main.py friday/nucleo.py
PYTHONPATH=tests python -m unittest discover -s tests -p 'test_nucleo_concorrencia.py'
PYTHONPATH=tests python -m unittest discover -s tests -p 'test_coordenador.py'
PYTHONPATH=tests python -m unittest discover -s tests -p 'test_pre_cortex_*.py'
```

O último comando pode levar mais tempo por iniciar processos trabalhadores locais. Não remova `PRECORTEX_MODO=distribuido` nem `PRECORTEX_WORKERS` para aplicar estas mudanças.


## Fase 2 — comunicação por eventos (17/11/2026)

Foi adicionada publicação/assinatura assíncrona de metadados entre os oito neurônios de mensagem e os trabalhadores locais/remotos. O nono papel é a coordenação no hub. O contrato `precortex/1` recebe `tipo="evento"`; pedidos e execução continuam no caminho anterior. Cada worker deduplica eventos separadamente e cada neurônio mantém uma janela local de até 32 eventos.

O fan-out usa pool separado e limite de 64 envios em voo. Só metadados permitidos são propagados; texto, descrição, plano, argumentos e memória não entram no evento. A entrega é best-effort: evento persistido continua no armazém, mas não existe replay automático para worker que reinicia. Os hooks atuais guardam contexto; respostas mais inteligentes exigem implementação específica por neurônio e não são presumidas.

Verificação desta fase: `compileall` OK; `test_pre_cortex_eventos.py` 5 aprovados; `test_pre_cortex_distribuido.py` 18 aprovados; `test_nucleo_concorrencia.py` 4 aprovados (27 no total). `test_pre_cortex_fluxo.py` ultrapassou 200 segundos durante `test_so_planejar_nao_executa_nada`, portanto não foi declarada integralmente aprovada. Ver `RELATORIO_FASE2_EVENTOS.md` e `docs/ARQUITETURA_EVENTOS.md`.
