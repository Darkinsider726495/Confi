#!/usr/bin/env bash
# Backup 3-2-1 com restic: configurações dos serviços, banco e auditoria da FRIDAY, segredos (.env).
# Bancos SQLite são copiados com a API de backup online (consistentes, sem parar nenhum serviço).
# Rode manualmente (bash backup.sh) ou agende (veja README, "Agendar o backup").
set -Eeuo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
: "${RESTIC_REPOSITORY:?defina RESTIC_REPOSITORY no .env}"
: "${RESTIC_PASSWORD_FILE:?defina RESTIC_PASSWORD_FILE no .env}"
command -v restic >/dev/null || { echo "restic não instalado (sudo apt install restic)"; exit 2; }

RAIZ="$(cd .. && pwd)"
STAGE="$RAIZ/.stage-backup"   # caminho fixo: o restic reaproveita o que não mudou

avisar() {
  [ -n "${NTFY_URL:-}" ] || return 0
  curl -s --max-time 10 -H "Title: FRIDAY backup" -H "Priority: high" ${NTFY_TOKEN:+-H "Authorization: Bearer $NTFY_TOKEN"} \
    -d "$1" "$NTFY_URL" >/dev/null 2>&1 || true
}
trap 'avisar "Backup FALHOU em $(hostname) ($(date +%F\ %R))"; rm -rf "$STAGE"' ERR
trap 'rm -rf "$STAGE"' EXIT

rm -rf "$STAGE"; mkdir -p "$STAGE"
copiar_sqlite() {   # origem destino
  [ -f "$1" ] || return 0
  python3 - "$1" "$2" <<'PY'
import sqlite3, sys
a = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True); b = sqlite3.connect(sys.argv[2]); a.backup(b); b.close(); a.close()
PY
}
copiar_sqlite "$RAIZ/friday/friday.db"             "$STAGE/friday.db.bak"
copiar_sqlite "$PWD/dados/kuma/kuma.db"            "$STAGE/kuma.db.bak"
copiar_sqlite "$PWD/dados/ntfy/lib/user.db"        "$STAGE/ntfy-user.db.bak"
copiar_sqlite "$PWD/dados/ntfy/cache/cache.db"     "$STAGE/ntfy-cache.db.bak"

# primeira execução: cria o repositório
restic cat config >/dev/null 2>&1 || restic init

ALVOS=("$PWD/dados" "$STAGE" "$PWD/.env")
[ -f "$RAIZ/.env" ] && ALVOS+=("$RAIZ/.env")
[ -f "$RAIZ/friday/auditoria.jsonl" ] && ALVOS+=("$RAIZ/friday/auditoria.jsonl")

restic backup --tag friday --exclude-caches \
  --exclude "$PWD/dados/ollama" \
  --exclude '*.db' --exclude '*.db-wal' --exclude '*.db-shm' \
  "${ALVOS[@]}"

# retenção: 7 dias, 4 semanas, 6 meses
restic forget --tag friday --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
# integridade: confere uma amostra de 5% dos dados a cada execução
restic check --read-data-subset=5%

date +%s > "$PWD/.ultimo-backup-ok"
echo "Backup concluído: $(date '+%F %R')"
