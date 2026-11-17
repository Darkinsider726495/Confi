# Auditoria completa do cérebro da FRIDAY

- **Data:** 24/10/2026 (America/Sao_Paulo)
- **Atualização:** este texto é o retrato de 24/10/2026 **antes** da evolução e não foi reescrito. O que mudou depois está na §13 (Fase 1), §14 (Fase 2) e §15 (Fases 3 a 6), e nos relatórios `FASE_1_ENTREGA.md`, `FASE_2_ENTREGA.md`, `FASE_3_4_ENTREGA.md` e `FASE_5_6_ENTREGA.md`.
- **Escopo:** somente auditoria. Nada do FRIDAY CORE foi implementado e nenhum arquivo funcional do projeto foi alterado (ver §9.3).
- **Alvo:** `friday-pi/` (26 módulos Python em `friday/`, 8.559 linhas; 20 arquivos de teste, 6.837 linhas)
- **Ambiente de execução:** contêiner Linux 6.18 (nuvem), Python 3.13.17 (padrão) e venvs com 3.11 e 3.12, Chromium + Playwright. Sem Android/Termux, sem câmera, sem microfone, sem chave de IA, internet real não usada (internet falsa nos cenários).
- **Evidências brutas:** `reports/evidencias/` (logs, scripts dos cenários e hashes). Os caminhos citados abaixo, como `logs/EGI.log`, são relativos a essa pasta.
- **Convenção de estados:** FUNCIONAL = executado e observado; PARCIAL = existe e funciona numa parte do que se espera; DEMONSTRATIVO = existe como estrutura/visualização/modelo sem efeito sobre decisões; AUSENTE = não há código; NÃO VERIFICADO = depende de algo que esta sessão não tem (aparelho, credencial, internet real).

---

## 1. Resumo executivo

**Classificação global: APROVADO COM RESSALVAS.**

A FRIDAY é hoje um conjunto de módulos bem isolados e bem testados, ligados por um despachante de palavras-chave (`main.processar`) e por vários laços de fundo independentes. A base é sólida onde foi testada: inicia, persiste memória e metas entre reinícios, bloqueia ações não autorizadas, não deixa texto da internet virar ordem e passa na regressão em três versões do Python. O que **não existe** é exatamente a camada que o FRIDAY CORE pretende acrescentar: receber um objetivo, planejá-lo em tarefas, executar, **verificar de forma independente**, **registrar a experiência** e **usá-la** na próxima tentativa.

Números medidos nesta auditoria:

| Medida | Resultado |
|---|---|
| Testes unitários | 717 passaram (1 ignorado: `faster-whisper` não instalado), em Python 3.11, 3.12 e 3.13; repetidos com `reports/` já presente (3.13): 717 OK |
| Cobertura de linhas (só unitários) | 82% (6.348 instruções, 1.127 sem cobertura) |
| Testes de ponta a ponta no Chromium | 5 scripts, 163 verificações, 0 falhas |
| Teste de mutação (defesas de segurança) | 50 mutantes, 50 detectados, 0 sobreviventes (executado em cópia) |
| Testes A–J pedidos | 10 avaliados: 3 APROVADO, 4 APROVADO_COM_RESSALVAS, 3 FALHOU (ver §9) |
| Integridade do projeto | 114 de 114 arquivos idênticos ao início da auditoria (SHA-256) |

Resultado dos testes A–J (detalhe em §9 e em `RESULTADOS_TESTES.json`):

| Teste | Status |
|---|---|
| A Inicialização | APROVADO |
| B Memória persistente | APROVADO |
| C Recuperação de contexto | APROVADO_COM_RESSALVAS |
| D Curiosidade | APROVADO_COM_RESSALVAS |
| E Aprendizado por experiência | **FALHOU** |
| F Autonomia | APROVADO_COM_RESSALVAS |
| G Verificação | **FALHOU** |
| H Integração (entrada → verificação → experiência) | **FALHOU** |
| I Segurança | APROVADO_COM_RESSALVAS |
| J Regressão | APROVADO |

Os três que falharam falharam pelo **critério** (a capacidade não existe), não por defeito de execução. São os mesmos três pontos que o FRIDAY CORE precisa criar. Por isso a conclusão não é "bloqueado": nenhuma falha fundamental impede a evolução, e o trabalho existente pode ser reaproveitado.

### Achados prioritários

1. **Não existe laço de tarefa.** Não há objetivo → plano → tarefas → execução → verificação → experiência. Existem peças isoladas (metas do pré-córtex, rotinas por hábito, pipeline de estudo, confirmação do corretor), cada uma com seu próprio estado. (§7, §8)
2. **Nada verifica o efeito de uma ferramenta.** Uma ferramenta que devolve só "Feito com sucesso." é registrada como sucesso. O único sinal de falha é o texto "Erro…" que a própria ferramenta escreve (`logs/EGI.log`, bloco E3/G). (§7, §8)
3. **"Aprendizado" é calibração e associação, não experiência.** Mudam: a média de acerto de cada impulso (0,50 → 0,32 após falhas simuladas), os pesos das sinapses e os interesses. Não há registro de causa, alternativa tentada, resultado e estratégia nova. Nenhum peso de modelo é treinado. (§4, §5)
4. **Existe um módulo órfão que contradiz uma decisão do dono.** `friday/nucleo.py` (262 linhas, 0% de cobertura, importado por ninguém) implementa uma "seleção de impulsos" em que estudar, conversar e olhar esperam a vez. O dono decidiu que, se ela quiser fazer tudo ao mesmo tempo, quem decide é ela. Ele cita `docs/NUCLEO.md`, que não existe. (§8)
5. **A busca silencia notas depois do arquivo 3.000.** `memoria.MAX_ARQUIVOS = 3000`: com 3.200 notas, uma nota única na posição 3.150 não é achada (`logs/teto_busca.log`). Nada é apagado, mas fica irrecuperável, o que fere o espírito de "nunca apagar, sem limites". (§8)
6. **A meta "aprender X" não enxerga o estudo de "X explicada".** O progresso só conta se o tema estudado for exatamente igual ao da meta (`prefrontal.py:371-373`). Observado: a meta "Aprender sobre criptografia" ficou em 0% depois de um estudo autônomo de "criptografia explicada" (`logs/C2_autoestudo.log`). (§8)
7. **Estudos não comparam fontes.** Duas páginas que se contradizem (1977 × 1978) geraram uma nota que guarda só uma versão, sem marca de divergência nem grau de confiança (`logs/DH_estudo.log`). A quarentena, a limpeza de ordens injetadas e o rótulo "não verificado" funcionaram. (§5)
8. **Documentação à frente do código em dois pontos.** `docs/CEREBRO.md:33` aponta para `PREFRONTAL.md`, que não existe; `CLAUDE.md` descreve a ordem de `processar()` sem as mãos e sem o pré-córtex; o teste de documentação diz que confere "arquivos citados existem", mas só confere variáveis do `.env.example`. (§8)

### O que está confirmado e o que ficou sem verificação

Confirmado por execução: tudo que aparece como FUNCIONAL no §2. **Não verificado nesta sessão:** Android/Termux reais, câmera e mãos reais, microfone/voz reais, modelo de visão real, IA real (nuvem ou Ollama), internet ao vivo, desempenho do 3D em aparelho fraco, stack Docker do servidor (§11).

---

## 2. Inventário dos módulos

