# Provedor Groq (API externa, modelos Llama)

A FRIDAY pode usar a API da Groq como alternativa independente à OpenAI e à Anthropic/Claude. A chamada é feita pelo endpoint compatível com Chat Completions da Groq; o modelo padrão é `llama-3.3-70b-versatile`. Confirme os modelos ativos e os limites no painel/documentação oficial da Groq antes de uso.

## Configuração

1. Crie uma conta e uma chave em https://console.groq.com/.
2. Copie `.env.example` para `.env` se ainda não existir.
3. Defina `IA_PROVEDOR=groq`, `GROQ_API_KEY=sua_chave` e, opcionalmente, `GROQ_MODEL=llama-3.3-70b-versatile`.
4. Restrinja permissões do arquivo: `chmod 600 .env`.
5. Instale dependências e faça um teste manual:

```bash
python -m pip install requests python-dotenv
python scripts/perguntar_groq.py 'Explique o que a FRIDAY faz'
```

No Termux, use os mesmos comandos na pasta do projeto. A integração não precisa do SDK Groq nem de uma chave OpenAI/Anthropic.

## Integração com a FRIDAY

Com `IA_PROVEDOR=groq`, o cérebro conversacional e a função de resumo usam Groq quando `GROQ_API_KEY` está definida. A opção é explícita: não usa a chave Anthropic como fallback. Se `IA_MODO=auto`, uma falha da nuvem pode levar ao modelo local Ollama; `IA_MODO=nuvem` não faz fallback local.

As chamadas de ferramentas continuam passando por `TAR.executar_registrado`, isto é, pelo corretor de segurança existente. A integração não concede permissões novas ao modelo. A visão por nuvem continua desativada para o provedor Groq nesta integração; use um modelo local de visão ou mantenha outro provedor configurado explicitamente.

## Privacidade e custos

As mensagens enviadas para Groq saem do aparelho e são processadas pelo serviço externo. Não envie senhas, chaves, dados bancários ou conteúdo sensível. Verifique termos, retenção, limites e preço no painel da Groq. O código não grava a chave em logs nem no repositório; nunca compartilhe o arquivo `.env`.

## Diagnóstico

- `GROQ_API_KEY não configurada`: preencha a variável no `.env` e confirme que o processo carrega esse arquivo.
- `Falha na chamada à Groq`: verifique rede, chave, cota e disponibilidade do modelo. A mensagem de erro não imprime a chave nem o corpo privado da requisição.
- Para rodar testes sem rede: `pytest -q tests/test_provedor_groq.py`.
