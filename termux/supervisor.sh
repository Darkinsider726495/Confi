#!/usr/bin/env bash
# Mantém a FRIDAY de pé no Termux: reinicia se ela cair ou travar (batimento parado / painel sem responder).
# Rode pelo Termux:Boot (veja instalar-termux.sh) ou manualmente:  bash termux/supervisor.sh
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR" || exit 1
LOG="${FRIDAY_LOG:-$HOME/friday.log}"
export FRIDAY_HEARTBEAT="${FRIDAY_HEARTBEAT:-$DIR/friday/.heartbeat}"
PORTA="${HUD_PORTA:-8080}"
CHECK="${CHECK_INTERVAL:-30}"; STALE="${STALE_SEGUNDOS:-180}"; GRACE="${GRACE_SEGUNDOS:-120}"
PY="${FRIDAY_PY:-python}"; ARGS="${FRIDAY_ARGS:-friday/main.py --android}"
PIDF="${FRIDAY_PIDFILE:-$DIR/.supervisor.pid}"
OLLAMA_CMD="${OLLAMA_CMD:-ollama}"; OLLAMA_CHECK="${OLLAMA_CHECK_URL:-http://127.0.0.1:11434/api/tags}"; OPID=""

# uma cópia só
if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null; then echo "supervisor já está rodando"; exit 0; fi
echo $$ > "$PIDF"
trap 'rm -f "$PIDF"; for p in "$PID" "$OPID"; do if [ -n "$p" ]; then kill "$p" 2>/dev/null; wait "$p" 2>/dev/null; fi; done; exit 0' TERM INT
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock

log() { echo "[$(date '+%F %T')] supervisor: $*" >> "$LOG"; }

# IA local (Ollama): só sobe se OLLAMA_AUTOSTART=1 (no ambiente ou no .env; o instalar-ollama.sh liga isso) e o programa existir.
quer_ollama() { [ "${OLLAMA_AUTOSTART:-}" = 1 ] || grep -qs '^OLLAMA_AUTOSTART=1' "$DIR/.env"; }
ollama_garante() {
  quer_ollama || return 0
  command -v "$OLLAMA_CMD" >/dev/null 2>&1 || return 0
  if [ -n "$OPID" ] && kill -0 "$OPID" 2>/dev/null; then return 0; fi
  curl -sf -m 2 "$OLLAMA_CHECK" >/dev/null 2>&1 && return 0   # já tem um rodando (iniciado à mão): não duplica
  OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-30m}" "$OLLAMA_CMD" serve >> "$LOG" 2>&1 &
  OPID=$!; log "ollama iniciado (pid $OPID)"
}
B0="${BACKOFF_INICIAL:-5}"; BMAX="${BACKOFF_MAX:-60}"; espera=$B0
while true; do
  inicio=$(date +%s); rm -f "$FRIDAY_HEARTBEAT"; falhas=0
  ollama_garante
  # shellcheck disable=SC2086
  $PY $ARGS >> "$LOG" 2>&1 &
  PID=$!; log "iniciada (pid $PID)"
  while kill -0 "$PID" 2>/dev/null; do
    sleep "$CHECK" & wait $!   # em segundo plano para o sinal de parada (termux/parar.sh) valer na hora, sem esperar o intervalo
    ollama_garante
    agora=$(date +%s)
    if [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt 5000000 ]; then tail -c 500000 "$LOG" > "$LOG.tmp" && cat "$LOG.tmp" > "$LOG"; rm -f "$LOG.tmp"; fi
    [ $((agora - inicio)) -le "$GRACE" ] && continue
    hb=$(stat -c %Y "$FRIDAY_HEARTBEAT" 2>/dev/null || echo 0)
    curl -sf -m 5 "http://127.0.0.1:$PORTA/saude" >/dev/null 2>&1 && falhas=0 || falhas=$((falhas + 1))
    if [ $((agora - hb)) -gt "$STALE" ] || [ "$falhas" -ge 3 ]; then
      log "travada (batimento há $((agora - hb))s, falhas do painel: $falhas): reiniciando"
      kill "$PID" 2>/dev/null; sleep 3; kill -9 "$PID" 2>/dev/null; break
    fi
  done
  wait "$PID" 2>/dev/null; cod=$?
  dur=$(( $(date +%s) - inicio ))
  log "encerrada (código $cod) após ${dur}s"
  if [ "$dur" -gt 300 ]; then espera=$B0; else espera=$(( espera * 2 > BMAX ? BMAX : espera * 2 )); fi
  sleep "$espera" & wait $!
done
