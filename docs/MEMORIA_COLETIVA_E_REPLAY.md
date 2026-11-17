# Memória coletiva, relações e recuperação de contexto

## Objetivo

Adicionar memória operacional compartilhada ao pré-córtex sem substituir o hub, o transporte HTTP, os workers ou o escalonador distribuído.

## O que a memória aprende

`pre_cortex/memoria_coletiva.py` mantém estatísticas descritivas derivadas de eventos:

- frequência de tipos de evento;
- transições observadas entre tipos de evento por objetivo;
- conexões entre neurônios inferidas da sequência real de mensagens roteadas (`para`/`neuronio`);
- sequência recente de metadados para contexto.

As conexões são evidência de roteamento observado, não uma alegação de causalidade ou competência cognitiva.

## Persistência e reconstrução

O índice agregado é salvo atomicamente em `memoria_coletiva.json`. Se o índice não existir, é reconstruído a partir do `eventos.jsonl` disponível no armazém. No arranque de workers locais, o hub reenvia uma janela curta de oito eventos seguros por neurônio. No modo distribuído, `atualizar_saude()` detecta um PID novo e reenvia a janela ao worker que voltou.

O replay usa o contrato `precortex/1` e mensagens `tipo="evento"`; não entra na fila de objetivos nem altera a execução de pedidos.

## Privacidade e limites

A projeção aceita somente campos escalares explicitamente permitidos. Texto livre, descrição de objetivo, argumentos, planos, memória de conversa, tokens e credenciais não entram no índice nem no replay. A memória não executa ferramentas, não aprova planos e não modifica parâmetros de segurança. A aprendizagem é observacional e precisa de uma etapa separada de validação antes de qualquer adaptação comportamental.

O índice é um resumo estatístico. O log `eventos.jsonl` continua sendo a fonte para reconstrução; se o histórico for arquivado pelo recurso de limpeza do cenário, o índice agregado existente permanece separado e não é apagado automaticamente.

## Verificação

Executar na raiz do projeto:

```bash
python -m compileall -q friday
python -m unittest discover -s tests -p 'test_memoria_coletiva.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_eventos.py' -v
python -m unittest discover -s tests -p 'test_pre_cortex_distribuido.py' -v
python -m unittest discover -s tests -p 'test_nucleo_concorrencia.py' -v
```

A suíte de fluxo completo deve ser executada separadamente; não declarar cobertura global com base apenas nas suítes focadas.
