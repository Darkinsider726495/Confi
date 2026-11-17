#!/usr/bin/env bash
# Fixa cada imagem Docker pelo digest (sha256) que você acabou de baixar e testar.
# Uso: docker compose pull && bash fixar-versoes.sh   (depois: docker compose up -d)
# Para atualizar de propósito: apague as linhas IMG_* do .env, rode pull de novo, teste e fixe outra vez.
set -Eeuo pipefail
cd "$(dirname "$0")"
declare -A VAR=([adguard]=IMG_ADGUARD [uptime-kuma]=IMG_KUMA [ntfy]=IMG_NTFY [ollama]=IMG_OLLAMA)
[ -f .env ] || { echo "Crie o .env primeiro (cp .env.example .env)"; exit 1; }
CONF="$(docker compose config --format json)"
for s in "${!VAR[@]}"; do
  img="$(python3 -c "import sys,json;print(json.load(sys.stdin)['services']['$s']['image'])" <<<"$CONF")"
  dig="$(docker image inspect --format '{{index .RepoDigests 0}}' "$img" 2>/dev/null || true)"
  [ -n "$dig" ] || { echo "Imagem $img ainda não foi baixada (rode: docker compose pull)"; exit 1; }
  sed -i "/^${VAR[$s]}=/d;/^# ${VAR[$s]}=/d" .env
  echo "${VAR[$s]}=$dig" >> .env
  echo "fixado: $s -> $dig"
done
