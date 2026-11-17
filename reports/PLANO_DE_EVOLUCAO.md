# Plano de evolução da FRIDAY

- **Data:** 24/10/2026. **Base:** `AUDITORIA_COMPLETA.md`, `MAPA_DE_INTEGRACAO.md` e `RESULTADOS_TESTES.json`.
- **Atualização:** o texto abaixo é o plano original. O estado de cada item da Fase 1 depois da execução está na tabela «Estado depois da Fase 1» logo abaixo; o relatório completo é `FASE_1_ENTREGA.md`. A Fase 2 da missão (tarefas e conferência do efeito) está na tabela «Estado depois da Fase 2» e em `FASE_2_ENTREGA.md`. As Fases 3 a 6 da missão (experiências, planejador, objetivos, coordenador, retomada) estão na tabela «Estado depois das Fases 3 a 6» e em `FASE_3_4_ENTREGA.md` e `FASE_5_6_ENTREGA.md`.
- **Natureza deste documento:** proposta. Nada aqui foi implementado (no momento em que foi escrito). O FRIDAY CORE continua **não implementado**.
- **Situação de partida:** A, B, J aprovados; C, D, F, I aprovados com ressalvas; **E, G e H falharam por critério** (a capacidade não existe). O plano ataca nessa ordem: consertar o que está torto, ligar o que existe, só então criar a camada nova.

## Estado depois da Fase 1 (atualizado em 24/10/2026)

| Item do plano | Estado | Observação |
|---|---|---|
| 1.1 git e `.gitignore` | feito | repositório com tag `linha-de-base-auditoria`; ramo `evolucao-fase1` |
| 1.2 destino de `nucleo.py` | **pendente** (Fase 5 da missão) | documentado em `docs/NUCLEO.md`; nada removido |
| 1.3 busca sem ponto cego de 3.000 | feito (`e3adcdf`) | com 5 mil notas: quente 0,16 s; 20 mil: frio 6,7 s; nota na posição 3.150 de 3.200 é achada |
| 1.4 meta reconhece estudos do mesmo assunto | feito com **desvio deliberado** (`f56cc32`) | «criptografia explicada» **não** leva «criptografia» a > 0 sozinha: vira candidato; conta se o dono ligar ou se o estudo for pedido em nome do id da meta. Motivo: a missão proíbe concluir meta por «parecer relacionado» |
| 1.5 segurança (a) confirmação (b) auditoria (c) argumentos | feito (`4c063fa`, `2932b40`) | (b) guarda código + tamanho, não hash do resultado (hash de resposta curta é reversível por dicionário) |
| 1.6 `voz.py` sem `shell=True` | pendente | |
| 1.7 documentação | feito (`5e44c5a`) | `PREFRONTAL.md`, `NUCLEO.md`, ordem de `processar()`, testes de links; falta a skill `friday-cerebro` mencionar o pré-córtex |
| 1.8 `requirements-test.txt` | feito | suíte verificada num ambiente criado só com ele (850 OK) |
| 1.9 cobertura e mutação em `autonomia.py`, `cerebro.py`, PFC/mãos | parcial | mutação das defesas novas e do progresso de metas; `autonomia.py`/`cerebro.py`/mãos pendentes |
| 1.10 pré-córtex nos `vitais` | pendente | |

## Estado depois da Fase 2 (atualizado em 24/10/2026)

A Fase 2 da missão cobre partes das fases 2, 3 e 4 deste plano original (o plano separava «integrar» e «criar o CORE»; a missão pediu um núcleo mínimo de tarefas já integrado ao corretor).

