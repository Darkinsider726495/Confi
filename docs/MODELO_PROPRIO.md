# Modelo próprio da FRIDAY (sem API de terceiros)

Tudo escrito do zero, em Python + NumPy, dentro do projeto:

| Peça | Arquivo | O que é |
|---|---|---|
| Tokenizador | `friday/modelo/tokenizador.py` | BPE por bytes (a ideia do Karpathy): treino por palavras únicas (rápido), encode, decode, salvar |
| GPT | `friday/modelo/gpt.py` | Transformer só-decodificador: embeddings + L blocos (LayerNorm → atenção causal multi-cabeça → MLP GELU) → logits. Retropropagação escrita à mão (gradiente conferido por diferença finita) + AdamW |
| Treino | `friday/modelo/treino.py`, `scripts/treinar_modelo.py` | monta o texto (conversas Dono/FRIDAY, memórias, estudos de cibersegurança, docs, `modelos_ia/corpus/*.txt`), treina tokenizador e GPT, salva em `modelos_ia/friday-gpt/` |
| API própria | `friday/modelo/api.py`, `scripts/api_modelo.py` | `POST /v1/chat/completions` (formato de chat padrão), chave em `friday/.modelo_token`, só rede local |

## Usar
```bash
python scripts/baixar_corpus.py --livros 100  # livros em português do Projeto Gutenberg (mais texto = modelo melhor)
python scripts/treinar_modelo.py --rapido      # teste: minutos
python scripts/treinar_modelo.py               # padrão: ~1 M de parâmetros (no celular, deixe a noite toda; no PC, ~30 min)
python scripts/treinar_modelo.py --grande      # ~6 M de parâmetros: PC ou Colab (horas)
python scripts/treinar_modelo.py --conversar   # conversar com ele
python scripts/bpe_continuo.py                 # BPE em loop contínuo: aprende tokens novos com o texto que chega (também roda no treino diário)
echo 'IA_PROVEDOR=propria' >> .env && bash termux/atualizar.sh --reiniciar   # a FRIDAY passa a usar o modelo dela
```
Treinar no PC e usar no celular: no PC `python scripts/api_modelo.py --rede`; no celular `.env` com `IA_PROVEDOR=propria`,
`PROPRIA_URL=http://IP-DO-PC:8100` e `PROPRIA_CHAVE=<conteúdo de friday/.modelo_token do PC>`.

## Honestidade sobre a qualidade
Um modelo treinado do zero com pouco texto aprende o JEITO de escrever (palavras, pontuação, o formato Dono/FRIDAY) muito antes de aprender a
RACIOCINAR. Com ~1 M de parâmetros e alguns megabytes de texto, ele escreve português com cara de FRIDAY, mas erra fatos e perde o fio. Melhora
com: mais texto (conversas, estudos, livros de domínio público em `modelos_ia/corpus/`), modelo maior (`--grande`) e mais passos — de preferência
no PC/Colab. O modelo próprio não usa as ferramentas (não chama o corretor): ele só conversa.

## Modelo híbrido (profundidade recorrente + BPTT)
`python scripts/treinar_modelo.py --hibrido 3`: o texto passa 3 vezes pelas MESMAS camadas antes da resposta (a ideia de «recurrent depth»):
pensa mais fundo com os mesmos parâmetros. O treino é retropropagação através das repetições (BPTT na profundidade: o gradiente de cada passada
se soma nos mesmos pesos — conferido por diferença finita nos testes). Custa R vezes mais tempo por passo. Num teste curto (400 passos, modelo de
2 camadas) ficou um pouco atrás do normal (perda 5,00 × 4,90): a vantagem aparece em treino mais longo e em tarefas de vários passos, não em
modelo minúsculo. A FRIDAY também tem BPTT clássico (no tempo) na GRU da rotina (`friday/rotina.py`).

## Escalar: PC e celular (medido)
Velocidade medida num processador de 4 núcleos (NumPy usa todos):

| Tamanho | Parâmetros | Segundos por passo | Treino padrão | Tempo estimado aqui |
|---|---|---|---|---|
| `--rapido` | 0,2 M | 0,04 s | 300 passos | ~15 s |
| padrão | 1,1 M | 0,56 s | 2.000 passos | ~20 min |
| `--grande` | 5,9 M | 7,8 s | 20.000 passos | ~43 h |

Num PC com mais núcleos fica proporcionalmente mais rápido; no celular, conte de 3 a 5 vezes mais lento. Por isso:
- **o treino salva sozinho a cada 200 passos** e `--continuar` retoma de onde parou (Ctrl+C também salva) — dá para treinar em várias noites;
- **geração com cache KV**: responde ~11× mais rápido (mesma resposta, conferido em teste).

### Roteiro no PC (Windows, Linux ou Kali; só Python 3 + `pip install numpy`)
```bash
python scripts/baixar_corpus.py --livros 100      # 1. dados: livros em português
python scripts/treinar_modelo.py                   # 2. pré-treino (aprende português)
python scripts/treinar_modelo.py --continuar       #    (se parou no meio)
python scripts/treinar_modelo.py --ajuste          # 3. ajuste fino: aprende a CONVERSAR (conversas + perguntas e respostas dos estudos)
python scripts/chaves_api.py criar celular         # 4. a chave do celular (aparece uma vez)
python scripts/api_modelo.py --rede                # 5. a API própria na rede de casa
```
No celular (`.env`): `IA_PROVEDOR=propria`, `PROPRIA_URL=http://IP-DO-PC:8100`, `PROPRIA_CHAVE=fri_…`.

### Chaves da API própria
`scripts/chaves_api.py criar|listar|revogar NOME`: uma chave por aparelho, com nome; no disco fica só o hash (sha256); revogar uma não mexe nas outras.
