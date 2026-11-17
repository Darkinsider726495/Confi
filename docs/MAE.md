# MAE — Modo de Autonomia de Engenharia (auto-modificação real, confinada)

O MAE é o modo em que a FRIDAY examina, propõe e **aplica** modificações de código nela mesma — de verdade,
não como sugestão — dentro de um laboratório isolado. A alteração acontece de verdade (arquivos criados,
editados, excluídos), cada passo sai pelo corretor (auditoria), cada modificação tem snapshot antes e o
conteúdo anterior fica recuperável. **O que ela nunca faz é escrever fora do laboratório nem promover uma
alteração para o projeto real.**

## O ciclo (8 estados)

`examinar → identificar → hipotetizar → propor → modificar → testar → analisar → registrar`

1. **Examinar**: semeia o experimento no laboratório (`lab_excluir` + `lab_criar`) — exclusão e recriação reais, confinadas.
2. **Identificar**: roda o teste designado (`lab_testar`, subprocess confinado) e lê a saída **real** para achar a função que falha.
3. **Hipotetizar**: formula uma hipótese de causa e correção (tabela de hipóteses conhecidas do módulo semente).
4. **Propor**: lê o código (`lab_ler`) e verifica se a hipótese se aplica.
5. **Modificar**: **edita o arquivo no laboratório** (`lab_editar`) — snapshot automático antes.
6. **Testar**: roda o teste de novo.
7. **Analisar**: passou → sucesso. Falhou → **desfaz a edição desta tentativa** (rollback do snapshot) e tenta a alternativa. Se nenhuma hipótese funcionar, restaura a versão boa e registra a falha.
8. **Registrar**: experiência registrada (objetivo, problema, hipótese, tentativas, previsão × observado, arquivos, diff, versão de rollback) + evento `mae:ciclo` na auditoria.

O ciclo avança **um estado por vez** na thread de fundo (`MAE.laco`, `main.py`), a cada `INTERVALO` segundos,
só quando o dono ativou o modo. **A thread nunca muda o modo sozinha**: iniciar/pausar/retomar/encerrar são do dono.

## Comandos (só o dono)

- «inicia o modo experimental» / «inicia o laboratório»
- «pausar o modo experimental» — o estado do ciclo fica guardado
- «retoma o laboratório» — continua do estado onde pausou
- «encerra o modo experimental» — se houver edição em andamento, a versão boa volta (rollback)
- «como vai o laboratório?» · «registros do laboratório»

Não há **nenhuma ferramenta do corretor** para mudar o modo (testado em `test_mae`): só a conversa com o dono
ou os botões do painel, que falam as mesmas frases pelo caminho normal do `processar()`.

## Modelo de segurança

| Barreira | Como |
|---|---|
| Confinamento de caminho | `laboratorio._validar_caminho`: recusa `..`, caminho absoluto, nomes ocultos (`.versoes/`, `.grave/`), extensão fora da lista, **e** resolve `realpath` (symlink) exigindo que fique dentro de `LAB_ROOT` |
| Snapshot + rollback | toda edição/exclusão/renomeação tira snapshot antes (`.versoes/<id>/`); `lab_restaurar` recupera qualquer versão |
| Corretor | todas as 10 ferramentas `lab_*` são nível 0/1, auditadas (cadeia de hashes); nada roda sem o corretor decidir |
| Coordenador | recursos `lab:arquivo:<nome>` e `lab:teste` exclusivos — duas operações no mesmo arquivo não se pisam |
| Execução de teste | só arquivos `teste_*.py` designados, subprocess com cwd = raiz do lab, **ambiente limpo** (sem `FRIDAY_DB`, PIN, auditoria…), sem shell, tempo limite de 30 s |
| «Nunca apaga» | o lab apaga só DENTRO de `.lab/`, sempre depois de snapshot (recuperável); `test_nunca_apaga` escopa a exceção e o teste estático exige que toda apagada use o alvo validado |
| Painel | botões do MAE só afetam o laboratório; `test_sem_botao_de_desligar` escopa a exceção e continua proibindo pausar/encerrar a escuta ou a FRIDAY |

## Prova prática (demo reproduzível)

```
python3 tests/demo_mae.py
```

Ciclo 1: semente com **defeito controlado** (`dobrar` devolve n*2+1) → teste falha → hipótese 1 (errada de
propósito) → teste falha de novo → desfaz a tentativa → hipótese 2 (alternativa) → **teste passa** →
experiência registrada, diff exibido, rollback disponível.
Ciclo 2: só a hipótese errada existe → o ciclo falha → **rollback restaura o original** (recuperação provada) →
sentinela fora do laboratório intacta.

Testes: `tests/test_laboratorio.py` (confinamento, snapshot/rollback, subprocess confinado, corretor),
`tests/test_mae.py` (ciclo real, tentativa→falha→alternativa, rollback, comandos do dono, estado adulterado).
Defesas verificadas por mutação: quebrar o confinamento de caminho e o escopo de botão faz os testes falharem.

## Painel (HUD)

Seção «Laboratório (MAE)» com: modo, estado do ciclo, objetivo, problema identificado, hipótese atual,
arquivos em análise/modificados/excluídos, teste em andamento, resultado do teste, tentativas, versão e ponto
de rollback, comparação de versões (diff), consumo do laboratório (arquivos, versões, KB), histórico e a
última experiência. **Os eventos são sempre reais**: sem ciclo rodando, o painel mostra «sem ciclo», nunca
atividade inventada.

## Limitações do ambiente (documentadas, não escondidas)

1. **Sem Docker (Termux é o alvo).** O isolamento é **lógico**: diretório + validação de caminho + resolução
   de symlink + subprocesso com ambiente limpo. Não é isolamento de kernel: um bug do próprio Python ou uma
   syscall que o confinamento não enxerga não são barrados por um hipervisor. Por isso as barreiras são em
   camadas (validação **antes** de normalizar, realpath depois, snapshot sempre) e o que se apaga é sempre
   recuperável.
2. **O subprocess de teste roda no mesmo kernel**: o confinamento dele é cwd + ambiente limpo + tempo limite +
   só o arquivo designado na linha de comando. Um teste malicioso *escrito pelo próprio ciclo* poderia tentar
   ler o disco por caminho absoluto — o que o mitiga é o fato de o conteúdo do teste vir da tabela de sementes
   do MAE (código em `mae.py`), não da internet, e tudo que ele faz sair na auditoria.
3. **As hipóteses são determinísticas** (tabela `HIPOTESES` em `mae.py`): o ciclo prova o *mecanismo* de
   engenharia (identificar → corrigir → provar → alternativa → registrar), não um raciocínio aberto. O
   acoplamento com a IA (propor hipóteses novas via modelo) é a evolução natural, atrás do mesmo corretor.
4. **A integração com `experiencias.py` fica para quando um ciclo MAE for atado a um objetivo do pré-córtex**
   (o registro dela exige tarefa `tNNNNN`/objetivo `pcNNNN`). Hoje a experiência do ciclo fica no diário do
   MAE e na auditoria — previsão × observado já é registrada.
5. **e2e do painel no Chromium**: neste ambiente de desenvolvimento o driver do Playwright não sobe
   (`Connection closed while reading from the driver`, mesmo em lançamento direto do Chromium). A sintaxe dos
   blocos JS do HUD é verificada e `test_http`/`test_sem_botao` cobrem o servidor e o HTML; o e2e visual deve
   ser rodado onde o Playwright funciona (`python3 tests/e2e_hud.py`).