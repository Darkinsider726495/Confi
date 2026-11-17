# Entrega das Fases 3 e 4 — experiências, planejador e objetivos que ela propõe

- **Data:** 24/10/2026. **Ramo:** `evolucao-fase1` (as fases seguem empilhadas no mesmo ramo, em commits próprios, porque cada uma depende da anterior). **Linha de base:** tag `linha-de-base-auditoria` (`6030a56`). **Fim da Fase 2:** `1a16793`. **Backup fora do repositório:** `/home/claude/backups/friday-pi-pre-evolucao-20261024/`.
- **Commits:** `a7ec5ad` (Fase 3: registro de experiências) · `73b21e3` (4.1: planejador, troca de estratégia, aprendizado pela experiência) · `09714cb` (4.2: objetivos que ela propõe e só o dono aprova) · `22bf0e7` (documentação e evidências das fases 3 e 4, junto com a atualização dos guias — o commit que traz este arquivo).
- **Escopo (missão de 24/10, Fases 3 e 4):** guardar **o que tentou, o que esperava, o que viu e o que isso quer dizer** (experiência); usar isso para **escolher a próxima estratégia com justificativa verificável**; um **ciclo de planejamento** que executa pelo corretor, observa, confere e troca de estratégia dentro do permitido; e **objetivos próprios** com limites (propor ≠ planejar ≠ ser autorizada). Testes pedidos: **C, E** (e **G**, **J** de novo).
- **Fora do escopo, de propósito:** coordenador e destino do `nucleo.py` (Fase 5), retomada depois de reinício (Fase 6).
- **Honestidade sobre «aprender»:** nada aqui treina, ajusta ou muda o modelo de linguagem. O aprendizado é **memória de episódios + contagem honesta** que só **reordena** estratégias que o código já permite. Isso está escrito em `docs/EXPERIENCIAS.md`, nas falas dela e no código.

## 1. Resumo das alterações

| Peça | O que mudou |
|---|---|
| Experiências (`friday/experiencias.py`, novo, 485 linhas) | Liga-se ao fim das tarefas (`tarefas.GANCHOS_FIM`) e guarda: objetivo, contexto, **hipótese gravada antes de agir**, estratégia, ações, **esperado × observado**, evidência da conferência, diferença, **causas prováveis com confiança e tipo** (`fato` · `inferencia` · `hipotese` · `desconhecido`), o que aprendeu, o que continua desconhecido, alternativas e **condições de reutilização**. Resultados: `sucesso`, `falha` (`falso_sucesso`, `erro`, `recusa`), `sem_conferencia`, `interrompida`, `cancelada` |
| Escolha por experiência | `sinais(estrategia, condicoes)` conta só experiências **compatíveis com as condições de agora** e de desfecho conhecido; taxa suavizada `(acertos+1)/(n+2)`, então **uma falha nunca zera uma estratégia nem vira regra**. `conferir_escolha()` recalcula a justificativa e **apanha uma justificativa adulterada** |
| Planejador (`friday/planejador.py`, novo, 323 linhas) | Ciclo de **11 passos** devolvido em `resultado["ciclo"]`; catálogo de estratégias **escrito em código** (3 objetivos); executa **pelo corretor**; se o efeito não aparece, registra a experiência e tenta alternativa equivalente e permitida, ou pede esclarecimento, ou para. Reavalia o ambiente a cada tentativa |
| Objetivos (`friday/objetivos.py`, novo, 369 linhas) | Ela **propõe** a partir de `experiencias.padroes()` (mesma estratégia falhou ≥ 2× sem acerto, nas mesmas condições, em tarefa que o dono pediu). Só o dono aprova, por frase explícita. Limites fixos **no código**: nível ≤ 1, 2 tentativas, nada sai do aparelho |
| Tarefas (`friday/tarefas.py`, +15 linhas) | `plano_v` (versão do plano: cada plano novo é uma tentativa nova) e `DICAS`: quando uma ação **da IA** falha ou o efeito não aparece, uma dica curta (≤ 500 caracteres, uma só) vai junto com o resultado. Recusa do corretor **não** ganha dica (a IA deve corrigir o pedido, não trocar de ferramenta) |
| Ligação (`friday/main.py`) | `XP.tratar` e `OBJ.tratar` na ordem de `processar()`; `experiencias` e `objetivos` no painel (contagens) |
| Voz | «o que você aprendeu com as tarefas?», «minhas experiências» · «quais objetivos você propõe?», «aprova o objetivo N», «pausa/retoma/cancela/recusa o objetivo N» |

