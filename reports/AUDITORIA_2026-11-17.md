# Auditoria — FRIDAY fase 3 (17/11/2026)

**Base auditada:** commit `edfbb1b` (código da fase 3 enviado pelo dono) + pastas `.claude/` e `reports/`.
**Resultado:** branch `refino-fase3`, juntada à `main`.
**Ambiente da auditoria:** Linux, Python 3.13. **Nada foi testado no celular/Termux** (ver seção 6).

## 1. Resumo

| | Antes | Depois |
|---|---:|---:|
| Testes na suíte completa (unittest) | 1461 | 1469 |
| Falhas + erros | 13 | **1** (aceita pelo dono, ver 4.1) |
| Testes estilo pytest (evolução, API, ponte IA) | não rodavam | 27 aprovados, 1 pulado |
| Scripts `.sh` executáveis | 0 de 11 | 11 de 11 |

Os 90 testes focados citados no relatório da fase 3 foram confirmados. O `test_conversa.py`, que tinha estourado o tempo no relatório, roda em ~1,3 s (68 testes, OK). A suíte inteira leva ~95 s.

## 2. Achados corrigidos

| # | Gravidade | Onde | Problema | Correção |
|---|---|---|---|---|
| 1 | Alta | `pre_cortex/memoria_coletiva.py` | **Corrida:** o gravador de fundo e um `flush()` explícito escreviam no mesmo `.tmp` ao mesmo tempo; um truncava o arquivo enquanto o outro o colocava no lugar → índice corrompido ou falha falsa. | Trava `_gravando` serializa as gravações. Teste com 4 threads. |
| 2 | Alta | `termux/*.sh`, `servidor/*.sh`, `install.sh`, `friday/acao.sh`, hook | O zip feito no Windows tirou o `+x` de **todos** os scripts. `./termux/parar.sh` — a parada do dono — daria "permissão negada". | `+x` restaurado no git (11 scripts + hook). |
| 3 | Média | `memoria_coletiva.py` | Regra «nada é apagado»: `os.unlink` do `.tmp` em falha de gravação. | O `.tmp` fica e é sobrescrito na próxima gravação (como `armazem.py`); erro vai para `ultimo_erro`. |
| 4 | Média | `evolucao.py` | Regra «nada é apagado»: 3 `unlink` (`.tmp` de escrita falha, módulo novo no rollback). | `_arquivar()` move para `.evolucao/arquivo/` (recuperável). |
| 5 | Média | `api_evolutiva.py` | Gravava o código recebido em arquivo temporário só para relê-lo e apagá-lo. | `gerador_local.preparar_texto()`: o texto vai direto para a fila. |
| 6 | Média | `hub.py` + `neuronio.py` | **Replay duplicava contexto:** eventos não tinham identidade; replay repetido (falso "reinício") ou interrompido e refeito gravava o mesmo evento duas vezes no neurônio. | Eventos levam o `seq` (só o número de ordem); o neurônio ignora `seq` já visto (últimos 256). |
| 7 | Média | `memoria_coletiva.py` | **Crescimento sem fim:** `ultimos`/`ultimo_neuronio` guardavam 1 entrada por objetivo para sempre, no JSON do celular. | Limite dos 2000 objetivos mais recentes (`max_objetivos`). Contagens/transições/conexões não são cortadas. Ordem de recência preservada no JSON (tirado `sort_keys`). |
| 8 | Baixa | `hub.py` | Pool de eventos criado com `hasattr` sem trava: dois eventos simultâneos podiam criar dois pools. | Criação protegida por `_TRAVA_POOL`. |
| 9 | Baixa | `voz.py` | `subprocess.run(..., shell=True)` com o caminho da voz (`PIPER_VOZ`) dentro do comando. A fala vai por stdin (sem injeção pela voz), mas um caminho com aspas quebrava o comando. | `piper \| aplay` com dois `Popen`, sem shell. |
| 10 | Baixa | docs | O relatório e `docs/MEMORIA_COLETIVA_E_REPLAY.md` diziam "8 eventos **por neurônio**"; o código manda os 8 mais recentes **no total**. | Docs e docstring corrigidos. |