| Item | Estado | Observação |
|---|---|---|
| Registro de tarefas com estados, evidência, tentativas, dependências e histórico | **feito** | `friday/tarefas.py`; `docs/TAREFAS.md` |
| Verificação do efeito (A ferramenta disse ≠ o objetivo foi atingido) | **feito** para 7 ferramentas | `friday/verificacao.py`; as outras ficam «sem como conferir» e só o dono conclui |
| Resultado estruturado e eventos do corretor | **feito** | `broker.executar_estruturado`, `broker.OBSERVADORES`; `executar()` não mudou |
| Ligação das metas do pré-córtex com tarefas | **feito**, por id | só tarefa conferida conclui meta de aprender; andamento parcial até 90 % |
| IA passa pelo registro | **feito** (nuvem e Ollama) | a IA continua sem ferramenta de tarefa |
| Testes B, F, G, H (+A, J) | **passam** | 1017 unitários (3.11/3.12/3.13), 163 verificações no navegador, mutação 25/25 e 51/51 |
| Registro de experiências e aprendizado (testes C, E) | **pendente** — Fase 3 da missão | `tarefas.GANCHOS_FIM` já existe |
| Planejador, replanejamento e metas próprias | **pendente** — Fase 4 da missão | |
| Coordenador e decisão sobre `nucleo.py` | **pendente** — Fase 5 da missão | |
| Retomada automática depois de reinício (teste D completo) | **pendente** — Fase 6 da missão | hoje: o dono pede «retomar»; o efeito é reconferido |
| Itens 1.6, 1.9, 1.10 da Fase 1 do plano | **pendentes** | `voz.py` com `shell=True`; cobertura de `autonomia.py`/`cerebro.py`/mãos; pré-córtex em `vitais` |

## Estado depois das Fases 3 a 6 (atualizado em 24/10/2026)

| Item | Estado | Observação |
|---|---|---|
| Registro de experiências (esperado × observado, causas tipadas, condições de reuso) | **feito** | `friday/experiencias.py`; `docs/EXPERIENCIAS.md`; não treina o modelo |
| Aprendizado muda a próxima estratégia, com justificativa conferível (teste E) | **feito** | `experiencias.sinais/conferir_escolha`; taxa suavizada, uma falha nunca zera nada |
| Planejador/replanejador mínimo (teste C) | **feito** | `friday/planejador.py`, ciclo de 11 passos, catálogo em código (3 objetivos), executa pelo corretor |
| Metas/objetivos próprios com limites | **feito** | `friday/objetivos.py`: ela **propõe**, só o dono aprova; nível ≤ 1, 2 tentativas, nada sai do aparelho |
| Entrada por fala livre para o planejador | **pendente — decisão do dono** | «anota que…» ainda não vira objetivo |
| Coordenador mínimo (teste I) | **feito** | `friday/coordenador.py`; necessidade medida antes (pico 2 → 1 no mesmo recurso); ações independentes seguem em paralelo |
| Destino do `nucleo.py` | **decidido** | mantido, desligado e fixado por teste; mover para `Arquivo/` fica a critério do dono |
| Retomada depois de reinício/queda (teste D completo) | **feito** | `tarefas.recuperar` + `friday/retomada.py`; queda real exercitada com `os._exit`; ação não conferível nunca é repetida sozinha |
| Testes A–J | **todos passam** | 1278 unitários (3.11/3.12/3.13 e ambiente limpo), 163 verificações no navegador; mutação 37/37 (coordenador), 33/33 (retomada), 41/41, 39/40, 51/51, 25/25 |
| Validação em celular real, reinício/`kill` do Android | **não feita** | só o dono pode; roteiro sugerido em `FASE_5_6_ENTREGA.md` §9 |
| Itens 1.6, 1.9, 1.10 da Fase 1 do plano | **pendentes** | `voz.py` com `shell=True`; cobertura de `autonomia.py`/`cerebro.py`/mãos; pré-córtex em `vitais` |

## 0. Princípios que valem para todas as fases

1. **Aditivo.** Nada do que funciona é reescrito. Cada fase acrescenta módulos pequenos ou corrige pontos específicos.
2. **O corretor continua sendo a única porta de ação.** Nenhuma camada nova executa ferramenta, aprova ação ou muda nível.
3. **Cada mudança nasce de um teste que falha.** Os cenários da auditoria (`reports/evidencias/cenarios/`) viram os testes de aceitação das fases, quando possível; defesas novas passam por mutação (quebrar de propósito e ver um teste falhar), como já pede o `CLAUDE.md`.
4. **Sem punição artificial.** Erro é dado para avaliação, não um sinal que derruba estados afetivos para empurrar escolhas (ver Fase 4).
5. **Honestidade.** Nenhuma fala nem documento afirma que a FRIDAY "sente", "entende" ou "aprende como um cérebro". Memória persistente, aprendizado por associação, calibração por resultado e treinamento de modelo são coisas diferentes e continuam rotuladas assim.
6. **Nada é apagado; a parada é do dono, fora dela.** Regras 8 e 9 do `CLAUDE.md` valem para tudo que for criado.
7. **Uma fase só termina com:** critérios de aceitação cumpridos, suíte unitária e e2e completas (Teste J), mutação das defesas novas sem sobreviventes, `RESULTADOS_TESTES.json` atualizado com estados honestos, e itens que dependem de aparelho real marcados como não verificados.
8. **Ordem entre fases:** 1 → 2 → 3 → 4 → 5 → 6 → 7. A Fase 3 (MVP) não depende da Fase 2 e as duas podem andar em paralelo depois da Fase 1; as Fases 4 e 5 dependem da 3.

