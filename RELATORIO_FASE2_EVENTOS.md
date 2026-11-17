# Relatório técnico — FRIDAY, fase 2 da arquitetura distribuída

**Data:** 17 de novembro de 2026  
**Escopo:** adicionar comunicação por eventos entre os neurônios sem desligar nem substituir o pré-córtex distribuído.

## 1. Resultado

Foi implementada uma camada de publicação/assinatura (pub/sub) de metadados sobre o contrato de mensagens existente `precortex/1`.

O hub persiste os eventos e publica notificações independentes para os neurônios roteados. Os workers recebem `tipo="evento"`, fazem deduplicação separada das mensagens de pedido e executam o hook do neurônio em paralelo. A implementação base conserva uma janela local limitada aos 32 eventos mais recentes.

## 2. Arquivos alterados

| Arquivo | Alteração |
|---|---|
| `friday/pre_cortex/neuronio.py` | Hook `receber_evento()` e leitura `eventos_recentes()` |
| `friday/pre_cortex/transporte.py` | Recepção assíncrona de eventos e cache de deduplicação separada |
| `friday/pre_cortex/hub.py` | Fan-out para os neurônios locais e remotos, com pool e limite próprios |
| `tests/test_pre_cortex_eventos.py` | Cinco testes de evento, deduplicação, HTTP e fan-out |
| `docs/ARQUITETURA_EVENTOS.md` | Documentação do contrato, limites e pontos de extensão |

## 3. Preservação da arquitetura existente

- O pré-córtex distribuído permanece ativo e configurável pelos mesmos parâmetros `PRECORTEX_MODO` e `PRECORTEX_WORKERS`.
- O contrato JSON existente foi estendido usando o tipo `evento`; pedidos continuam no caminho anterior.
- O núcleo (`nucleo.py`) continua observacional e não controla workers, tarefas ou execução.
- O coordenador continua reservando somente recursos conflitantes.
- Crítica, autorização do dono, corretor e verificador não foram contornados.
- O evento não contém o texto integral do usuário, descrição do objetivo, plano, argumentos ou memória.

## 4. Limites conhecidos

Esta fase entrega fan-out assíncrono e contexto recente local, não uma memória global compartilhada. O limite de 64 envios em voo evita crescimento ilimitado de trabalho; ao atingir o limite, eventos de notificação podem ser descartados, mas o evento de origem já foi persistido pelo armazém. A cache de deduplicação e a janela dos neurônios são voláteis. Ainda não há replay/reconstrução automática do contexto quando um worker reinicia.

Os hooks base armazenam metadados; os neurônios atuais ainda precisam de implementações específicas para transformar cada evento em inferências úteis. Nenhum ganho cognitivo ou de qualidade de respostas deve ser presumido apenas pela entrega do mecanismo.

## 5. Verificações executadas nesta fase

| Verificação | Resultado |
|---|---:|
| `python -m compileall -q friday` | OK |
| `test_pre_cortex_eventos.py` | 5 aprovados |
| `test_pre_cortex_distribuido.py` | 18 aprovados |
| `test_nucleo_concorrencia.py` | 4 aprovados |
| **Total das três suítes focadas** | **27 aprovados** |

A suíte `test_pre_cortex_fluxo.py` foi iniciada, mas a execução ultrapassou o limite de 200 segundos durante `test_so_planejar_nao_executa_nada`. Não há base para declarar a suíte completa aprovada nem para classificar esse encerramento por timeout como falha de código.

## 6. Como validar no Linux/Termux

Na raiz do projeto:

```bash
python -m compileall -q friday
python -m unittest discover -s tests -p 'test_pre_cortex_eventos.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_distribuido.py' -v
python -m unittest discover -s tests -p 'test_nucleo_concorrencia.py' -v
```

Para verificar o fluxo completo, executar separadamente:

```bash
python -m unittest discover -s tests -p 'test_pre_cortex_fluxo.py' -v
```

Não remova nem altere `PRECORTEX_MODO=distribuido` ou `PRECORTEX_WORKERS` para aplicar esta fase.

## Continuidade

A fase 3 amplia esta camada com memória coletiva descritiva, relações observadas entre neurônios e replay de contexto após reinicializações. Consulte `RELATORIO_TECNICO_FRIDAY_FASE3.md` e `docs/MEMORIA_COLETIVA_E_REPLAY.md`.
