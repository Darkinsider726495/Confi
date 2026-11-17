#!/data/data/com.termux/files/usr/bin/bash
# Instala o Ollama (IA local) no Termux e liga a FRIDAY a ele.  Uso:  bash termux/instalar-ollama.sh [modelo]
#
# NÃO use "curl -fsSL https://ollama.com/install.sh | sh" no Termux: aquele script é para Linux comum (PC/servidor).
# No Termux o caminho é o pacote "ollama" do próprio Termux, que é o que este script faz.
set -e
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Rode antes: bash termux/instalar-termux.sh"; exit 1; }

echo "== 1/5 Aparelho =="
ARQ="$(uname -m)"
case "$ARQ" in aarch64|x86_64) ;; *) echo "Arquitetura $ARQ não tem pacote do Ollama no Termux (só aarch64 e x86_64). Use o Ollama em um PC/servidor: veja docs/ANDROID.md, 'IA local'."; exit 2;; esac
RAM_GB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 / 1024 ))
LIVRE_GB=$(( $(df -k "$HOME" | awk 'NR==2{print $4}') / 1024 / 1024 ))
echo "RAM: ~${RAM_GB} GB · espaço livre: ~${LIVRE_GB} GB"
if [ -n "$1" ]; then MODELO="$1"
elif [ "$RAM_GB" -ge 11 ]; then MODELO="qwen2.5:7b"     # ~4,7 GB: lento no celular, mas cabe
elif [ "$RAM_GB" -ge 5 ];  then MODELO="llama3.2:3b"    # ~2,0 GB
else MODELO="llama3.2:1b"; echo "Pouca RAM: vou usar o modelo pequeno (1,3 GB). Ele erra mais ao usar ferramentas."; fi
echo "Modelo escolhido: $MODELO (para outro: bash termux/instalar-ollama.sh nome:tag)"
[ "$LIVRE_GB" -ge 4 ] || { echo "Pouco espaço livre para baixar o modelo. Libere ao menos 4 GB."; exit 3; }

echo "== 2/5 Pacote =="
pkg update -y
pkg show ollama >/dev/null 2>&1 || { echo "O pacote 'ollama' não está nos repositórios do seu Termux. Atualize o Termux (F-Droid) ou use o Ollama em um PC/servidor."; exit 4; }
pkg install -y ollama curl

echo "== 3/5 Servidor =="
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
if ! curl -sf -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  OLLAMA_KEEP_ALIVE=30m nohup ollama serve >> "$HOME/ollama.log" 2>&1 &
  for _ in $(seq 1 30); do curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
fi
curl -sf -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || { echo "O servidor do Ollama não subiu. Veja ~/ollama.log"; exit 5; }

echo "== 4/5 Baixando o modelo (pode demorar; use Wi-Fi) =="
ollama pull "$MODELO"

echo "== 5/5 Ligando à FRIDAY =="
setvar() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
setvar OLLAMA_URL http://127.0.0.1:11434
setvar OLLAMA_MODEL "$MODELO"
setvar OLLAMA_AUTOSTART 1      # o supervisor sobe o Ollama junto com a FRIDAY e o reergue se cair
grep -q '^IA_MODO=' .env || echo 'IA_MODO=auto' >> .env
chmod 600 .env
cat <<MSG

Pronto. Modo atual: auto (nuvem quando houver chave e internet; modelo local como reserva).
  - Só local, nada sai do celular:   IA_MODO=local   no .env
  - Testar:   python friday/main.py --diagnostico --completo      (mede quanto o modelo demora a responder)
  - Reinicie a FRIDAY para o supervisor subir o Ollama junto.
Aviso honesto: no celular o modelo pequeno é lento (a 1ª resposta carrega o modelo) e erra mais ao escolher ferramentas.
O corretor continua valendo: o modelo só propõe, nada perigoso passa sem confirmação.
MSG
