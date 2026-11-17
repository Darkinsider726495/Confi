#!/usr/bin/env bash
# Instala o servidor de voz (faster-whisper + Kokoro) neste PC/servidor Linux, em um ambiente isolado (.venv).
#   cd servidor/voz && bash instalar-voz.sh
# Na primeira vez baixa os modelos (alguns GB no total): use uma boa conexão.
set -Eeuo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
"$PY" - <<'PYV' || { echo "Precisa de Python 3.10 a 3.13 (o Kokoro não suporta fora disso)."; exit 1; }
import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)
PYV

if command -v apt-get >/dev/null 2>&1; then
  echo "== espeak-ng e venv (pede a senha do sudo) =="
  sudo apt-get install -y espeak-ng python3-venv
else
  echo "Instale o espeak-ng pelo gerenciador do seu sistema (o Kokoro precisa dele para o português)."
fi

echo "== Ambiente isolado =="
"$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -U pip
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "(sem GPU NVIDIA: instalando o PyTorch só de CPU, bem menor)"
  pip install torch --index-url https://download.pytorch.org/whl/cpu
fi
pip install -r requirements.txt

echo "== Configuração =="
if [ ! -f .env ]; then
  cp .env.example .env
  TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s|^VOZ_TOKEN=.*|VOZ_TOKEN=$TOKEN|" .env
fi
grep -q '^HF_HOME=' .env && sed -i "s|^HF_HOME=.*|HF_HOME=$PWD/modelos|" .env || echo "HF_HOME=$PWD/modelos" >> .env
chmod 600 .env
set -a; . ./.env; set +a

echo "== Teste de ida e volta (fala uma frase e a reconhece de volta) =="
python servidor_voz.py --testar

DIR="$PWD"
sed "s#__DIR__#$DIR#g; s#__USUARIO__#$(id -un)#g" friday-voz.service > friday-voz.service.pronto
cat <<MSG

Instalado. Falta:
  1. Edite .env e ponha em VOZ_BIND o IP do Tailscale deste servidor (tailscale ip -4) ou o IP fixo da sua rede.
     Deixe 127.0.0.1 só se a FRIDAY roda neste mesmo aparelho. NUNCA exponha esta porta à internet.
  2. Iniciar agora:        set -a; . ./.env; set +a; .venv/bin/python servidor_voz.py
  3. Iniciar com o boot:   sudo cp friday-voz.service.pronto /etc/systemd/system/friday-voz.service && sudo systemctl enable --now friday-voz
  4. No celular (.env da FRIDAY):  VOZ_URL=http://IP-DO-SERVIDOR:${VOZ_PORTA:-8765}   VOZ_TOKEN=<o mesmo valor de VOZ_TOKEN do .env deste servidor>
MSG
