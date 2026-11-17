# Evidências da auditoria (24/10/2026)

Material bruto que sustenta os relatórios em `reports/`. Não faz parte do programa: é só registro e instrumento de teste. Nada aqui é importado por `friday/` nem pelos testes do projeto.

## `logs/`

| Arquivo | O que registra |
|---|---|
| `A_boot.log` | Processo real: boot, painel, estado, threads, SIGTERM (token de painel de teste redigido) |
| `B_proc1.log`, `B_proc2.log` | Gravação e reinício (dois processos sobre o mesmo cofre) |
| `C_retomada.log`, `C2_autoestudo.log`, `C3_dbg.log` | Meta persistida, estudo autônomo após reinício e diagnóstico dos portões do estudo |
| `DH_estudo.log` | Curiosidade com internet falsa (duas fontes que se contradizem, uma com ordem embutida), contaminação do corretor, meta → estudo → progresso |
| `E_sinapse.log`, `E_sinapse2.log` | Sinapse hebbiana: peso, promoção a `[[link]]`, efeito na busca |
| `EGI.log` | Calibração (E1), falhas de internet (E2), ferramenta que falha e que mente (E3/G), segurança (I): corretor, SSRF, painel, segredos |
| `F_autonomia.log`, `F3_repete.log` | Rotinas por hábito com relógio injetado; não repetição no mesmo dia |
| `H_llm.log` | Caminho com modelo roteirizado (nunca chama IA real) |
| `ferr.log`, `vig.log` | Catálogo de ferramentas por nível; vigilância (erro → serotonina) |
| `perf.log`, `teto_busca.log` | Tempo de busca com 500/2.000/5.000 notas; teto silencioso de 3.000 arquivos |
| `unit_py3.11.log`, `unit_py3.12.log`, `unit_py3.13_cobertura.log`, `unit_py3.13_final_com_reports.log`, `cobertura.txt` | Suíte unitária (717 testes; 1 ignorado por falta de `faster-whisper`), cobertura, e a repetição final já com `reports/` presente |
| `e2e/` | Saída dos cinco scripts de ponta a ponta no Chromium (163 verificações) e `resumo.txt` com os códigos de saída; as capturas de tela ficaram fora da pasta |
| `mutacao_1.log`, `mutacao_2.log` | Teste de mutação em cópia: 20 + 30 mutantes, todos detectados |
| `baseline_inicio.sha256`, `baseline_conferencia_final.txt` | Hashes dos 114 arquivos do projeto no início e a conferência no fim |
| `inventario_modulos.json` | Saída da análise por AST (linhas, funções, importações, alcance a partir de `main`) |

## `cenarios/`

Scripts usados para produzir os logs. **São instrumentos de teste, não implementação.** Cada um recebe uma pasta-base como argumento e usa uma cópia do projeto; `amb.py` define o ambiente isolado (banco, cofre, trilha, token e PIN de teste, internet e IA desligadas ou falsas). Para repetir em outra máquina:

1. Copie o projeto para uma pasta de trabalho (não rode contra o cofre real).
2. Ajuste a constante `COPIA` em `amb.py` e o `sys.path.insert` no topo de cada script, que apontam para o diretório temporário da sessão da auditoria.
3. Rode `python3 -I <cenario>.py <pasta-base-vazia>`. `B_proc2.py` e `C_retomada.py` reutilizam a base criada por `B_proc1.py` (copie-a antes, para não alterar o original).
4. `mutar.py` e `mutar2.py` alteram arquivos da **cópia** para provar que os testes detectam a quebra; nunca os rode dentro do projeto.

## O que não está aqui

Capturas de tela dos e2e, ambientes virtuais, a cópia do projeto usada nos cenários e arquivos de estado temporários ficaram fora do projeto, na pasta temporária da sessão. Nenhum token, senha ou chave foi gravado nestes arquivos: o token do painel impresso por um processo de teste foi substituído por `<REDIGIDO>`.
