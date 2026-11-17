# Entrega da Fase 2 — tarefas com estado e conferência do efeito

- **Data:** 24/10/2026. **Ramo:** `evolucao-fase1` (a Fase 2 foi feita em cima da Fase 1, em commits próprios; não houve ramo novo para não separar duas fases que dependem uma da outra). **Linha de base:** tag `linha-de-base-auditoria` (`6030a56`). **Fim da Fase 1:** `d49b2c2`. **Backup fora do repositório:** `/home/claude/backups/friday-pi-pre-evolucao-20261024/`.
- **Commits:** `d9f332d` (2.1 corretor estruturado) · `e6be253` (2.2 verificação) · `a29ae3d` (2.3 tarefas, IA, voz, metas) · 2.4 (documentação, relatórios e evidências — o commit que traz este arquivo).
- **Escopo (missão de 24/10, Fase 2):** núcleo mínimo de tarefas (registro, plano, estados, evidência, tentativas, dependências, próxima ação, histórico) e verificação do efeito («a ferramenta disse que fez» ≠ «o objetivo foi atingido»). Testes pedidos: **A, B, F, G, H** (e **J**, regressão).
- **Fora do escopo desta fase, de propósito:** experiências e aprendizado (Fase 3), planejador e metas próprias (Fase 4), coordenador e `nucleo.py` (Fase 5), retomada automática depois de reinício (Fase 6).

## 1. Resumo das alterações

| Peça | O que mudou |
|---|---|
| Corretor (`friday/broker.py`) | `executar_estruturado()` devolve `{estado, texto, codigo, nivel, pendencia, erro, ajustes}`; `executar()` continua devolvendo o mesmo texto de sempre. Novo `OBSERVADORES`: quem se inscreve é avisado quando uma ação é **executada, cancelada, expira ou é substituída**. O corretor segue decidindo tudo (nível, contaminação, confirmação, PIN, auditoria) |
| Conferência (`friday/verificacao.py`, novo) | Olha o **estado real** (banco, pasta de arquivos, cofre) com uma marca tirada **antes** da ação. Vereditos: `confirmado`, `refutado`, `nao_verificavel`, `inconclusivo`; força da prova: `independente`, `da_resposta`, `nenhuma`. Só lê. Evidência sem o conteúdo pedido |
| Tarefas (`friday/tarefas.py`, novo) | Registro persistente com id (`t0001`, nunca reaproveitado), objetivo, contexto, restrições, plano com passos e dependências, estado, ferramenta/ação executada, evidência, veredito, tentativas, próxima ação e histórico. Máquina de estados com `TRANSICOES` como única regra |
| Ligação com a conversa | As duas chamadas de ferramenta da IA (nuvem e Ollama) passam por `tarefas.executar_registrado()`. Se o efeito **não** foi encontrado, a IA recebe o aviso no resultado da própria ferramenta |
| Ligação com as metas | Por **id** (`criar(…, meta="m01", conclui_meta=True)`). Só uma tarefa `CONCLUIDA` **com efeito conferido** conclui uma meta de aprender; o resto só mostra andamento (máximo 90 %) |
| Voz | «minhas tarefas», «cancela a tarefa 3», «retomar a tarefa 3», «a tarefa 3 está feita» |
| Painel | `estado_completo()["tarefas"]` com contagens (sem conteúdo) |
| Privacidade | Argumentos só vão a disco se forem de nível ≤ 1, não da conversa e sem dado sensível, e **saem do registro quando a tarefa termina** (`CONCLUIDA`/`CANCELADA`) |

## 2. Problemas confirmados e corrigidos

Reprodução no código atual por `tests/auditoria_achados.py` (saída em `reports/evidencias/logs/fase2/achados_depois_fase2.json`). As sondas dos achados 1, 2, 3, 5 e 6 foram reescritas para exercitar o comportamento real (as antigas procuravam nomes de função que eu havia suposto).

