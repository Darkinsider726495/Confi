# Entrega da Fase 7 — pré-córtex distribuído, neurônios funcionais e demonstração visual

- **Data:** 24/10/2026. **Ramo:** `precortex-fase7` (criado a partir de `evolucao-fase1`, último commit anterior `a52cd71`). **Linha de base da auditoria:** tag `linha-de-base-auditoria` (`6030a56`).
- **Commits:** `7207b41` (núcleo: contrato, transporte, 9 neurônios, hub) · `4342a5b` (API, fachada de voz, tela, demonstração) · `a883386` (integração ao `main.py`, testes do fluxo, 2 defeitos corrigidos) · `0a519ad` (testes dos neurônios, distribuído, painel, pacote, demo) · `45336cb` (e2e da tela, atalho no painel) · `5b93907` (documentação) · o commit que traz este relatório.
- **Documentação:** [`docs/PRE_CORTEX.md`](../docs/PRE_CORTEX.md) (arquitetura, neurônios, diagramas, mensagens, instalação, configuração, iniciar serviços e tela, demonstração, testes, adicionar neurônio, diagnóstico, desligar, local × distribuído, limitações).

## 1. Auditoria antes de mexer

| O que | Resultado |
|---|---|
| Suíte unitária na linha de base | 1278 testes, OK (1 pulado), ~62 s — `reports/evidencias/logs/fase7/baseline_unit_py3.13.log` |
| Cinco roteiros no Chromium | todos com saída 0 — `baseline_e2e_*.log`, `baseline_resumo.txt` |
| O que já existia e foi reaproveitado (não duplicado) | corretor (`broker.py`), tarefas e conferência do efeito (`tarefas.py`, `verificacao.py`), experiências (`experiencias.py`, que ganhou a API de registros cognitivos), catálogo de estratégias do planejador (`planejador.OBJETIVOS`), cofre (`memoria.py`/`estado.py`) |
| `nucleo.py` | **continua desligado.** A missão diz que ele foi desativado «devido a um problema de processamento de sinais»; o registro do projeto ([NUCLEO.md](../docs/NUCLEO.md)) diz outra coisa: ele serializa os impulsos (contra a decisão do dono), descarta sinais por limiar/vagas e não tinha importadores nem testes. Não reproduzi nenhum problema de processamento de sinais e **não o religuei** — o pré-córtex distribuído não depende dele. Registro a discrepância para o dono decidir qual motivo vale. |

## 2. O que foi construído

`friday/pre_cortex/` (26 módulos Python, só biblioteca padrão), `friday/precortex.html` (tela), integração mínima em `friday/main.py` (rotas `/precortex*`, `PC.tratar` em `processar()`, resumo em `/state`, recuperação na partida) e um atalho no painel (`hud.html`, botão «Neurônios em rede»).

- **Nove neurônios** com responsabilidade, interface (`acao_*`), estado (contadores e tempos no trabalhador) e testes próprios: 1 percepção, 2 contexto/memória, 3 hipóteses, 4 planejamento/previsão (plano de 10 campos assinado por hash), 5 crítica/segurança (R1–R14; rejeita ou devolve; nenhuma configuração a desliga), 6 coordenação/execução (registro antes de agir, uma tarefa pelo corretor, reanexar depois de queda), 7 verificação independente (relê o armazenamento real), 8 aprendizagem (previsão × observado, sem punição/recompensa, só `ordem_de_estrategias`, revogável), 9 monitoramento (modos normal/degradado/bloqueado, confiança por módulo).
- **Comunicação real:** envelope JSON `precortex/1` (id único, correlação, plano id+versão, emissor/destino, horários, validade, tentativa, estados, erro, processado_por, tempos, duplicada); entrega «ao menos uma vez» + dedupe no trabalhador + neurônios idempotentes; cancelamento cooperativo; saúde por trabalhador; modo local (threads, passando pelo JSON) e modo distribuído (processos `python -m friday.pre_cortex.worker`, HTTP 127.0.0.1, chave de sessão só por ambiente).
- **Fluxo com dependências explícitas** (grafo no dossiê), paralelismo onde é independente (contexto ‖ conteúdo; crítica ‖ coerência), falha crítica bloqueia, módulo opcional faltando → modo degradado que exige o dono, limites de replanejamento/devoluções/tempo/etapas, detector de laço, fim por «sem alternativas».
- **Raciocínio observável:** as 12 perguntas respondidas só com o dossiê, cada item tipado e com fonte; na tela e por voz.
- **Exploração controlada** (`exploracao.py`) e **registro estruturado de objetivo** (dossiê com id, descrição, origem pedido/sugerido/aceito, resultado esperado, prioridade, restrições, recursos, estado, próxima etapa, dependências, histórico de decisões, critérios de conclusão). A execução usa o MESMO caminho das tarefas e do corretor (não há segundo sistema de execução); os objetivos que ela propõe (`objetivos.py`) continuam como estão — são outra porta de entrada, com a mesma execução por baixo.
- **Tela** `/precortex`: A mapa dos neurônios com estados reais, B objetivo/plano/etapas, C fluxo de eventos, D hipóteses, E planejamento, F aprendizagem, 12 perguntas, G estado operacional, H entrada e controles (iniciar, só planejar, autorizar/negar o plano exato, interromper = cancelar objetivos, limpar = arquivar o cenário sem tocar em experiências e memórias). Consulta periódica ao backend; nada é animado sem dado.
- **Demonstração** `python -m friday.pre_cortex.demo` (padrão: distribuído com 2 processos; `--modo local`; `--ui` para a tela). Sem credenciais, sem internet; backend «deterministico»; modelo de linguagem não incluído (só ponto de extensão).