## 3. Mudança de comportamento pedida pelo dono

**Pré-córtex assimila a atenção do núcleo e guarda registro de atividades.**
- `main.py`: `NC.assinar(ao_entrar=PFC.assimilar)`. Cada sinal que o núcleo nota chega ao pré-córtex.
- `prefrontal.assimilar()` grava em `.cerebro/atividades.jsonl` **só rótulos** (`t`, `origem`, `tipo`, `saliencia`, `confiavel`) — nunca o texto nem o resumo. Só acrescenta.
- «no que você está focada?», «o que chamou sua atenção?», «onde está a sua atenção?» agora são do pré-córtex: memória de trabalho + o que o núcleo notou por último + atividades de hoje. O núcleo segue respondendo a arquitetura.
- O pré-córtex **não importa** o núcleo (o teste de arquitetura «só lê o resto» continua valendo sem ser afrouxado).

## 4. Pendências

### 4.1 Aceita pelo dono
- `test_nunca_apaga` falha porque a regex conta os nomes `"os.remove"`, `"os.unlink"` etc. que aparecem **como texto** na lista de chamadas que `evolucao.py` **bloqueia** em candidatos. Não há chamada real de apagar. O dono escolheu manter o teste como está.

### 4.2 Abertas (baixa gravidade, não corrigidas)
- `memoria_coletiva`: acima de 10 000 transições distintas, a menos frequente sai do contador (`del`). É estatística, mas encosta na regra «nada é apagado»; decidir se vira arquivo ou se o teto sai.
- `hub`: se o índice não existir, a reconstrução usa só os últimos `eventos_em_memoria` do log, não o histórico inteiro.
- `.gitignore` ignora `*.log` e `*.jsonl`: os 106 logs de evidência de `reports/` não entraram no git (só estão no zip da Release).

### 4.3 Dependem do dono
- **`.env` dentro do zip da Release** (repositório privado). Se tiver chaves reais, considerar gerar chaves novas; apagar a Release antes de dar acesso a alguém.
- **`android/` e `voz/`** não estão no repositório (só no zip da Release).
- **Validar no Termux** (seção 6).

## 5. Verificação de segurança feita
- Varredura de segredos em todo o código e em `reports/`: só dados de teste (`sk-ant-abcd…`, `pw@example.com`, `chave-falsa-de-teste`).
- `.claude/settings.json`: nega leitura de `.env`, `auditoria.jsonl`, `*.key`, `Privado/`; pede confirmação para editar `broker.py`, `protocolos.py`, `acao.sh`, `termux/`, `servidor/`.
- Padrões de risco (`shell=True`, `eval`, `exec`, `pickle`, `verify=False`, bind em `0.0.0.0`): só o `shell=True` do item 9; `api_evolutiva` já bloqueia bind externo sem `FRIDAY_API_ALLOW_REMOTE=yes`.
- Nenhum arquivo com fim de linha Windows (CRLF).
- Cada correção de defesa foi **quebrada de propósito** para confirmar que o teste novo falha.

## 6. O que não foi verificado
Celular e Termux reais, Termux:API, microfone, `piper`/`aplay` reais (o item 9 foi testado com programas falsos no lugar deles), modo distribuído com processos reais reiniciando no Android, internet ao vivo.

**Para validar no Termux**, na pasta do projeto:
```bash
git pull
python -m compileall -q friday
python -m unittest discover -s tests -p 'test_*.py'
```
Espere 1 falha (`test_nunca_apaga`, item 4.1). Qualquer outra falha é novidade: mande o print.

## 7. Commits (branch `refino-fase3`)
1. `memoria_coletiva`: não apaga o `.tmp` e serializa as gravações
2. evolução: arquiva em vez de apagar
3. scripts: restaura permissão de execução dos 11 `.sh`
4. pré-córtex assimila a atenção do núcleo e guarda registro de atividades
5. adiciona `.claude/` e `reports/`
6. auditoria: replay sem duplicar, memória coletiva sem crescer sem fim, voz sem shell
7. este relatório + correção da doc do replay