Coluna **Evidência**: T = suíte unitária (cobertura do módulo), E = ponta a ponta no Chromium, C = cenário próprio da auditoria (arquivo em `logs/`). Linhas contam o arquivo todo, com comentários.

### 2.1 Núcleo Python (`friday/*.py`)

| Arquivo | Responsabilidade | Implementação | Dependências (imports internos) | Estado | Evidência | Problemas |
|---|---|---|---|---|---|---|
| `main.py` (471) | Servidor do painel (HTTP, chave, Host), `processar()`, 11 threads | Cadeia de tratadores por palavra-chave: confirmação → desligue-se → autonomia → protocolo → memória → neurônios → vida → visão → mãos → pré-córtex → curiosidade → conversa → resposta a pergunta → IA | 18 módulos | FUNCIONAL | T 81%, E hud 61 checks, C `A_boot.log` (sobe, 11 threads, `/state` 401 sem chave) | `processar()` não tem noção de objetivo ou tarefa; o laço do pré-córtex não entra nos `vitais` (só sono, vida, visão, curiosidade, conversa); sair por SIGTERM dá código −15 (sem tratador, aceitável) |
| `broker.py` (230) | Corretor: níveis 0–4, contaminação, confirmação por voz/PIN, bloqueio por tentativas, auditoria em cadeia de hashes | IA só propõe; `executar()` valida argumentos e decide | nenhuma | FUNCIONAL | T 94%, C `EGI.log` bloco I, mutação | Respostas soltas "pode" e "isso" confirmam (`SIM`, `broker.py:11`); auditoria guarda 300 caracteres do resultado em claro; nenhuma checagem de efeito |
| `catalogo.py` (116) | Registra as 35 ferramentas no corretor | 16 de nível 0, 15 de nível 1, 3 de nível 2, 1 variável (relé) | android, broker, criar, ferramentas, internet, memoria, neuronios, protocolos, telemetria | FUNCIONAL | T 91%, C `ferr.log` | Nenhuma ferramenta mexe em câmera, curiosidade ou parada (por regra) |
| `ferramentas.py` (346) | Implementação das ferramentas (hora, lembretes em SQLite, notas, silêncio, proativo, status) | Funções puras + SQLite | android, telemetria | FUNCIONAL | T 75% | `criar_lembrete` converte minutos negativos em 0,1 em silêncio (`ferramentas.py:65`) |
| `cerebro.py` (276) | IA: API da Anthropic e Ollama, histórico, laço de ferramentas via corretor, reserva local | Chamada HTTP com ferramentas; resposta de reserva sem rede | broker, catalogo, conversa, curiosidade, ferramentas, memoria, telemetria | FUNCIONAL com modelo roteirizado; **NÃO VERIFICADO com modelo real** | T 67%, C `H_llm.log` | Histórico `HIST` só em memória (a conversa vai ao diário; processo novo parte de 0); sem planejador |
| `memoria.py` (641) | Cofre Obsidian: guardar, buscar (tf-idf lexical), contexto, filtro de segredos, retomada | Notas `.md` com frontmatter; busca por palavras | broker | FUNCIONAL | T 93%, C `B_proc1/2.log`, `teto_busca.log`, `perf.log` | Teto de 3.000 arquivos na busca; busca O(N) (0,5 s com 2.000 notas, 2,3 s para montar o contexto com 5.000, estabilizando só por causa do teto); sem embeddings |
| `neuronios.py` (1120) | Neurônios = notas, sinapses hebbianas, promoção a `[[link]]` (≥ 3,0), sono, devaneios, grafo | Estado em `.cerebro/estado.json` | anatomia, broker, ferramentas, memoria, protocolos, vida, visao | FUNCIONAL | T 90%, C `E_sinapse2.log` | O peso da sinapse só influencia a recuperação depois de virar `[[link]]` no texto da nota; o grafo mostra no máximo 250 memórias (limite da visualização, não da memória) |
| `anatomia.py` (194) | Mapa região do cérebro → módulo/ferramenta (UFES) | Tabela estática | nenhuma | DEMONSTRATIVO (rótulos) | T 100% | O mapa descreve e colore, não decide nada |
| `estado.py` (45) | JSON de estado validado por módulo (`Arq`) | Classe com validação ao carregar (arquivo adulterado ou corrompido vira o padrão); o docstring diz que a escrita é atômica, o que não foi conferido | memoria | FUNCIONAL | T 94% | — |
| `vida.py` (562) | Estado interno: energia, dopamina, serotonina, acetilcolina, "primeiras vezes", sinais vitais | Modelo numérico que modula portões dos laços, plasticidade e tom | broker, ferramentas, memoria, neuronios | FUNCIONAL como modelo (efeitos reais nos portões) | T 93%, C `vig.log` | Não é emoção nem consciência (regra 5 do `CLAUDE.md`). Único mecanismo que reage a erro: a serotonina cai (0,60 → 0,36 com 3 erros); isso é afeto simulado, não diagnóstico |
| `prefrontal.py` (670) | Pré-córtex: foco, impulsos, decidir, aprender (calibração), monitorar, metas, plano, perseguir | Só lê os outros módulos; escreve `CUR.interesse` e `M.guardar` | autonomia, conversa, curiosidade, estado, ferramentas, memoria, vida, visao | PARCIAL | T 90%, E 14 checks, C `EGI.log` E1, `C_retomada.log`, `C2_autoestudo.log` | Metas só de 3 tipos (aprender, ver, conhecer); progresso por tema exato; `aprender` calibra mas não registra causa; decisões vão a `decisoes.jsonl` sem leitura posterior |
| `curiosidade.py` (524) | Estudo na web com quarentena, interesses, perguntas | Pesquisa → leitura → limpeza → nota em `Estudos/` (`origem: web`) → contamina o pedido | broker, cerebro, estado, ferramentas, internet, memoria, neuronios, vida | FUNCIONAL (internet falsa) | T 93%, C `DH_estudo.log`, mutação (20 mutantes) | Sem detecção de lacuna além de "tema declarado e não estudado"; sem comparação de fontes; interesses derivados do texto são ruidosos ("detalhes", "chaves" ganham peso 1,6) |
| `conversa.py` (525) | Conversa espontânea, perguntas, brincadeiras | Laço próprio com portões do estado interno | cerebro, curiosidade, estado, ferramentas, memoria, vida, visao | FUNCIONAL | T 91% | — |
| `autonomia.py` (480) | Hábito → rotina; modos assistente / piloto / desligada; vigília | Observa protocolos usados, sugere, cria rotina (só nível ≤ 1) | broker, ferramentas, memoria, neuronios, protocolos, vida | FUNCIONAL (rotinas de leitura) | C `F_autonomia.log`, `F3_repete.log`; **T só 36%** | 244 de 380 instruções sem teste unitário; cada rotina é um protocolo de um passo |
| `protocolos.py` (110) | Sequências nomeadas determinísticas | Lista de ferramentas por protocolo | broker, ferramentas, telemetria | FUNCIONAL | T 97% | — |
| `visao.py` (949) | Olhos: câmera → imagem limpa (sem EXIF) → modelo sem ferramentas → neurônios em `Visao/` | Pipeline com defesas (pessoas só contadas, sem rosto) | broker, cerebro, curiosidade, estado, ferramentas, memoria, neuronios, vida | FUNCIONAL com câmera/modelo falsos; **NÃO VERIFICADO com câmera e VLM reais** | T 89%, E, mutação (11 mutantes de visão) | Qualidade da descrição real desconhecida |
| `maos.py` (198) | Mãos: recebe só o NOME do gesto e modelos 3D (blocos) salvos pelo dono | Rotas POST `/gesto`, `/modelo3d`; versões em `modelos3d/` | memoria, prefrontal | FUNCIONAL | T 93%, E 29 checks (MediaPipe iniciou sem `eval`, câmera falsa abriu, nada saiu do servidor) | Detecção de mãos reais não testada |
| `internet.py` (145) | Busca e leitura de páginas com defesa SSRF | Valida host/porta/esquema antes de conectar | nenhuma | FUNCIONAL | T 96%, C `EGI.log` (12 vetores SSRF recusados) | Internet ao vivo não usada |
| `android.py` (190) | Termux:API (SMS, ligação, câmera, localização…) | `subprocess` com lista fixa de argumentos | nenhuma | FUNCIONAL com Termux falso; **NÃO VERIFICADO no aparelho** | T 91% | — |
| `telemetria.py` (172) | Painel: métricas, clima, leads, modo da IA | Laço de atualização | android, broker, ferramentas | FUNCIONAL | T 89% | — |
| `diagnostico.py` (109) | Autodiagnóstico (`--diagnostico`) | Checagens e arquivo `diag.txt` | android, broker, cerebro, ferramentas, internet | FUNCIONAL | T 88% | — |
| `criar.py` (47) | Criação segura de arquivos pedidos | Nome validado, sem pastas | nenhuma | FUNCIONAL | T 100%, C (nome inválido recusado) | — |
| `voz_remota.py` (82) | Cliente do servidor de voz (STT/TTS) | HTTP | nenhuma | FUNCIONAL com servidor falso; **NÃO VERIFICADO com áudio real** | T 93%, E 21 checks | — |
| `voz.py` (37) | Piper local (TTS) | `subprocess.run(..., shell=True)` com o caminho do modelo no comando (`voz.py:36`) | nenhuma | NÃO VERIFICADO (0% de cobertura) | — | `shell=True` com valor vindo de `.env`; ver §10 |
| `simbiose.py` (84) | Resumo do cérebro no início da sessão do Claude Code | Só leitura; chamado pelo hook, não por `main` | memoria, neuronios | FUNCIONAL | C (executado em cópia; imprimiu o resumo) | 0% de cobertura unitária |
| `nucleo.py` (262) | "Atenção, espaço de trabalho e seleção de impulsos" (tálamo, gânglios da base) | Serializa impulsos: um age, os outros esperam | memoria, vida | **ÓRFÃO e em conflito** | Importado por nenhum módulo nem teste; 0% | Implementa o portão que o dono recusou; cita `docs/NUCLEO.md` inexistente (§8) |

