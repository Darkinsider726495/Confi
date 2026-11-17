# FRIDAY — assistente pessoal autônoma (estilo JARVIS), com cérebro que aprende

## API de IA alternativa: Groq (Llama)

Para usar uma API que não seja OpenAI nem Claude, veja [`docs/GROQ.md`](docs/GROQ.md). Defina `IA_PROVEDOR=groq` e `GROQ_API_KEY` no `.env`; o modelo padrão é Llama hospedado pela Groq. A chave é externa e pode ter limites/custos. Teste com `python scripts/perguntar_groq.py "Olá, FRIDAY"`.


IA que ouve, responde falando, age por conta própria, estuda sozinha, puxa assunto e **fica de pé sozinha**. O celular Android é a base (via Termux, **como software editável, sem APK**); um servidor em casa é retaguarda opcional.

**Leia primeiro:** `docs/ANDROID.md` (instalar no celular) · `docs/CEREBRO.md` (como ela aprende, regiões, estado interno, o que é real e o que é metáfora) · `docs/ARQUITETURA.md` · `servidor/README.md` · `CLAUDE.md` (para trabalhar nela com o Claude Code)

## O que ela faz
- **Funciona continuamente:** sobe sozinha quando o celular liga (Termux:Boot + supervisor), se reergue se travar e a escuta do painel liga sozinha. **Não existe botão de desligar na tela**; só você a para, de fora dela (`bash termux/parar.sh`).
- **Tem memória e cérebro:** cada memória é um neurônio no seu Obsidian; as ligações crescem com o uso, **sem teto de sinapses**; de madrugada ela "dorme": o que ficou fraco adormece, equilibra, repassa suas conversas, descobre sinapses novas e sonha. **Nada é apagado**: esquecer é arquivar.
- **Enxerga (lobo occipital):** pela câmera do celular, do painel, webcam, Raspberry Pi ou uma câmera por endereço (o corpo dela, no futuro). Cada coisa que reconhece vira um neurônio; você ensina nomes («isso é o meu notebook»). Não reconhece rostos, não guarda foto por padrão, e texto dentro da imagem nunca é ordem.
- **Estuda sozinha:** pesquisa na internet nas horas livres e guarda o que aprendeu em quarentena (`Estudos/`, marcado como não verificado). Você também manda: "estude sobre buracos negros".
- **Conversa de forma espontânea:** puxa assunto, faz perguntas para te conhecer, conta o que estudou e brinca (números, charadas, pedra-papel-tesoura). Sem teto de perguntas.
- **Tem estado interno:** motivação, humor, atenção e energia que mudam o comportamento, e **primeiras vezes** que ela registra e conta. É um modelo simples, não prova de consciência (veja `docs/CEREBRO.md`).
- **Confere se deu certo:** o que ela faz passa por *tarefas*; depois de cada passo ela olha o estado real (banco, arquivos, cofre) e só conta como feito se o efeito existe. Se a ferramenta disse «feito» e não fez, a tarefa falha e a IA é avisada; o que ela não consegue conferir (SMS, ligação…) fica «executada, mas não consegui conferir» (`docs/TAREFAS.md`).
- **Aprende com o que tentou, sem treinar o modelo:** cada tarefa terminada vira uma experiência (o que esperava × o que viu, causas com confiança); na vez seguinte começa pela estratégia que funcionou nas mesmas condições e troca de estratégia se uma falhar. Ela pode **propor** objetivos, mas só executa o que você aprovar (`docs/EXPERIENCIAS.md`, `docs/PLANEJADOR.md`).
- **Não se pisa nem se repete:** duas ações no mesmo recurso (o mesmo relé, contato, arquivo) esperam a vez; depois de um reinício ou queda ela confere por fora o que ficou pela metade, retoma o que é seguro e **nunca repete o que pode já ter acontecido e não dá para conferir** — pede você (`docs/COORDENADOR.md`, `docs/RETOMADA.md`).
- **Tem um pré-córtex:** junta o que ela quer fazer (estudar, conversar, olhar, descansar), decide, guarda metas («tenha como meta aprender sobre X») e confere se deu certo. Só lê o resto e não executa ferramenta (`docs/PREFRONTAL.md`).
- **Tem um pré-córtex distribuído:** nove neurônios de software que conversam por mensagens (no mesmo processo ou em processos separados) para planejar um objetivo, passar pela crítica, executar pelo corretor, conferir o efeito por fora e aprender com a diferença. Tela em `/precortex` e demonstração sem internet: `python3 -m friday.pre_cortex.demo` (`docs/PRE_CORTEX.md`).
- **Mostra o cérebro em 3D** com as regiões da página da UFES (frontal, motor, parietal, temporal, occipital, cérebro médio, cerebelo, tronco, hipocampo, límbico).
- **Painel cinematográfico (HUD), briefing falado, protocolos, lembretes, SMS/ligação com confirmação, pesquisa web, criar arquivos.**