## 2. Problemas confirmados e corrigidos

Reprodução no código atual por `tests/auditoria_achados.py` (`reports/evidencias/logs/fase3_4/achados_depois_fase3_4.json`):

| # | Achado | Auditoria | Fim da Fase 2 | Depois da Fase 4 |
|---|---|---|---|---|
| 1 | Ciclo objetivo → plano → execução → verificação → experiência | CONFIRMADO | PARCIAL | **RESOLVIDO** |
| 4 | Sem registro de experiências | CONFIRMADO | CONFIRMADO | **RESOLVIDO** |
| 5 | Sem planejamento multietapas / replanejamento | CONFIRMADO | PARCIAL | **PARCIALMENTE_CONFIRMADO** (ver abaixo) |
| 12 | Documentos desatualizados | PARCIAL | PARCIAL | **RESOLVIDO** (docs novos + testes de links) |
| 6, 13 | retomada · `nucleo.py` | | PARCIAL | continuam PARCIAIS (Fases 6 e 5) |

Total depois da Fase 4: **10 resolvidos, 3 parciais, 0 confirmados** (na Fase 2: 8 / 4 / 1).

**O que ainda faz o #5 ficar parcial** (dito sem enfeite): o planejador executa e troca de estratégia, mas **só recebe objetivo por código ou por proposta aprovada**. «Anota que…» dito livremente **não** vira objetivo do planejador. Ligar a fala livre exige decidir quais frases viram objetivo — decisão do dono, e não a tomei por ele.

Modos de falha **previstos no desenho** e travados por teste e por mutação (não são defeitos encontrados no código antigo: o módulo é novo; são os erros que um sistema que «aprende» costuma cometer):
- **Recusa do corretor não é falha da estratégia** (senão ela «aprenderia» a evitar uma ferramenta por causa de um pedido mal feito): a recusa aparece à parte e não pesa (`test_recusa_do_corretor_nao_e_falha_da_estrategia`; recusa e execução sem conferência também não pesam: `test_recusas_e_execucoes_sem_conferencia_nao_pesam`).
- **A mesma tentativa não conta duas vezes** quando o dono confirma depois (execução sem conferência → concluída pelo dono): vale a última versão da tentativa (`test_o_dono_confirma_e_a_ultima_versao_da_tentativa_vale`).
- **Experiência de outras condições não vale** (cofre desligado × ligado): `test_experiencia_de_outras_condicoes_nao_vale`.
- **Uma falha nunca zera uma estratégia** e um acerto não a torna imune: `test_uma_falha_nao_proibe_a_estrategia`, `test_um_acerto_nao_faz_a_estrategia_imune`.
- **O que ela faz por conta própria não alimenta novas propostas** (evita laço): `test_o_que_ela_fez_por_conta_propria_nao_alimenta_novas_propostas`.
- **Justificativa adulterada é apanhada** por `conferir_escolha()`: `test_justificativa_adulterada_e_apanhada`.
- A mutação mostrou camadas que se cobrem (filtro do padrão × validação do vínculo): um mutante de **uma** camada só sobrevive, de propósito e documentado (§5).

## 3. Arquivos

