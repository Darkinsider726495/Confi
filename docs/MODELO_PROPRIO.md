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