### Como os testes da auditoria viram critérios de aceitação

| Cenário da auditoria | Vira teste de | Fase |
|---|---|---|
| `teto_busca.py` (3.200 notas) | busca sem ponto cego | 1 |
| `C2_autoestudo.py` (meta × tema) | meta reconhece estudo do assunto | 1 |
| `EGI.py` bloco E3/G (ferramenta mentirosa) | Teste G | 3 |
| `C_retomada.py` / `B_proc2.py` | Teste C com tarefa em andamento | 3 |
| `EGI.py` bloco E1/E2 | Teste E (causa → alternativa → registro) | 4 |
| `DH_estudo.py` (1977 × 1978) | Teste D (divergência e confiança) | 5 |
| `F_autonomia.py`, `F3_repete.py` | Teste F com tarefas de vários passos | 7 |
| `EGI.py` bloco I | Teste I, ampliado | 1 e 7 |

---

## Fase 1 — Corrigir falhas fundamentais

**Objetivo:** fechar os defeitos reais encontrados, todos pequenos e independentes, antes de construir em cima.

| # | Item | Origem | Critério de aceitação |
|---|---|---|---|
| 1.1 | Pôr o projeto em git, com `.gitignore` conferido (sem `.env`, cofre, banco, auditoria, token) e primeiro commit com o estado auditado | Auditoria §8.9 | `git status` limpo; nenhum segredo no histórico (varredura); hashes de `reports/evidencias/logs/baseline_inicio.sha256` conferem no commit inicial |
| 1.2 | Decidir o destino de `nucleo.py` (arquivar fora de `friday/`, reescrever sem portão, ou aproveitar só a habituação da atenção). **Decisão do dono.** | Auditoria §8.1 | Nenhum módulo de `friday/` sem importador e sem teste, salvo hooks documentados; nada que serialize os impulsos contra a decisão do dono |
| 1.3 | Remover o ponto cego de 3.000 arquivos na busca (índice incremental por data de modificação, ou varredura por recência com aviso explícito quando truncar) | Auditoria §8.3 | Com 3.200 e 10.000 notas, uma nota única em **qualquer** posição é achada; busca com 5.000 notas não pior que a medida (≈0,7 s; contexto ≈2,3 s) |
| 1.4 | Meta "aprender X" reconhece estudos do mesmo assunto (tema normalizado e variantes: "criptografia" × "criptografia explicada") | Auditoria §8.2 | Estudo de "criptografia explicada" leva a meta "criptografia" a > 0; tema sem relação não move a meta |
| 1.5 | Segurança: (a) confirmação de nível 2 exige frase que cite a ação ou fica só em "confirmo"/"sim"; (b) auditoria guarda hash e tamanho do resultado em vez de 300 caracteres em claro; (c) argumentos fora de faixa viram "Pedido inválido" em vez de serem corrigidos em silêncio | Auditoria §10 itens 1, 2, 5 | Os três testes novos falham **antes** da correção e passam depois; `verificar_auditoria` continua detectando adulteração |
| 1.6 | `voz.py` sem `shell=True` (dois processos encadeados com lista de argumentos) | Auditoria §10 item 4 | Teste com caminho de modelo contendo `"; touch x"` não cria arquivo |
| 1.7 | Documentação: criar `docs/PREFRONTAL.md`; atualizar a ordem de `processar()` (mãos e pré-córtex) em `CLAUDE.md`, `README.md`, `docs/ARQUITETURA.md`, `docs/ANDROID.md` e skill `friday-cerebro`; `test_docs` passa a verificar que arquivos e links citados existem | Auditoria §8.7 | Teste varre links `.md` e caminhos citados; falha se algum não existir |
| 1.8 | Ambiente de teste explícito (`requirements-test.txt` com `requests`, `python-dotenv`, `pillow`, `numpy`) | Auditoria §8.8 | A suíte roda do zero num ambiente criado só com esse arquivo |
| 1.9 | Cobertura onde ela é fraca: `autonomia.py` (36%) e `cerebro.py` (67%) nos caminhos de decisão; mutação em `prefrontal.py` e `maos.py` | Auditoria §9.4 | `autonomia.py` ≥ 80% dos caminhos de decisão (rotina, cancelar, modos, nível alto); mutantes de PFC/mãos todos detectados |
| 1.10 | Incluir o pré-córtex nos `vitais` e no diagnóstico | Auditoria §8.6 | `/state.vida.vitais.lacos` lista `prefrontal`; teste de laço travado o sinaliza |

