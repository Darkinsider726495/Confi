# FRIDAY no celular Android — passo a passo

**Como ela roda:** como **software editável dentro do Termux**, não como APK. O código é um conjunto de arquivos de texto (Python + um painel em HTML) em `~/friday-pi`: você pode abrir, mudar e reiniciar qualquer parte (com `nano` ou, no computador, com o Claude Code), e a memória fica em arquivos seus. Existe um app opcional, **`friday-painel.apk`**, que é só a **janela do painel** em tela cheia (seção «App FRIDAY» abaixo): ele não contém a FRIDAY, que continua rodando no Termux. Um app nativo completo, que também permitiria ouvir com a tela apagada, continua sendo um projeto futuro.

Tempo: uns 30 minutos. Custo: zero (só a chave da IA, se quiser a nuvem). Você faz a instalação; eu ajudo a testar e corrigir com o resultado do diagnóstico.

## O que você precisa
- Celular Android 8 ou mais novo, com internet.
- Os **3 apps do Termux pela F-Droid** (não pela Play Store: lá a versão é antiga e não funciona com os outros): **Termux**, **Termux:API** e **Termux:Boot**. Os três precisam vir da mesma loja, senão não se reconhecem.
- A pasta `friday-pi` deste pacote no celular (ex.: copie o `.zip` para Downloads).

## Instalação
1. Instale a F-Droid (f-droid.org) e, por ela, os três apps acima. **Abra cada um uma vez** (o Termux:Boot e o Termux:API precisam ser abertos ao menos uma vez para o Android registrá-los).
2. No Termux:
   ```
   termux-setup-storage          # toque em "Permitir"
   cd ~ && cp ~/storage/downloads/friday-pi.zip . && pkg install -y unzip && unzip friday-pi.zip
   cd friday-pi && bash termux/instalar-termux.sh
   ```
   O instalador pede um PIN (4 a 8 números) para as ações críticas, roda o diagnóstico e **já deixa a FRIDAY rodando** (sem botão de ligar).
3. Edite o `.env` (`nano .env`; salvar = Ctrl+O, Enter; sair = Ctrl+X):
   - `ANTHROPIC_API_KEY=` a chave da IA (sem ela só funciona o modelo local, sem ferramentas);
   - `CONTATOS=mae:+5511999999999,socio:+5511988888888` quem ela pode usar para SMS, ligação e WhatsApp (só esses);
   - `SUPABASE_SERVICE_KEY=` se quiser aviso de lead novo do site.
4. Permissões do Android (o sistema não deixa automatizar):
   - Configurações → Apps → **Termux:API** → Permissões: Microfone, **Câmera** (os olhos dela), Localização, SMS, Telefone, Contatos, Notificações.
   - Configurações → Apps → **Termux**, **Termux:API** e **Termux:Boot** → Bateria → **Sem restrições**.
   - Android 12 ou mais novo: o sistema pode matar processos de segundo plano do Termux (o "phantom process killer"). No Android 14 ou mais novo há, em Opções do desenvolvedor, a chave para desativar as restrições de processos filhos; nas versões 12 e 13 a solução usa o ADB. O comando muda conforme a versão: procure "phantom process killer" na wiki do Termux antes de aplicar.
5. Teste: `python friday/main.py --diagnostico`. Ele fala uma frase, mostra uma notificação e faz o celular vibrar; confirme se você ouviu, viu e sentiu. Depois `python friday/main.py --diagnostico --completo` testa localização, microfone, IA, internet e Supabase.
6. **Cole aqui o conteúdo de `diagnostico.txt`** (`cat diagnostico.txt`). Ele não contém senhas nem chaves. Com isso eu vejo o que falhou no seu aparelho e ajusto.
7. Depois de editar o `.env`: `bash termux/atualizar.sh --reiniciar`. Ela já sobe sozinha sempre que o celular ligar (Termux:Boot) e se reergue se travar; não existe botão de ligar nem de desligar. **Só você a para**, daqui do Termux: `bash termux/parar.sh` (ela não resiste; para não voltar ao ligar o celular, `rm ~/.termux/boot/friday`).
8. Abra a notificação **"FRIDAY online"**: ela abre o painel já com a chave. Dali você fala, digita ou confirma ações.
9. Teste de reinício: reinicie o celular, espere 1 a 2 minutos e veja se a notificação voltou.

