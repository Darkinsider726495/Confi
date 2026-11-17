# FRIDAY — comunicação por eventos entre neurônios

**Fase 2 · 17/11/2026**

## Objetivo

Permitir que os neurônios do pré-córtex recebam sinais de contexto sem transformar o núcleo em escalonador, sem substituir o transporte distribuído e sem serializar objetivos.

## Arquitetura

1. O hub registra o evento no armazém como já fazia.
2. Em seguida, publica uma cópia de metadados para cada neurônio roteado, local ou remoto.
3. Cada destino recebe um envelope `precortex/1` com `tipo="evento"`, separado dos pedidos normais.
4. O worker deduplica eventos numa cache própria e agenda `Neuronio.receber_evento()` no seu pool de trabalho.
5. A implementação base de `Neuronio` mantém os últimos 32 eventos numa janela local. Cada neurônio pode sobrescrever o hook e chamar `super()` para conservar essa janela.
6. A coordenação continua no hub; os neurônios não recebem acesso ao corretor por causa dos eventos.

## Garantias e limites

- **Não substitui o modo distribuído:** as mensagens continuam passando pelo mesmo roteador, destino HTTP/local e contrato JSON.
- **Não cria fila global de objetivos:** eventos usam pool próprio, separado do pool que executa objetivos.
- **Não bloqueia fases:** o fan-out é assíncrono e limitado a 64 envios em voo. Se o limite estiver cheio ou um worker estiver indisponível, a notificação pode ser descartada; o evento original já foi persistido no armazém.
- **Deduplicação:** o mesmo id de evento não dispara o hook duas vezes no mesmo processo worker. A cache é limitada e volátil.
- **Privacidade:** o hub só distribui `evento`, `fase`, `ciclo` e uma allowlist de campos escalares (`estado`, `modulo`, `recuperavel`, `tipo_objetivo`, `suportado`). Campos como `texto`, descrição do objetivo, plano, argumentos, conteúdo de conversa e memória não são propagados.
- **Sem autorização implícita:** eventos são informativos. Não executam ferramentas, não autorizam ações, não alteram a crítica, o verificador ou o corretor.
- **Sem replay ainda:** a persistência dos eventos é mantida, mas não há reentrega automática dos eventos antigos a um worker que reinicie. A janela local é reconstruída a partir dos eventos novos.

## Pontos de extensão

Um neurônio pode reagir a eventos sobrescrevendo:

```python
def receber_evento(self, evento, ctx):
    super().receber_evento(evento, ctx)
    # Atualize apenas contexto derivado e seguro; não execute ferramentas aqui.
```

Para ler sua janela local:

```python
eventos = self.eventos_recentes(limite=10)
```

## Testes adicionados

`tests/test_pre_cortex_eventos.py` verifica:

- recepção assíncrona;
- deduplicação;
- cache de eventos separada da cache de pedidos;
- transporte HTTP entre processos;
- fan-out do hub para os oito neurônios de mensagem no modo local;
- filtragem de campos privados no payload distribuído.

A coordenação é o nono papel arquitetural, executado no hub; ela não é um destinatário de mensagens como os oito neurônios de processamento.