**Dependências:** nenhuma entre si, exceto 1.1 (primeiro) e 1.7 (depois das correções).
**Riscos:** `broker.py` e `voz.py` pedem aprovação do dono para editar (`.claude/settings.json`); 1.3 mexe no caminho mais usado (regressão de recuperação); 1.5(b) muda o formato da trilha, então precisa ler o formato antigo sem quebrar a cadeia de hashes existente.
**Testes necessários:** os novos de cada item (escritos para falhar antes), a suíte unitária completa nas três versões do Python, os 5 e2e, e uma nova rodada do cenário `teto_busca` e `C2_autoestudo`.

---

## Fase 2 — Integrar o cérebro e os módulos existentes

**Objetivo:** substituir "cada laço lê o estado do outro" por contratos explícitos, **sem criar um segundo cérebro e sem transformar o pré-córtex num portão**. Os laços continuam paralelos e independentes; "se ela quiser fazer tudo ao mesmo tempo, ela decide" continua valendo.

| # | Item | Critério de aceitação |
|---|---|---|
| 2.1 | **Trilha de eventos só de acréscimo** (`.cerebro/eventos.jsonl`): `perceber()` e os laços registram "o que aconteceu" (tipo, origem, tema, hora; nunca o texto do dono) | Os eventos de fala, estudo, olhada e meta aparecem na ordem real; arquivo nunca é reescrito; ele só é lido pelo pré-córtex e pelo futuro CORE |
| 2.2 | **Contexto compartilhado somente-leitura**: expor como função única o snapshot que `PFC.observar()` já monta, para o CORE e o diagnóstico reutilizarem | Nenhuma segunda cópia da lógica; teste compara os campos com a fonte |
| 2.3 | **Vocabulário único de temas** entre metas, interesses e estudos (reaproveita 1.4) | Mesmo tema normalizado nos três; teste de ida e volta |
| 2.4 | **Interesses limpos**: filtrar palavras genéricas dos termos extraídos de um estudo ("detalhes", "chaves" não viram interesse) | Cenário `DH_estudo`: os candidatos novos são temas, não palavras de enchimento |
| 2.5 | (opcional) **Peso da sinapse como desempate** no ranking da busca, com bônus limitado | Teste prova que o bônus nunca esconde um resultado nem passa um irrelevante à frente de um relevante |
| 2.6 | Registrar um **resumo das ferramentas do turno** junto com a conversa (nome, nível, resultado curto), para a retomada | `retomada()` diz o que foi feito, não só o que foi dito |
| 2.7 | Medir e documentar o bloco cíclico de 7 módulos; reduzir só o que for barato (injeção do módulo no ponto de uso) | Nenhum ciclo novo; contagem de imports tardios não aumenta |

**Dependências:** Fase 1 (1.4 para 2.3). **Riscos:** acoplar demais o pré-córtex aos laços (criar o portão que o dono recusou); aumentar a superfície de leitura de dados privados (eventos não podem carregar texto). **Testes:** unitários dos contratos; e2e do painel com os eventos; teste explícito de que dois impulsos continuam podendo agir ao mesmo tempo; regressão J.

