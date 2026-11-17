#!/usr/bin/env bash
# Instalação da FRIDAY (Raspberry Pi OS 64 bits, Debian ou Ubuntu). Rode:  bash install.sh [--servico]
#   --servico  também instala o serviço systemd para iniciar com o aparelho (usa seu usuário e esta pasta)
set -e
cd "$(dirname "$0")"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip portaudio19-dev alsa-utils curl
sudo apt-get install -y python3-lgpio 2>/dev/null || echo "(python3-lgpio indisponível aqui: relés GPIO só funcionam no Raspberry Pi)"
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -U pip && pip install -r requirements.txt
pip install -r requirements-rag.txt || echo "(busca semântica: lightrag não instalou agora; a FRIDAY funciona sem ela)"
mkdir -p voz && cd voz
for f in pt_BR-faber-medium.onnx pt_BR-faber-medium.onnx.json; do
  [ -f "$f" ] || curl -L -o "$f" "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/$f"
done
cd ..
python -c "import openwakeword; openwakeword.utils.download_models()"
[ -f .env ] || cp .env.example .env
chmod 600 .env
if [ "$1" = "--servico" ]; then
  sed -e "s#__USUARIO__#$(id -un)#g" -e "s#__DIR__#$PWD#g" friday.service | sudo tee /etc/systemd/system/friday.service >/dev/null
  sed -e "s#__USUARIO__#$(id -un)#g" -e "s#__DIR__#$PWD#g" friday-api.service | sudo tee /etc/systemd/system/friday-api.service >/dev/null
  sudo systemctl daemon-reload && sudo systemctl enable friday friday-api
  echo "Serviço instalado. Depois de editar o .env:  sudo systemctl start friday friday-api   (logs: journalctl -u friday -u friday-api -f)"
fi
echo "Pronto. Edite o .env e teste:  .venv/bin/python friday/main.py --teclado   (texto)   ou   .venv/bin/python friday/main.py   (voz)"
