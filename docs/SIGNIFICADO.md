# Significado — a rede neural própria da FRIDAY

Pedido do criador: deep learning próprio, treinado **da mesma forma** que um modelo de linguagem grande, em escala de celular.

| Etapa | Num modelo grande | Na FRIDAY (`friday/significado.py`, NumPy puro) |
|---|---|---|
| 1. Pré-treino autossupervisionado | prever a próxima palavra em trilhões de palavras | **skip-gram com amostragem negativa**: prever as palavras vizinhas. Base com as docs do projeto (vai no pacote, sem dado pessoal); no aparelho, também o cofre dela (estudos, memórias, lembranças — nunca `Privado/`) |
| 2. Ajuste fino | exemplos de conversas boas | **as sinapses dela** viram exemplos (contrastivo): o que anda junto para o dono se aproxima, pares aleatórios se afastam |
| 3. Feedback humano | pessoas escolhem a melhor resposta | **o dono corrige** por voz: «X tem a ver com Y» / «X não tem nada a ver com Y» (peso 3× o das sinapses) |

Tamanho da base: 2.706 palavras × 64 dimensões ≈ 173 mil parâmetros (um modelo grande tem bilhões). É uma rede de *embeddings* — a mesma peça que é a primeira camada de um Transformer —, não um Transformer.

## O que ela faz com isso
- **Assimilação:** assunto novo se liga, por significado, aos 2 assuntos que ela já conhece mais parecidos (sinapse semântica de peso 0,5 × parecença; a de uso vale 1). Só liga acima de **0,80** — calibrado: só 1% dos pares aleatórios passa disso.
- **«o que é parecido com X?»** — os assuntos dela mais próximos, com a porcentagem, dita como o que a rede aprendeu, não certeza.
- **Ajuste sozinho:** a cada 6 h, no tempo ocioso, ela refaz a etapa 2/3 com as sinapses e o feedback novos.
- A rede **só sugere ligações**: não decide nem executa nada.

## Treinar
```bash
python scripts/treinar_significado.py --base        # etapa 1 só com as docs → friday/significado_base.npz (pacote)
python scripts/treinar_significado.py --pretreino   # etapa 1 com docs + o cofre → cofre/.cerebro/significado.npz (aparelho)
python scripts/treinar_significado.py --ajuste      # etapas 2 e 3 (ela também faz sozinha a cada 6 h)
```
No Termux precisa do NumPy: `pkg install python-numpy`. Sem ele, tudo isto fica desligado e a FRIDAY segue normal.

## Limites honestos
- A base foi treinada com só ~35 mil palavras (as docs): palavras raras nelas («treino») ainda saem com vizinhos ruins. O pré-treino no aparelho, com o cofre dela, é que dá o vocabulário do dono.
- O modelo pessoal (`.cerebro/significado.npz`) é derivado da memória dela: fica no cofre, nunca no git.

Testes: `tests/test_significado.py` — o pré-treino separa mundos de palavras sem rótulo, a perda cai, sinapse aproxima, feedback afasta, assunto sem relação não se liga, sem NumPy tudo desliga. Mutações (feedback invertido, ajuste que não aprende, ligar sem limiar) foram pegas.
