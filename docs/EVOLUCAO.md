# Evolução local controlada da FRIDAY (sem API)

A implementação é local: **não depende de OpenAI API, Anthropic/Claude ou qualquer chave externa**. `friday/gerador_local.py` coloca candidatos em quarentena. `friday/evolucao.py` valida o alvo, executa a suíte atual, cria uma cópia de staging, testa nela, registra um backup e só então troca o módulo ativo. A suíte é executada de novo depois da troca; se falhar, os bytes originais são restaurados.

O gerador local não finge criar algoritmos gerais sem um modelo: pode receber um arquivo `.py` escrito localmente ou gerar um candidato por substituição literal que encontra exatamente uma ocorrência. A aprovação depende dos testes; passar na suíte não prova ausência de bugs nem substitui revisão.

## Regras obrigatórias

- A allowlist atual é `memoria.py`, `neuronios.py`, `curiosidade.py`, `planejador.py`, `conversa.py`, `objetivos.py`, `tarefas.py`, `voz.py` e `visao.py`.
- O próprio promotor, MAE, laboratório, broker/corretor, catálogo, autonomia, privacidade, verificação, coordenador, inicialização, estado e ferramentas não podem ser alvo.
- Caminhos absolutos, `..`, subpastas inesperadas e links simbólicos como alvo são recusados.
- A sintaxe é analisada antes de testar; a política estática compara capacidades sensíveis óbvias adicionadas pelo candidato.
- A versão atual tem de passar. O candidato é testado em staging antes de substituir o arquivo ativo. Após a promoção, os testes rodam de novo; se falharem, há rollback.
- Cada versão aceita gera um backup `original.py.bak`, manifesto SHA-256 e permissões locais restritivas. O mecanismo não tem comando de exclusão de backups ou de histórico.
- Uma experiência do MAE é registrada no diário de engenharia e, quando a memória está ativa, na memória episódica. **Resultado de laboratório não dá permissão para promover código.**

## Usar no Termux/PC

Execute a partir da raiz `friday-pi/`.

```bash
# Ver os módulos elegíveis
python scripts/evoluir.py alvos

# 1. Crie uma cópia e edite o novo código com seu editor local.
cp friday/memoria.py "$HOME/memoria-candidata.py"
# Edite $HOME/memoria-candidata.py; ainda não altera o módulo ativo.

# 2. Coloque na fila local de candidatos (quarentena)
python scripts/evoluir.py preparar friday/memoria.py "$HOME/memoria-candidata.py" --descricao "ajuste de memória"

# 3. Liste a fila e copie o ID cand-... retornado
python scripts/evoluir.py fila

# 4. Promova somente depois de testes; por padrão roda a suíte em tests/
python scripts/evoluir.py promover cand-ID-RETORNADO --suite pytest

# Veja auditoria/resultado
python scripts/evoluir.py historico
```

### Criar um módulo novo, sem ligar automaticamente ao núcleo

Módulos novos só podem ser colocados em `friday/generated/`. Crie primeiro um arquivo de teste para o módulo, seguindo o modelo real `tests/test_exemplo_local.py`; o teste-base garante que a suíte execute durante o baseline, enquanto o teste do módulo fica pulado até o arquivo existir:

```python
# tests/test_exemplo_local.py
import pytest

def test_harness_disponivel():
    assert True

def test_funcao_gerada():
    pytest.importorskip("friday.generated.exemplo_local")
    from friday.generated.exemplo_local import calcular
    assert calcular(2) == 4
```

Depois crie um arquivo candidato e enfileire-o. O arquivo de teste `tests/test_exemplo_local.py` do exemplo já acompanha este projeto:

```bash
cat > "$HOME/exemplo_local.py" <<'PY'
def calcular(n):
    return n * 2
PY
python scripts/evoluir.py preparar friday/generated/exemplo_local.py "$HOME/exemplo_local.py" --descricao "novo cálculo local"
python scripts/evoluir.py fila
# copie o ID retornado e promova:
python scripts/evoluir.py promover cand-ID-RETORNADO --suite pytest
```

A pasta `generated/` não é carregada automaticamente pelo núcleo: a integração do novo módulo precisa ser planejada e revisada separadamente. O timeout padrão por comando é 120 segundos; pode ser aumentado com `--timeout 300` (limite máximo: 600).

Para uma substituição pequena e exata, a fila pode ser criada sem copiar arquivo:

```bash
python scripts/evoluir.py substituir friday/memoria.py \
  'TRECHO ORIGINAL EXATO' 'TRECHO NOVO' --descricao "hipótese local"
```

A substituição só é gerada se o trecho original aparece **exatamente uma vez**. Revise o código antes de promover. O candidato não entra na produção apenas por estar na fila.

Se o pytest não estiver instalado, instale as dependências de teste (`pip install -r requirements-test.txt`) ou use `--suite unittest`.

## Logs e backups

- Fila de candidatos: `.evolucao/candidatos/`
- Backups por versão + manifesto SHA-256: `.evolucao/backups/`
- Diário append-only do mecanismo: `.evolucao/diario.jsonl`
- Experiências do MAE também alimentam `experiencias.py` quando o cofre está ativo; não são recompensa/punição e não alteram permissões.

Não edite nem remova manualmente esses arquivos durante uma promoção. Para restaurar manualmente, interrompa a FRIDAY e copie `original.py.bak` da versão desejada para o caminho do módulo correspondente, depois execute os testes.

## Limites de segurança importantes

O staging é uma **cópia de trabalho, não um sandbox de kernel**. O código candidato é importado/executado pelos testes e pode ter os mesmos acessos ao sistema/rede que o usuário atual. A checagem estática reduz algumas alterações de risco óbvias, mas não consegue provar que um programa é seguro. Portanto, não promova nem teste código não confiável neste processo sem isolamento externo. Em Linux/servidor, use um usuário/contêiner/VM separado com arquivos e rede limitados; no Termux, não presuma que namespaces, Docker ou `chattr` estejam disponíveis.

As permissões `0400`/`0500`, o manifesto e a ausência de API de apagamento protegem contra acidentes e deixam evidências verificáveis. **Não são imutabilidade absoluta contra o mesmo usuário, root ou código malicioso com acesso ao sistema.**

## Testes

```bash
python -m unittest discover -s tests -p 'test_evolucao.py' -v
python -m unittest discover -s tests -p 'test_gerador_local.py' -v
python -m unittest discover -s tests -p 'test_mae.py' -v
python -m unittest discover -s tests -p 'test_experiencias.py' -v
```
