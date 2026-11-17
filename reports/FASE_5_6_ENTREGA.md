# Entrega das Fases 5 e 6 — coordenação mínima, destino do `nucleo.py` e retomada depois de queda

- **Data:** 24/10/2026. **Ramo:** `evolucao-fase1` (fases empilhadas no mesmo ramo). **Linha de base:** tag `linha-de-base-auditoria` (`6030a56`). **Fim da Fase 4:** `09714cb`. **Backup fora do repositório:** `/home/claude/backups/friday-pi-pre-evolucao-20261024/`.
- **Commits:** `7b54e94` (Fase 5: coordenador mínimo e decisão sobre o `nucleo.py`) · `a66ec00` (Fase 6: retomada) · `22bf0e7` (documentação das Fases 3 a 6 e evidências das Fases 3 e 4) · o commit que traz este arquivo e as atualizações dos três relatórios antigos.
- **Escopo (missão de 24/10, Fases 5 e 6):** (5) coordenação de impulsos e ações concorrentes — decidir com **evidência** se `nucleo.py` entra, fica ou sai, e criar só o mínimo necessário; (6) retomar o que ficou interrompido por reinício ou queda **sem repetir o que não pode ser repetido**. Testes pedidos: **D, F, G, I** (e **J**, regressão final de todas as fases).
- **Regras da missão seguidas:** medir antes de criar (os dois módulos nasceram de um script que prova a necessidade); `nucleo.py` **não foi apagado, movido nem religado**; o corretor continua a única porta de ação; nada de ferramenta nova para a IA; nenhum teto de conhecimento recolocado.

## 1. Resumo das alterações

| Peça | O que mudou |
|---|---|
| Coordenador (`friday/coordenador.py`, novo, 289 linhas) | (a) **Reserva de recursos tudo-ou-nada** (`excl` / `comp`): `tarefas.py` reserva antes de cada passo e libera no `finally`; quem não consegue espera até `ESPERA_RECURSO_S` (3 s) e, se continuar ocupado, a tarefa fica `PRONTA` com o motivo, **sem executar**. (b) **`avaliar()`** de propostas com decisão explicada: `executar_agora` · `esperar` · `pedir_dono` · `recusar`, pesos fixos no código (relevância +0,40, urgência +0,30, custo −0,10, risco −0,15, incerteza −0,05). Cada decisão vai para `.cerebro/coordenacao.jsonl` sem conteúdo (recursos como tipo + código de 6 caracteres). **Ações independentes continuam em paralelo** (decisão do dono) |
| `nucleo.py` | **Mantido como está** (não apagado, não movido, não religado). Decisão documentada em `docs/NUCLEO.md` com a evidência medida; `tests/test_coordenador.py::NucleoFicaDesligado` falha se alguém o importar ou se `main.py` o iniciar |
| Recuperação (`tarefas.recuperar`, `tarefas.confirmacao_perdida`) | Tarefa que ficou `EXECUTANDO`/`VERIFICANDO` sem estar sendo executada por este processo: cada passo que estava «executando» é **conferido no mundo** (verificador independente da Fase 2, com a marca de antes). Efeito achado → `verificado`, **não repete**. Provadamente ausente (ou ferramenta só de leitura), com menos de `MAX_QUEDAS` (2) quedas → volta a `pendente`. Qualquer outra coisa → `intervencao` («interrompido»): **pode ter acontecido, não repete, pede o dono**. Confirmação pendente que sumiu no reinício → nada executa, o dono pede a ação de novo |
| Retomada (`friday/retomada.py`, novo, 277 linhas) | `retomar_pendentes()`: recupera, depois retoma **só o seguro** — origem do dono/meta/objetivo aprovado (**não** a conversa com a IA), parada há ≤ 30 min, nível < 2, argumentos guardados, e o coordenador libera dependência e recurso. Sequencial, uma rodada por vez, no máximo 20 tarefas. Quem executa é `tarefas.executar` → corretor |
| Ligação (`friday/main.py`) | `RET.tratar` depois de `TAR.tratar`; retomada **ao ligar** numa thread (`FRIDAY_RETOMADA=0` desliga só a parte automática); `OBJ.conciliar()` logo depois; só **fala** se retomou, conferiu ou precisa do dono; painel só com contagens |
| Voz | «o que você está coordenando?» · «retoma o que ficou pendente» / «continua de onde parou» (confere e retoma o seguro) · «o que ficou interrompido?» (**só lê**) · «a tarefa N está feita» também aceita passo interrompido |
| `.env.example` | `FRIDAY_RETOMADA=1` (comentado) |