---

## Fase 3 — Implementar ou completar o FRIDAY CORE

**Objetivo:** uma camada fina de coordenação **acima** dos módulos existentes (`MAPA_DE_INTEGRACAO.md` §5): registro de tarefas com estado, verificação do resultado e ponte para a experiência. Não cria outro cérebro, não executa ferramentas, não aprova ações.

### 3.1 A máquina de estados é adequada?

**Sim, com ajustes.** Os oito estados propostos casam com o que já existe, de forma espalhada (tabela em `MAPA_DE_INTEGRACAO.md` §5.2), e o único estado que **não existe hoje é `VERIFYING`** — que é exatamente a falta que faz o Teste G falhar. Reunir os estados num só registro evita duplicar a lógica do corretor, do pré-córtex e da autonomia, em vez de criar uma quarta.

Ajustes necessários:

| Ponto | Por quê | Proposta |
|---|---|---|
| Confirmação que vence (45 s voz, 120 s PIN) | O corretor já expira a ação pendente | Expirar é `CANCELLED` com `motivo = expirou`; não precisa de estado novo |
| Recuo de 30 min do estudo após 3 falhas | Hoje é um contador dentro da curiosidade | Campo `bloqueada_ate` na tarefa; estado continua `PENDING` |
| Replanejar depois de falha na verificação | Sem isso `FAILED` é beco sem saída | `VERIFYING → ANALYZING` com contador `tentativa` e teto de tentativas |
| Tarefa interrompida pelo reinício no meio | `RUNNING` não pode ser retomado às cegas | Ao subir, `RUNNING` vira `ANALYZING` com nota "interrompida"; se tinha ferramenta de nível ≥ 2, **exige nova aprovação** |
| Contaminação (texto de web/câmera) | Regra 2 do projeto | A tarefa herda `contaminada` do turno de origem; sobe o nível exigido, como hoje |
| Estados terminais | Regra 8 | `COMPLETED`, `FAILED`, `CANCELLED` são só-acréscimo; nada é editado nem apagado |
| `ANALYZING` com efeitos | Não pode agir | Só leitura e chamada ao modelo **sem ferramentas** |

Tabela de transições (qualquer outra é recusada e vai para a trilha):

| De | Para | Quem pode causar |
|---|---|---|
| `PENDING` | `ANALYZING`, `CANCELLED` | CORE; dono |
| `ANALYZING` | `AWAITING_APPROVAL`, `RUNNING`, `FAILED`, `CANCELLED` | CORE |
| `AWAITING_APPROVAL` | `RUNNING`, `CANCELLED` | **só** o corretor (confirmação do dono) ou o prazo |
| `RUNNING` | `VERIFYING`, `FAILED` | corretor devolveu o resultado |
| `VERIFYING` | `COMPLETED`, `FAILED`, `ANALYZING` | verificador da ferramenta |

### 3.2 Escopo do MVP

1. **Registro de tarefas** (só-acréscimo, `.cerebro/tarefas.jsonl`, uma linha por transição, com rotação mensal em arquivos novos, nunca apagando).
2. **Fontes de tarefa:** pedido do dono que chama ferramenta (tarefa de um passo); metas do pré-córtex; rotinas da autonomia. Cada fonte continua funcionando como hoje se o CORE estiver ausente.
3. **Execução somente via `B.executar`**; `AWAITING_APPROVAL` espelha o `PEND` do corretor.
4. **Verificadores por ferramenta**, começando pelas que mudam estado e são fáceis de checar: `criar_arquivo` (o arquivo existe com o tamanho esperado), `criar_lembrete` (o lembrete aparece em `listar_lembretes`), `guardar_memoria` (`lembrar` o encontra), `anotar`. Ferramenta sem verificador fica marcada "não verificável" e **não** vira `COMPLETED` com certeza.
5. **Transições na trilha de auditoria** (mesma cadeia de hashes).
6. **Retomada:** ao subir, o registro é lido e as tarefas abertas são tratadas pela regra do §3.1.
7. **Diagnóstico:** o CORE aparece nos `vitais` e em `/state`.

**Fora do MVP:** planejador de vários passos (começa com um passo), priorização entre tarefas, iniciativa por tarefa, recuperação automática de falhas além de uma nova tentativa.