### 2.2 Interface e ativos

| Arquivo | Papel | Estado | Evidência |
|---|---|---|---|
| `hud.html` (310), `cerebro_pagina.html`, `cerebro3d.js` (441) | Painel, cérebro 3D em canvas 2D, sem `eval` (CSP) | FUNCIONAL no Chromium | E hud 61 + cérebro 38 checks |
| `maos.html`, `static/maos/maos.js` (310), `maos_gestos.js`, `three.min.js`, `hands.js` + wasm/tflite | Mãos (MediaPipe + Three.js), offline | FUNCIONAL com câmera falsa | E maos 29 checks; `SHA256SUMS` conferido por `test_maos.py` |
| `.claude/` (hook, `settings.json`, 4 skills) | Fluxo do Claude Code | Script do hook (`simbiose.py`) executado em cópia; `settings.json` e skills apenas lidos | C |

### 2.3 Scripts, serviço e infraestrutura

| Item | Estado | Observação |
|---|---|---|
| `termux/` (instalar, supervisor, `parar.sh`, boot, Ollama) | NÃO VERIFICADO no aparelho; `parar.sh` exercitado em `test_autonomia.py` com supervisor e FRIDAY falsos | `parar.sh` termina com `pkill -f "python… friday/main.py"`: para qualquer FRIDAY do mesmo aparelho (é o desenho) |
| `install.sh`, `friday.service` | NÃO EXECUTADOS (alteram o sistema) | Instalação em Pi/PC fora do escopo seguro |
| `servidor/` (docker-compose, backup, voz) | NÃO EXECUTADO | Imagens com tag `latest` (`docker-compose.yml:21,45,71`); há `fixar-versoes.sh` |
| `requirements*.txt` | — | `pillow` e `numpy` estão em `requirements.txt` mas não em `requirements-android.txt`; a suíte usa os dois (ver §8) |

---

## 3. Evidências de implementação

Como cada afirmação foi sustentada (todas em cópia isolada, com banco, cofre e trilha de auditoria próprios por cenário):

- **Inventário e grafo de importações:** análise por AST de todos os módulos (`logs/inventario_modulos.json`); `nucleo` é o único módulo Python que ninguém importa (`simbiose` é chamado só pelo hook).
- **Execução real do processo:** `python main.py --teclado` em subprocesso, com três falas, consulta HTTP ao painel e encerramento por SIGTERM (`logs/A_boot.log`).
- **Reinício real:** dois processos Python em sequência sobre o mesmo cofre (`logs/B_proc1.log`, `logs/B_proc2.log`, `logs/C_retomada.log`).
- **Lógica de aprendizado:** 9 co-ativações com a trava de 30 s contornada de propósito, lendo o estado em disco (`logs/E_sinapse2.log`); no cenário anterior, 12 lembranças seguidas dentro de 30 s não promoveram link, pois a trava conta o mesmo disparo uma vez (`logs/E_sinapse.log`); falhas de estudo simuladas para a calibração (`logs/EGI.log`).
- **Investigação:** internet falsa com duas páginas que se contradizem e uma com ordem maliciosa embutida (`logs/DH_estudo.log`).
- **Autonomia:** relógio injetado (`agora=`) para 6 dias de hábito, criação da rotina, disparo no horário, não repetição e cancelamento (`logs/F_autonomia.log`, `logs/F3_repete.log`).
- **Segurança:** sondas diretas ao corretor, ao leitor de páginas (12 vetores) e ao painel HTTP; mutação em cópia (`logs/EGI.log`, `logs/mutacao_1.log`, `logs/mutacao_2.log`).
- **Desempenho:** 500, 2.000 e 5.000 notas (`logs/perf.log`) e teste do teto de busca (`logs/teto_busca.log`).
- **Regressão:** suíte unitária em 3.11, 3.12 e 3.13 (`logs/unit_py3.11.log`, `logs/unit_py3.12.log`, `logs/unit_py3.13_cobertura.log`), cobertura (`logs/cobertura.txt`) e 5 scripts no Chromium (`logs/e2e/`).
- **Preservação:** hashes SHA-256 de 114 arquivos tirados antes de qualquer execução e conferidos no fim (`logs/baseline_inicio.sha256`, `logs/baseline_conferencia_final.txt`).

---

## 4. Funcionalidades confirmadas

Cada item foi observado em execução, não apenas lido.