## 2. Problemas confirmados e corrigidos

**2.1 Duas ações no mesmo recurso se pisavam** (medido: `reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py`). O corretor solta a trava antes de rodar a ferramenta, então duas tarefas do mesmo recurso ficavam **as duas dentro da ferramenta ao mesmo tempo**.

| Situação | Antes (`necessidade_de_coordenacao.antes.log`) | Depois (`…depois.log`) |
|---|---|---|
| duas tarefas, **mesmo** recurso | pico de **2** dentro da ferramenta | pico de **1** (uma esperou a outra) |
| duas tarefas, recursos **diferentes** | — | pico de **2** (continuam em paralelo, como o dono decidiu) |
| reservas que sobraram depois | — | nenhuma |

**2.2 Tarefa presa em `EXECUTANDO` para sempre depois de uma queda** (medido com **queda real de processo**, `os._exit` no meio da ação, três processos de verdade e um quarto que reinicia: `necessidade_de_retomada.py`). Antes, nem `executar_proximo` («já está em execução») nem `reabrir` («a tarefa está executando; não há o que retomar») aceitavam o estado.

| Queda | Antes (`necessidade_de_retomada.antes.log`) | Depois (`necessidade_de_retomada.depois.log`) |
|---|---|---|
| **depois** do efeito (lembrete criado, resultado não registrado) | presa em `EXECUTANDO` | efeito achado por fora → `CONCLUIDA`; lembrete **não** duplicado (1) |
| **antes** do efeito | presa | a conferência prova que não existe → refeito **uma vez** → `CONCLUIDA` (1 lembrete) |
| ação que **não dá para conferir** (lanterna) | presa | **não repetida** → `PRECISA_INTERVENCAO`, com o motivo escrito |

**2.3 Achados da auditoria** (`tests/auditoria_achados.py`, `reports/evidencias/logs/fase5_6/achados_depois_fase5_6.json`):

| # | Achado | Auditoria | Fim da Fase 4 | Agora |
|---|---|---|---|---|
| 6 | Sem retomada de tarefas interrompidas | CONFIRMADO | PARCIAL | **RESOLVIDO** (a sonda simula a queda depois do efeito, retoma e confere que o lembrete existe uma só vez; a queda com `os._exit` real está em `necessidade_de_retomada.py` e em `test_retomada.QuedaReal`) |
| 13 | Conflito `nucleo.py` × `main.py` × `simbiose.py` | PARCIAL | PARCIAL | **RESOLVIDO** (evidência + decisão documentada + teste que fixa; `simbiose.py` é usado pelo hook do Claude Code) |
| 5 | Planejamento multietapas / replanejamento | CONFIRMADO | PARCIAL | **PARCIALMENTE_CONFIRMADO**: o planejador só recebe objetivo por código ou proposta aprovada; falar «anota que…» ainda não vira objetivo (decisão do dono) |
| demais | 1–4, 7–12 | | | RESOLVIDOS, sem regressão |

Total: **12 resolvidos, 1 parcial, 0 confirmados** (na auditoria: 12 confirmados e 1 parcial).