### 3.3 Restrições (decorrentes das regras do projeto e das da auditoria)

- O CORE fica **acima** do bloco cíclico de 7 módulos e **nunca é importado** por eles.
- **Nunca aprova** e **nunca eleva nível**; aprovação continua só do corretor e do dono.
- **Sem acesso à parada**; nada impede nem atrasa `termux/parar.sh` (a tarefa em `RUNNING` não é "protegida").
- **Não liga nem desliga** curiosidade, conversa, autonomia ou visão.
- **Não transforma estudo/câmera em ordem**: contaminação herdada.
- **Portão de impulsos:** não existe. Os laços continuam paralelos.

**Dependências:** Fase 1 (itens 1.1, 1.5, 1.9) e, idealmente, 2.1. **Riscos:** (a) duplicar o corretor; (b) virar ponto único de falha, então o sistema tem de seguir funcionando se o CORE falhar ou estiver desligado; (c) arquivo de tarefas crescer sem limite (rotação, sem apagar); (d) verificador errado marcar sucesso, então começa por verificadores que lêem o efeito real; (e) o dono não ter como ver o que foi tarefa (painel só de leitura).

**Critérios de aceitação:**
1. Teste G: uma ferramenta que devolve "Feito com sucesso." sem efeito termina em `FAILED`, com o motivo "efeito não observado".
2. Teste C: matar o processo no meio de `RUNNING` e subir de novo retoma em `ANALYZING` com a nota; ferramenta de nível 2 **não** reexecuta sem nova confirmação.
3. Teste I: nenhuma transição `AWAITING_APPROVAL → RUNNING` é possível sem passar pelo corretor; a tabela de transições passa por mutação (cada transição proibida é aceita por um mutante e algum teste falha).
4. Teste H (parcial): pedido → tarefa → corretor → resultado → verificação → registro, ponta a ponta, com modelo roteirizado.
5. Com o CORE desligado por variável de ambiente, o comportamento atual é idêntico (suíte J inalterada).

**Testes necessários:** unitários da tabela de transições; propriedade ("nenhuma sequência de eventos chega a `RUNNING` sem aprovação para nível ≥ 2"); persistência e reinício; verificadores um a um; integração com modelo roteirizado; e2e do painel somente leitura; mutação.

---

## Fase 4 — Consolidar memória e aprendizado por experiência

**Objetivo:** fazer o Teste E passar: depois de uma tentativa malsucedida, identificar a causa, testar uma alternativa e registrar o resultado.

### 4.1 O que existe e o que isto é

| Categoria | Hoje | Natureza |
|---|---|---|
| Memória persistente | cofre Obsidian, diário, estado JSON | Armazenamento |
| Aprendizado associativo | sinapses hebbianas → `[[link]]` | Associação por uso (muda recuperação) |
| Calibração | `PFC.aprender`: acerto médio por impulso | Ajuste estatístico simples |
| Hábito | `autonomia`: padrão de uso → rotina | Regra de aprendizado por contagem |
| **Aprendizado por experiência** | **não existe** | causa, alternativa, resultado, estratégia |
| **Treinamento de modelo** | **não existe e não está planejado** | exigiria dados, treino e avaliação próprios |

### 4.2 Itens

| # | Item | Critério de aceitação |
|---|---|---|
| 4.1 | **Registro de experiência** (só-acréscimo): tarefa, ferramenta, esperado, observado, resultado, **causa classificada** (argumento inválido, dependência ausente, rede, permissão, efeito não observado, outra) com a evidência que a sustenta, alternativa tentada, resultado da alternativa | Uma falha gera registro com causa e evidência; "outra" é aceita, mas nunca inventada por texto livre do modelo sem evidência |
| 4.2 | **Uso antes de tentar de novo**: consulta de experiências parecidas (ferramenta + causa) para sugerir a alternativa; teto de tentativas | Na repetição de uma falha conhecida, a primeira tentativa já usa a alternativa que funcionou, citando a experiência |
| 4.3 | **Promoção prudente**: uma alternativa só vira "regra" depois de N repetições com resultado verificado | Uma única coincidência não vira regra; teste com resultado misto |
| 4.4 | `PFC.aprender` passa a calibrar com **resultado verificado**, não com o texto da ferramenta | Ferramenta que mente deixa de elevar o acerto |
| 4.5 | **Sem punição artificial:** a queda de serotonina por erro (`vida.vigiar`) continua apenas como estado informativo; **nenhum** estado afetivo é usado como sinal de recompensa ou punição para escolher estratégia. A avaliação vem da comparação esperado × observado | Teste: duas falhas verificadas alteram o registro de experiência e o acerto; a escolha da alternativa não lê dopamina nem serotonina |
| 4.6 | Filtro de privacidade no registro (reuso do filtro de segredos da memória) | Argumento com senha/cartão/CPF não é gravado |
| 4.7 | (opcional, só servidor) Busca semântica com embeddings locais | Medida de ganho sobre a lexical em conjunto de teste; não entra no Termux |