## 3. Defeitos achados e corrigidos durante a fase

1. O evento `limite_atingido` recebia `tipo=` duas vezes; o tratamento do limite quebrava e o objetivo ficava «em andamento» para sempre. Corrigido (`limite=`) e a linha do objetivo agora nunca termina sem estado final, mesmo se o próprio tratamento falhar (`hub._fim_com_excecao`). Achado pelos testes de limite.
2. O neurônio de hipóteses estava marcado como crítico, mas o fluxo já o substituía em modo degradado: o monitor dizia «bloqueado» enquanto o objetivo seguia. Agora é não crítico, e um teste confere o comportamento degradado.
3. A demonstração não registrava as ferramentas do celular (o SMS ficava sem estratégia); passou a usar `FRIDAY_PLATAFORMA=android` com comandos `termux-*` de mentira que anotam qualquer tentativa.

## 4. Comandos executados e resultados reais

| Comando | Resultado | Evidência |
|---|---|---|
| `python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'` | **1367 testes, OK (1 pulado)**, 82 s (1278 antigos + 89 novos) | `logs/fase7/regressao_final.log` |
| `… -p 'test_pre_cortex_*.py'` | 89 testes, OK, ~20 s (abre processos trabalhadores de verdade) | idem |
| `python3 tests/e2e_hud.py`, `e2e_voz_memoria.py`, `e2e_cerebro.py`, `e2e_maos.py`, `e2e_prefrontal.py` | saída 0 nos cinco | `logs/fase7/final_e2e_*.log` |
| `python3 tests/e2e_precortex.py` (novo) | saída 0; 36 verificações na tela, incluindo «processando» visto enquanto o neurônio trabalhava e nenhum erro de JavaScript | `logs/fase7/final_e2e_precortex.log`, `evidencias/fase7/precortex-*.png` |
| `python3 -m friday.pre_cortex.demo` | saída 0; **12/12**; trabalhadores em processos separados (pids diferentes do hub) | `logs/fase7/demo_distribuido.log`, `.json` |
| `python3 -m friday.pre_cortex.demo --modo local` | saída 0; **10/10** | `logs/fase7/demo_local.log`, `.json` |
| Mutação das defesas novas (7: hash na crítica, reconferência antes de executar, hash na autorização, dedupe, detector de laço, pedido de autorização, verificador) | **as 7 quebras derrubaram testes** | `logs/fase7/mutacoes.log` |
| `coverage` do pacote (sem `demo.py` e `worker.py`, que rodam em subprocesso e não são medidos) | **89%** das linhas | `logs/fase7/cobertura_pre_cortex.txt` |

Cobertura das 18 áreas de teste pedidas: todas têm teste executado (mapa no topo de cada `tests/test_pre_cortex_*.py`). Áreas 10 (falha parcial) e partes da 13 (queda no meio) usam **injeção de falha**, porque neste ambiente não acontece falha parcial natural; a queda é simulada encerrando o hub no meio da fase (não é um reinício real do Android).

## 5. Limitações e o que não foi verificado

- **Limite do corretor que o pré-córtex não lê:** o corretor recusa texto acima de 1000 caracteres em ferramentas sem `maxLength` (`anotar`, `criar_arquivo` — que aceitaria 100 KB —, `guardar_memoria` — 2000). Só «anotar_em_partes» guarda o plano inteiro. É isso que faz a 1ª estratégia da demonstração falhar **de verdade**. Corrigir de vez exige declarar limites em `catalogo.py` (mexe no catálogo do corretor; fica para o dono).
- Correção de uma crença anterior: «anotar corta calado» estava errado — o corretor recusa e nada é gravado.
- Mesma máquina ≠ várias máquinas: provado entre processos no mesmo computador; rede entre máquinas não testada e o HTTP não é cifrado.
- Confianças são contagens pequenas, não calibradas; as confianças-base do monitor são suposições de projeto.
- Currículo interno, não conferido com fonte externa; interpretação por regras (sem modelo de linguagem).
- «Processando» só aparece em trabalho lento (cada neurônio responde em milissegundos); a demonstração usa `ritmo_demo_s` (pausa entre fases, registrada como evento) para dar tempo de ver.
- Não verificado aqui: celular e Termux:API reais, reinício real do Android, desempenho em aparelho fraco, uso prolongado.

## 6. Pacote

`/home/claude/friday-pi.zip` montado a partir de uma cópia limpa (sem `.env`, `auditoria.jsonl`, `Privado/`, caches, bancos e ambientes virtuais), extraído em pasta nova e validado lá (`unzip -t`, suíte unitária, varredura de segredos) — resultados no fim da mensagem de entrega.
