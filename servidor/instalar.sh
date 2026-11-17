#!/usr/bin/env bash
# Prepara o servidor (Ubuntu Server 24.04 / Debian 12+): Docker, Tailscale, firewall, backup e a pilha de serviços.
# Rode como usuário comum com sudo:   bash instalar.sh
# Cada etapa pergunta antes de mexer em algo sensível (firewall, Tailscale). Pode rodar de novo sem problema.
set -Eeuo pipefail
cd "$(dirname "$0")"
DIR="$PWD"
ask() { read -r -p "$1 [s/N] " r; [[ "$r" =~ ^[sSyY]$ ]]; }
[ "$(id -u)" -ne 0 ] || { echo "Rode como usuário comum (o script usa sudo quando precisa)."; exit 1; }
[ -f .env ] || { cp .env.example .env; echo "Criei o .env. Edite (nano .env) — principalmente LAN_IP — e rode de novo."; chmod 600 .env; exit 0; }
chmod 600 .env
set -a; . ./.env; set +a
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/etc/friday/restic-senha}"
case "$LAN_IP" in 192.168.1.10|"") ask "LAN_IP=$LAN_IP é o valor de exemplo. Continuar mesmo assim?" || exit 1;; esac

echo "== 1/6 Pacotes =="
sudo apt-get update
sudo apt-get install -y docker.io restic ufw curl python3 ca-certificates
sudo apt-get install -y docker-compose-v2 2>/dev/null || sudo apt-get install -y docker-compose-plugin 2>/dev/null || true
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 não instalado. Instale pelo repositório oficial: https://docs.docker.com/engine/install/"; exit 1; }
sudo systemctl enable --now docker

echo "== 2/6 Tailscale (acesso remoto sem abrir portas no roteador) =="
if ! command -v tailscale >/dev/null; then
  ask "Instalar o Tailscale pelo script oficial (tailscale.com/install.sh)?" && curl -fsSL https://tailscale.com/install.sh | sh
fi
if command -v tailscale >/dev/null; then
  tailscale status >/dev/null 2>&1 || { echo "Faça login no Tailscale agora:"; sudo tailscale up; }
  echo "IP do Tailscale deste servidor: $(tailscale ip -4 2>/dev/null | head -1)  (use em PAINEL_IP e NTFY_BASE_URL no .env)"
  # o Docker só pode subir depois do Tailscale, senão não consegue ligar as portas no IP dele
  sudo mkdir -p /etc/systemd/system/docker.service.d
  printf '[Unit]\nAfter=tailscaled.service\nWants=tailscaled.service\n' | sudo tee /etc/systemd/system/docker.service.d/apos-tailscale.conf >/dev/null
  sudo systemctl daemon-reload
fi

echo "== 3/6 Pastas e senha do backup =="
mkdir -p dados/adguard/work dados/adguard/conf dados/kuma dados/ntfy/cache dados/ntfy/lib dados/ollama
if ! sudo test -f "$RESTIC_PASSWORD_FILE"; then
  sudo mkdir -p "$(dirname "$RESTIC_PASSWORD_FILE")"
  head -c 32 /dev/urandom | base64 | sudo tee "$RESTIC_PASSWORD_FILE" >/dev/null
  sudo chmod 600 "$RESTIC_PASSWORD_FILE"
  echo "!! Senha do backup criada em $RESTIC_PASSWORD_FILE. COPIE para o gerenciador de senhas: sem ela o backup não abre."
fi

echo "== 4/6 Firewall =="
if ask "Configurar o firewall (UFW)? Cuidado: se você está em SSH pela rede local, a regra de SSH abaixo mantém o acesso."; then
  LAN_CIDR="${LAN_CIDR:-${LAN_IP%.*}.0/24}"
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw allow from "$LAN_CIDR" to "$LAN_IP" port 22 proto tcp comment 'ssh da rede local'
  sudo ufw allow from "$LAN_CIDR" to "$LAN_IP" port 53 comment 'dns da rede local'
  command -v tailscale >/dev/null && sudo ufw allow in on tailscale0 comment 'tailscale'
  sudo ufw --force enable
  echo "Depois de testar o acesso pelo Tailscale, remova o SSH da rede local: sudo ufw delete allow from $LAN_CIDR to $LAN_IP port 22 proto tcp"
fi

echo "== 5/6 Serviços =="
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps

echo "== 6/6 Backup diário às 03:30 =="
sed "s#__DIR__#$DIR#g" friday-backup.service | sudo tee /etc/systemd/system/friday-backup.service >/dev/null
sudo cp friday-backup.timer /etc/systemd/system/friday-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now friday-backup.timer

cat <<MSG

Pronto. Próximos passos (detalhes no README):
  1. AdGuard: http://${PAINEL_IP:-127.0.0.1}:3000 (assistente). Depois aponte o DNS do roteador para $LAN_IP.
  2. ntfy: crie o usuário e o token   ->  sudo docker exec -it friday-ntfy ntfy user add --role=admin SEU_USUARIO
                                          sudo docker exec -it friday-ntfy ntfy token add SEU_USUARIO
  3. Uptime Kuma: http://${PAINEL_IP:-127.0.0.1}:3001 (cadastre os monitores e a notificação ntfy).
  4. Modelo local:  sudo docker exec friday-ollama ollama pull llama3.2:3b
  5. Fixar versões: sudo bash fixar-versoes.sh   |   Testar backup: sudo bash backup.sh
MSG