**2.4 Defeitos encontrados pelos próprios testes durante a fase** (todos corrigidos, com teste):
- **Reserva vazando** se a preparação do passo quebrasse depois de reservar: agora `except BaseException: _liberar_reserva(tid); raise`, com teste.
- **Nível ilegível no disco** não podia ser tratado como seguro: `_elegivel` e o coordenador tratam como nível 2 (sensível); o coordenador também passou a tratar o nível ilegível como 2 e a pedir o dono (`test_nivel_ilegivel_no_disco_e_tratado_como_sensivel`; teste novo em `test_coordenador`).
- **Motivo errado** para tarefa de nível 2 depois do reinício (dizia «argumentos» em vez de «nível 2»): camada 1 agora checa o nível antes.
- **Teste que vazava ferramentas `*_teste`** na suíte inteira (`test_toda_ferramenta_que_muda_algo_declara_seus_recursos`): passou a ignorar ferramentas cujo módulo começa com `test`.
- **Mutação com falsos positivos**: o executor de mutação agora roda a **linha de base antes** (a suíte tem de passar sem mutação); antes, um teste que dependia de arquivo fora da cópia «detectava» qualquer mutante.
- **Script de evidência do `nucleo`** poderia tocar o cofre real: passou a usar cofre, banco e auditoria temporários.

## 3. Arquivos

**Novos:** `friday/coordenador.py`, `friday/retomada.py`, `docs/COORDENADOR.md`, `docs/RETOMADA.md`, `tests/test_coordenador.py` (42 testes), `tests/test_retomada.py` (52), `reports/evidencias/cenarios/fase5_6/` (`necessidade_de_coordenacao.py`, `necessidade_de_retomada.py`, `nucleo_evidencia.py`, `mut_coordenador.py`, `mut_retomada.py`), `reports/evidencias/logs/fase5_6/`.

**Alterados:** `friday/tarefas.py` (+recuperar, +confirmacao_perdida, +reserva/liberação, `ATIVAS`, `MAX_QUEDAS`; `confirmar_manual` aceita passo interrompido), `friday/main.py` (COORD e RET), `.env.example`, `tests/test_tarefas_integracao.py` (+8), `tests/auditoria_achados.py` (sondas 6 e 13), `docs/NUCLEO.md` (decisão), `docs/TAREFAS.md`, `docs/ARQUITETURA.md`, `README.md`, `CLAUDE.md`, duas skills, e os três relatórios de `reports/`.

**Não tocados:** `broker.py`, `protocolos.py`, `acao.sh`, `termux/`, `servidor/`, `privacidade.py`, `visao.py`, `maos.py`, `nucleo.py`, `catalogo.py`, `autonomia.py`. Nada foi apagado.

## 4. Decisões arquiteturais

1. **Coordenar ≠ autorizar.** Reservar recurso ou dar nota não dá permissão; `pedir_dono` **não sai por nota alta** (`test_F_o_que_exige_o_dono_continua_exigindo_por_mais_alta_que_seja_a_nota`). O coordenador não importa o corretor nem executa nada (teste de AST).
2. **Reserva só em `tarefas.py`, por gancho.** `tarefas.RESERVAS` é preenchido quando `coordenador` é importado; `tarefas` não importa `coordenador` (sem ciclo; teste). Alternativa descartada: reservar dentro do corretor — misturaria política de concorrência com política de segurança e tocaria `broker.py`, que pede confirmação para editar.
3. **Não serializar o que não se atrapalha.** O dono decidiu: «se ela quiser fazer tudo ao mesmo tempo, ela que decide». Por isso conflito só existe **no mesmo recurso**, e pelo mesmo motivo o `nucleo.py` (que serializa) não foi religado.
4. **`nucleo.py`: mantido, desligado, fixado por teste.** Opções avaliadas em `docs/NUCLEO.md`: A religar como está (**rejeitada**: serializa e tem teto de foco); B reescrever e religar (**sem demanda demonstrada**, o coordenador resolve o que faltava); C mover para `Arquivo/` (**não feito por mim**: permitido pela regra 8, mas é limpeza de projeto — fica a critério do dono); D aproveitar só a habituação (**ideia guardada**, nenhuma medida a pede).
5. **Pesos fixos no código.** Nota = relevância·0,40 + urgência·0,30 − custo·0,10 − risco·0,15 − incerteza·0,05; nenhum aprendizado altera os pesos, e a nota só **ordena** quando há conflito.
6. **Tudo ou nada, sem esperar dentro da reserva.** Reservar parcial geraria impasse entre duas tarefas; a espera acontece **fora**, em `tarefas.py`, com teto de 3 s.
7. **Retomar ≠ repetir.** A regra central da Fase 6: **ação que pode já ter acontecido e não dá para conferir nunca é repetida sozinha.** Só repete o que a conferência independente **provou ausente**, ou o que apenas lê, e no máximo `MAX_QUEDAS` vezes (laço de queda).
8. **Olhar o mundo, nunca a resposta da ferramenta.** A recuperação usa o mesmo verificador da Fase 2 (marca tirada **antes** da ação), então um lembrete criado antes da queda é reconhecido e não duplicado.
9. **O que a retomada faz sozinha é estreito de propósito.** Pedido da conversa (`ia`) **não** é retomado: o contexto se perdeu e o corretor tratava aquele turno como mais perigoso (contaminação). Mais de 30 min também não: pode já não valer. Nível ≥ 2 pede a confirmação presa à ação, como sempre. **Duas camadas** barram o nível 2 (elegibilidade + coordenador).
10. **Depois de um reinício, argumentos de nível ≥ 2 não existem mais** (decisão de privacidade da Fase 2). A retomada não inventa a ação: pede o dono.
11. **Retomada sem threads e sem agente:** sequencial, uma rodada de cada vez (trava não bloqueante), no máximo 20 tarefas e 4 rodadas por chamada. O coordenador protege contra outras execuções simultâneas por reserva de recurso.
12. **Registro sem conteúdo.** `retomada.jsonl` e `coordenacao.jsonl` guardam ids, ação, motivo curto e estado; recursos viram tipo + 6 caracteres de hash.