**Novos:** `friday/experiencias.py`, `friday/planejador.py`, `friday/objetivos.py`, `docs/EXPERIENCIAS.md`, `docs/PLANEJADOR.md`, `tests/test_experiencias.py` (55 testes), `tests/test_planejador.py` (49), `tests/test_objetivos.py` (50), `reports/evidencias/cenarios/fase3_4/` (`cenario_autonomia.py`, `mutar.py`, `mut_experiencias_planejador.py`, `mut_objetivos.py`), `reports/evidencias/logs/fase3_4/`.

**Alterados:** `friday/tarefas.py` (+15, aditivo), `friday/main.py` (+8), `tests/test_tarefas_integracao.py` (+5 testes), `tests/auditoria_achados.py` (sondas dos achados 1, 4 e 5, que passaram a exercitar o comportamento real), `CLAUDE.md`, `README.md`, `docs/ARQUITETURA.md`, `docs/TAREFAS.md`, duas skills (`friday-cerebro`, `friday-nova-ferramenta`).

**Não tocados:** `broker.py`, `protocolos.py`, `acao.sh`, `termux/`, `servidor/`, `privacidade.py`, `visao.py`, `maos.py`, `nucleo.py`, `catalogo.py`. Nenhuma ferramenta nova para a IA.

## 4. Decisões arquiteturais

1. **Experiência ≠ treino ≠ permissão.** Nenhum peso muda; nenhuma experiência sobe nível, tira confirmação ou faz o corretor aceitar o que recusou. Teste: `test_experiencia_falsa_nao_cria_estrategia_nem_sobe_de_nivel`.
2. **Catálogo de estratégias em código.** Nem experiência, nem IA, nem texto da internet acrescentam ferramenta. Alternativa descartada: deixar a experiência «descobrir» ferramentas novas — daria ao aprendizado o poder de ampliar o que ela pode fazer.
3. **Fato × inferência × hipótese × desconhecido** nunca se misturam, e as confianças são por regra, **não probabilidades calibradas** (escrito nos docs).
4. **Taxa suavizada** em vez de contagem bruta ou punição: sem dados 0,5; uma falha → 0,33; um acerto → 0,67. «Sem punição artificial» da missão: falha é informação, nenhum número de prêmio/castigo é somado a nada.
5. **A justificativa é conferível.** A escolha guarda ranking, contagens e ids; `conferir_escolha()` recalcula com as experiências feitas **até o instante da escolha**. Uma frase bonita que não bate com o registro é detectada.
6. **Hipótese gravada antes de agir** (`experiencias.intencao()`): teste prova que o arquivo já tem a expectativa quando a ferramenta roda. Evita «previsão» escrita depois do resultado.
7. **Propor ≠ planejar ≠ ser autorizada.** `objetivos.propor` só grava; `planejador.executar_objetivo` monta e escolhe; **só o dono** autoriza («aprova o objetivo N»; «sim», «pode», «faz aí» nunca aprovam). Ela não consegue alterar regra de segurança: corretor, protocolos, autonomia e curiosidade não são tipos de objetivo.
8. **Recusa do corretor encerra a tentativa.** Não se contorna trocando de ferramenta. Estratégia de nível ≥ 2 nunca é escolhida sozinha: vira sugestão.
9. **O planejador não importa o corretor** (só o catálogo de ferramentas); teste de AST confere. A IA ganha só uma dica, continua apenas propondo.
10. **A verdade do objetivo está na tarefa.** Depois de um reinício `objetivos.conciliar()` põe a proposta de acordo com a tarefa que ela criou; sem tarefa, nada foi começado e **nada é repetido**.
11. **Estado validado ao ler.** `objetivos_proprios.json` não obedece a limite, autor da decisão ou estado vindos do arquivo: o código recalcula, então arquivo editado à mão não ganha permissão (`test_o_limite_da_proposta_e_o_do_codigo_nao_o_do_arquivo`, `test_estado_desconhecido_vira_pausado_e_quem_decidiu_so_pode_ser_o_dono`, `test_arquivo_estragado_nao_derruba_nada`).