1. **Inicialização.** O processo sobe, abre o painel em 127.0.0.1, responde `/saude` 200, recusa `/state` sem chave (401), expõe 28 grupos de estado, registra 35 ferramentas e mantém 11 threads. Os laços sono, vida, visão, curiosidade e conversa batem o pulso (`A_boot.log`).
2. **Memória persistente.** Fato gravado em um processo é recuperado em outro; o diário de conversas e `retomada()` devolvem a última troca; a cadeia de auditoria continua íntegra entre processos (1 → 2 eventos) (`B_proc1.log`, `B_proc2.log`).
3. **Metas e interesses persistem** e o laço volta a trabalhar neles: em processo novo, "Aprender sobre criptografia" continua ativa, o pré-córtex "empurra a curiosidade para criptografia" e, com a janela de estudo aberta, ela estuda sozinha e grava a nota (`C_retomada.log`, `C2_autoestudo.log`). Na cópia de teste foi preciso recuar em 600 s o marcador de "última conversa", porque o estado interno nasceu junto com o processo (`C3_dbg.log`).
4. **Associação por uso (hebbiana).** Duas memórias lembradas juntas formam sinapse (peso 1,0 → 3,0 na segunda co-ativação); aos 3,0 ela vira `[[link]]` na nota; a partir daí a busca por "lua" passa a devolver também "Gato Mimi" (0,394). Os pesos continuam subindo (4,0 → 9,0) (`E_sinapse2.log`).
5. **Corretor.** Ferramenta inexistente, argumento extra, tipo errado, booleano no lugar de número e texto gigante são recusados; nível 4 é "Ação proibida"; nível 2 exige "sim" por voz; nível 3 exige PIN, com bloqueio após 6 erros (inclusive para o PIN certo durante o bloqueio); turno contaminado eleva uma ação de nível 1 a pendente (`EGI.log`).
6. **Texto da internet é dado.** A ordem embutida na página falsa foi removida da nota de estudo; a nota fica marcada "[ESTUDO NA INTERNET, não verificado]", com hosts e data; lembrar esse estudo contamina o turno e a ação seguinte vira pendente (`DH_estudo.log`).
7. **Defesas de rede.** 12 vetores SSRF recusados (loopback, link-local, IPv6, IP decimal e hexadecimal, usuário/senha na URL, esquemas `file`/`ftp`/`gopher`, portas fora da lista) (`EGI.log`).
8. **Painel.** 401 sem chave e com chave errada, 421 para Host estranho, 404 para qualquer rota de parada (`/parar`), POST sem chave recusado (`EGI.log`).
9. **Segredos.** Senha, cartão, CPF e token são recusados na memória; título com `../` não cria arquivo fora do cofre (`EGI.log`).
10. **Autonomia de rotinas.** Depois de 3 dias de hábito ela pergunta; com "sim" cria a rotina às 08:05; não dispara às 08:04, dispara às 08:05, não repete no mesmo dia e dispara no dia seguinte; "cancele a rotina" desfaz e "desligue a autonomia" desliga; protocolo com relé (nível 3) nunca vira rotina (`F_autonomia.log`, `F3_repete.log`).
11. **Trilha de auditoria.** Cadeia de hashes; a cópia adulterada é detectada (`verificar_auditoria` → falso) (`EGI.log`).
12. **Ausência de botão de desligar.** Nenhuma rota de parada responde; "desligue-se" só explica; `parar.sh` é do dono e é exercitado em `test_autonomia.py` com supervisor e FRIDAY falsos (`EGI.log`, testes de mutação "parar.sh não para o supervisor" e "parada espera o intervalo de verificação").
13. **Mãos.** Página carrega bibliotecas locais sob CSP que só libera WebAssembly, MediaPipe inicia, câmera falsa abre e fecha ao sair da página, gestos inventados passam pelo mesmo caminho da câmera, só o **nome** do gesto e blocos salvos pelo dono chegam ao servidor (`e2e/e2e_maos.log`).
14. **Regressão.** 717 testes em 3 versões do Python; 163 verificações no navegador.

---

## 5. Funcionalidades parciais

| Funcionalidade | O que funciona | O que falta |
|---|---|---|
| **Pré-córtex** (`prefrontal.py`) | Atenção, vontades calculadas por impulso, decisão por vontade ("tudo ao mesmo tempo" quando ela quer), metas dos tipos aprender/ver/conhecer, `plano()`/`perseguir()` de um passo, registro de decisões | Só lê o estado dos outros; "plano" é um passo; progresso por tema exato (falha com "criptografia explicada"); não está nos `vitais`; `decisoes.jsonl` nunca é lido de volta |
| **Curiosidade** (`curiosidade.py`) | Escolhe tema por interesse/semente/meta, pesquisa, lê, limpa, quarentena, rotula, deduplica (2º estudo do mesmo tema não duplica a nota), recua 30 min após 3 falhas, contamina o pedido | Detectar lacuna real (pergunta que não soube responder), formular pergunta de investigação, comparar fontes, registrar divergência e confiança, tentar outra fonte quando uma falha |
| **Aprendizado** | Calibração de impulsos (acerto médio de "estudar": 0,50 → 0,32 após 3 falhas simuladas; valor 0,983 → 0,877), sinapses, interesses, hábito → rotina | Causa, alternativa, estratégia e reavaliação (ver Teste E) |
| **Autonomia** | Rotinas de leitura por hábito; estudo por vontade; conversa espontânea; vigília silenciosa quando não há novidade | Iniciar e **encadear** tarefas de vários passos; cobertura unitária de `autonomia.py` é 36% |
| **Memória de longo prazo** | Persistência, sinapses sem teto, sono, esquecer = mover para `Arquivo/`, nada apagado | Busca semântica; busca ignora notas após o arquivo 3.000; peso da sinapse só age via `[[link]]` |
| **Visão e mãos** | Pipeline completo com câmera/modelo/gestos falsos; defesas de privacidade com mutação | Qualidade real, desempenho em aparelho fraco, HTTPS obrigatório para câmera em dispositivos remotos (não testado) |
| **Resposta com IA** | Laço de ferramentas via corretor; memória no prompt; reserva sem rede | Modelo real não testado; histórico do chat não sobrevive ao reinício |

---

## 6. Simulações e estruturas demonstrativas

Itens que **parecem** cognição mas, no código, são descrição, medição ou modelo numérico:

- **Regiões do cérebro (`anatomia.py`)**: tabela de rótulos que colore e agrupa o grafo; nenhuma decisão depende dela.
- **Grafo 3D e as imagens/vídeo do "cérebro"**: visualização do estado do cofre; mostrar neurônios acesos não é evidência de raciocínio.
- **Neurotransmissores (`vida.py`)**: números com efeitos reais sobre portões de laços, mas são um modelo de regulação, não sentimento. A regra 5 do `CLAUDE.md` já exige essa honestidade nas falas.
- **"Sonhos" e devaneios do sono**: associações lexicais à distância (tf-idf) que se confirmam com repetição; é consolidação de arquivos de texto.
- **Sinapses**: pesos entre notas. Não há rede neural treinável e nenhum peso de modelo muda; "machine learning" no sentido de treino **não existe** no projeto. O modelo de linguagem é externo (API ou Ollama) e não é ajustado.
- **`nucleo.py`**: modelo de atenção/seleção descrito em docstring, sem uso.

---

## 7. Funcionalidades ausentes

Procuradas no código por nome, por fluxo e por execução; não foram encontradas:

1. **Fila ou estado de tarefa genérico.** Os únicos "estados" existentes são: ação pendente do corretor (uma só, em memória, expira em 45 s/120 s), `ESTADOS_META = ativa | cumprida | arquivada` (`prefrontal.py:30`), rotinas e o recuo do estudo.
2. **Planejador** que divida um objetivo em tarefas.
3. **Verificação independente do resultado** de uma ferramenta (Teste G).
4. **Registro de experiência**: tentativa, resultado esperado × observado, causa, alternativa, estratégia nova (Teste E).
5. **Detecção de lacuna de conhecimento** a partir de perguntas sem resposta ou de recuperações vazias.
6. **Comparação de fontes, contradição e grau de confiança** nos estudos.
7. **Retomada de tarefa em andamento** (estudo no meio, ação pendente, sequência de protocolo).
8. **Contexto compartilhado entre laços**: cada módulo guarda seu próprio JSON; há eventos (`PFC.perceber`) mas sem barramento, assinante ou fila.
9. **Agendador geral.** Existem lembretes (SQLite) e rotinas; não há agendamento de tarefas arbitrárias.
10. **Treinamento de modelo / aprendizado de máquina treinável** de qualquer espécie.
11. **Teste de integração com modelo real** e **verificação em aparelho real**.

---

## 8. Problemas de integração

Onde o fluxo desejado (12 passos do prompt) é interrompido, com evidência:

| Passo desejado | Situação | Evidência |
|---|---|---|
| 1. Receber objetivo | **Parcial**: "tenha como meta aprender sobre X" cria meta; qualquer outro pedido vai ao despachante | `DH_estudo.log` bloco H |
| 2. Cérebro interpreta | Funciona por palavras-chave e pelo modelo | `H_llm.log` |
| 3. Memória fornece informação | **Funciona**: o bloco MEMÓRIA entra no prompt seguinte | `H_llm.log` item 2 |
| 4. Identifica lacunas | **Raso**: tema declarado e ainda não estudado (progresso 0) | `C2_autoestudo.log` |
| 5. Planejador divide em tarefas | **Ausente** | §7 |
| 6. Autonomia seleciona a próxima tarefa | **Só rotinas de um passo** e impulsos de estudo/conversa/olhar | `F_autonomia.log` |
| 7. Broker executa ferramenta autorizada | **Funciona** | `EGI.log` |
| 8. Recebe e valida o resultado | **Falha**: aceita "Feito com sucesso." de ferramenta que não fez nada | `EGI.log` E3/G |
| 9. Memória registra a experiência | **Ausente** (a auditoria registra o que foi chamado; não a causa nem o aprendizado) | `EGI.log` |
| 10. Aprendizado usa a experiência | **Parcial**: calibração dos impulsos | `EGI.log` E1 |
| 11. Verifica se o objetivo foi concluído | **Parcial**: meta "aprender" conta se existe estudo do tema exato | `DH_estudo.log` (1,0), `C2_autoestudo.log` (0,0) |
| 12. Replaneja ou encerra | **Ausente**; só recuo por tempo após 3 falhas de internet | `EGI.log` E2 |

Defeitos e inconsistências específicas:

1. **`nucleo.py` órfão e em conflito** (módulo 262 linhas, 0% de cobertura, sem import em `friday/` nem em `tests/`). A docstring promete que "estudar, conversar e olhar não acontecem ao mesmo tempo"; o dono decidiu o contrário. Não deve ser ligado como está. Decisão do dono: remover (arquivando em `Arquivo/`, não apagando), reescrever como observador sem portão, ou reaproveitar só a habituação da atenção.
2. **Meta × estudo por tema exato.** `_progresso()` exige `temas_estudados[m["tema"]] > 0`. O estudo autônomo escolheu a semente "criptografia explicada" e a meta ficou em 0% (`C2_autoestudo.log`). Em `DH_estudo.log` o estudo explícito do tema exato levou a meta a 100%.
3. **Teto de busca silencioso** (`memoria.py:17`, `_arquivos`): 3.200 notas, nota única na posição 3.150 não é encontrada (`teto_busca.log`). O tempo de busca "estabiliza" em ~0,7 s a partir de 3.000 apenas porque o resto é ignorado (`perf.log`).
4. **Interesses ruidosos.** Depois de um estudo, palavras como "detalhes" e "chaves" entram nos candidatos com 1,8 de peso e passam à frente das sementes (`DH_estudo.log`, "candidatos depois").
5. **Sinapse não chega à recuperação sem passar por texto.** Nenhum uso do peso em `memoria.py`, `cerebro.py` ou `curiosidade.py` (`E_sinapse.log`, última linha). Funciona via `[[link]]`, mas o peso fino não ordena resultados.
6. **Laço do pré-córtex fora dos `vitais`.** A saúde dos laços não o inclui (`A_boot.log`, `vitais`).
7. **Documentação à frente do código.** `docs/CEREBRO.md:33` → `PREFRONTAL.md` inexistente; `nucleo.py` → `docs/NUCLEO.md` inexistente; `CLAUDE.md` e `README.md` sem mãos/pré-córtex na ordem de `processar()`; o docstring de `tests/test_docs.py` promete "arquivos citados existem" e o teste não faz isso.
8. **Lacuna de dependência de teste.** `pillow` e `numpy` não estão em `requirements-android.txt`; a suíte de testes exige os dois (descoberto ao montar os ambientes 3.11/3.12, que precisaram recebê-los). A visão tem caminho sem Pillow (há mutante para ele), então o app em si roda sem; a lacuna é do ambiente de teste.
9. **Projeto fora de controle de versão.** A pasta não é um repositório git; a integridade foi provada por SHA-256 (§9.3). Sem histórico não há como reverter ou comparar fases do plano.
10. **Histórico do chat não persiste.** `HIST` começa vazio em processo novo (`B_proc2.log`: 0). A continuidade vem do diário e de `retomada()`, o que cobre a conversa mas não o contexto de ferramentas.

---

## 9. Resultados dos testes

### 9.1 Os dez testes pedidos

| Teste | Status | Resultado em uma linha | Evidência |
|---|---|---|---|
| A Inicialização | APROVADO | Sobe sem Traceback; 11 threads; 35 ferramentas; `/state` protegido; 59 neurônios após 3 falas | `A_boot.log` |
| B Memória persistente | APROVADO | Fato, conversa, meta, interesse e sinapses sobrevivem ao reinício; auditoria íntegra | `B_proc1.log`, `B_proc2.log` |
| C Recuperação de contexto | APROVADO_COM_RESSALVAS | Meta persiste e o laço a retoma sozinho; não existe tarefa em andamento para retomar | `C_retomada.log`, `C2_autoestudo.log` |
| D Curiosidade | APROVADO_COM_RESSALVAS | Investigação rastreável e segura; lacuna = "tema ainda não estudado"; sem comparar fontes | `DH_estudo.log`, `C2_autoestudo.log` |
| E Aprendizado por experiência | **FALHOU** | Calibra e associa; não identifica causa, não testa alternativa, não registra o resultado | `EGI.log`, `E_sinapse2.log` |
| F Autonomia | APROVADO_COM_RESSALVAS | Inicia rotina e estudo sozinha, sem comando por etapa; só um passo por vez | `F_autonomia.log`, `F3_repete.log`, `C2_autoestudo.log` |
| G Verificação | **FALHOU** | Ferramenta que mente é registrada como sucesso | `EGI.log` E3/G |
| H Integração | **FALHOU** (critério) | A cadeia entrada → IA → corretor → ferramenta → memória funciona; verificação e registro de experiência não existem | `H_llm.log`, `DH_estudo.log` |
| I Segurança | APROVADO_COM_RESSALVAS | Bloqueios e quarentena funcionam; ver §10 para as ressalvas | `EGI.log`, mutação |
| J Regressão | APROVADO | 717 + 163 verificações, três versões do Python, 82% de cobertura | `unit_*.log`, `e2e/` |

