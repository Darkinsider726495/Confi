# Sincronia do cofre com o PC (direto pelo Wi-Fi)

Ninguém no meio: o celular e o PC conversam direto na sua rede. Só o dono liga: **«liga a sincronização com o PC»**.

## Passo a passo
1. Na FRIDAY: «liga a sincronização com o PC».
2. No Termux: `python scripts/parear_pc.py` → mostra o comando (com o IP do celular e a chave).
3. Copie `scripts/sincronizar_pc.py` para o PC e rode o comando mostrado (Python 3, sem instalar nada).
4. Para manter sincronizando: `python sincronizar_pc.py --pasta "Cofre FRIDAY" --sempre`.
5. No Obsidian do PC: «Abrir pasta como cofre» → a pasta escolhida.

## Regras
| Situação | O que acontece |
|---|---|
| mudou só de um lado | copia para o outro |
| mudou dos dois lados | as duas versões ficam (uma com «(conflito PC …)» no nome) |
| saiu de um lado | do outro, vai para o arquivo morto (`FRIDAY/Arquivo/sincronia/` no celular, `.sincronia-arquivo/` no PC). **Nada é apagado.** |

## Segurança
- Servidor separado do painel, na porta 8090 (`SYNC_PORTA`); recusa tudo com a sincronia desligada.
- Só IPs da rede local; só com a chave de pareamento (32 bytes, `friday/.sync_chave`, chmod 600, fora do git); 5 erros = 1 minuto travado.
- Caminhos validados (sem `..`, absoluto, barra invertida, controle ou link simbólico); arquivo de até 5 MB.
- `Privado/` fica de fora (`SYNC_PRIVADO=1` inclui). O `.env` não fica no cofre.
- Não há ferramenta da IA para ligar a sincronia nem para ler a chave.
- A conexão no Wi-Fi não é criptografada (HTTP): use só em rede de confiança (a sua casa), não em Wi-Fi público.

## O que não dá para verificar aqui
Rede de verdade entre o seu celular e o seu PC (roteador que isola aparelhos, firewall do Windows pedindo permissão).

## MCP: o Claude do PC consulta a FRIDAY
`scripts/friday_mcp.py` é um servidor MCP (stdio, só biblioteca padrão) que roda **no PC** e usa a mesma ponte (mesma chave, mesma regra: só com a sincronia ligada, só na rede local).

- **Claude Code:** `claude mcp add friday -- python /caminho/friday_mcp.py --pasta "/caminho/Cofre FRIDAY"`
- **Claude Desktop:** em `claude_desktop_config.json`:
  `"mcpServers": {"friday": {"command": "python", "args": ["C:/caminho/friday_mcp.py", "--pasta", "C:/caminho/Cofre FRIDAY"]}}`

Ferramentas, **todas só de leitura**: `friday_estado`, `friday_buscar_memoria`, `friday_ler_nota`, `friday_pedidos`.
O Claude não manda nela, não executa nada no celular e não escreve no cofre. `Privado/` e notas privadas nunca saem.
O que ele lê vai para o modelo do Claude (nuvem da Anthropic): é a sua memória saindo do aparelho, por escolha sua.
