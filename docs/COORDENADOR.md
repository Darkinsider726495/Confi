# Coordenador (`friday/coordenador.py`)

O mínimo para duas coisas que ela quer fazer não se pisarem, e para cada escolha ter uma explicação que dá para conferir. **Não é um agente, não tem fila, não cria threads e não executa nada**: quem executa continua sendo o corretor, por meio das tarefas ([TAREFAS.md](TAREFAS.md)).

## Por que existe (e por que é pequeno)

Antes de escrever uma linha, a necessidade foi medida: `reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py`. Duas tarefas que mexem no mesmo recurso, rodando ao mesmo tempo, ficam **as duas dentro da ferramenta** (pico de 2; o corretor solta o travão geral antes de rodar a ferramenta, então a concorrência é real). Log do «antes»: `reports/evidencias/logs/fase5_6/necessidade_de_coordenacao.antes.log`; do «depois»: `necessidade_de_coordenacao.depois.log` (pico de 1 no mesmo recurso, 2 em recursos diferentes).

O dono já decidiu que, se ela quiser fazer tudo ao mesmo tempo, ela decide. Por isso o coordenador **não serializa o que não se atrapalha**. O núcleo integrado é apenas observacional e não interfere nessa decisão ([NUCLEO.md](NUCLEO.md)).

## 1. Reserva de recursos

`tarefas.py` reserva os recursos do passo **antes** de chamar o corretor e libera **depois** (`finally`, então também quando a ferramenta quebra ou o corretor pede confirmação). A ligação é por `tarefas.RESERVAS` (preenchido quando `coordenador` é importado, em `main.py`): `tarefas.py` não importa o coordenador, então não há ciclo.

| Modo | Convive com |
|---|---|
| `excl` (exclusivo) | ninguém no mesmo recurso |
| `comp` (compartilhado) | outro `comp` no mesmo recurso |

Recursos por ferramenta (tabela `RECURSOS` no código; é a fonte de verdade):

| Ferramenta | Recurso |
|---|---|
| `rele` | `rele:<nome>` exclusivo |
| `lanterna`, `vibrar` | `lanterna`, `vibracao` exclusivos |
| `enviar_sms`, `preparar_whatsapp` | `contato:<nome>` exclusivo |
| `ligar` | `contato:<nome>` + `linha_telefonica`, exclusivos (não existem duas ligações juntas) |
| `criar_arquivo`, `compartilhar_arquivo` | `arquivo:<nome>` exclusivo |
| `guardar_memoria`, `pedir_evolucao` | `cofre` compartilhado (duas notas se somam) |
| `consolidar_memoria`, `esquecer_memoria`, `exportar_cerebro` | `cofre` exclusivo |
| `silenciar`, `voltar_a_falar` | `silencio` exclusivo |

`SEM_RECURSO` lista o que muda algo mas só se soma (`anotar`, `criar_lembrete`, `notificar`) ou só lê (`localizacao`), cada uma com o motivo escrito. **Toda ferramenta de nível 1 ou mais precisa estar numa das duas listas** (teste `test_toda_ferramenta_que_muda_algo_declara_seus_recursos`): ferramenta nova sem declaração quebra a suíte.

Regras:
- **Tudo ou nada, sem esperar** (`reservar`): se qualquer recurso está em uso por outro dono, nada é reservado.
- Nomes são comparados sem acento e sem caixa («Mãe» = «mae»). Nome que não deu para ler vira «algum» e conflita com outro «algum»: na dúvida, espera.
- Regra de recurso que quebra vira exclusivo (`<ferramenta>:?`), nunca «livre».
- O mesmo dono pode reservar de novo (substitui).
- **Espera:** a tarefa que não conseguiu reservar espera até `ESPERA_RECURSO_S` (3 s). Se o recurso continua ocupado, ela **não executa**: fica `PRONTA`, com `proxima_acao` dizendo «esperar o recurso … em uso por tNNNN», e o resultado do passo traz o motivo.
- Reservar **não dá permissão**: nível 2 continua pedindo a confirmação presa à ação (teste `test_o_corretor_continua_decidindo`).

## 2. Avaliação de propostas