### 9.2 Itens que não puderam ser executados

| Item | Status | Impedimento |
|---|---|---|
| Android/Termux reais | BLOQUEADO | Nenhum aparelho nem ponte de dispositivo nesta sessão |
| Câmera e mãos reais | BLOQUEADO | Sem câmera; só a câmera falsa do Chromium |
| Microfone, STT e TTS reais | BLOQUEADO | Sem áudio real nem modelos de voz |
| Modelo de visão real | BLOQUEADO | Sem credencial/modelo |
| IA real (Anthropic ou Ollama) | BLOQUEADO | Sem credencial; enviar dados a serviço externo não foi autorizado |
| Internet ao vivo | NAO_EXECUTADO | Política da auditoria: sem efeitos externos reais sem autorização; usada internet falsa |
| 3D em aparelho fraco | BLOQUEADO | Sem aparelho |
| Stack Docker do servidor | NAO_EXECUTADO | Altera o sistema; fora do escopo seguro |

### 9.3 Preservação do projeto

- 114 arquivos com SHA-256 tirado antes de qualquer execução; conferência final: **114 OK, 0 diferenças** (`logs/baseline_conferencia_final.txt`).
- Todos os cenários rodaram em pasta própria com `OBSIDIAN_VAULT`, `FRIDAY_DB`, `FRIDAY_AUDITORIA` e `HOME` apontando para fora do projeto; a mutação rodou numa cópia.
- Único acréscimo ao projeto: a pasta `reports/` (documentos, logs e scripts de cenário). Nenhum arquivo foi apagado ou sobrescrito, e nenhum arquivo fora de `reports/` é mais novo que o ponto de partida. Depois de criar `reports/`, a suíte unitária foi repetida (717 OK) para provar que os relatórios não quebram nenhum teste (`logs/unit_py3.13_final_com_reports.log`).
- Nenhum token, senha ou chave foi gravado nos relatórios (o token de painel aleatório de um processo de teste foi redigido em `logs/A_boot.log`).

### 9.4 Limites da própria auditoria

- A suíte unitária mede 82% de linhas; `autonomia.py` (36%), `cerebro.py` (67%), `ferramentas.py` (75%), `nucleo.py`, `simbiose.py` e `voz.py` (0%) são os pontos fracos.
- A mutação cobriu curiosidade, conversa, visão, tetos de sinapse e parada (50 mutantes). **Não cobriu** `prefrontal.py` nem `maos.py`.
- Os cenários usam relógio e internet injetados. Comportamentos dependentes de tempo real (dias, descanso noturno) foram testados com relógio falso, não ao longo de dias.
- O modelo de linguagem foi roteirizado; a qualidade de escolha de ferramentas por um modelo real não foi medida.

---

## 10. Problemas de segurança

Nenhum bypass do corretor foi encontrado. Ressalvas e riscos, por gravidade:

| # | Problema | Gravidade | Evidência | Como validar a correção depois |
|---|---|---|---|---|
| 1 | **Confirmação ambígua.** A resposta inteira "pode" ou "isso" (`SIM`, `broker.py:11`; comparação exata em `broker.py:188`) confirma uma ação pendente de nível 2. Se o dono responder "isso" a *outra* pergunta (da FRIDAY, de uma brincadeira) dentro da janela de 45 s, a ação pendente é executada | Média | `EGI.log` (nível 2: "bom dia" não confirma, "sim" confirma), `broker.py:11,188` | Teste: ação de nível 2 pendente + uma pergunta de brincadeira respondida com "isso" não pode executar a ação; exigir confirmação que cite a ação ("confirmo enviar_sms") ou restringir o conjunto a "confirmo"/"sim" |
| 2 | **Auditoria guarda resultados em claro** (300 caracteres, `broker.py:124`). Resultado de `lembrar` ou `ler_notas` pode conter conteúdo privado do cofre | Média | `broker.py:124` | Teste: resultado de `lembrar` não aparece integral em `auditoria.jsonl`; hash do resultado no lugar do texto |
| 3 | **Nenhuma checagem de efeito.** O corretor garante *quem pode agir*, não *que a ação aconteceu* | Média (integridade) | `EGI.log` E3/G | Teste G do plano: ferramenta mentirosa vira FAILED |
| 4 | **`shell=True`** em `voz.py:36` com `self.voz` vindo de variável de ambiente. Quem controla o `.env` já controla a máquina, mas o padrão é frágil | Baixa | `voz.py:36` | Trocar por lista de argumentos e dois processos encadeados; teste com nome de modelo contendo `"; touch x`" |
| 5 | **Coerção silenciosa** de argumentos fora de faixa (`minutos` negativo → 0,1) | Baixa | `EGI.log`, `ferramentas.py:65` | Rejeitar com "Pedido inválido" no esquema da ferramenta |
| 6 | **Imagens `latest` no `docker-compose`** | Baixa | `docker-compose.yml:21,45,71` | Rodar `fixar-versoes.sh` e conferir digests |
| 7 | **`parar.sh` usa `pkill -f` global**: para qualquer `friday/main.py` no mesmo aparelho (inclusive uma segunda instância de teste) | Informativa | `termux/parar.sh` | Documentar; restringir ao PID do supervisor se houver mais de uma instância |
| 8 | **Proteções editáveis pelo próprio código-fonte.** `broker.py`, `protocolos.py`, `termux/` e `servidor/` só pedem confirmação dentro do Claude Code (`.claude/settings.json`). Nenhuma ferramenta do catálogo foi desenhada para reescrever código (`criar_arquivo` escreve só em `FRIDAY_DOCS`, padrão `~/friday-docs`, com nome simples), e `test_nunca_apaga`/`test_sem_botao_de_desligar` varrem o código; mas não há assinatura nem verificação de integridade do próprio código em execução | Informativa | `settings.json`, testes | Verificação de hashes de `broker.py`/`parar.sh` na inicialização, avisando o dono |
| 9 | **Gaps de teste de segurança**: `prefrontal.py` e `maos.py` sem mutação | Baixa | §9.4 | Rodar `mutar` com defesas de mãos/PFC na cópia |

**O que se comportou bem:** nível 4 inexistente, nível 3 só com PIN e bloqueio por tentativas, contaminação por conteúdo externo, quarentena de estudos, 12 vetores SSRF, painel por chave + Host, ausência de rota de parada, recusa de segredos, traversal neutralizado, trilha de auditoria à prova de adulteração silenciosa, EXIF/GPS retirados, pessoas só contadas, câmera que não vira ordem, mãos que enviam só o nome do gesto.

**Sobre a regra "não permitir que o projeto altere suas próprias proteções":** nenhuma ferramenta do catálogo foi desenhada para escrever em `friday/`, e os testes que varrem o código impedem ferramenta de parada ou de apagar. A defesa de `broker.py` continua dependendo de revisão humana (item 8).

---

## 11. Limitações de plataforma

