# API autoevolutiva local da FRIDAY

Esta API é uma camada HTTP de controle para o motor de evolução local. Ela **não usa OpenAI, Anthropic ou qualquer API de modelo**. Recebe candidatos preparados por uma ferramenta externa/local, valida o alvo contra a allowlist e coloca o código em quarentena usando `friday.gerador_local`.

## Segurança por padrão

- Escuta em `127.0.0.1:8765`, não na rede.
- Exige `Authorization: Bearer ...` em todos os endpoints, exceto `/health`.
- `POST /v1/candidates` apenas enfileira. Não executa nem promove o código recebido.
- Promoção continua local e explícita com `python scripts/evoluir.py promover ...`.
- `PUT`/`DELETE` não promovem nem apagam candidatos/backups.
- Tamanho máximo de corpo: 600 KB.
- O endpoint não registra token, corpo ou código-fonte.
- O staging de testes não é um sandbox de kernel. Promova apenas candidatos confiáveis.

## Configurar no Termux

Na raiz `friday-pi`:

```bash
cp .env.example .env
nano .env
```

Adicione um token aleatório com pelo menos 24 caracteres. Exemplo de geração:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copie o resultado para `FRIDAY_API_TOKEN` no `.env` e proteja o arquivo:

```bash
chmod 600 .env
```

Carregue o `.env` no ambiente (se a inicialização da FRIDAY já usa `python-dotenv`, aproveite o mesmo mecanismo):

```bash
set -a
. ./.env
set +a
python -m friday.api_evolutiva
```

A API precisa estar no mesmo ambiente Python do projeto. Se a execução via `python -m` não encontrar `.env`, exporte as variáveis explicitamente; o módulo não lê `.env` sozinho para evitar depender de um pacote adicional.

## Endpoints

- `GET /health` — saúde básica, sem autenticação.
- `GET /v1/status` — alvos permitidos/protegidos e contagem de candidatos.
- `GET /v1/candidates` — lista a fila.
- `POST /v1/candidates` — adiciona candidato JSON com `target`, `source`, `description`.

Exemplo:

```bash
curl -s http://127.0.0.1:8765/v1/status \
  -H "Authorization: Bearer $FRIDAY_API_TOKEN"
```

Adicionar candidato (apenas fila; não é executado):

```bash
python - <<'PY'
import json, os, urllib.request
payload = {
    "target": "friday/memoria.py",
    "source": "'''"""Módulo candidato de exemplo."""\n\ndef exemplo():\n    return 'ok'\n'''",
    "description": "Candidato de exemplo"
}
req = urllib.request.Request(
    "http://127.0.0.1:8765/v1/candidates",
    data=json.dumps(payload).encode(),
    headers={"Content-Type":"application/json", "Authorization":"Bearer " + os.environ["FRIDAY_API_TOKEN"]},
    method="POST",
)
print(urllib.request.urlopen(req).read().decode())
PY
```

## Promoção

Veja o ID na resposta e faça a promoção local depois de revisar o diff e confiar no código:

```bash
python scripts/evoluir.py fila
python scripts/evoluir.py promover cand-ID --suite pytest --timeout 300
```

**Não exponha a API à internet.** Para uso remoto, prefira túnel privado com autenticação e firewall. A opção `FRIDAY_API_ALLOW_REMOTE=yes` apenas remove a trava de bind; não configura TLS, firewall nem proteção contra abuso.