`avaliar(propostas)` devolve, para cada proposta, uma das decisões abaixo, com componentes, nota e motivo. Uma proposta é um dicionário com `id`, `modulo`, `recursos`, `depende_de`, `precisa_dono` e cinco componentes entre 0 e 1.

| Componente | Peso | Como `proposta_de_tarefa` o preenche |
|---|---|---|
| relevância | +0,40 | pela origem: pedido seu 1,0 · meta 0,8 · conversa 0,6 · objetivo dela, aprovado 0,3 |
| urgência | +0,30 | 0,5 se foi pedido seu (0,2 nos demais), mais até 0,5 conforme espera (12 h = máximo) |
| custo | −0,10 | passos que faltam / máximo de passos |
| risco | −0,15 | maior nível dos passos que faltam / 3 |
| incerteza | −0,05 | 1 − confiança da experiência com essa estratégia nas condições de agora (sem experiência = 1,0) |

**Os pesos são escolhas de projeto, escritas no código; não são aprendidos nem se ajustam sozinhos.** A nota **ordena**; não autoriza.

Ordem das regras (a primeira que vale decide):

1. proposta mal formada (componente que não é número, `id` ou módulo ausente) → `recusar`;
2. exige o dono (nível 2 ou mais) → `pedir_dono` — por mais alta que seja a nota;
3. depende de algo que não terminou → `esperar`;
4. recurso ocupado por ação em andamento → `esperar`;
5. conflito com outra proposta de nota maior na mesma rodada → `esperar` (quem espera não segura recurso de ninguém nesta rodada);
6. senão → `executar_agora`. **Várias podem sair juntas.**

Empate de nota se resolve pelo `id`, então o resultado é estável.

## Quem usa a avaliação
A [retomada](RETOMADA.md) depois de reinício: monta uma proposta por tarefa pronta (`proposta_de_tarefa`) e executa na ordem que `avaliar` decide, reavaliando quem esperou dependência ou recurso. Nenhum outro módulo chama `avaliar` hoje; os objetivos dela passam pelo corretor como tarefas, e a reserva de recursos já cobre o que disputa o mesmo recurso.

## 3. Registro e voz

- Cada decisão vira uma linha em `.cerebro/coordenacao.jsonl` (só acrescenta): quem, módulo, decisão, motivo, nota, componentes e recursos como **tipo + código curto** (`contato:3fa9c1`). Dá para ver que dois pedidos bateram no mesmo contato, sem o log dizer qual contato (teste `test_cada_decisao_fica_registrada_sem_conteudo`, com texto-isca).
- «O que você está coordenando?» (só lê) mostra o que está reservado e as últimas decisões.
- O painel recebe só contagens (`coordenacao: {reservas, erros}`).

## 4. O que ele não faz

- Não cria agentes concorrentes, filas ou threads (teste varre o código).
- Não importa o corretor, não executa, não tem ferramenta da IA (os nomes de ferramenta são varridos).
- Não altera segurança e não aprende pesos.
- **Cobertura:** só o que passa por `tarefas.py` (pedidos da IA, planejador, objetivos aprovados, retomada). Protocolos, rotinas da autonomia e atalhos de voz da memória chamam o corretor direto e ficam fora da reserva. Cobrir esses caminhos seria mexer em `protocolos.py`/`autonomia.py` e não foi pedido por nenhum problema medido.
- A reserva vale dentro de **um processo**. Dois processos da FRIDAY no mesmo cofre não se coordenam por aqui.

## Como validar

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_coordenador.py'
python3 reports/evidencias/cenarios/fase5_6/necessidade_de_coordenacao.py
```

Mutação das defesas (37 mutantes, todos detectados): `reports/evidencias/cenarios/fase5_6/mut_coordenador.py`, resultado em `reports/evidencias/logs/fase5_6/mut_coordenador.log`; roda com `mutar.py` da pasta `fase3_4`.

## Como declarar uma ferramenta nova

Em `coordenador.py`: ponha a ferramenta em `RECURSOS` (o que ela usa e em que modo) ou em `SEM_RECURSO` (com o motivo). A skill `friday-nova-ferramenta` lembra disso.

Relatório da fase (decisões, números, limites): [FASE_5_6_ENTREGA.md](../reports/FASE_5_6_ENTREGA.md).