| # | Achado | Auditoria | Depois da Fase 1 | Depois da Fase 2 |
|---|---|---|---|---|
| 1 | Ciclo objetivo → plano → execução → verificação → experiência | CONFIRMADO | CONFIRMADO | **PARCIALMENTE_CONFIRMADO**: objetivo → plano → execução → verificação existem; falta o elo «experiência» (Fase 3) |
| 2 | Sem registro estruturado de tarefas | CONFIRMADO | CONFIRMADO | **RESOLVIDO** |
| 3 | Sem verificação independente do resultado | CONFIRMADO | CONFIRMADO | **RESOLVIDO** (ferramenta que mente termina `FALHOU`, veredito `refutado`, prova `independente`) |
| 4 | Sem registro de experiências | CONFIRMADO | CONFIRMADO | CONFIRMADO (Fase 3) |
| 5 | Sem planejamento multietapas / replanejamento | CONFIRMADO | CONFIRMADO | **PARCIALMENTE_CONFIRMADO**: planos de vários passos com dependências são executados; quem escreve o plano é o chamador, ninguém gera nem revisa (Fase 4) |
| 6 | Sem retomada de tarefas interrompidas | CONFIRMADO | CONFIRMADO | **PARCIALMENTE_CONFIRMADO**: o estado sobrevive ao reinício e o dono pode «retomar» (conferindo antes se o efeito já existe); nada retoma sozinho (Fase 6) |
| 7–11 | busca, metas, confirmação, auditoria, argumentos | RESOLVIDO na Fase 1 | | continuam RESOLVIDO |
| 12 | Documentos desatualizados | PARCIALMENTE | | PARCIALMENTE (resta o destino de `nucleo.py`) |
| 13 | Conflito `nucleo.py` × `main.py` × `simbiose.py` | PARCIALMENTE | | PARCIALMENTE (Fase 5) |

Total agora: **8 resolvidos, 4 parciais, 1 confirmado** (eram 12 confirmados e 1 parcial).

Problemas **novos** achados e corrigidos durante a fase (todos com teste):
- O roteiro G mostrou que `tarefas.json` mantinha o conteúdo de tarefas já concluídas. Corrigido: os argumentos saem do registro quando a tarefa termina.
- Os testes de privacidade antigos olhavam o disco **depois** do fim da tarefa, e o novo apagamento passou a esconder qualquer defeito de gravação: a mutação mostrou **2 defeitos plantados sobrevivendo** (guardar argumento sensível; guardar argumentos da conversa). Agora há testes que olham o disco **durante** a execução (por uma ferramenta espiã) e com a tarefa pronta ou esperando o dono; a mutação voltou a 51/51.
- Uma confirmação nascida enquanto a tarefa era cancelada podia ficar solta no corretor. Agora é derrubada, e só se for a pendência daquela tarefa (comparação por id).

## 3. Arquivos

**Novos:** `friday/tarefas.py` (829 linhas), `friday/verificacao.py` (229), `docs/TAREFAS.md`, `tests/test_broker_estruturado.py` (22 testes), `tests/test_verificacao.py` (37), `tests/test_tarefas.py` (88), `tests/test_tarefas_integracao.py` (8), `tests/test_tarefas_metas.py` (11), `reports/evidencias/cenarios/fase2/` (`cenario_tarefas.py`, `mutar.py`, `mut_verificacao.py`, `mut_tarefas.py`), `reports/evidencias/logs/fase2/`.

**Alterados:** `friday/broker.py` (64 linhas mexidas, aditivo), `friday/ferramentas.py` (+23: `marca_lembretes`, `lembretes_depois`, `marca_notas`, `notas_depois`, só leitura), `friday/cerebro.py` (as duas chamadas passam por `executar_registrado`), `friday/main.py` (`TAR.tratar` depois de `PFC.tratar`; `tarefas` no estado do painel), `friday/prefrontal.py` (lê `resumo_por_meta`; quarta via de evidência «tarefa conferida»; andamento parcial limitado a 90 %), `tests/test_prefrontal.py` (permite importar `tarefas` só para ler + teste que garante isso), `tests/auditoria_achados.py`, `CLAUDE.md`, `README.md`, `docs/ARQUITETURA.md`, `docs/PREFRONTAL.md`, duas skills (`friday-nova-ferramenta`, `friday-testar`) e os três relatórios de `reports/`.

