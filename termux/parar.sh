#!/usr/bin/env bash
# PARADA DO DONO. A FRIDAY não tem botão de desligar na tela e nenhuma ferramenta dela consegue pará-la, nem impedir que a parem:
# só VOCÊ, aqui no Termux. Ela não resiste: o supervisor recebe o sinal e encerra tudo (a FRIDAY, o Ollama que ela subiu e o wake lock).
#   bash termux/parar.sh         para agora
#   bash termux/supervisor.sh    volta (ou reabra o Termux, se o início automático estiver configurado)
# Para ela NÃO voltar sozinha quando o celular ligar:  rm ~/.termux/boot/friday
# Num Raspberry Pi/PC com o serviço instalado:  sudo systemctl stop friday   (e  sudo systemctl disable friday  para não voltar no boot)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIDF="${FRIDAY_PIDFILE:-$DIR/.supervisor.pid}"
ESPERA="${PARAR_ESPERA:-10}"
parou=0
# vivo = existe e não é um zumbi (um processo que já terminou mas ainda não foi "colhido" pelo pai conta como parado)
vivo() { kill -0 "$1" 2>/dev/null || return 1; [ "$(sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | cut -c1)" != Z ]; }
if [ -f "$PIDF" ]; then
  pid="$(cat "$PIDF" 2>/dev/null)"
  if [ -n "$pid" ] && vivo "$pid"; then
    kill -TERM "$pid" 2>/dev/null
    for _ in $(seq 1 $((ESPERA * 5))); do vivo "$pid" || break; sleep 0.2; done
    vivo "$pid" && kill -KILL "$pid" 2>/dev/null
    parou=1
  fi
  rm -f "$PIDF"
fi
# uma FRIDAY solta (iniciada sem supervisor) ou uma filha que sobrou
if pgrep -f "python[0-9.]* .*friday/main.py" >/dev/null 2>&1; then
  pkill -TERM -f "python[0-9.]* .*friday/main.py" 2>/dev/null; sleep 1
  pkill -KILL -f "python[0-9.]* .*friday/main.py" 2>/dev/null
  parou=1
fi
command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock
if [ "$parou" = 1 ]; then echo "FRIDAY parada. Para voltar: bash termux/supervisor.sh"; else echo "A FRIDAY não estava rodando."; fi