## 5. Testes e resultados

| Item | Linha de base | Fim da Fase 2 | Agora (fim da Fase 4) |
|---|---|---|---|
| Unitários, Python 3.11 / 3.12 / 3.13 | 717 OK | 1017 OK | **1176 OK** (1 pulado, o mesmo de antes) nas três — `reports/evidencias/logs/fase3_4/unit_py3.11.log`, `unit_py3.12.log`, `unit_py3.13.log` |
| Unitários em ambiente criado só com `requirements-test.txt` | — | 1017 OK | **1176 OK** (`unit_venv_limpo.log`) |
| Roteiros no Chromium (5 scripts) | 163 / 0 | 163 / 0 | **163 / 0** (hud 61, voz e memória 21, cérebro 38, mãos 29, pré-córtex 14; `e2e_*.fase3_4.log`) |
| Mutação — experiências + planejador | — | — | **41 de 41** detectados (`mut_experiencias_planejador.log`) |
| Mutação — objetivos | — | — | **39 de 40** (`mut_objetivos.log`); o sobrevivente é um mutante de **uma** camada, coberto de propósito pela camada seguinte; o mutante das **duas** camadas juntas é detectado |
| Mutação das fases anteriores, de novo | 51/51 · 25/25 | | **51/51** (tarefas, corretor, pré-córtex) · **25/25** (verificação) — `mut_tarefas_reexecutada.log`, `mut_verificacao_reexecutada.log` |
| Testes novos | — | +167 | **+159** (55 + 49 + 50 + 5 de integração) |

**Os testes A–J da missão, no estado desta fase:**

| Teste | Situação | Onde |
|---|---|---|
| A — execução básica verificada | **passa** | `test_planejador.Ciclo`; cenário A |
| B — falso sucesso não vira `CONCLUIDA` | **passa** | `test_tarefas`, `test_planejador`; cenário B (sem alternativa a trocar → `pedir_esclarecimento`, tarefa `FALHOU`) |
| C — falha + alternativa permitida com experiência registrada | **passa** | `test_planejador.FalhaEAlternativa.test_C_…`; cenário C (`guardar_memoria` mente → experiência `x0003` falha/`falso_sucesso` → `anotar` conclui, `x0004` sucesso) |
| D — retomada depois de interrupção | **parcial**: o estado sobrevive, `reabrir` reconfere o efeito, `objetivos.conciliar()` não repete nada; retomada automática é a Fase 6 | `test_tarefas`, `test_objetivos` |
| E — aprendizado muda a próxima estratégia | **passa**, com justificativa conferível | `test_planejador.AprendizadoMudaAEscolha.test_E_…`; cenário E (`anotar` 0,67 passa à frente de `guardar_memoria` 0,5; `conferir_escolha` bate) |
| F — ação sensível não executa com confirmação ambígua | **passa**, sem regressão | `test_tarefas`, `test_confirmacao` |
| G — privacidade | **passa**: o conteúdo do dono não aparece em `experiencias.jsonl`, `objetivos_proprios*.json*`, `tarefas.json` nem na auditoria | `test_planejador.Privacidade`, `test_experiencias`, `test_objetivos`; cenário G (`arquivos que contêm o conteúdo: nenhum`) |
| H — metas relacionadas com texto diferente | **passa**, sem regressão | `test_tarefas_metas` |
| I — concorrência e coordenação | **parcial**: confirmações trocadas, cancelamento durante a execução e tarefas simultâneas estão testados; o coordenador é a Fase 5 | `test_tarefas` |
| J — regressão | **passa** (tabela acima) | suíte inteira |

**Roteiro de demonstração** (`python3 reports/evidencias/cenarios/fase3_4/cenario_autonomia.py`, saída em `reports/evidencias/logs/fase3_4/cenario_autonomia.log`): cenas A, B, C, E e G, mais a cena de objetivos (duas falhas pedidas por você fecham um padrão → ela **propõe** anotar a observação; «sim» não faz nada; «aprova o objetivo 1» executa pelo planejador e confere o efeito; decidida por: dono).