**Não tocados:** `protocolos.py`, `acao.sh`, `termux/`, `servidor/`, `privacidade.py`, `visao.py`, `maos.py`, `nucleo.py`. `broker.py` pede confirmação para editar (regra 7 do `CLAUDE.md`): a alteração é aditiva e está descrita acima.

## 4. Decisões arquiteturais

1. **Tarefa não é um segundo caminho de execução.** Cada passo chama o corretor. O que o corretor ganhou foi *informação* (resultado estruturado e eventos), não novas permissões. Alternativa descartada: pôr o estado da tarefa dentro do corretor/auditoria — misturaria a trilha (que não guarda conteúdo) com um registro que precisa de argumentos para retomar.
2. **A resposta da ferramenta não prova o efeito.** `CONCLUIDA` só é alcançável passando por `VERIFICANDO`, e só com veredito `confirmado`. O que não dá para conferir (SMS, ligação, relé…) termina em `EXECUTADA_SEM_VERIFICACAO` e **só o dono** conclui («a tarefa N está feita»). Ferramenta nova sem verificador cai em `nao_verificavel`, nunca em `confirmado`. Não inventei evidência.
3. **Marca de antes.** «Existe um lembrete com esse texto» não prova que *esta* ação o criou; por isso a conferência só aceita o que apareceu depois da marca.
4. **Gravar antes de executar** e **nunca segurar a trava das tarefas durante uma chamada ao corretor** (o corretor avisa os observadores com a trava dele presa; duas travas se esperando seria impasse). Observadores nunca chamam o corretor.
5. **Falha do registro:** antes da chamada ao corretor, cai no caminho antigo (a conversa não quebra); depois da chamada, **nunca repete** a ação.
6. **A IA não ganhou ferramenta** para criar, planejar, executar, cancelar ou confirmar tarefas (teste varre os nomes). Meta própria e planejador ficam para a Fase 4, com os limites da missão.
7. **Meta × tarefa por id**, não por parecer com o texto (coerente com a decisão da Fase 1). O pré-córtex só lê (`resumo_por_meta`); teste de AST garante que ele não cria nem executa tarefas.
8. **Tarefas ≠ metas.** Meta é o que ela quer; tarefa é uma tentativa concreta de fazer algo. Reaproveitar as metas como tarefas foi descartado porque as metas têm ciclo próprio (candidatos, ligações do dono).
9. **Retomada não é automática ainda.** Decisão consciente: repetir uma ação depois de um reinício exige saber se ela já aconteceu; a Fase 6 usa a marca e o passo «executando» que já estão no disco. Hoje, `reabrir` reconfere o efeito pela marca antes de repetir e ação de nível 2 pede confirmação outra vez.
10. **Gancho de fim** (`GANCHOS_FIM`, chamado fora da trava, com cópia) deixado pronto para o registro de experiências da Fase 3.

## 5. Testes e resultados

Comparação com a linha de base da auditoria e com o fim da Fase 1:

| Item | Linha de base | Fim da Fase 1 | Agora |
|---|---|---|---|
| Unitários, Python 3.11 / 3.12 / 3.13 | 717 OK | 850 OK | **1017 OK** (1 pulado, o mesmo de antes) nas três — `reports/evidencias/logs/fase2/unit_py3.11.log`, `unit_py3.12.log`, `unit_py3.13.log` |
| Unitários em ambiente criado só com `requirements-test.txt` | — | 850 OK | **1017 OK** (`reports/evidencias/logs/fase2/unit_venv_limpo.log`) |
| Roteiros no Chromium (5 scripts) | 163 verificações, 0 falhas | 163 / 0 | **163 / 0** (hud 61, voz e memória 21, cérebro 38, mãos 29, pré-córtex 14; `reports/evidencias/logs/fase2/e2e_*.fase2.log`) |
| Mutação (defesas quebradas de propósito numa cópia) | — | 51/51 da Fase 1 | verificação **25/25**; tarefas + corretor + pré-córtex **51/51** (`reports/evidencias/logs/fase2/mut_verificacao.log`, `mut_tarefas.log`) |
| Testes novos no código da Fase 1 | — | — | **falham todos** (os 4 arquivos de tarefas e verificação nem importam; os 22 do corretor estruturado dão erro) — `reports/evidencias/logs/fase2/testes_novos_no_codigo_da_fase1.log` |
| Testes novos | — | +133 | **+167** (22 + 37 + 88 + 8 + 11 + 1 em `test_prefrontal`) |