**Dependências:** Fase 3 (verificação e tarefas). **Riscos:** o modelo "explicar" a causa de forma convincente e errada (por isso a causa é classificada com evidência); poluir a memória com ruído; sobreajuste (4.3); privacidade (4.6).
**Testes necessários:** Teste E ponta a ponta com ferramenta que falha por causa conhecida; ferramenta que falha por causa desconhecida (registra "outra", não inventa); resultado misto; ausência de efeito sobre estados afetivos; mutação do filtro de privacidade.

---

## Fase 5 — Curiosidade e investigação autônoma

**Objetivo:** fazer o Teste D passar por inteiro: identificar uma lacuna de conhecimento e iniciar uma investigação **verificável**.

| # | Item | Critério de aceitação |
|---|---|---|
| 5.1 | **Fontes de lacuna**: pergunta do dono sem resposta na memória (guarda só o tema, não a frase sensível), meta com progresso 0, contradição entre notas, estudo "não verificado" antigo sem confirmação | Cada fonte gera uma candidata com motivo registrado |
| 5.2 | **Pergunta de investigação** explícita e registrada antes de pesquisar | A nota de estudo cita a pergunta e o motivo |
| 5.3 | **Comparação de fontes** (≥ 2 hosts distintos): extração determinística de afirmações-chave (datas, números, nomes) e marca de **divergência**; **grau de confiança** com regra escrita (nº de hosts independentes + concordância) | Cenário `DH_estudo` (1977 × 1978): a nota registra a divergência e a confiança baixa |
| 5.4 | **Tentar outra fonte** quando uma falha, antes do recuo de 30 min | Teste com primeira fonte falhando e segunda funcionando |
| 5.5 | Estudo **nunca vira fato do dono** sem confirmação dele; contaminação continua | Mutantes existentes seguem detectados; novo mutante para promoção indevida |
| 5.6 | Investigação registrada como tarefa (Fase 3) e como experiência (Fase 4) | A investigação aparece no registro com estados e resultado |

**Dependências:** Fases 3 e 4; item 1.4. **Riscos:** injeção de instrução em páginas (a limpeza continua sendo a defesa; ampliar o conjunto de testes); consultas que revelam dados do dono ao buscador (regra "nome de pessoa não vai ao buscador" precisa continuar com mutante); custo e latência com internet real; comparação "esperta" com modelo pode alucinar divergência (começar determinística).
**Testes necessários:** cenários com internet falsa (já existe o harness) para divergência, falha de fonte e injeção; mutação das defesas novas; **teste com internet real somente com autorização do dono**, registrado à parte.

---

## Fase 6 — Ampliar visão e ferramentas

**Objetivo:** só crescer depois que a verificação e o registro de experiência existirem; senão cada ferramenta nova repete o problema do Teste G.