## App FRIDAY (janela do painel, opcional)
O `friday-painel.apk` abre o painel da FRIDAY (`http://127.0.0.1:8080`) em tela cheia, como um app, com microfone e câmera liberados só para esse endereço. **Ele não substitui o Termux:** a FRIDAY precisa estar rodando lá (passos acima).
1. Copie o `friday-painel.apk` para o celular e toque nele. O Android pede para permitir «instalar apps desconhecidos» para o app que abriu o arquivo (Arquivos/Chrome): permita só para essa instalação. O Play Protect pode avisar que o app é de desenvolvedor desconhecido e foi feito para uma versão antiga do Android (alvo: Android 6): isso é esperado num app feito por você; toque em «Instalar mesmo assim».
2. Toque na notificação **«FRIDAY online»** e, se o Android perguntar com qual app abrir, escolha **FRIDAY**. Ou abra o app e cole o link da notificação (termina com `#t=…`, que é a chave do painel).
3. Na primeira vez que o painel pedir microfone ou câmera, o Android pergunta: permita se quiser falar com ela ou usar os olhos e as mãos.
4. Voltar (botão do Android) leva à tela de configuração do link; o app **não** para a FRIDAY (não há botão de desligar; a parada continua sendo `bash termux/parar.sh`).
Para gerar o APK de novo a partir do código: `bash android/build.sh` (precisa de JDK e dos pacotes `android-sdk-platform-23 aapt dalvik-exchange zipalign apksigner`). Cada build cria uma chave de assinatura própria em `android/build/assinatura` (fora do git); para atualizar o app sem desinstalar, use sempre a mesma.
**Não testado:** o APK foi compilado, alinhado e assinado aqui (`apksigner verify` ok), mas não foi instalado em um celular de verdade nem num emulador.

## Editar e atualizar (software modificável)
- **Mudar o código:** `nano friday/vida.py` (por exemplo), salve e rode `bash termux/atualizar.sh --reiniciar`. Os testes rodam no Termux: `python -m unittest discover -s tests -p 'test_*.py'`.
- **Trabalhar com o Claude Code:** abra a pasta `friday-pi` no computador (o `CLAUDE.md` e as skills em `.claude/` explicam o projeto). Faça as mudanças, rode os testes, gere um novo `friday-pi.zip` e mande para o celular.
- **Colocar a versão nova no celular sem perder nada:** copie o zip para Downloads e rode `bash termux/atualizar.sh ~/storage/downloads/friday-pi.zip`. Ele faz uma cópia de segurança em `~/friday-backup-*.tar.gz`, troca só o código e **nunca toca** no `.env`, no `protocolos.json`, na auditoria nem no cofre de memória.
- **Sua memória:** fica no cofre do Obsidian (`Documents/Obsidian/Cofre FRIDAY`), que você abre no app Obsidian e copia como qualquer pasta.

## Como ela funciona sozinha
- **Escuta:** o painel liga a escuta sozinho (diga "Friday, ..."). "Escutando sempre" é só um aviso: não há botão para pausar ou desligar. O navegador mostra o ícone de microfone. Com a voz do navegador, o que ele ouve vai ao serviço de voz do Google; com a voz privada (servidor), o áudio vai só ao seu servidor.
- **Cérebro:** ela estuda, puxa assunto, dorme de madrugada e conta "primeiras vezes". Tudo está explicado em `docs/CEREBRO.md`.
- **Olhos:** diga "Friday, olhe". Ela usa a câmera do celular (Termux:API) e guarda só o texto do que entendeu; não guarda foto (a menos que `VISAO_GUARDAR_FOTOS=1`) e não reconhece rostos. Sozinha, olha de vez em quando (nunca no descanso nem no silêncio); "não olhe mais sozinha" desliga. Sem Pillow (`pkg install python-pillow`, o instalador já tenta) a foto não é reduzida.

## Como usar
- **Painel:** botão *Falar (toque)*, ou *Escutar sempre* e dizer "Friday, que horas são?". *Modo mesa* mantém a tela ligada e escurecida (celular carregando, como um console).
- **Notificação:** botão *Falar* usa o reconhecimento do Android sem abrir nada; *Cancelar* cancela a ação pendente; *Confirmo* só aparece quando há uma ação pendente e vale **somente para ela** (leva o código daquela pendência: se a FRIDAY propôs outra coisa depois, o toque não executa nada e ela avisa). Ações críticas (nível 3) continuam só com o PIN. Isto foi testado com comandos simulados do Termux:API; não foi visto numa notificação de celular real.
- **Pedidos que ela entende:** "me lembra em 20 minutos de ligar para o cliente", "pesquise o preço do dólar", "crie um arquivo com o resumo da reunião", "liga a lanterna", "manda um SMS para a mãe dizendo que chego às 19h" (pede confirmação), "prepara um WhatsApp para o sócio".

