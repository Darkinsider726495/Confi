# Entrega da Fase 1 — correções fundamentais

- **Data:** 24/10/2026. **Ramo:** `evolucao-fase1` (a partir da tag `linha-de-base-auditoria`, commit `6030a56`). **Backup fora do repositório:** `/home/claude/backups/friday-pi-pre-evolucao-20261024/` (+ `.tar.gz` e `.sha256`).
- **Escopo (missão de 24/10, Fase 1):** busca (3.1), progresso de metas (3.2), confirmação (3.3), privacidade da auditoria (3.4), validação de argumentos (3.5), documentação (3.6).
- **Commits:** `e3adcdf` (3.1) · `4c063fa` (3.3) · `2932b40` (3.4 e 3.5) · `f56cc32` (3.2) · `5e44c5a` (3.6).

## 1. Resumo das alterações

| Item | O que mudou |
|---|---|
| 3.1 Busca | A busca na memória deixou de cortar em 3.000 arquivos. Sem teto por padrão; se o dono pôr `CEREBRO_MAX_ARQUIVOS`, ficam as **mais recentes**. Termos de cada nota são calculados uma vez e guardados em RAM (`CEREBRO_CACHE_NOTAS`). Cofre externo lido por inteiro: 3.000 mais recentes, com aviso ao cortar |
| 3.2 Progresso de metas | Meta de aprender deixou de depender do texto idêntico. Contam: mesmo assunto (chave sem caixa/acento/ordem/palavras de ligação), assunto **ligado pelo dono** (`conte X na meta Y`) e estudo feito **em nome do id** da meta. Estudo de assunto *parecido* só vira **candidato** (sugestão), nunca conclui |
| 3.3 Confirmação | Nível 2 exige consentimento explícito («confirmo», «confirmado», «autorizo») logo após o anúncio ou junto do nome da ação. «Sim», «pode», «isso» nunca executam. O corretor (não a IA) diz o que será executado. O botão leva o id da pendência |
| 3.4 Auditoria | A trilha guarda o fato (tamanho, código, números), não o conteúdo; camada final de redação de cartão, CPF/CNPJ, telefone, e-mail, chaves, tokens e links |
| 3.5 Argumentos | Fora da faixa → «Pedido inválido» com a faixa e o valor recebido; ajuste só onde declarado (`ao_exceder="limitar"`) e sempre avisado e registrado |
| 3.6 Documentação | `docs/PREFRONTAL.md` e `docs/NUCLEO.md` criados; ARQUITETURA, CEREBRO, ANDROID, README, CLAUDE.md e 2 skills corrigidos; testes passam a verificar links e caminhos citados; `requirements-test.txt` |

## 2. Problemas confirmados e corrigidos

Validação no código atual (`tests/auditoria_achados.py`; "antes" em `reports/evidencias/logs/fase1/` e na pasta temporária da sessão, "depois" em `achados_depois_1.json`):

| # | Achado | Antes | Depois da Fase 1 |
|---|---|---|---|
| 7 | Busca limitada a ~3.000 notas | CONFIRMADO (nota na posição 3.150 de 3.200 não achada) | **RESOLVIDO** |
| 8 | Progresso depende de tema idêntico | CONFIRMADO (estudo de «criptografia explicada», meta «criptografia» em 0 %) | **RESOLVIDO** com decisão de projeto (ver §4) |
| 9 | Confirmações ambíguas | CONFIRMADO («pode», «isso», «sim» executavam) | **RESOLVIDO** |
| 10 | Trechos de resultado em claro na auditoria | CONFIRMADO | **RESOLVIDO** |
| 11 | Normalização silenciosa de argumentos | CONFIRMADO (`criar_lembrete(-5)` → «daqui a 0,1 minutos») | **RESOLVIDO** |
| 12 | Documentos desatualizados | CONFIRMADO (4 pendências) | **PARCIALMENTE_CONFIRMADO**: resta o destino de `nucleo.py` (Fase 5) |
| 13 | Conflito `nucleo.py` × `main.py` × `simbiose.py` | PARCIALMENTE_CONFIRMADO | continua; documentado em `docs/NUCLEO.md`; decisão na Fase 5 |
| 1–6 | Ciclo objetivo→plano→execução→verificação→experiência, registro de tarefas, verificação independente, registro de experiências, planejamento multietapas, retomada | CONFIRMADO | continuam CONFIRMADOS (Fases 2–6) |

Efeitos colaterais encontrados e tratados no caminho: a busca descartava primeiro as conversas **mais novas** (a ordem alfabética cortava o fim); `curiosidade._nomes_de_pessoas` só olhava 3.000 notas de pessoas (agora o cofre inteiro); temas de estudo ligados a metas eram os primeiros a ser despejados quando a lista enchia (agora são os últimos).

