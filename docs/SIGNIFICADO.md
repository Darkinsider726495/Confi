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

## Com um Transformer pré-treinado (opcional, recomendado)
A etapa 1 pode vir **pronta** de um Transformer aberto, treinado com bilhões de palavras — como o pré-treino de um modelo grande:

| | Rede própria (padrão) | Com Transformer |
|---|---|---|
| Etapa 1 | ela treina sozinha (skip-gram) | **paraphrase-multilingual-MiniLM-L12-v2** (~118 milhões de parâmetros, 50+ línguas, já vem compactado para celular ARM), **congelado** |
| Etapas 2 e 3 | mexem nos vetores das palavras | treinam um **adaptador** dela (matriz d×d que começa na identidade), salvo no cofre (`.cerebro/significado_adaptador.npz`) |
| Limiar para ligar | 0,80 | **calibrado na exportação** para aquele modelo (`meta.json`) |

```bash
# no PC ou no Google Colab (o celular não precisa baixar nem converter nada)
pip install "optimum[onnxruntime]" transformers
python scripts/exportar_transformer.py            # → modelos_ia/significado-transformer/ (~120 MB, 8 bits)
# copie a pasta modelos_ia/ para friday-pi/ no aparelho e instale o que roda o modelo:
pip install -r requirements-transformer.txt       # numpy, onnxruntime, tokenizers
```
A FRIDAY detecta a pasta sozinha (`motor()` passa a dizer `transformer`). Sem ela, ou sem `onnxruntime`/`tokenizers`, volta para a rede própria.
Termo que o Transformer não reconhece (só «[UNK]») fica **sem significado** — nunca «parecido» com outro desconhecido (teste).

### Teste com os modelos reais (17/11/2026)
12 pares de assuntos (6 relacionados, 6 sem relação), limiar no percentil 95 dos pares aleatórios:

| Modelo | Relacionados (média) | Sem relação (média) | Acertos |
|---|---|---|---|
| e5-small, sem centralizar | 0,88 | 0,85 | 7/12 (tudo parece parecido) |
| e5-small, centralizado | 0,12 | −0,05 | 9/12 |
| **MiniLM, centralizado** (padrão) | **0,29** | −0,04 | **10/12** |

Por isso a exportação **centraliza** (salva `centro.npy`, a direção comum dos vetores, que a FRIDAY subtrai) e o padrão é o MiniLM.
Dentro da FRIDAY, com 14 assuntos ditos separados, ela ligou só por significado: sql↔banco de dados, férias↔viagem, guitarra↔música,
estudo↔prova, cansaço↔musculação (e academia↔estudo — «academia» também é meio acadêmico). Nenhuma ligação absurda.

### Jeito mais simples (o repositório já traz a versão ARM pronta)
```bash
mkdir -p ~/Downloads/minilm && cd ~/Downloads/minilm
R=https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/resolve/main
wget -O model.onnx $R/onnx/model_qint8_arm64.onnx      # 118 MB, já em 8 bits; roda no celular e no PC
wget $R/tokenizer.json
cd ~/friday-pi && python scripts/exportar_transformer.py --de-pasta ~/Downloads/minilm --saida modelos_ia/significado-transformer --sem-quantizar
```

## Treinar
```bash
python scripts/treinar_significado.py --base        # etapa 1 só com as docs → friday/significado_base.npz (pacote)
python scripts/treinar_significado.py --pretreino   # etapa 1 com docs + o cofre → cofre/.cerebro/significado.npz (aparelho)
python scripts/treinar_significado.py --ajuste      # etapas 2 e 3 (ela também faz sozinha a cada 6 h)
```
No Termux precisa do NumPy: `pkg install python-numpy`. Sem ele, tudo isto fica desligado e a FRIDAY segue normal.

## Limites honestos
- Exportação e motor testados com os modelos reais (e5-small e MiniLM) num Linux x86; o arquivo ARM roda também em x86. No celular de verdade não foi testado.
- `onnxruntime` e `tokenizers` instalam direto num PC/Linux (inclusive Kali). No Termux podem não ter versão pronta para Android; se não instalarem, ela segue com a rede própria.
- A base foi treinada com só ~35 mil palavras (as docs): palavras raras nelas («treino») ainda saem com vizinhos ruins. O pré-treino no aparelho, com o cofre dela, é que dá o vocabulário do dono.
- O modelo pessoal (`.cerebro/significado.npz`) é derivado da memória dela: fica no cofre, nunca no git.

Testes: `tests/test_significado.py` — o pré-treino separa mundos de palavras sem rótulo, a perda cai, sinapse aproxima, feedback afasta, assunto sem relação não se liga, sem NumPy tudo desliga. Mutações (feedback invertido, ajuste que não aprende, ligar sem limiar) foram pegas.