## Segurança em uma frase
A IA só propõe; um corretor em código comum decide, pede confirmação (voz, botão ou PIN) conforme o risco e registra tudo em um log à prova de adulteração. Depois de ler a internet, ações de risco sobem um nível. Aprender sem limites e segurança não se contradizem: a segurança protege o celular, não limita o que ela estuda (`docs/CEREBRO.md`, seção "Sem limitações").

## Início rápido (Termux, no celular)
```
termux-setup-storage
cd ~ && cp ~/storage/downloads/friday-pi.zip . && pkg install -y unzip && unzip friday-pi.zip
cd friday-pi && bash termux/instalar-termux.sh     # instala, pede o PIN, testa e já deixa rodando
```
Atualizar o código sem perder nada: `bash termux/atualizar.sh ~/storage/downloads/friday-pi.zip`. Em PC/Linux para experimentar: `pip install -r requirements-android.txt && python friday/main.py --teclado`.

## Estrutura
```
friday/      código (corretor, cérebro, ferramentas, memória, neurônios, anatomia, vida, curiosidade, conversa, autonomia, painel, 3D)
android/     app opcional «FRIDAY»: janela do painel em tela cheia (`bash android/build.sh` gera o APK)
termux/      instalador, atualizador, supervisor, parada do dono (`parar.sh`), início automático, Ollama
servidor/    pilha opcional em Docker + backup + voz privada (faster-whisper/Kokoro)
tests/       testes automáticos + roteiros do painel no Chromium
docs/        android, cérebro, pré-córtex, pré-córtex distribuído, tarefas, experiências, evolução controlada, planejador, coordenador, retomada, arquitetura
.claude/     Claude Code: configurações, resumo de início de sessão e skills da FRIDAY
```
`install.sh` (raiz) instala no Raspberry Pi/PC com voz local.

## Testes
Ambiente de teste: `pip install -r requirements-test.txt` (inclui pytest, requests, python-dotenv, pillow, numpy; o Playwright só para os roteiros no Chromium). Verificado: a suíte unitária roda do zero num ambiente criado só com esse arquivo.
`python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'` e, com o Playwright, `python tests/e2e_hud.py`, `python tests/e2e_voz_memoria.py`, `python tests/e2e_cerebro.py` (também `e2e_maos.py`, `e2e_prefrontal.py` e `e2e_precortex.py`).
**Não testado:** celular real e Termux:API reais (comandos simulados), microfone e voz de verdade, internet ao vivo e IA de resumo reais (simuladas), 3D em celular fraco, contêineres do servidor, e se o estado interno "parece vivo" no uso. Detalhes em `docs/CEREBRO.md`.

## Pendências conhecidas
Ouvir e ver com o celular desligado ou com a tela apagada (o Android não deixa um app comum; para ela continuar, rode-a num Raspberry Pi/PC/servidor ligado, veja `servidor/README.md`) · câmera do celular em segundo plano (o Android recente pode bloquear) · satélite de voz para o servidor · WhatsApp Business API · chave só de leitura para os leads · trocar as chaves se perder o celular.

## Promoção controlada de automodificações

A evolução local não usa API externa. `friday/gerador_local.py` coloca candidatos em quarentena por arquivo local ou substituição literal única; `friday/evolucao.py` valida, testa numa cópia de staging, cria backup SHA-256, promove atomicamente e reverte se a suíte pós-promoção falhar. O MAE registra experiências na memória episódica quando ativa e no diário de engenharia, mas suas experiências de laboratório não promovem código automaticamente. Leia [`docs/EVOLUCAO.md`](docs/EVOLUCAO.md) para comandos, allowlist, limites e recuperação.

**Limite importante:** staging não é sandbox de kernel; candidatos executados pelos testes ainda têm os acessos do usuário. Não teste código não confiável sem isolamento externo. Backups read-only e hash são proteção contra acidentes, não imutabilidade absoluta contra o mesmo usuário/root.


## API autoevolutiva local

Veja [`docs/API_EVOLUTIVA.md`](docs/API_EVOLUTIVA.md). A API enfileira candidatos, mas não os executa nem promove por HTTP.
\n\n## Evolução distribuída segura\n\nVeja [`docs/EVOLUCAO_DISTRIBUIDA.md`](docs/EVOLUCAO_DISTRIBUIDA.md) para catálogo OpenAPI local, verificação de pares previamente autorizados e promoção automática local opcional com testes fixos, backup e rollback. A descoberta não varre redes nem copia código automaticamente para máquinas encontradas.\n\n\n## Ponte híbrida de IA\n\nA API local autenticada inclui `POST /v1/ia/chat`, com Ollama local primeiro e Groq opcional como fallback. Veja [`docs/PONTE_IA_HIBRIDA.md`](docs/PONTE_IA_HIBRIDA.md). O endpoint é somente textual e não executa ferramentas.\n