## 3. Arquivos

**Código (`friday/`)** — criado: `privacidade.py`. Modificados: `broker.py`, `catalogo.py`, `main.py`, `memoria.py`, `curiosidade.py`, `prefrontal.py`, `hud.html`, `acao.sh`.
**Configuração:** `.env.example` (`CEREBRO_MAX_ARQUIVOS`, `CEREBRO_CACHE_NOTAS`), `requirements-test.txt` (novo).
**Documentação:** novos `docs/PREFRONTAL.md`, `docs/NUCLEO.md`; alterados `docs/ARQUITETURA.md`, `docs/CEREBRO.md`, `docs/ANDROID.md`, `README.md`, `CLAUDE.md`, `.claude/skills/friday-nova-ferramenta/SKILL.md`, `.claude/skills/friday-testar/SKILL.md`.
**Testes** — novos: `test_busca_volume.py` (15), `test_confirmacao.py` (35), `test_auditoria_privada.py`, `test_argumentos.py`, `test_prefrontal_progresso.py` (35), `bench_busca.py`, `auditoria_achados.py`. Alterados: `test_docs.py` (+3 de links), `test_http.py` e `test_core.py`.
**Testes preexistentes que mudei, e por quê (nenhum enfraquecido):**
- `test_core.py::test_nivel2…` esperava que «Confirmo!» logo depois de «bom dia» executasse. Pela regra nova, isso exige a ação no texto; o teste agora verifica que **não** executa, que a frase com a ação executa, e outro teste novo cobre o «Confirmo» imediato.
- `test_http.py`: `/confirmar_voz` passa a receber o `id` da pendência (era `{}`). Dois testes novos cobrem ausência e id de outra pendência.
Detalhe por commit: `git diff --stat linha-de-base-auditoria..HEAD` (42 arquivos, +2.717/−139).

## 4. Decisões arquiteturais

1. **Parecer relacionado não conclui meta (3.2).** O plano da auditoria (§1.4) pedia que o estudo de «criptografia explicada» levasse a meta «criptografia» a > 0. A missão posterior é mais específica («não concluir um objetivo porque uma mensagem parece relacionada»; semelhança só com critérios verificáveis). Escolhi: relação **explícita** (mesmo assunto normalizado, ligação do dono, id da meta) conta; semelhança de palavras (Jaccard ≥ 0,34) só gera **candidato** que o dono confirma com uma frase. Alternativa descartada: progresso parcial por semelhança, que faria o painel mostrar avanço não verificado. Se o dono preferir menos atrito, o caminho é a conversa perguntar sozinha «conta para a meta?» (não implementado).
2. **Auditoria: código + tamanho, sem hash do resultado (3.4).** O plano falava em «hash e tamanho». Um hash de resposta curta («ligado») é trivial de reverter por dicionário; o código (`ok`/`Erro`/`faixa:x`) dá a mesma utilidade sem vazar.
3. **Uma pendência por vez, com id (3.3).** Mantive o `PEND` único e em memória (45 s/120 s) e acrescentei id por pendência em vez de criar fila: menor mudança que fecha a troca de ação entre o anúncio e o toque.
4. **Recusar por padrão, ajustar só o declarado (3.5).** Compatível com o princípio «não normalizar em silêncio»; o ajuste ficou só em leituras sem efeito colateral.
5. **Busca continua léxica (3.1).** Sem embeddings: a infraestrutura não existe aqui, e a missão pede semelhança semântica só com infraestrutura adequada.
6. **`nucleo.py` não foi tocado.** Está órfão e sem testes; mexer exige a decisão da Fase 5 com evidência.

## 5. Testes e resultados reais