**Os testes A–J da missão, no estado desta fase:**

| Teste | Situação | Onde |
|---|---|---|
| A — execução básica verificada | **passa** | `tests/test_tarefas.py`; cenário A |
| B — falso sucesso não vira `CONCLUIDA` | **passa** (tarefa `FALHOU`, veredito `refutado`; a IA recebe o aviso) | `tests/test_tarefas.py`, `tests/test_tarefas_integracao.py`; cenário B |
| C — falha + alternativa permitida com experiência registrada | **não coberto** (precisa de experiências e planejador: Fases 3–4) | — |
| D — retomada depois de interrupção | **parcial**: o estado sobrevive, `reabrir` reconfere o efeito e não repete sem prova; retomada automática é a Fase 6 | `tests/test_tarefas.py` (persistência e reabertura) |
| E — aprendizado muda a próxima estratégia | **não coberto** (Fase 3) | — |
| F — ação sensível não executa com confirmação ambígua | **passa** («sim», «pode», «isso mesmo» → 0 SMS; «confirmo» → 1 SMS, tarefa `EXECUTADA_SEM_VERIFICACAO`) | `tests/test_tarefas.py`, `tests/test_tarefas_integracao.py`; cenário F |
| G — privacidade da auditoria | **passa** (auditoria sem conteúdo, cadeia de hashes íntegra; `tarefas.json` sem conteúdo de nível 2, de dado sensível, da conversa e de tarefa terminada) | `tests/test_tarefas.py` (`G_Privacidade`); cenário G |
| H — metas relacionadas com texto diferente | **passa** («sono» × «entender como dormir bem ajuda a lembrar», nenhuma palavra em comum, ligadas por id; mesmo texto em outra meta não conta) | `tests/test_tarefas_metas.py`; cenário H |
| I — concorrência e coordenação | **parcial**: cancelamento durante a execução, confirmações trocadas e tarefas simultâneas estão testados; o coordenador é a Fase 5 | `tests/test_tarefas.py` |
| J — regressão | **passa** (tabela acima) | suíte inteira |

**Roteiro de demonstração** (`python3 reports/evidencias/cenarios/fase2/cenario_tarefas.py`, saída em `reports/evidencias/logs/fase2/cenario_tarefas.log`): A concluída e conferida; B ferramenta mente → `FALHOU`, «refutado (independente)», com o aviso que a IA recebe; F as três falas vagas não enviam nada e «confirmo» envia uma vez; G a auditoria não tem o texto e a cadeia está íntegra (`True, 8`); H meta cumprida por «tarefa conferida».

**Não executável aqui:** celular real e Termux:API (os testes usam o corretor de verdade com comandos `termux-*` falsos), microfone, internet ao vivo (um teste existente chama `api.open-meteo.com`, bloqueado pelo proxy desta sessão; o resultado não depende disso), desempenho em aparelho fraco, qualidade real de qualquer modelo de IA (os laços da nuvem e do Ollama são testados com respostas simuladas).

## 6. Limitações e riscos