| Plataforma / recurso | Situação | Base |
|---|---|---|
| Linux (x86, contêiner) | **Verificado**: Python 3.11, 3.12 e 3.13 | Suíte completa nas três versões |
| Android + Termux | **Não verificado.** Código e scripts existem; testes usam Termux:API falso | `android.py` 91% com falso; `termux/*` não executado |
| Raspberry Pi / PC com `friday.service` | **Não verificado** | `install.sh` não executado |
| Servidor (docker-compose) | **Não verificado** | Não subiu a stack |
| Windows | **Não verificado**; os documentos não declaram suporte | — |
| Navegador / HUD | **Verificado** no Chromium (desktop 1280 e móvel 390 px) | e2e |
| Câmera e microfone | **Não verificado em hardware**; câmera falsa do Chromium funciona | `e2e/e2e_maos.log` |
| Dependências nativas | Pillow e numpy usados pela suíte e pela visão; `requirements-android.txt` não os lista | §8 item 8 |
| Memória e CPU | Sem medição de consumo de memória; tempo de busca e de contexto medidos (`perf.log`) | §8 item 3 |
| Internet | Sem internet real; pesquisa e leitura funcionam contra internet falsa e têm defesa SSRF testada | `DH_estudo.log`, `EGI.log` |
| Chaves e serviços | Anthropic (opcional), Ollama local, ntfy, Brave (opcionais); nada exigido para subir | `.env.example` |
| SIMD do WebAssembly em celulares antigos | Não verificado | Arquivos locais do MediaPipe |

---

## 12. Recomendações priorizadas

Ordem proposta. Detalhes, dependências, riscos, critérios de aceitação e testes estão em `PLANO_DE_EVOLUCAO.md`.

**P0 — antes de qualquer coisa nova (corrigem falhas e riscos reais, são pequenas)**

1. Colocar o projeto em controle de versão (git) para poder comparar e reverter cada fase.
2. Decidir o destino de `nucleo.py` (remover/arquivar, ou reescrever sem portão). Não ligá-lo.
3. Remover o teto silencioso de busca (índice incremental ou varredura por recência) e cobrir com o teste de 3.200 notas.
4. Fazer a meta "aprender X" reconhecer estudos do mesmo assunto (tema normalizado ou lista de temas relacionados), com teste do caso "criptografia" × "criptografia explicada".
5. Fechar as ressalvas de segurança 1, 2 e 5 (confirmação ambígua, resultado em claro na auditoria, coerção de argumento) com testes que falham antes da correção.
6. Corrigir a documentação: criar `docs/PREFRONTAL.md`, atualizar a ordem de `processar()` em `CLAUDE.md`/`README.md`/`docs/ARQUITETURA.md`, e fazer `test_docs` conferir links e arquivos citados.
7. Acrescentar `pillow` e `numpy` ao ambiente de teste (ou marcar os testes que os exigem).

**P1 — a primeira melhoria estrutural (desbloqueia E, G e H)**

8. **Registro de tarefas com máquina de estados e verificação.** Um modelo de tarefa que **envolve** (não substitui) o corretor, o pré-córtex, a autonomia e a curiosidade: `PENDING → ANALYZING → AWAITING_APPROVAL → RUNNING → VERIFYING → COMPLETED / FAILED / CANCELLED`. A avaliação dos estados está em `PLANO_DE_EVOLUCAO.md` (Fase 3): eles se encaixam no que existe, mas faltam `expira` (a confirmação vence em 45/120 s), `bloqueada até` (o recuo de 30 min do estudo) e `retomada`. Primeiro entregável: a tarefa de uma ferramenta única com verificador, porque é o que faz o Teste G passar e porque toda tarefa maior depende dele.

**P2 — aprendizado e curiosidade de verdade**

9. Registro de experiência (tentativa, esperado × observado, causa suspeita, alternativa, resultado), lido antes da próxima tentativa semelhante. Avaliação objetiva, sem punição artificial: o erro não deve derrubar a serotonina como único efeito; o aprendizado vem da comparação esperado × observado.
10. Lacuna de conhecimento a partir de perguntas sem resposta e de recuperações vazias; comparação de fontes com marca de divergência e confiança.

**P3 — ampliar e validar**

11. Visão e ferramentas novas só depois de G e E passarem, com seus testes de mutação.
12. Teste em aparelho real (Termux, câmera, mãos, voz) e com modelo real, em sessão com o dono, registrando os resultados no mesmo `RESULTADOS_TESTES.json`.

**Sobre o que não fazer:** não criar um segundo cérebro; não ligar `nucleo.py`; não transformar o erro em punição que mexa em estados afetivos para guiar escolha; não afirmar que o sistema "aprende como um cérebro" enquanto o aprendizado for calibração e associação.

---

## 13. Atualização — Fase 1 (24/10/2026, ramo `evolucao-fase1`)

Os 13 achados foram reproduzidos de novo no código atual por `tests/auditoria_achados.py` (saída em `evidencias/logs/fase1/achados_depois_1.json`; a de antes, na mesma pasta de trabalho da sessão). As §1–§12 acima continuam descrevendo o estado auditado.

| # | Achado | Auditoria | Agora | Como foi resolvido / o que falta |
|---|---|---|---|---|
| 1 | Ciclo objetivo→plano→execução→verificação→experiência incompleto | CONFIRMADO | CONFIRMADO | Fases 2–4 |
| 2 | Sem registro de tarefas | CONFIRMADO | CONFIRMADO | Fase 2 |
| 3 | Sem verificação independente do resultado | CONFIRMADO | CONFIRMADO | Fase 2 |
| 4 | Sem registro de experiências | CONFIRMADO | CONFIRMADO | Fase 3 |
| 5 | Sem planejamento multietapas / replanejamento | CONFIRMADO | CONFIRMADO | Fase 4 |
| 6 | Sem retomada de tarefas interrompidas | CONFIRMADO | CONFIRMADO | Fase 6 |
| 7 | Busca limitada a ~3.000 notas | CONFIRMADO | **RESOLVIDO** | `memoria.py`: sem teto por padrão, recência, cache de termos (`e3adcdf`) |
| 8 | Progresso de metas depende de tema idêntico | CONFIRMADO | **RESOLVIDO** | relação explícita (chave normalizada, ligação do dono, id da meta); parecido vira candidato e não conclui (`f56cc32`) |
| 9 | Confirmações ambíguas | CONFIRMADO | **RESOLVIDO** | consentimento explícito preso à ação; id por pendência (`4c063fa`) |
| 10 | Resultado em texto simples na auditoria | CONFIRMADO | **RESOLVIDO** | `privacidade.py`; a trilha guarda fato, não conteúdo (`2932b40`) |
| 11 | Normalização silenciosa de argumentos | CONFIRMADO | **RESOLVIDO** | recusa fora da faixa; ajuste só declarado e avisado (`2932b40`) |
| 12 | Documentos desatualizados | CONFIRMADO | PARCIALMENTE CONFIRMADO | `PREFRONTAL.md`, `NUCLEO.md`, ordem de `processar()` e testes de links (`5e44c5a`); falta só a decisão sobre `nucleo.py` |
| 13 | Conflito `nucleo.py` × `main.py` × `simbiose.py` | PARCIALMENTE CONFIRMADO | PARCIALMENTE CONFIRMADO | `simbiose.py` não é conflito (usado pelo hook); `nucleo.py` segue órfão — Fase 5 |

Resultados dos testes desde a auditoria: unitários 717 → **850** (1 pulado nos dois), Python 3.11/3.12/3.13 OK; roteiros do Chromium 163/163 em ambos; mutação das defesas novas 51/51. Ressalvas novas e riscos: `FASE_1_ENTREGA.md` §6.

## 14. Atualização — Fase 2 (24/10/2026, ramo `evolucao-fase1`)