| Verificação | Linha de base | Agora |
|---|---|---|
| Unitários, Python 3.13 | 717 OK, 1 pulado | **850 OK, 1 pulado** |
| Unitários, Python 3.11 / 3.12 | OK | **850 OK / 850 OK** (`logs/fase1/unit_py3.11.log`, `unit_py3.12.log`) |
| Unitários num ambiente criado só com `requirements-test.txt` | não existia | **850 OK** |
| Roteiros no Chromium (5 scripts) | 163 verificações, 0 falhas | **163 verificações, 0 falhas** (`logs/fase1/e2e_*.fase1.log`) |
| Mutação das defesas novas (quebra de propósito numa cópia) | — | confirmação **11/11**, auditoria + argumentos **23/23**, progresso de metas **17/17** (um mutante equivalente descartado: ordem de iteração de `set`) |
| Novos testes falham no código antigo? | — | **Sim, os 5 arquivos novos** (rodados contra a tag `linha-de-base-auditoria`: busca 8 falhas + 1 erro; confirmação não importa — `registrar(rotulo=)` não existia; auditoria idem; argumentos 24 falhas + 4 erros; progresso de metas 2 falhas + 47 erros) — `logs/fase1/testes_novos_no_codigo_antigo.log` |
| Busca — antes × depois (`perf_busca_ANTES/DEPOIS.log`) | 5 mil notas: frio 0,91 s, quente 0,95 s, contexto 2,7 s, **mas não achava a última nota**; 20 mil: 1,1 s / 1,1 s / 3,3 s, também sem achar | 5 mil: frio 1,6 s, quente **0,16 s**, contexto **0,35 s**, acha; 20 mil: frio 6,7 s, quente 1,1 s, contexto 1,7 s, acha. O primeiro uso por processo ficou mais lento porque agora lê **todas** as notas |

**Não executável aqui:** celular real e Termux:API (botão da notificação e `acao.sh` só com comandos simulados), microfone/voz reais, internet ao vivo (um teste existente chama `api.open-meteo.com` e é bloqueado pelo proxy desta sessão; o resultado do teste não depende disso), desempenho em celular fraco.

## 6. Limitações e riscos

- **Interface mudou:** `POST /confirmar_voz` agora exige `{"id": …}`. Chamadores no repositório (HUD, `acao.sh`, notificação) foram atualizados; scripts externos que mandem `{}` recebem «A ação pendente mudou». O botão permanente *Confirmo* da notificação do Android foi substituído por um botão por pendência — **não verificado num celular real**.
- «Confirmo» sozinho só vale logo após o anúncio; depois de outra conversa a FRIDAY pede a frase com a ação (mais um passo, de propósito).
- Linhas **antigas** de `auditoria.jsonl` continuam em claro (a cadeia de hashes impede editar); para começar limpo, o dono move o arquivo. A redação não pega endereço/nome escrito por extenso; o rótulo «chave» mascara demais.
- RAM da busca cresce com o número de notas (sem teto padrão); em celular fraco, usar `CEREBRO_CACHE_NOTAS`/`CEREBRO_MAX_ARQUIVOS`. Cofre externo continua em 3.000 mais recentes.
- Candidatos de meta dependem do dono confirmar; nada pergunta sozinho. Semelhança é contagem de palavras, não significado.
- `nucleo.py` segue órfão. `voz.py` com `shell=True`, tags `latest` do Docker, pré-córtex fora de `vitais` e cobertura de `autonomia.py` ficaram para depois (itens 1.6, 1.9, 1.10 do plano).

## 7. Como executar e validar

```
pip install -r requirements-test.txt
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py'     # 850 testes
python3 tests/e2e_hud.py && python3 tests/e2e_voz_memoria.py && python3 tests/e2e_cerebro.py && python3 tests/e2e_maos.py && python3 tests/e2e_prefrontal.py
python3 tests/auditoria_achados.py            # reclassifica os 13 achados no código atual
python3 tests/bench_busca.py                  # desempenho da busca por tamanho de cofre
python3 reports/evidencias/cenarios/fase1/mutar_fase1.py reports/evidencias/cenarios/fase1/mut_progresso.py .    # mutação (idem mut_confirmacao.py, mut_audit_args.py)
```

## 8. Documentação atualizada

`docs/PREFRONTAL.md` (novo), `docs/NUCLEO.md` (novo), `docs/ARQUITETURA.md` (confirmação, auditoria, validação, módulos fora do fluxo), `docs/CEREBRO.md` (busca, comandos de meta, variáveis, contagem de testes), `docs/ANDROID.md` (botões), `README.md`, `CLAUDE.md` (ordem de `processar()`, mapa, regras), skills `friday-nova-ferramenta` e `friday-testar`, e os três relatórios em `reports/` (seção «Atualização — Fase 1»).

## 9. Próxima fase (objetiva)

**Fase 2 — núcleo mínimo de tarefas e verificação** (`friday/tarefas.py`): registro persistente com id, objetivo, restrições, plano/passos, estado (CRIADA→PLANEJANDO→PRONTA→EXECUTANDO→VERIFICANDO→CONCLUÍDA, mais FALHOU/BLOQUEADA/CANCELADA/PRECISA_INTERVENÇÃO), ação executada, evidência, resultado da verificação, tentativas, dependências, próxima ação, histórico de mudanças; verificadores por tipo de tarefa para que «a ferramenta disse que fez» ≠ «o objetivo foi atingido»; ligação por id com as metas do pré-córtex; testes A, B, F, G e H.
