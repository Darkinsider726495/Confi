#!/data/data/com.termux/files/usr/bin/bash
# Instala a FRIDAY no celular Android (dentro do app Termux, instalado pela F-Droid).  Uso:  bash termux/instalar-termux.sh
set -e
cd "$(dirname "$0")/.."
DIR="$PWD"
echo "== 1/5 Pacotes =="
pkg update -y && pkg install -y python termux-api curl nano
pkg install -y python-pillow || echo "(sem Pillow: ela ainda enxerga, mas a foto vai sem ser reduzida)"   # olhos: reduz a foto e tira a localização antes de qualquer análise
pip install -r requirements-android.txt
echo "== 2/5 Configuração =="
[ -f .env ] || cp .env.example .env
chmod 600 .env
if ! grep -qE '^FRIDAY_PIN=.{4,}' .env; then
  while :; do
    read -r -s -p "Escolha um PIN de 4 a 8 dígitos para ações críticas: " PIN; echo
    [[ "$PIN" =~ ^[0-9]{4,8}$ ]] && break || echo "Use só números, de 4 a 8."
  done
  sed -i "s/^FRIDAY_PIN=.*/FRIDAY_PIN=$PIN/" .env
fi
grep -q '^SILENCIO=' .env || echo 'SILENCIO=22:00-07:00' >> .env
mkdir -p "$HOME/friday-docs"
echo "== 3/5 Início automático (precisa do app Termux:Boot) =="
mkdir -p "$HOME/.termux/boot"
sed "s#__DIR__#$DIR#g" termux/boot-friday > "$HOME/.termux/boot/friday"
chmod +x "$HOME/.termux/boot/friday" termux/supervisor.sh termux/parar.sh friday/acao.sh
echo "== 4/5 Teste =="
python friday/main.py --diagnostico || true
echo "== 5/5 Subindo agora (sem botão: ela já fica de pé sozinha) =="
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
nohup bash termux/supervisor.sh >/dev/null 2>&1 &
sleep 3
echo "Pronto: ela está rodando e volta sozinha quando o celular reiniciar (Termux:Boot)."
cat <<MSG

Falta (manual, o Android não deixa automatizar):
  1. Edite o .env:  nano .env   (ANTHROPIC_API_KEY, CONTATOS, SUPABASE_SERVICE_KEY se quiser leads). Depois:  bash termux/atualizar.sh --reiniciar
  2. Configurações do Android > Apps > Termux, Termux:API e Termux:Boot > Bateria > "Sem restrições"
  3. Configurações > Apps > Termux:API > Permissões: Microfone, Câmera (os olhos dela), Localização, SMS, Telefone, Contatos, Notificações
  4. Abra o Termux:Boot uma vez (para o Android registrar o início automático).
  5. Abra a notificação "FRIDAY online" para ver o painel. A escuta liga sozinha e NÃO existe botão de desligar.
     Só você a para, daqui do Termux:  bash termux/parar.sh   (ela não resiste)
  6. Olhos: diga «Friday, olhe». A câmera do celular pode ser bloqueada pelo Android com a tela apagada; para ela ver o tempo todo use
     uma câmera dedicada (VISAO_FONTE=url) ou o servidor (veja servidor/README.md). Nenhuma foto é guardada (só o que ela entendeu em texto).
MSG