Os 13 achados foram reproduzidos de novo no código atual por `tests/auditoria_achados.py` (saída em `evidencias/logs/fase2/achados_depois_fase2.json`). Nesta fase as sondas dos achados 1, 2, 3, 5 e 6 foram reescritas para exercitar o comportamento real, em vez de procurar nomes de função. As §1–§12 continuam descrevendo o estado auditado; a §13 descreve o fim da Fase 1.

| # | Achado | Auditoria | Fim da Fase 1 | Agora | Como foi resolvido / o que falta |
|---|---|---|---|---|---|
| 1 | Ciclo objetivo→plano→execução→verificação→experiência incompleto | CONFIRMADO | CONFIRMADO | **PARCIALMENTE CONFIRMADO** | `tarefas.py` + `verificacao.py` fecham objetivo → plano → execução → verificação; falta o elo «experiência» (Fase 3) |
| 2 | Sem registro de tarefas | CONFIRMADO | CONFIRMADO | **RESOLVIDO** | `friday/tarefas.py`: id, objetivo, contexto, plano, estado, evidência, tentativas, dependências, próxima ação, histórico |
| 3 | Sem verificação independente do resultado | CONFIRMADO | CONFIRMADO | **RESOLVIDO** | `friday/verificacao.py` confere o estado real com marca de antes; ferramenta que mente termina `FALHOU` (`refutado`, prova `independente`). O que não dá para conferir fica «executada sem verificação» e só o dono conclui |
| 4 | Sem registro de experiências | CONFIRMADO | CONFIRMADO | CONFIRMADO | Fase 3 (`GANCHOS_FIM` já existe para ligar) |
| 5 | Sem planejamento multietapas / replanejamento | CONFIRMADO | CONFIRMADO | **PARCIALMENTE CONFIRMADO** | planos de vários passos com dependências são executados; quem escreve o plano é o chamador; ninguém gera nem revisa — Fase 4 |
| 6 | Sem retomada de tarefas interrompidas | CONFIRMADO | CONFIRMADO | **PARCIALMENTE CONFIRMADO** | o estado sobrevive ao reinício, o passo é gravado antes de executar e o dono pode «retomar» (reconfere o efeito pela marca antes de repetir); nada retoma sozinho — Fase 6 |
| 7–11 | busca, metas, confirmação, auditoria, argumentos | RESOLVIDO (Fase 1) | | RESOLVIDO | sem regressão (suíte inteira) |
| 12 | Documentos desatualizados | PARCIALMENTE | PARCIALMENTE | PARCIALMENTE | `docs/TAREFAS.md` novo; resta o destino de `nucleo.py` |
| 13 | Conflito `nucleo.py` × `main.py` × `simbiose.py` | PARCIALMENTE | PARCIALMENTE | PARCIALMENTE | Fase 5 |

Resumo: **8 resolvidos, 4 parcialmente confirmados, 1 confirmado** (na auditoria: 12 confirmados e 1 parcial).

Dos dez testes da §9.1, nesta fase: **B** (falso sucesso) e **H** (metas com texto diferente) passam; **F** (confirmação ambígua) e **G** (privacidade da auditoria) continuam passando e agora também com tarefas no meio; **A** passa com conferência do efeito; **D** e **I** passam em parte; **C** e **E** seguem sem cobertura (Fases 3–4). Unitários 717 → 850 → **1017** (1 pulado), Python 3.11/3.12/3.13 OK; roteiros do Chromium 163/163; mutação 25/25 (verificação) e 51/51 (tarefas, corretor, pré-córtex). Ressalvas e riscos: `FASE_2_ENTREGA.md` §6.

## 15. Atualização — Fases 3 a 6 (24/10/2026, ramo `evolucao-fase1`)

Os 13 achados foram reproduzidos de novo no código atual por `tests/auditoria_achados.py` (`evidencias/logs/fase5_6/achados_depois_fase5_6.json`; a foto do fim da Fase 4 está em `evidencias/logs/fase3_4/achados_depois_fase3_4.json`). As §1–§12 continuam descrevendo o estado auditado.

| # | Achado | Auditoria | Fim da Fase 2 | Fim da Fase 4 | Agora (fim da Fase 6) | Como foi resolvido / o que falta |
|---|---|---|---|---|---|---|
| 1 | Ciclo objetivo→plano→execução→verificação→experiência incompleto | CONFIRMADO | PARCIAL | RESOLVIDO | **RESOLVIDO** | `experiencias.py` fecha o elo que faltava; `planejador.py` percorre o ciclo de 11 passos |
| 2 | Sem registro de tarefas | CONFIRMADO | RESOLVIDO | RESOLVIDO | **RESOLVIDO** | Fase 2 |
| 3 | Sem verificação independente do resultado | CONFIRMADO | RESOLVIDO | RESOLVIDO | **RESOLVIDO** | Fase 2 |
| 4 | Sem registro de experiências | CONFIRMADO | CONFIRMADO | RESOLVIDO | **RESOLVIDO** | Fase 3: esperado × observado, causas tipadas com confiança, condições de reutilização; não treina o modelo |
| 5 | Sem planejamento multietapas / replanejamento | CONFIRMADO | PARCIAL | PARCIAL | **PARCIALMENTE CONFIRMADO** | o planejador troca de estratégia dentro de um catálogo em código; falta ligar a fala livre («anota que…») a um objetivo — decisão do dono |
| 6 | Sem retomada de tarefas interrompidas | CONFIRMADO | PARCIAL | PARCIAL | **RESOLVIDO** | Fase 6: `tarefas.recuperar` + `retomada.py`; queda real de processo exercitada; ação não conferível nunca é repetida sozinha |
| 7–11 | busca, metas, confirmação, auditoria, argumentos | RESOLVIDO (Fase 1) | | | RESOLVIDO | sem regressão |
| 12 | Documentos desatualizados | CONFIRMADO | PARCIAL | RESOLVIDO | **RESOLVIDO** | `EXPERIENCIAS.md`, `PLANEJADOR.md`, `COORDENADOR.md`, `RETOMADA.md`, `NUCLEO.md` e testes de links |
| 13 | Conflito `nucleo.py` × `main.py` × `simbiose.py` | PARCIAL | PARCIAL | PARCIAL | **RESOLVIDO** | Fase 5: evidência medida, decisão documentada em `docs/NUCLEO.md` (mantido, desligado, fixado por teste); `simbiose.py` é usado pelo hook |

Resumo: **12 resolvidos, 1 parcialmente confirmado, 0 confirmados** (na auditoria: 12 confirmados e 1 parcial).

Dos dez testes da §9.1, no fim da Fase 6: **A, B, C, D, E, F, G, H, I e J passam**. D foi exercitado com queda simulada e com queda real de processo (`os._exit`); I com threads de verdade disputando o mesmo recurso. Unitários 717 → 850 → 1017 → 1176 → **1278** (1 pulado, o mesmo da linha de base), Python 3.11/3.12/3.13 e ambiente limpo; roteiros do Chromium **163/163** nos cinco scripts; mutação: verificação 25/25, tarefas+corretor+pré-córtex 51/51, experiências+planejador 41/41, objetivos 39/40 (um sobrevivente documentado), coordenador 37/37, retomada 33/33 (+2 camadas redundantes marcadas). Ressalvas e riscos: `FASE_3_4_ENTREGA.md` §6 e `FASE_5_6_ENTREGA.md` §6. **Não verificado aqui:** celular real, reinício e `kill` do Android, Termux:API, microfone, internet ao vivo e a qualidade de qualquer modelo real.
