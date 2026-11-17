# Pré-córtex (`friday/prefrontal.py`)

O pré-córtex é a camada que **junta o que a FRIDAY quer fazer, decide, guarda metas e confere se deu certo**. É um modelo de software inspirado num artigo sobre o córtex pré-frontal (Agrela Rodrigues, 2022, *Ciencia Latina* 6(3), doi 10.37811/cl_rcm.v6i3.2578), com a ideia de preparação semântica de Jamali et al. (*Nature*, 2024). Não é biologia nem consciência; o artigo tem autor único e poucas referências, então só a estrutura funcional foi usada.

Este documento descreve **o que o código faz hoje**. O que ainda não existe está em [Limites](#limites-e-o-que-não-existe).

## Contrato do módulo

| | |
|---|---|
| **Lê** | estado interno (`vida.py`), curiosidade (`curiosidade.py`), conversa, visão, autonomia, ferramentas de silêncio/descanso, contagem de memórias. Se algum não responde, vira um valor neutro: o pré-córtex nunca derruba nada |
| **Escreve** | só o próprio estado (`.cerebro/prefrontal.json`), o histórico de decisões (`.cerebro/decisoes.jsonl`, só acrescenta), notas `Meta …` / `Meta cumprida …` em `Memorias/` e o interesse da curiosidade (`curiosidade.interesse`) |
| **Não faz** | não tem ferramenta da IA, não chama o corretor, não executa ação, não liga nem desliga curiosidade, conversa ou visão (só o dono, por voz), não apaga nada (meta cumprida ou arquivada continua guardada) |
| **Quando roda** | `laco()` (thread iniciada em `main.py`) chama `pensar()` a cada ~20 s; `perceber()` é chamado por `main.processar` a cada pedido (só o rótulo, nunca o texto) |
| **Paralelismo** | estudar, conversar e olhar seguem independentes. «Simultâneo» na decisão só significa que mais de um impulso passou do limiar ao mesmo tempo; nada aqui exclui nada |

## Peças

| Peça | Função | O que faz |
|---|---|---|
| Memória de trabalho (DLPFC) | `perceber`, `foco` | guarda **rótulos** do que chamou a atenção (origem, tipo, resumo de até 80 letras, assunto) com força que decai; o que se repete perde força (habituação); itens de assuntos parecidos se reforçam (parecido = palavras de conteúdo em comum). Sem teto por padrão (`PFC_FOCO`) |
| Valor (OFC) | `impulsos`, `valor` | quanto ela quer estudar, conversar, olhar e descansar, ponderado pelo que já deu certo e pela dopamina; cansada, segura o impulso de ir atrás |
| Decisão (vmPFC) | `observar`, `decidir`, `aprender` | monta o quadro geral, compara cada valor com um limiar (a serotonina o sobe), e depois de 10 min conferindo se o que quis aconteceu, ajusta o peso daquele impulso |
| Monitoração (ACC) | `monitorar`, `limites` | avisa conflito entre impulsos, falta de iniciativa (baixa um pouco o limiar) e repetição sem fim (dá uma pausa); `limites` diz o que ela não consegue agora |
| Metas | `nova_meta`, `ligar`, `perseguir`, `plano` | ver abaixo |

## Metas

Três tipos (`TIPOS_META`): `aprender` (um assunto), `ver` (número de coisas que enxerga) e `conhecer` (número de memórias). Estados: `ativa`, `cumprida`, `arquivada`. Cada meta tem id (`m1`, `m2`…), título, assunto, alvo, origem (`dono` ou `propria`), progresso 0–1, contadores de empurrões, e as listas `ligados` e `candidatos`.

`perseguir` roda a cada pensamento: recalcula o progresso, marca como cumprida, e para metas `aprender` empurra a curiosidade para o assunto (`curiosidade.interesse`, no máximo uma vez a cada 3 h por meta, só se a curiosidade estiver ligada, fora do descanso). Meta que empaca 3 empurrões seguidos passa a vez por 24 h.

### Como o progresso de uma meta `aprender` é decidido

Só vale **estudo que aconteceu** (a nota foi guardada em `Estudos/` e o contador do assunto subiu) ou uma **tarefa conferida**, nunca vontade de estudar. Há quatro caminhos, todos explícitos, e o motivo fica na nota da meta (`cumprida em … (evidência: …)`):

1. **mesmo assunto** — o assunto da meta, comparado por `chave_tema`: sem caixa, acento nem pontuação, sem palavras de ligação («de», «dos», «como»…) e sem importar a ordem. «Teoria dos grafos» = «grafos teoria». Isto é **normalização**, não semântica: «criptografia» e «criptografia explicada» continuam sendo assuntos diferentes.
2. **assunto ligado** — o dono disse que outro assunto conta (`ligar`, por voz: «conte criptografia explicada na meta criptografia»). Limite de `MAX_LIGADOS` (20) por meta; o assunto passa pelo mesmo filtro de qualquer assunto de estudo; meta ambígua é recusada, não escolhida no chute.
3. **pedido pela meta** — um estudo feito em nome do **id** da meta (`curiosidade.interesse(tema, meta="m3")` ou `curiosidade.estudar(tema, meta="m3")`). O id fica no assunto (`temas[assunto]["m"]` em `.cerebro/curiosidade.json`) e só conta quando o estudo deu certo. Vale só para a meta indicada, com as palavras que o assunto tiver. Id malformado é ignorado.
4. **tarefa conferida** — uma tarefa ligada por id à meta (`tarefas.criar(…, meta="m3", conclui_meta=True)`) terminou `CONCLUIDA`, ou seja, todos os passos tiveram o efeito **conferido** por fora ([TAREFAS.md](TAREFAS.md)). O texto da tarefa pode não ter nenhuma palavra em comum com a meta. Tarefa sem a marca `conclui_meta`, de outra meta, falha, falso sucesso ou «executada, mas não consegui conferir» não concluem: mostram andamento, no máximo 90% (`0,9 × concluídas/total`).

**O que NÃO conclui uma meta:** um estudo de assunto *parecido* (semelhança de palavras ≥ `LIMIAR_CANDIDATO`, 0,34) vira só **candidato**: aparece em `candidatos` e na fala «quais são as suas metas?», pedindo que o dono confirme com «conte … na meta …». Candidato não muda o progresso, não zera o contador de empacada e não cumpre nada. Uma mensagem que «parece relacionada» também não mexe em meta: a preparação semântica do foco só reforça atenção.

A semelhança usada é contagem de palavras (Jaccard), não entendimento de significado. Não há modelo de embeddings neste módulo.

## Registro de atividades (assimila o núcleo)

O núcleo (`nucleo.py`) observa a atenção; o pré-córtex **assimila** o que ele nota. Em `main.py`, `NC.assinar(ao_entrar=PFC.assimilar)` faz cada sinal notado chegar a `assimilar()`, que:

- guarda em `.cerebro/atividades.jsonl` **só rótulos** — `t`, `origem`, `tipo`, `saliencia`, `confiavel` —, nunca o texto nem o resumo;
- só acrescenta (nada é apagado); na memória fica o contador de hoje por origem e as 50 últimas, o histórico inteiro fica no arquivo;
- nunca levanta erro: assimilar não pode atrapalhar a atenção.

O pré-córtex **não importa** o núcleo (continua só lendo o resto): o núcleo empurra os sinais pela assinatura. Por isso é o pré-córtex quem responde «no que você está focada?»; o núcleo segue respondendo só sobre a arquitetura.

## Comandos de voz

Tratados por `tratar()`, na ordem de `main.processar` logo antes da curiosidade:

| Diga | Efeito |
|---|---|
| «o que você decidiu?» / «o que você quer fazer?» | `falar_decisao` |
| «quais são as suas metas?» | `falar_metas` (inclui candidatos pendentes) |
| «no que você está focada?» / «o que chamou sua atenção?» / «onde está a sua atenção?» | `falar_foco`: memória de trabalho do pré-córtex + o que o núcleo notou por último + quantas atividades registrou hoje |
| «o que você não consegue agora?» | `falar_limites` |
| «como funciona o seu pré-córtex?» | `falar_como_funciona` |
| «tenha como meta aprender sobre X» | `nova_meta("aprender", X)` (X passa pelo filtro de assunto) |
| «tenha como meta aprender a ver 10 coisas» | meta de visão |
| «conte X na meta Y» / «ligue o assunto X à meta Y» | `ligar(Y, X)` |
| «arquive a meta de X» | arquiva (não apaga) |

## Estado e configuração

- `.cerebro/prefrontal.json` — metas, aprendizado dos impulsos, últimas 200 decisões, contadores. Validado ao carregar (`_limpar_estado`: campo desconhecido é descartado; estado antigo sem `ligados`/`candidatos` carrega com listas vazias).
- `.cerebro/decisoes.jsonl` — só acrescenta uma linha quando a decisão ou algo feito muda.
- `PFC_FOCO` (`.env`) — teto de itens no foco; `0` = sem teto (padrão).

## Risco

Nível 0 no sentido do corretor: o módulo não executa ferramenta nenhuma. O efeito externo mais forte é pedir à curiosidade que estude um assunto, o que já tem os próprios limites (quarentena, consulta segura, só se o dono ligou a curiosidade). `ligar` e `nova_meta` aceitam apenas assuntos que `curiosidade._tema_valido` aceitaria (sem números longos, links, e-mails, nomes de pessoas guardadas ou palavras de ordem).

## Testes

`tests/test_prefrontal.py` (43) cobre foco, impulsos, decisão, monitoração, metas e voz; `tests/test_prefrontal_progresso.py` (35) cobre a relação explícita meta ↔ estudo: chave de assunto, crédito por id, ligação do dono, candidatos que não concluem, passos com palavras diferentes, persistência e limpeza do estado; `tests/test_tarefas_metas.py` (11) cobre a relação meta ↔ tarefa conferida. Rodar: `python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_prefrontal*.py'`.

## Limites e o que não existe

- Este módulo guarda **metas** de longo prazo, não tarefas. O registro de tarefas (plano, passos, conferência do efeito) é o `friday/tarefas.py` ([TAREFAS.md](TAREFAS.md)); o pré-córtex só **lê** dele um resumo por meta (`resumo_por_meta`) e não cria, executa nem cancela tarefa (há teste).
- `plano()` devolve uma lista fixa de passos por tipo de meta e o primeiro obstáculo; não replaneja.
- Metas `ver` e `conhecer` medem números que existem (coisas vistas, memórias), não a qualidade do que foi aprendido.
- A calibração dos pesos (`BASE_FORCA`, limiares) é de bom senso, não foi ajustada com uso real.
- Nada disto foi observado no celular real: os testes usam relógio e estado inventados.