- **Sem como conferir:** `enviar_sms`, `ligar`, `rele`, `lanterna`, `vibrar`, `notificar`, `preparar_whatsapp`, `localizacao`, `compartilhar_arquivo`, `esquecer_memoria`, `consolidar_memoria`, `exportar_cerebro` ficam «executada, mas não consegui conferir». Só o dono conclui. Esta é a principal fronteira da honestidade do sistema.
- **Fora do registro:** protocolos, rotinas da autonomia e atalhos de voz da memória chamam o corretor direto. Continuam protegidos pelo corretor, mas **não geram tarefa nem conferência**.
- **Retomada depois de reinício não é automática.** Uma tarefa que estava `EXECUTANDO` quando o processo caiu fica assim no disco até o dono pedir «retomar» ou cancelar. Ação de nível 2 depois do reinício vai para `PRECISA_INTERVENCAO` (os argumentos só existiam na memória do processo).
- **Conferência por texto** em `guardar_memoria` e `pedir_evolucao`: se a ferramenta gravar o texto normalizado, pode dar `refutado` por engano. O efeito prático é seguro (a tarefa pede o dono, não repete sozinha), mas pode irritar.
- **Argumentos de baixo risco ficam no disco** enquanto a tarefa pode ser retomada (`PRONTA`, `BLOQUEADA`, `FALHOU`, `PRECISA_INTERVENCAO`, `EXECUTADA_SEM_VERIFICACAO`) — o roteiro G mostra um lembrete com `texto` em `tarefas.json` numa tarefa `FALHOU`. Sai quando ela termina `CONCLUIDA`/`CANCELADA`. É local e privado (cofre), diferente da auditoria, mas não é zero.
- **Interface:** `corretor.executar()` não mudou; `executar_estruturado()` e `OBSERVADORES` são novos. Quem registra observador recebe argumentos e resultado **em memória** (nunca em disco); erros de observador são engolidos de propósito para nunca impedirem o corretor.
- **Tetos de operação** (não de conhecimento): `MAX_PASSOS` 12, `MAX_ABERTAS` 200, `MAX_FINAIS` 100 (as mais antigas saem do estado vivo e ficam no histórico; nada é apagado), `MAX_HIST` 40 por tarefa.
- A ordem em `processar()` ganhou `TAR.tratar` depois do pré-córtex: falas que começam como «minhas tarefas» ou «cancela a tarefa N» não chegam mais à IA.

## 7. Como executar e validar

```
pip install -r requirements-test.txt
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'            # 1017 testes
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_tarefas*.py'     # só tarefas (107)
python3 tests/e2e_hud.py && python3 tests/e2e_voz_memoria.py && python3 tests/e2e_cerebro.py && python3 tests/e2e_maos.py && python3 tests/e2e_prefrontal.py
python3 tests/auditoria_achados.py                       # reclassifica os 13 achados no código atual
python3 reports/evidencias/cenarios/fase2/cenario_tarefas.py                                            # roteiro A, B, F, G, H com o corretor de verdade
python3 reports/evidencias/cenarios/fase2/mutar.py reports/evidencias/cenarios/fase2/mut_tarefas.py .      # mutação (idem mut_verificacao.py)
```

## 8. Documentação atualizada

`docs/TAREFAS.md` (novo), `docs/ARQUITETURA.md`, `docs/PREFRONTAL.md`, `README.md`, `CLAUDE.md` (regra 1, mapa do código, ordem de `processar()`), as skills `friday-nova-ferramenta` (ferramenta nova precisa de verificador ou de motivo para não ter) e `friday-testar`, e os três relatórios em `reports/` (seção «Atualização — Fase 2»).

## 9. Próxima fase (objetiva)

**Fases 3 e 4 — experiência e planejamento** (`friday/experiencias.py`, `friday/planejador.py`):

1. **Registro de experiências** ligado a `tarefas.GANCHOS_FIM`: objetivo/contexto, hipótese, estratégia, ações, esperado × observado, evidência, diferença, causas prováveis **com confiança**, o que foi aprendido, alternativas e condições de reuso — separando fato, inferência, hipótese e desconhecido. Uma tentativa nunca vira regra universal. Sem punição artificial; as travas de segurança não mudam; nada de dizer que pesos de modelo foram treinados.
2. **Consulta de experiências** que muda a estratégia seguinte com justificativa verificável (teste **E**).
3. **Planejador/replanejador mínimo** sobre `tarefas.py`: gerar plano de vários passos, observar o resultado conferido, trocar de estratégia dentro do que é permitido (teste **C**). O corretor continua decidindo; a IA não ganha ferramenta de tarefa.
4. **Metas próprias** só com os limites da missão: coerentes com as metas do dono, rastreáveis, limitadas, pausáveis/canceláveis, sem alterar as próprias regras de segurança nem agir fora sem consentimento; propor ≠ planejar ≠ estar autorizada a executar.

Depois: Fase 5 (coordenador e decisão sobre `nucleo.py`, com evidências antes de qualquer mudança destrutiva) e Fase 6 (retomada automática).