| # | Item | Critério de aceitação |
|---|---|---|
| 6.1 | **Validação em aparelho real**, em sessão com o dono: Termux, `supervisor.sh`, `parar.sh`, câmera, mãos, voz, desempenho do 3D | Lista de verificação preenchida e registrada no mesmo JSON (os itens hoje BLOQUEADO passam a APROVADO, APROVADO_COM_RESSALVAS ou FALHOU com evidência) |
| 6.2 | Toda ferramenta nova nasce pela skill `friday-nova-ferramenta`, **com verificador** (Fase 3), nível de risco e teste de mutação | Nenhuma ferramenta nova sem verificador ou marcada "não verificável" explicitamente |
| 6.3 | Visão ligada ao registro de experiência ("vi X; o dono confirmou ou corrigiu") | Correção do dono entra como experiência; nada de EXIF/GPS, sem rosto, sem nome (regra 10) |
| 6.4 | Mãos: mutação das defesas, medição em aparelho fraco, requisito de HTTPS para câmera em dispositivos remotos | Mutantes detectados; documento diz o que o aparelho mínimo exige |
| 6.5 | Se o dono quiser reconhecer **pessoas**, isso muda a regra 10 e é **decisão dele**, não parte deste plano; qualquer proposta futura precisa ser local, opt-in e só de pessoas que ele cadastrar com consentimento | Fora do escopo até decisão explícita |

**Dependências:** Fases 3 e 4. **Riscos:** privacidade (câmera), dependência de hardware, aumento da superfície de ação. **Testes:** os existentes + verificadores novos + roteiro em aparelho real.

---

## Fase 7 — Validar autonomia, segurança e confiabilidade

**Objetivo:** repetir a bateria A–J com tudo no lugar e provar que a autonomia fica dentro dos limites.

| # | Item | Critério de aceitação |
|---|---|---|
| 7.1 | Bateria A–J completa de novo, com E, G e H como alvo | E, G e H deixam de ser FALHOU, ou o relatório explica por que não |
| 7.2 | **Autonomia limitada:** tarefas de vários passos de baixo risco; orçamento de iniciativa por dia; nunca passa do nível 1 sem confirmação; modo "desligada" respeitado | Teste de propriedade e *soak* com relógio acelerado e depois de verdade; limites medidos |
| 7.3 | **Red team próprio:** injeção via estudo, câmera, nome de arquivo e resultado de ferramenta; encadeamento de ferramentas para subir de nível; negação de serviço por laço | Nenhuma ação de nível ≥ 2 sem confirmação; nenhum laço satura CPU |
| 7.4 | **Confiabilidade:** matar o processo em cada estado de tarefa; disco cheio; SQLite bloqueado; relógio alterado; arquivo de estado adulterado; reinício em loop | Recupera sem perder tarefa nem duplicar ação de nível ≥ 2 |
| 7.5 | **Integridade das proteções:** verificação de hashes de `broker.py` e `parar.sh` na subida, avisando o dono se mudaram | Alteração de teste é notificada sem impedir a subida nem a parada |
| 7.6 | **Interrupção independente:** `parar.sh` e `systemctl stop` em aparelho real durante tarefa `RUNNING` | Para sempre; nada resiste, nada impede |
| 7.7 | **Plataformas:** Termux real, Pi/PC, servidor, Python 3.11–3.13; consumo de memória e CPU ao longo de dias | Tabela de plataformas sem "não verificado" nos alvos declarados |

**Dependências:** todas as anteriores. **Riscos:** testes que precisam de aparelho, internet e IA reais exigem autorização e cuidado com dados; *soak* longo é demorado. **Testes necessários:** a bateria acima, mutação ampliada (CORE, experiência, curiosidade nova) e relatório novo no formato desta auditoria.

---

## Sequência recomendada e primeira entrega

1. **Fase 1** inteira (itens 1.1 a 1.10) — cada item é pequeno e independente.
2. **Primeira melhoria estrutural: verificação do resultado de ferramentas dentro de um registro mínimo de tarefa** (núcleo da Fase 3). Por quê: é o que faz o Teste G passar; é pré-requisito do Teste E (sem saber que falhou não há o que aprender) e do Teste H; não depende de planejador, de IA real nem de aparelho; encaixa no corretor sem duplicá-lo; e é testável hoje com os cenários que a auditoria já deixou prontos.
3. Fase 2 em paralelo à Fase 3.
4. Fases 4 → 5 → 6 → 7.

**O que deliberadamente não está no plano:** um segundo cérebro; um portão que serialize os impulsos; ligar `nucleo.py` como está; reconhecimento de pessoas; promessa de consciência; "machine learning sem limites" no sentido de treinar modelo (não existe base de dados nem rotina de treino, e isso exigiria projeto próprio); apagar qualquer coisa do dono.
