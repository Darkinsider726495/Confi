# Ponte híbrida da FRIDAY (Ollama + Groq)

## Fluxo
A API local autenticada oferece `POST /v1/ia/chat`. A ponte tenta Ollama local primeiro e, se não responder, pode recorrer à Groq. Não há tool calling nesse endpoint; ele só devolve texto. A integração com ações da FRIDAY continua no fluxo de `cerebro.py` e no corretor existente.

## Configuração
1. Instale/execute Ollama localmente e baixe o modelo escolhido, por exemplo `ollama pull llama3.2:3b`.
2. Copie `.env.example` para `.env`, configure `GROQ_API_KEY` se quiser fallback externo e `FRIDAY_API_TOKEN` com token aleatório de pelo menos 24 caracteres.
3. Carregue `.env` no ambiente do shell (o módulo HTTP não carrega `.env` automaticamente):

```bash
set -a
. ./.env
set +a
chmod 600 .env
python -m friday.api_evolutiva
```

## Chamar a ponte
```bash
curl -s http://127.0.0.1:8765/v1/ia/chat \
  -H "Authorization: Bearer $FRIDAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Explique o que é uma API REST em três frases."}'
```

A resposta indica `provider` como `ollama` ou `groq`, sem incluir a chave.

## Privacidade e segurança
- O padrão é `FRIDAY_HYBRID_ORDER=local_first`.
- O fallback externo vem habilitado para a experiência híbrida; solicitações enviadas ao Groq saem do dispositivo. Para não enviar conteúdo à nuvem, configure `FRIDAY_HYBRID_CLOUD_FALLBACK=no`.
- Não use `0.0.0.0` sem controles de rede. A API exige bearer token e mantém limites de tamanho.
- O endpoint não executa ferramentas, comandos ou código gerado. O endpoint de candidatos continua somente enfileirando mudanças.
- A ponte não copia nem transfere o modelo de IA para o celular; ela envia texto a um modelo já instalado localmente ou a um provedor externo.
