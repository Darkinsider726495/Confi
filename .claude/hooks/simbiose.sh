#!/usr/bin/env bash
# SessionStart: entrega ao Claude Code o resumo da FRIDAY (cérebro, pedidos, diagnóstico). Só leitura; sempre sai com 0.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" 2>/dev/null || exit 0
PY="$(command -v python3 || command -v python)"
[ -n "$PY" ] || { echo "FRIDAY: python não encontrado; resumo indisponível."; exit 0; }
timeout 20 "$PY" -I friday/simbiose.py 2>/dev/null || echo "FRIDAY: resumo indisponível."
exit 0