## 5. Testes e resultados

| Item | Linha de base | Fim da Fase 2 | Fim da Fase 4 | **Agora** |
|---|---|---|---|---|
| Unitários, Python 3.11 / 3.12 / 3.13 | 717 OK | 1017 OK | 1176 OK | **1278 OK** (1 pulado, o mesmo de antes) nas três — `reports/evidencias/logs/fase5_6/unit_py3.11.log`, `unit_py3.12.log`, `unit_py3.13.log` |
| Unitários num ambiente criado só com `requirements-test.txt` (Python 3.13, cópia limpa) | — | 1017 OK | 1176 OK | **1278 OK** (`unit_venv_limpo.log`) |
| Roteiros no Chromium (5 scripts) | 163 / 0 | 163 / 0 | 163 / 0 | **163 / 0** (hud 61, voz e memória 21, cérebro 38, mãos 29, pré-córtex 14; `e2e_*.fase5_6.log`) |
| Mutação do coordenador | — | — | — | **37 de 37** (`mut_coordenador.log`) |
| Mutação da retomada (+ recuperar/confirmação perdida/ligação) | — | — | — | **33 de 33** detectados; **2 sobreviventes esperados e marcados `[redundante]`**: camadas que outra camada cobre (nível ilegível só na camada 1; recuperar tarefa ativa na retomada, que `tarefas.recuperar` também barra). O mutante que quebra **as duas** camadas é detectado (`mut_retomada.log`) |
| Mutação das fases anteriores, reexecutada no código de agora | 51/51 · 25/25 | | 41/41 · 39/40 | **todas confirmadas no código de agora:** verificação 25/25, tarefas+corretor+pré-córtex 51/51, experiências+planejador 41/41, objetivos 39/40 (o mesmo sobrevivente documentado de uma camada) — `mut_verificacao_reexecutada.log`, `mut_tarefas_reexecutada.log`, `mut_experiencias_planejador_reexecutada.log`, `mut_objetivos_reexecutada.log` |
| Testes novos | — | +167 | +159 | **+102** (42 + 52 do coordenador e da retomada, +1 de nível ilegível e +8 de integração em `test_tarefas_integracao`) — em todo o trabalho: **+561** sobre a linha de base |

**Os testes A–J da missão, no estado final:**