## Estilo JARVIS: o que dizer
| Diga (ou toque no botão do painel) | O que acontece |
|---|---|
| "Friday, bom dia" / "briefing" | Hora, clima, agenda, leads e saúde dos sistemas, falados. Sem gastar IA. |
| "relatório de sistemas" | Bateria, memória, disco, temperatura, IA em uso, auditoria. |
| "modo foco" | 1 hora só com notificações (sem voz). "boa noite" faz o mesmo por 8 horas. |
| "pode falar" / "retomar" | Volta a falar normalmente. |
| "quais protocolos" | Lista os disponíveis (inclusive os seus). |
| "protocolo X" | Executa o protocolo X. |
Protocolos são sequências que **só você** dispara (a IA não consegue). Se um passo precisar de confirmação, o protocolo pausa e pede.

**Seus próprios protocolos:** copie `friday/protocolos.exemplo.json` para `protocolos.json` (pasta `friday-pi`) e edite. Cada passo é `{"falar": "texto"}` ou `{"ferramenta": "nome", "args": {...}}`; dentro de textos, `@briefing`, `@relatorio` e `@tratamento` são trocados na hora. Nome igual ao de um padrão substitui o padrão. Arquivo inválido é ignorado, sem derrubar nada.

**Voz mais "JARVIS":** no `.env`, `TTS_VELOCIDADE=0.92` e `TTS_TOM=0.85` deixam a voz do Android um pouco mais lenta e grave. O efeito depende do mecanismo de voz do aparelho (o do Google costuma obedecer; alguns ignoram): teste valores diferentes e fique com o que soar melhor. Em Configurações do Android → Saída de texto para fala, vale baixar uma voz em português de melhor qualidade.

**Painel:** o botão ◐ no canto troca entre o tema azul (JARVIS) e o dourado (FRIDAY). A abertura animada roda uma vez por sessão; toque nela para pular. Com "reduzir movimento" ligado no sistema, o painel fica sem animações. **Clima:** `CLIMA_LAT`, `CLIMA_LON` e `CLIMA_LOCAL` no `.env` (padrão São Paulo).

## O que pede confirmação (e por quê)
| Ação | Confirmação |
|---|---|
| ler, pesquisar, lembretes, notas, lanterna, localização, criar arquivo | nenhuma (fica na auditoria) |
| SMS, ligação | dizer «confirmo» **logo depois** de ela anunciar a ação, ou «confirmo enviar sms» (verbo + ação) a qualquer hora enquanto vale (45 s), ou tocar em *Confirmo* da própria notificação. «Sim», «pode» e «isso» sozinhos **não** executam |
| qualquer coisa acima depois de ela ler a internet ou um lead **no mesmo pedido** | sobe um nível: SMS passa a exigir o PIN digitado |
Isso existe porque uma página ou mensagem maliciosa pode tentar mandar a IA agir; o PIN só você digita.

## Limites conhecidos (sem enrolação)
- **Celular desligado:** nada roda. Para ela continuar funcionando (ouvindo, vendo, estudando) com o celular desligado, rode o mesmo código num Raspberry Pi/PC/servidor que fica ligado e use o celular só como janela (`servidor/README.md`, `install.sh --servico`).
- **Câmera com a tela apagada:** o Android recente pode bloquear a câmera para apps em segundo plano; se `Friday, olhe` falhar assim, use uma câmera dedicada (`VISAO_FONTE=url`) ou o servidor.
- **Tela apagada:** o Android não deixa um app comum escutar o microfone o tempo todo em segundo plano. "Escutar sempre" só funciona com o painel aberto e a tela ligada (modo mesa). Ouvir com a tela apagada exige um app nativo (projeto futuro). O botão *Falar* da notificação funciona com a tela apagada? Depende do aparelho: o diagnóstico `--completo` mostra.
- O reconhecimento de voz do painel é o do Chrome e **envia o áudio ao Google**. O botão "Ouvir pelo Android" também usa o serviço do aparelho. Digitar não envia nada além do texto para a IA.
- O Chrome para Android pode apitar a cada reinício da escuta contínua. Se incomodar, use o botão *Falar (toque)*.
- As animações do painel (reator, ondas) usam um pouco de bateria e CPU. Em celular fraco, ligue o *Modo mesa* só quando estiver carregando, ou ative "reduzir movimento" no Android.
- Nada disto foi testado em celular real por mim: os testes usam comandos simulados do Termux:API. Por isso o passo 6.
- SMS e ligação dependem do plano da operadora; o Android pode pedir permissão extra na primeira vez.
- Se você perder o celular: o `.env` guarda chaves. Use bloqueio de tela e criptografia do aparelho, e revogue as chaves no painel de cada serviço.
