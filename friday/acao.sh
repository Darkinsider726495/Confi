#!/bin/sh
# Chamado pelos botões da notificação do Android:  sh acao.sh ouvir | cancelar | confirmar_voz <id da pendência>
# O «Confirmo» só vale para a pendência cujo id vai no botão (o id é hexadecimal; qualquer outro caractere é descartado).
DIR=$(cd "$(dirname "$0")" && pwd)
TOK=$(cat "${FRIDAY_TOKEN_ARQ:-$DIR/.token}") || exit 1
ID=$(printf '%s' "${2:-}" | tr -cd '0-9a-f')
CORPO='{}'
[ -n "$ID" ] && CORPO="{\"id\":\"$ID\"}"
exec curl -s -m 60 -X POST -H "X-Friday-Token: $TOK" -H 'Content-Type: application/json' -d "$CORPO" "http://127.0.0.1:${HUD_PORTA:-8080}/$1" >/dev/null