| Teste | Situação | Onde |
|---|---|---|
| A — execução básica verificada | **passa** | `test_tarefas`, `test_planejador`; cenário A |
| B — falso sucesso não vira `CONCLUIDA` | **passa** | `test_tarefas`, `test_planejador`, `test_tarefas_integracao`; cenário B |
| C — falha + alternativa permitida, experiência registrada | **passa** | `test_planejador.FalhaEAlternativa.test_C_…`; cenário C |
| D — retomada depois de interrupção | **passa**, simulada **e com queda real de processo** (`os._exit`): efeito existia → conferido, não duplicado; efeito ausente → refeito uma vez; não conferível → não repetido; laço de queda para na segunda; o dono pode dizer «está feita» ou mandar repetir | `test_retomada` (`test_D_…`, `QuedaReal`); `necessidade_de_retomada.py --depois` |
| E — aprendizado muda a próxima estratégia, justificativa conferível | **passa** | `test_planejador.AprendizadoMudaAEscolha`; cenário E |
| F — ação sensível não executa com confirmação ambígua | **passa**, inclusive **depois de um reinício** («sim», «pode», «confirmo» não ressuscitam a confirmação que se perdeu; nível 2 não é retomado sozinho) | `test_tarefas`, `test_retomada` (`test_F_…`), `test_coordenador` |
| G — privacidade da auditoria | **passa**: auditoria, `tarefas.json`, `experiencias.jsonl`, `objetivos_proprios*`, `retomada.jsonl` e `coordenacao.jsonl` sem o conteúdo do dono | `test_retomada.Privacidade`, `test_coordenador.Registro`, demais |
| H — metas relacionadas com texto diferente | **passa**, sem regressão | `test_tarefas_metas` |
| I — concorrência e coordenação | **passa**: reserva por recurso com threads de verdade, compartilhado × exclusivo, retomada coordenada, tarefa em execução não é tocada | `test_coordenador` (`test_I_…`), `test_retomada.Coordenacao`; `necessidade_de_coordenacao.py` |
| J — regressão | **passa** (tabela acima) | suíte inteira em 3 versões do Python + ambiente limpo + 5 roteiros no navegador |

O resultado final dos dez testes, no formato de `RESULTADOS_TESTES.json` (que continua sendo a foto da auditoria), está em `reports/RESULTADOS_TESTES_FINAL.json`: **8 aprovados e 2 aprovados com ressalvas** (D: reinício real do Android não exercitado; I: o coordenador só cobre o que passa por `tarefas.py`).

**Não executável aqui (dito sem enfeite):** celular real e Termux:API; **reinício e `kill` reais do Android** (a queda foi simulada por exceção e exercitada com `os._exit` num processo Linux separado — é o mais próximo possível sem aparelho); microfone; internet ao vivo; qualidade de qualquer modelo de linguagem real; desempenho em aparelho fraco. Um teste antigo chama `api.open-meteo.com`, bloqueado pelo proxy desta sessão (o resultado não depende disso).

## 6. Limitações e riscos

- **O coordenador só vê o que passa por `tarefas.py`.** Protocolos, rotinas da autonomia e atalhos de memória por voz chamam o corretor direto e **não reservam recurso**. O corretor continua protegendo todos, mas dois deles no mesmo recurso ainda podem se sobrepor. Cobrir isso exige editar `protocolos.py` (pede confirmação, regra 7).
- **A coordenação é por processo.** Duas instâncias da FRIDAY no mesmo cofre não se coordenam.
- **Só sete ferramentas têm conferência independente** (`criar_lembrete`, `anotar`, `criar_arquivo`, `guardar_memoria`, `silenciar`, `voltar_a_falar`, `pedir_evolucao`). Para as outras, «efeito achado → não repete» não existe: a recuperação cai em «pede o dono», que é o lado conservador. Isso significa que SMS, ligação, relé e lanterna interrompidos **sempre** esperam você.
- **A conferência de efeito ausente assume efeito imediato** (ferramentas locais). Um efeito assíncrono poderia ser dado como ausente cedo demais; hoje nenhuma ferramenta conferível é assim.
- **Efeitos parciais de estratégias que falharam** continuam no mundo (Fase 4).
- **Tarefas de nível ≥ 2 perdem os argumentos no reinício** (privacidade): você pede de novo.
- **Pedido feito na conversa e interrompido** não é retomado sozinho (só por «retomar a tarefa N», se ainda houver os dados).
- **`FRIDAY_RETOMADA=0`** desliga só a retomada automática ao ligar; o comando de voz continua valendo (não há botão que a pare: regra 9).
- **Pesos do coordenador** são julgamento meu, fixos no código; não foram calibrados com dados reais de uso.
- **Experiências em `.jsonl`, não neurônios** (Fase 3), e **catálogo de 3 objetivos** (Fase 4) continuam valendo.
- **Pendências herdadas, não tocadas:** `voz.py:36` com `shell=True`; tags `latest` no Docker; pré-córtex nos `vitais`; cobertura e mutação de `autonomia.py`, `cerebro.py` e mãos; o 1 teste pulado já existia na linha de base.

