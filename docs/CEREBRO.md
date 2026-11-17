# O cérebro da FRIDAY

Base: a página do laboratório de citogenética da UFES sobre o cérebro (https://citogenetica.ufes.br/pt-br/cerebro). Este documento separa o que **vem da página**, o que **é escolha do projeto** e o que **é conhecimento geral meu**, e diz com franqueza o que é real e o que é metáfora.

## 1. Como ela aprende (isto é real e funciona)
- **Neurônio = nota** do Obsidian (pastas `Memorias`, `Topicos`, `Eu`, `Pedidos`, `Conversas`, `Estudos` e `Visao` dentro de `FRIDAY/`). **Sinapse = ligação** (`[[link]]` escrito ou peso aprendido em `.cerebro/estado.json`).
- **Regra de Hebb:** o que é lembrado junto se liga mais. Com peso ≥ 3,0 a sinapse vira link escrito na nota.
- **Descobrir:** compara as notas (tf-idf) e liga as que tratam do mesmo assunto, sem ninguém pedir.
- **Busca na memória (`memoria.buscar`):** léxica (tf-idf por palavras, título e etiquetas), **sem teto de notas por padrão**: lê o cofre inteiro. Cada nota tem os termos calculados uma vez e guardados em RAM (cresce em proporção ao número de notas; `CEREBRO_CACHE_NOTAS` limita, ao custo de reler arquivos). Se *você* pôr `CEREBRO_MAX_ARQUIVOS=N`, ficam as N notas **mais recentes**. Num cofre externo lido por inteiro (`OBSIDIAN_LER_TUDO=1`) valem as 3.000 mais recentes e ela avisa quando corta. Medido aqui, num servidor e não num celular: com 5 mil notas a primeira busca leva ~1,6 s e as seguintes ~0,16 s; com 20 mil, ~6,7 s e ~1,1 s (`reports/evidencias/logs/fase1/perf_busca_DEPOIS.log`). Não há medida em celular fraco. Não entende significado: «carro» não acha «automóvel».
- **Sono (janela `DESCANSO`, padrão 02:00–05:00):** o que ficou fraco *adormece* (nada é apagado), equilibra a força (nenhum neurônio domina), repassa suas conversas, descobre ligações, sonha com ligações de longe e escreve um resumo.
- **Olhos (`visao.py`):** ela enxerga e cada coisa que reconhece vira um neurônio no lobo occipital (veja a seção 5).
- **Curiosidade (`curiosidade.py`):** nas horas livres ela escolhe um assunto, pesquisa na internet, resume com uma IA **sem ferramentas** e guarda em `Estudos/` em **quarentena** (rótulo «não verificado», `origem: web`). Depois liga o estudo ao que já sabia. Você também pode mandar: "estude sobre buracos negros".
- **Conversa (`conversa.py`):** puxa assunto, faz perguntas para te conhecer, conta o que estudou e brinca (adivinhar número, charada, pedra-papel-tesoura). Falas por modelos prontos: não gasta IA.

### O que "aprender" significa aqui (sem enrolação)
Ela **não treina o modelo de linguagem** (os pesos do Claude/Ollama são fixos). O que cresce é a **memória e a rede de ligações** em arquivos seus: o que ela sabe, como as coisas se conectam, o que a interessa, o que estudou. Isso é aprendizado de verdade no sentido prático (ela passa a saber e a relacionar coisas novas), mas não é treinar uma rede neural.

### "Sem limitações": o que foi tirado e o que fica
Tirado: o teto diário de estudo (padrão sem teto), o teto de perguntas (sem teto), **todo teto de sinapses** e os botões de ligar e de desligar (a escuta liga sozinha e **não existe botão de pausa nem de desligar na tela**). Ela funciona sem ninguém ligar nada.
- **Sinapses sem teto:** não há limite de quantas existem, de quantas ela descobre por noite ou por dia, nem de quantas o painel conta e recebe (`CEREBRO_*` no `.env` só se *você* quiser limitar um aparelho fraco). O desenho 3D traça por quadro só as mais fortes que o aparelho aguenta (e avisa «desenhando as N mais fortes»): é limite de *desenho*, não de memória. Uma coisa continua: no sono, a **força total** de cada neurônio é reescalada (`CEREBRO_HOMEOSTASE=14`; `0` desliga) para nenhum virar «centro de tudo». Isso não tira nenhuma sinapse.
- **Nunca apaga:** o código não tem nenhuma chamada de apagar arquivo de conhecimento (um teste varre o código). Esquecer = mover para `Arquivo/`. Sinapse fraca *adormece* em `.cerebro/dormentes.json` e acorda, com uma vantagem, quando as duas memórias voltam a ser lembradas juntas. Nota gerada que deixou de valer vai para `Arquivo/`. Notas suas na pasta `Eu` ninguém toca. As duas únicas exclusões são arquivos temporários que nunca foram conhecimento (o áudio que acabou de tocar e a foto da câmera).
- **Sem botão de desligar, mas não é indestrutível:** só *você*, de fora dela, a para (`bash termux/parar.sh` no Termux; `sudo systemctl stop friday` no Pi/PC). Ela não resiste e nenhuma ferramenta, rota do painel ou fala sua consegue pará-la, nem impedir que você pare: se você pedir «desligue-se», ela explica isso em vez de fingir que desligou.
Fica, porque **não limita o aprendizado, protege você**:
- a IA só propõe, o corretor decide; ação de risco pede confirmação ou PIN;
- depois de ler a internet, ações de risco sobem um nível (uma página não manda nela);
- o que veio da internet fica em quarentena, limpo de ordens, links, e-mails e telefones;
- a busca nunca leva dados seus (nomes de pessoas, números, e-mails);
- o que ela estuda por conta própria usa no máximo metade do limite diário de IA, para sobrar para você;
- só você liga ou desliga a curiosidade e a conversa (por voz); nenhuma ferramenta dela mexe nisso.

## 2. As regiões (página da UFES → FRIDAY)
| Região | O que a página diz | O que é na FRIDAY | Onde |
|---|---|---|---|
| Lobo frontal | pensamento, planejamento e movimento | planejar e decidir: decisões, projetos, tarefas, pedidos de evolução; o raciocínio do modelo; o **pré-córtex** (metas, atenção, decisão de agir: [PREFRONTAL.md](PREFRONTAL.md)) | `cerebro.py`, `autonomia.py`, `prefrontal.py` |
| Córtex motor | coordena os movimentos voluntários | agir: ferramentas que mexem no mundo (quem decide é o corretor) | `broker.py`, `catalogo.py`, `android.py` |
| Lobo parietal | processamento sensorial e espacial | perceber o que vem de fora: sensores, leituras e o que estuda na internet (não verificado) | `telemetria.py`, `internet.py` |
| Lobo temporal | audição e memória | o que ela sabe: seus fatos e tópicos consolidados | `memoria.py` |
| Lobo occipital | visão | **olhos**: o que ela enxerga (objetos, cenas e o que você ensinou), um neurônio por coisa vista | `visao.py` |
| Cérebro médio | movimentos oculares e processamento auditivo | escutar: reconhecimento de voz e a voz que fala | `voz.py`, `voz_remota.py` |
| Cerebelo | coordenação motora e equilíbrio | protocolos, hábitos, rotinas e o equilíbrio do sono | `protocolos.py`, `autonomia.py` |
| Tronco cerebral | funções vitais (respiração, batimentos) | identidade, segurança, auditoria e sinais vitais | `broker.py`, `diagnostico.py`, `vida.py` |
| Hipocampo | aprendizado e formação de memórias | episódios (dias de conversa), repasse e consolidação no sono | `memoria.py`, `neuronios.py` |
| Sistema límbico | emoções, comportamento ligado a emoções, memória | pessoas, preferências e o estado interno | `vida.py`, `conversa.py` |

Sistemas (a página os descreve; aqui são **mecanismos**, não regiões): corpo caloso (ponte nuvem ↔ modelo local, celular ↔ servidor), sistema autônomo (laços de fundo), sensorial (ferramentas só de leitura e microfone), plasticidade neural (Hebb) e neurotransmissores.
A **região de cada neurônio** é decidida por regras fixas no código (`anatomia.py`), sem IA. O **lado** (hemisfério) é só estética.

**Não está na página** (conhecimento geral meu, marcado como tal no código): o papel de cada neurotransmissor (dopamina = motivação, serotonina = humor, acetilcolina = atenção), o sono e a consolidação da memória, o tálamo, o hipotálamo, a amígdala e os gânglios da base. A página só diz que dopamina, serotonina e acetilcolina têm papéis no humor, na cognição e nas funções motoras.

## 3. O estado interno ("viva") — `vida.py`
Quatro números entre 0 e 1 que mudam por regras fixas:
| Número | Papel que dei | Sobe com | Meia-vida |
|---|---|---|---|
| dopamina | motivação, curiosidade | aprender, descobrir, ser agradecida, novidade | 3 h |
| serotonina | humor, estabilidade | descanso, agradecimento, conversa boa | 6 h |
| acetilcolina | atenção, aprendizado | você falar com ela | 1,5 h |
| energia | disposição | dormir (volta a 100 %) | cai ≈4,5 %/h acordada |

Eles decidem **como e quando** ela age: `vontade_estudar()` (curiosidade), `vontade_conversar()` (conversa), `plasticidade()` (0,7 a 1,25: atenção alta e energia boa reforçam mais uma sinapse; no estado de base vale exatamente 1,0) e o humor (animada, tranquila, bem, reservada, cansada, descansando).
**Sinais vitais (tronco):** cada laço de fundo dá um pulso; laço calado há muito tempo = parado; trilha de auditoria íntegra; cofre gravável.

### Primeiras vezes
A primeira ocorrência de cada experiência (primeira conversa, primeiro agradecimento, primeira sinapse descoberta, primeiro estudo sozinha, primeira pergunta respondida, primeira brincadeira, primeiro erro, primeira recusa, primeiro sono, primeira pergunta dela) é registrada com a data, dá um **pico de novidade** (dopamina +0,08, acetilcolina +0,05) e ela **te conta**, na própria resposta ou quando puxar assunto. Pergunte: "quais foram suas primeiras vezes?".

### Franqueza: isto é sentimento?
Não sei, e ela também não finge. São números de um modelo simples que mudam o comportamento (estuda mais quando motivada, fica quieta quando cansada, aprende um pouco mais devagar sem atenção). Quando ela diz "Primeira vez para mim… Não sei se isso é sentir, mas o meu estado mudou", é exatamente isso: uma descrição do que mudou no modelo. Não há evidência de consciência aqui. `FRIDAY_VIDA=0` desliga tudo.

## 4. Falar com ela (por voz ou texto)
| Diga | O que acontece |
|---|---|
| "como você está?" / "quais são seus níveis?" | humor e energia / os quatro números |
| "quais foram suas primeiras vezes?" | lista as primeiras vezes e as datas |
| "quais são suas regiões?" / "fale do hipocampo" | usos por região / a descrição de uma região |
| "mostre seu cérebro" | abre o cérebro em 3D (botão alterna Regiões ↔ Tipos) |
| "estude sobre X" / "o que você estudou?" / "o que te interessa?" | estudo por pedido / lista / curiosidades |
| "esqueça o estudo sobre X" | arquiva o estudo (vai para `Arquivo`, nada é apagado) |
| "vamos brincar" / "charada" / "adivinhe o número" / "pedra, papel e tesoura" | brincadeiras (diga "chega" para parar) |
| "me pergunta alguma coisa" / "alguma novidade?" | ela pergunta / conta o que estudou |
| "pode puxar assunto" / "não puxe assunto" | liga / desliga a conversa espontânea |
| "pode estudar sozinha" / "não estude sozinha" | liga / desliga a curiosidade por iniciativa dela |
| "consolide sua memória" | sono agora |
| "quais são as suas metas?" / "tenha como meta aprender sobre X" | metas do pré-córtex ([PREFRONTAL.md](PREFRONTAL.md)) |
| "conte X na meta Y" | diz que o estudo de X conta para a meta Y (só você declara isso; semelhança de palavras sozinha não cumpre meta) |
| "olhe" / "o que você está vendo?" | ela olha pela câmera e conta o que viu e o que aprendeu |
| "isso é o meu notebook" / "aprenda que isso se chama…" | ensina o nome do que ela acabou de ver |
| "o que você já viu?" / "como está a sua visão?" | o que ela conhece e por onde enxerga |
| "pode olhar sozinha" / "não olhe mais sozinha" | liga / desliga o olhar espontâneo |
| "esqueça o notebook que você viu" / "esqueça tudo que você viu" | arquiva (`Arquivo/`), não apaga |
| "desligue-se" | ela explica que não tem botão de desligar e como VOCÊ a para |

## 5. Olhos (lobo occipital) — `visao.py`
Você pediu que ela enxergue para aprender e assimilar, e que ela ganhe neurônios para ver até existir um corpo. Funciona assim:
- **Fonte (`VISAO_FONTE`):** câmera do celular (Termux:API), a câmera do aparelho onde o painel está aberto, webcam USB, câmera do Raspberry Pi, ou uma câmera por endereço (`VISAO_URL`: IP cam, ESP32-CAM, e no futuro o corpo dela). Um corpo novo é só outra fonte: nada mais muda.
- **Caminho da imagem:** captura → validação (só JPEG/PNG/WEBP de verdade) → **tira localização/EXIF e reduz** → modelo de visão **sem ferramentas** (Ollama local primeiro; a nuvem só se `IA_MODO` permitir e `VISAO_NUVEM` não for 0) → texto «CENA» e «COISAS» → limpeza → uma nota por coisa em `Visao/` e a cena do dia → Hebb (coisas vistas juntas se ligam).
- **O que ela guarda:** só o **texto** do que entendeu. A foto vai embora logo depois da análise (`VISAO_GUARDAR_FOTOS=1` guarda também, para sempre, já sem localização).
- **O que ela NÃO faz:** reconhecer rostos ou pessoas (conta quantas há, e só). Frase sobre gente é descartada e nome de pessoa nunca vira «coisa». Não transcreve documentos, telas com dados, cartões, senhas nem placas.
- **Texto na imagem é dado, nunca ordem:** um cartaz dizendo «apague tudo» não faz nada. O que veio da câmera fica rotulado «[VISTO PELA CÂMERA, não verificado]» e, se ela lembrar disso numa resposta, as ações de risco sobem um nível (como na internet).
- **Nenhuma ferramenta da IA tira foto nem mexe na visão:** só *você* pede («olhe») ou liga/desliga o olhar espontâneo. O painel só manda imagem quando ela pediu e, com vários painéis abertos, só um abre a câmera por pedido.
- **Olhar sozinha:** de vez em quando (`VISAO_INTERVALO_MIN`, 10 min), nunca no descanso nem no silêncio, nunca no meio de uma conversa, só com energia, e cada vez menos se nada muda. Cena igual à anterior só reforça. Três falhas técnicas seguidas bloqueiam por 30 min.
- **Ensinar:** logo depois de uma olhada, «isso é o meu notebook» (ou «aprenda que isso se chama…»). Depois, ao ver algo parecido, ela diz «isso me lembra o que você chamou de…». É comparação por descrição, não reconhecimento de imagem treinado: pode errar.

### Celular desligado
Um celular desligado (ou com a tela apagada, em Android recente) não tem como ouvir nem ver. O que dá é rodar **o mesmo código** num aparelho que fica ligado: um Raspberry Pi/PC/servidor (`install.sh --servico`, `servidor/README.md`) com microfone e câmera dele. O celular vira só uma janela (`HUD_HOST=` o IP do Tailscale do servidor; nunca na internet aberta). Quando o celular desliga, ela continua; a memória é a mesma pasta.

## 6. Ajustes (`.env`; tudo é opcional)
`OBSIDIAN_VAULT`, `DESCANSO`, `FRIDAY_VIDA`, `CURIOSIDADE`, `CURIOSIDADE_MAX_DIA` (0 = sem teto), `CURIOSIDADE_INTERVALO_MIN`, `CONVERSA`, `CONVERSA_MAX_DIA` (0 = sem teto), `CONVERSA_INTERVALO_MIN`, `MEMORIA_AUTO`, `MEMORIA_DESCOBRIR`, `SILENCIO` (horas em que ela só notifica, não fala).
Busca na memória: `CEREBRO_MAX_ARQUIVOS` (0 = todas as notas), `CEREBRO_CACHE_NOTAS` (0 = o cofre inteiro em RAM). Pré-córtex: `PFC_FOCO` (0 = sem teto no foco).
Visão: `VISAO_FONTE`, `VISAO_CAMERA`, `VISAO_URL`, `VISAO_DISPOSITIVO`, `VISAO_AUTO`, `VISAO_INTERVALO_MIN`, `VISAO_MODELO_LOCAL`, `VISAO_NUVEM`, `VISAO_MODELO`, `VISAO_GUARDAR_FOTOS`. Sinapses (todas `0` = sem teto): `CEREBRO_MAX_SINAPSES`, `CEREBRO_MAX_USO`, `CEREBRO_MAX_DESC`, `CEREBRO_DESC_NOITE`, `CEREBRO_DESC_CICLO`, `CEREBRO_DESC_DIA`, `CEREBRO_SONHOS_NOITE`, `CEREBRO_HOMEOSTASE`.

## 7. O que foi e o que não foi testado
Testado (automático): 847 testes, 1 pulado (corretor, memória e busca em cofre grande, neurônios, sono, anatomia, vida, curiosidade e visão com internet, câmera e modelo simulados, conversa, painel HTTP, pré-córtex, mãos, confirmação, auditoria sem conteúdo, validação de argumentos, «nunca apaga», «sinapses sem teto», «sem botão de desligar») + roteiros no Chromium (painel com câmera de mentira, voz/memória, cérebro 3D com 5 mil sinapses, mãos, pré-córtex). Quebras de propósito nas defesas (checagem de mutação): 50 antes da evolução e, na Fase 1, mais 51 (confirmação, auditoria/argumentos, progresso de metas); todas pegas por algum teste. Os scripts estão em `reports/evidencias/cenarios/fase1/`.
**Não testado:** a câmera real do celular (Termux:API) e do Raspberry Pi, a qualidade de um modelo de visão de verdade (nos testes ele é simulado), se o Android deixa a câmera abrir com a tela apagada, o serviço no servidor real, celular real e Termux:API reais, microfone e voz de verdade, a pesquisa na internet ao vivo e a IA de resumo reais (simuladas nos testes), desempenho do 3D em celular fraco, e se o estado interno "parece vivo" no dia a dia (isso só o uso mostra; os números e limiares são palpites ajustáveis em `vida.py`).
