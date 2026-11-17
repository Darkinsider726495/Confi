# Relatório técnico — FRIDAY, fase 3: memória coletiva e aprendizagem distribuída

**Data:** 17 de novembro de 2026  
**Base:** pacote `FRIDAY-fase2-arquitetura-eventos.zip` fornecido na conversa  
**Objetivo:** ampliar a arquitetura de eventos com memória operacional coletiva, relações observadas entre neurônios e recuperação de contexto após reinicializações, sem desligar nem substituir o pré-córtex distribuído.

## 1. Resultado

A fase 3 adiciona uma camada de memória coletiva descritiva. Ela aprende padrões operacionais observados — frequências de eventos, transições e ligações de roteamento entre neurônios — e ajuda a reconstituir o contexto recente quando workers são iniciados ou reiniciados.

A aprendizagem não reescreve código, não muda parâmetros de segurança, não aprova planos e não autoriza ferramentas. Qualquer adaptação comportamental futura deve passar por revisão e testes independentes.

## 2. Componentes implementados

| Arquivo | Alteração |
|---|---|
| `friday/pre_cortex/memoria_coletiva.py` | Índice persistente de frequências, transições e conexões observadas entre neurônios; projeção de metadados permitidos |
| `friday/pre_cortex/hub.py` | Integração com o armazém, reconstrução incremental do índice, replay local e replay após mudança de PID de worker remoto |
| `tests/test_memoria_coletiva.py` | Sete testes de privacidade, persistência, transições, conexões e replay após reinício |
| `docs/MEMORIA_COLETIVA_E_REPLAY.md` | Documentação da camada e dos limites |

A fase 2 permanece incluída: `neuronio.py`, `transporte.py`, `hub.py`, `tests/test_pre_cortex_eventos.py` e o contrato de eventos continuam integrados.

## 3. Memória coletiva: o que aprende

- Frequência de cada tipo de evento operacional.
- Transições observadas entre tipos de evento por objetivo.
- Conexões de roteamento entre neurônios, calculadas a partir da sequência real de mensagens endereçadas (`para`/`neuronio`).
- Janela recente de metadados para fornecer contexto aos neurônios.

As conexões representam coocorrência/sequência de roteamento observada. Não provam causalidade, qualidade de raciocínio ou competência cognitiva.

## 4. Persistência sem bloquear o fluxo

O índice agregado é salvo em `memoria_coletiva.json` por gravação atômica. As atualizações são agrupadas por um gravador em segundo plano; o caminho síncrono de cada evento atualiza somente o estado em memória e sinaliza o gravador. No encerramento do hub, o último lote é descarregado.

Se o processo cair antes da gravação do índice, o hub reconcilia o índice com os eventos posteriores disponíveis no `eventos.jsonl` na próxima inicialização. O log de eventos continua sendo a fonte para reconstrução.

## 5. Recuperação de contexto

- Workers locais recebem até oito eventos recentes e seguros por neurônio na montagem do hub.
- No modo distribuído, o hub observa a saúde dos workers. Quando detecta uma nova identidade de processo (PID + instante de início), reenvia a janela recente ao worker recuperado.
- O replay usa o contrato existente `precortex/1` e `tipo="evento"`; não converte eventos em pedidos e não passa pela fila de objetivos.
- A deduplicação de eventos permanece separada da deduplicação de pedidos.

## 6. Privacidade e segurança

A projeção permite somente campos escalares explicitamente listados. Texto livre, descrição de objetivo, argumentos, planos, conteúdo de conversa, tokens e credenciais não entram na memória coletiva nem no replay. Os limites de crítica, autorização do dono, corretor, verificador e coordenador não foram removidos nem contornados.

A configuração `PRECORTEX_MODO` e `PRECORTEX_WORKERS` não foi alterada. O pacote não deve ser considerado configurado em modo distribuído por padrão: o modo efetivo continua dependendo do `.env`/ambiente da instalação. Preserve as definições existentes ao atualizar o projeto.

## 7. Testes executados

`python -m compileall -q friday` — aprovado.

| Suíte | Testes aprovados |
|---|---:|
| `test_memoria_coletiva.py` | 7 |
| `test_pre_cortex_eventos.py` | 5 |
| `test_pre_cortex_distribuido.py` | 18 |
| `test_nucleo_concorrencia.py` | 4 |
| `test_pre_cortex_fluxo.py` | 30 |
| `test_pre_cortex_neuronios.py` | 26 |
| **Total focado** | **90** |

Cada uma das seis suítes acima foi executada separadamente e terminou com sucesso. A suíte completa de todos os testes também foi iniciada, mas ultrapassou o limite de execução de 200 segundos durante `test_conversa.py`; por isso, não declaro a suíte global aprovada.

## 8. Como validar no Linux/Termux

Na raiz `friday-pi/`:

```bash
python -m compileall -q friday
python -m unittest discover -s tests -p 'test_memoria_coletiva.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_eventos.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_distribuido.py' -v
python -m unittest discover -s tests -p 'test_nucleo_concorrencia.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_fluxo.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_neuronios.py' -v
```

Para preservar o modo distribuído existente, não remova nem substitua `PRECORTEX_MODO=distribuido` ou `PRECORTEX_WORKERS` na configuração da instalação.

## 9. Limitações e próxima fase

- O grafo atual representa rotas observadas, não uma rede neural treinável.
- A aprendizagem é estatística e descritiva; não altera pesos, políticas ou decisões.
- O replay usa uma janela curta de oito eventos por neurônio; não é uma reconstrução integral de todo o histórico.
- A memória coletiva não substitui a memória semântica/RAG ou as experiências já existentes.
- Próxima etapa recomendada: permitir que neurônios consultem uma API tipada de memória coletiva e registrem hipóteses avaliáveis, mantendo a crítica independente e a revisão humana para qualquer mudança de comportamento.

**Status:** implementação da fase 3 concluída e suítes focadas aprovadas. Ainda é necessário validar a instalação real no Linux/Termux do usuário; não houve implantação no dispositivo.