## 7. Como executar e validar

```
pip install -r requirements-test.txt
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'            # 1278 testes
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_coordenador.py'  # 42
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_retomada.py'     # 52 (inclui queda real de processo)
python3 tests/e2e_hud.py && python3 tests/e2e_voz_memoria.py && python3 tests/e2e_cerebro.py && python3 tests/e2e_maos.py && python3 tests/e2e_prefrontal.py
python3 tests/auditoria_achados.py
python3 reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py --depois
python3 reports/evidencias/cenarios/fase5_6/necessidade_de_retomada.py --depois     # sem --depois mostra o estado preso de antes
python3 reports/evidencias/cenarios/fase5_6/nucleo_evidencia.py
cd reports/evidencias/cenarios/fase3_4 && python3 mutar.py ../fase5_6/mut_coordenador.py ../../../..   # idem mut_retomada.py
```

Para o dono, por voz: «o que você está coordenando?», «o que ficou interrompido?» (só lê), «retoma o que ficou pendente», «a tarefa N está feita», «retomar a tarefa N».

## 8. Documentação atualizada

`docs/COORDENADOR.md` e `docs/RETOMADA.md` (novos), `docs/NUCLEO.md` (decisão e evidência), `docs/TAREFAS.md`, `docs/ARQUITETURA.md`, `README.md`, `CLAUDE.md` (regra 1: coordenar ≠ autorizar, retomar ≠ repetir; mapa do código; ordem de `processar()` com `RET.tratar`), as skills `friday-cerebro` e `friday-nova-ferramenta` (ferramenta nova de nível ≥ 1 declara seus recursos), `.env.example`, e as seções «Atualização — Fases 3 a 6» de `AUDITORIA_COMPLETA.md`, `MAPA_DE_INTEGRACAO.md` e `PLANO_DE_EVOLUCAO.md`.

## 9. Próxima fase (objetiva)

Não há mais fase na missão. O que sobra, em ordem de valor e com o dono decidindo onde marcado:

1. **Validar num aparelho real (só o dono pode).** Reinício e `kill` do Android no Termux com uma tarefa de lembrete no meio, para confirmar o que aqui só foi simulado. Sugestão (não testada por mim): rodar `necessidade_de_retomada.py --depois` no Termux e, depois, derrubar o processo da FRIDAY durante uma tarefa real.
2. **Fala livre → objetivo do planejador** (**decisão do dono**): quais frases («anota que…», «lembra de…») viram objetivo permitido. É o que mantém o achado #5 como parcial.
3. **Levar a coordenação a protocolos, autonomia e atalhos de voz** — exige editar `protocolos.py` (pede confirmação) e decidir se esses caminhos devem virar tarefas.
4. **Mais verificadores independentes** (hoje sete ferramentas) e, se algum efeito for assíncrono, verificação com espera.
5. **Experiências como neurônios do cofre** (**decisão do dono**: muda a semântica da memória).
6. **Cobertura e mutação de `autonomia.py`, `cerebro.py` e mãos;** `voz.py` sem `shell=True`; fixar versões das imagens Docker; pré-córtex nos `vitais`.
7. **`nucleo.py` para `Arquivo/`** (**decisão do dono**): o código fica fora do caminho; hoje custa nada.
