#!/data/data/com.termux/files/usr/bin/bash
# Atualiza o código da FRIDAY sem perder nada seu (memória, .env, protocolos, auditoria). Uso:
#   bash termux/atualizar.sh ~/storage/downloads/friday-pi.zip     # coloca o código novo por cima
#   bash termux/atualizar.sh --reiniciar                           # só reinicia (depois de editar o .env)
# O código fica em arquivos de texto: você pode editar qualquer coisa em friday/ com nano ou com o Claude Code, e reiniciar com --reiniciar.
set -e
cd "$(dirname "$0")/.."
DIR="$PWD"
reiniciar() {
  if [ -f .supervisor.pid ] && kill -0 "$(cat .supervisor.pid 2>/dev/null)" 2>/dev/null; then
    # o supervisor reergue o processo da FRIDAY sozinho: basta encerrar só ele
    pkill -f "python.*friday/main.py --android" 2>/dev/null || true
    echo "Reiniciando: o supervisor sobe a versão nova em até 10 segundos."
  else
    nohup bash termux/supervisor.sh >/dev/null 2>&1 &
    echo "Supervisor iniciado."
  fi
}
if [ "$1" = "--reiniciar" ] || [ -z "$1" ]; then reiniciar; exit 0; fi
ZIP="$1"
[ -f "$ZIP" ] || { echo "Não achei $ZIP"; exit 1; }
command -v unzip >/dev/null 2>&1 || pkg install -y unzip
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP"
NOVO="$(find "$TMP" -maxdepth 3 -name main.py -path '*friday/main.py' -print -quit | xargs -r dirname | xargs -r dirname)"
[ -n "$NOVO" ] && [ -f "$NOVO/friday/main.py" ] || { echo "Esse zip não parece ser da FRIDAY."; exit 1; }
BKP="$HOME/friday-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$BKP" -C "$DIR" . 2>/dev/null && echo "Cópia de segurança do que você tinha: $BKP"
# copia o código novo; NUNCA toca em .env, protocolos.json, token, auditoria, banco, cofre
tar -C "$NOVO" --exclude=.env --exclude=protocolos.json --exclude=auditoria.jsonl --exclude='*.db' --exclude=cofre --exclude=.friday-token --exclude=token.txt -cf - . | tar -C "$DIR" -xf -
pip install -q -r requirements-android.txt || true
chmod +x termux/*.sh friday/acao.sh 2>/dev/null || true
python friday/main.py --diagnostico || true
reiniciar