**Não executável aqui:** celular real e Termux:API, microfone, internet ao vivo, **qualidade de qualquer modelo de linguagem real** (a dica e o laço da IA são testados com respostas simuladas), desempenho em aparelho fraco.

## 6. Limitações e riscos

- **Aprendizado é estatística simples sobre poucas amostras.** Com 1–3 tentativas o texto diz «é indício, não regra». As confianças são estimativas por regra.
- **`experiencias.jsonl` não são neurônios do cofre.** O registro é um arquivo do processo; ainda não vira sinapse nem aparece nas regiões do cérebro 3D. (Ligar isso muda a semântica de memória, então ficou para decisão do dono.)
- **`ambiente()` olha duas condições** (cofre ativo, manutenção). Rede, bateria e horário ainda não são condições; uma falha causada por elas poderia ser atribuída à estratégia.
- **Catálogo fixo:** 3 objetivos (`registrar_informacao`, `registrar_e_avisar`, `lembrar_depois`); só o primeiro pode ser **próprio** (nível 1). Ela não inventa estratégia nova.
- **Sem entrada por fala livre** (ver §2, achado #5).
- **Efeito parcial de uma estratégia que falhou no meio** (nota salva antes de o lembrete falhar) fica no mundo; a experiência registra, nada desfaz sozinho.
- **Só tarefa que termina gera experiência.** Uma queda no meio só gera experiência quando a tarefa for fechada (a Fase 6 trata essa retomada).
- **Dica para a IA** é só texto; um modelo real pode ignorá-la. Não há como medir aqui.
- **Mutação:** 1 sobrevivente documentado (camadas redundantes); ficam sem mutação os módulos antigos `autonomia.py`, `cerebro.py` e mãos (item 1.9 do plano, pendente desde a Fase 1).
- **Interface:** `tarefas.DICAS`, `tarefas.GANCHOS_FIM` e o campo `plano_v` são novos; nada que existia mudou de significado. `broker.py` não foi tocado.

## 7. Como executar e validar

```
pip install -r requirements-test.txt
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'                 # 1176 testes nesta altura (1278 hoje, com as Fases 5 e 6)
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_experiencias.py'      # 55
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_planejador.py'        # 49
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_objetivos.py'         # 50
python3 tests/e2e_hud.py && python3 tests/e2e_voz_memoria.py && python3 tests/e2e_cerebro.py && python3 tests/e2e_maos.py && python3 tests/e2e_prefrontal.py
python3 tests/auditoria_achados.py
python3 reports/evidencias/cenarios/fase3_4/cenario_autonomia.py
cd reports/evidencias/cenarios/fase3_4 && python3 mutar.py mut_experiencias_planejador.py ../../../..   # idem mut_objetivos.py
```

## 8. Documentação atualizada

`docs/EXPERIENCIAS.md` e `docs/PLANEJADOR.md` (novos), `docs/ARQUITETURA.md`, `docs/TAREFAS.md`, `README.md`, `CLAUDE.md` (regra 1: propor ≠ planejar ≠ ser autorizada; mapa do código; ordem de `processar()`), as skills `friday-cerebro` e `friday-nova-ferramenta`, e as seções «Atualização — Fases 3 a 6» dos três relatórios de `reports/`.

## 9. Próxima fase (objetiva)

**Fases 5 e 6 — coordenação e retomada** (`friday/coordenador.py`, `friday/retomada.py`): medir primeiro se duas ações realmente se pisam, e só então criar o mínimo; decidir o destino do `nucleo.py` com evidência antes de qualquer mudança destrutiva; e, depois de reinício ou queda, **conferir o efeito por fora antes de repetir**, sem nunca repetir sozinha o que pode já ter acontecido e não dá para conferir. Entregue em `reports/FASE_5_6_ENTREGA.md`.
