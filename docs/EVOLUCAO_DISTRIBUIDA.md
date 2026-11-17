# Evolução distribuída segura da FRIDAY

## O que esta versão implementa
- **Pares de rede:** verifica apenas URLs que você já colocou em `FRIDAY_PEERS`. Não faz varredura de sub-redes, não tenta entrar em dispositivos e não transfere executáveis/código para eles.
- **Catálogo de APIs:** lê especificações OpenAPI 3.x em JSON local, extrai servidores/endpoints/metadados e grava um catálogo descritivo. Não executa código vindo de uma especificação. A importação de URLs remotas e a geração automática de clientes executáveis ficam desativadas por segurança.
- **Promoção local automática opcional:** `friday.evolucao_auto` usa a fila local, a allowlist existente, testes fixos, staging, backup e rollback implementados em `friday.evolucao`. Está desativada por padrão.

## Uso

### Verificar pares previamente autorizados
No shell do Termux/Linux, configure apenas dispositivos seus que já tenham concordado em expor `/health`:

```bash
export FRIDAY_PEERS='["http://192.168.1.22:8765","http://192.168.1.23:8765"]'
python -c "from friday.rede_autorizada import descobrir; import json; print(json.dumps(descobrir(), indent=2))"
```

O módulo não procura IPs vizinhos automaticamente. Confirme a propriedade/autorização dos equipamentos antes de adicioná-los.

### Catalogar uma API
Salve a especificação OpenAPI JSON em `openapi.json` e rode:

```bash
python -c "from friday.catalogo_apis import salvar_catalogo; print(salvar_catalogo('openapi.json', 'dados/catalogo_api.json'))"
```

O catálogo descreve endpoints; não replica serviços proprietários, não contorna autenticação nem copia código-fonte. Integrações devem respeitar licenças, termos e credenciais do provedor.

### Promoção local após testes
Primeiro, execute a suíte manualmente. Só depois de revisar os alvos e testes, ative explicitamente:

```bash
export FRIDAY_AUTO_PROMOTE=yes
python -m friday.evolucao_auto
```

A rotina usa um conjunto de testes fixo e não aceita comandos de teste enviados por API ou por candidatos. A promoção continua restrita à allowlist e ao mecanismo de backup/rollback existente. Desative com `unset FRIDAY_AUTO_PROMOTE`.

## Limites deliberados
Esta implementação **não faz autorreplicação autônoma para dispositivos descobertos**. Descobrir máquinas e instalar/copiar código nelas sem uma autorização específica por dispositivo se aproxima de propagação automática. Para distribuição em produção, use um agente de implantação instalado voluntariamente em cada dispositivo, identidade mútua (TLS/certificado ou chave por dispositivo), lista de alvos administrada pelo proprietário, pacote assinado, modo de simulação e opção de rollback. Não coloque chaves em código ou no catálogo.

Testes de candidato ainda executam código com as permissões do processo de teste; staging não é sandbox de kernel. Use usuário/contêiner isolado para candidatos não confiáveis.
