# Servidor privado da FRIDAY (retaguarda opcional)

Serve para: modelo local (Ollama) sem internet, push privado (ntfy), aviso quando algo cai (Uptime Kuma), DNS que bloqueia rastreadores (AdGuard Home) e backup diário (restic). **Nada aqui é necessário para a FRIDAY funcionar no celular.** Monte quando fizer sentido.

## Hardware
Mini PC com Ryzen 7 e 32 GB de RAM roda modelos locais de 3B a 8B parâmetros com folga e consome pouco; SSD de 500 GB; um HD/SSD USB para o backup. Um Raspberry Pi 5 aguenta tudo menos modelos grandes. (Preços e modelos mudam: confira antes de comprar.)

## Instalação (Ubuntu Server 24.04 ou Debian 12+)
1. Dê um **IP fixo** ao servidor no roteador.
2. Copie esta pasta para o servidor e rode:
   ```
   cd servidor && cp .env.example .env && nano .env     # ajuste LAN_IP e, se quiser, PAINEL_IP
   bash instalar.sh
   ```
   O script instala Docker e restic, pergunta antes de instalar o Tailscale e de ligar o firewall, cria a senha do backup (**guarde uma cópia fora do servidor**), sobe os serviços e agenda o backup às 03:30.
3. Depois de logar no Tailscale, coloque o IP dele (`tailscale ip -4`) em `PAINEL_IP` e `NTFY_BASE_URL` no `.env`, e rode `sudo docker compose up -d` de novo. Assim os painéis ficam acessíveis só pela sua conta Tailscale.

## A FRIDAY sempre ligada (celular desligado, ela continua)
O celular desligado não ouve nem vê. Para ela continuar funcionando com ele desligado, rode **a própria FRIDAY** neste aparelho que fica ligado (mini PC, Raspberry Pi 5): o celular passa a ser só uma janela para o painel.
1. Copie a pasta `friday-pi` para o servidor e rode `bash install.sh --servico` (cria o ambiente, a voz local e o serviço `friday` que sobe com o aparelho e se reergue sozinho).
2. No `.env` do servidor: `HUD_HOST=` o **IP do Tailscale do servidor** (assim o painel só responde pela sua rede privada; nunca `0.0.0.0` sem firewall). Para abrir do celular: `python friday/main.py --link`, troque `127.0.0.1` pelo IP do Tailscale e abra uma vez.
3. **Ouvir:** microfone USB no servidor (palavra de ativação «hey jarvis» + Whisper local, veja `install.sh`). **Ver:** `VISAO_FONTE=webcam` (USB), `picam` (câmera do Raspberry Pi) ou `url` (uma IP cam/ESP32-CAM). O corpo dela, quando existir, entra como `VISAO_URL`.
4. **Parar** (só você, fora dela): `sudo systemctl stop friday`; para não voltar no boot, `sudo systemctl disable friday`. Ela não tem botão de desligar nem como impedir isso.
5. A memória é a mesma pasta de sempre (`cofre/` ou `OBSIDIAN_VAULT`) e o backup diário já a cobre. Se o celular também rodar a FRIDAY, são duas cabeças com memórias separadas: escolha uma como principal.
Não testei isso num servidor real: o serviço, o microfone e a câmera do Pi são os pontos a conferir no primeiro dia.

## Depois de subir
- **AdGuard:** `http://PAINEL_IP:3000` (assistente; deixe a interface web na porta 80). Depois aponte o DNS do roteador para `LAN_IP`.
- **ntfy:** `sudo docker exec -it friday-ntfy ntfy user add --role=admin SEU_USUARIO` e `... ntfy token add SEU_USUARIO`. O token vai no `.env` da FRIDAY (`NTFY_TOKEN`) e no app ntfy do celular. O acesso anônimo é negado.
- **Uptime Kuma:** `http://PAINEL_IP:3001`; cadastre monitores e a notificação ntfy.
- **Modelo local:** `sudo docker exec friday-ollama ollama pull llama3.2:3b`. Para a FRIDAY do celular usar: `OLLAMA_BIND=` o IP do Tailscale do servidor, e no `.env` da FRIDAY `OLLAMA_URL=http://100.x.y.z:11434`.
- **Fixar versões:** `sudo docker compose pull && sudo bash fixar-versoes.sh && sudo docker compose up -d` grava o digest de cada imagem, para nada mudar sozinho.

## Backup
`sudo bash backup.sh` (manual) ou o timer diário. Guarda: configurações dos serviços, banco e auditoria da FRIDAY, `.env`. Retenção: 7 diários, 4 semanais, 6 mensais; confere 5% dos dados a cada execução e avisa por ntfy se falhar. Não guarda os modelos do Ollama (baixam de novo).
**Teste a restauração** uma vez por mês: `sudo restic -r $RESTIC_REPOSITORY --password-file $RESTIC_PASSWORD_FILE restore latest --target /tmp/teste-restauracao`. Backup que nunca foi restaurado não é backup.
Para a regra 3-2-1, aponte `RESTIC_REPOSITORY` para um disco USB e rode também com um segundo destino na nuvem (S3/B2).

## Limites e riscos
- O compose foi validado só na **sintaxe** (`docker compose config`); eu não consegui subir os contêineres. Faça o primeiro `up` olhando `docker compose ps` e os logs.
- As imagens usam a etiqueta `latest` (ou `1` no Uptime Kuma) até você rodar `fixar-versoes.sh`. Não consegui consultar as versões atuais.
- O Docker publica portas por conta própria e ignora o UFW; a proteção aqui vem de ligar cada porta a um IP específico (127.0.0.1, IP do Tailscale ou `LAN_IP` só no DNS).
- Ollama sem GPU é lento: modelos de 3B respondem em segundos; de 8B, bem mais devagar.
- Os bancos `*.db` vivos dos serviços não vão direto para o backup (ficam inconsistentes): o script copia o do Kuma, do ntfy e da FRIDAY com a API de backup do SQLite. As estatísticas do AdGuard (`stats.db`) ficam de fora de propósito.
