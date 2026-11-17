#!/usr/bin/env python3
"""Exporta um Transformer de embeddings do Hugging Face para a FRIDAY (rode no PC ou no Google Colab, não no celular):

    pip install "optimum[onnxruntime]" transformers
    python scripts/exportar_transformer.py                         # padrão: paraphrase-multilingual-MiniLM-L12-v2
    python scripts/exportar_transformer.py --modelo sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --prefixo ""
    python scripts/exportar_transformer.py --de-pasta ~/Downloads/e5 --saida modelos_ia/significado-transformer       # PC: já baixados
    python scripts/exportar_transformer.py --de-pasta ~/Downloads/e5 --saida modelos_ia/celular                       # cópia 8 bits p/ celular

Gera modelos_ia/significado-transformer/ com:
  model.onnx      o Transformer, quantizado em 8 bits (~4× menor, roda no CPU do celular)
  tokenizer.json  o tokenizador
  centro.npy      a direção comum dos vetores, que a FRIDAY subtrai (centralizar)
  meta.json       o modelo de origem, o prefixo e o LIMIAR calibrado (quanto «parecido» é parecido de verdade para ESTE modelo)
Funciona sozinho (não precisa do resto do projeto): no Colab, basta enviar este arquivo.
Copie a pasta para friday-pi/modelos_ia/ no aparelho. A FRIDAY passa a usar o Transformer sozinha; sem a pasta, usa a rede própria.
"""
import argparse, json, os, shutil

# palavras comuns em português para calibrar: pares aleatórios entre elas mostram quanto «parecido» o modelo dá ao acaso
CALIBRAR = ("casa carro comida trabalho escola prova estudo treino academia sono música filme série livro viagem praia chuva sol frio calor "
            "dinheiro conta banco mercado cozinha café almoço jantar família amigo cachorro gato médico remédio cabeça celular computador "
            "programa código internet jogo futebol corrida bicicleta ônibus cidade rua parque igreja festa aniversário presente roupa sapato "
            "cama quarto banheiro janela porta mesa cadeira tempo hora semana mês ano manhã noite projeto reunião chefe salário férias "
            "matemática história física química inglês python sql dados tabela consulta memória cérebro ideia sonho medo alegria cansaço").split()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--prefixo", default="", help="MiniLM/sentence-transformers: vazio; e5: «query: »")
    ap.add_argument("--saida", default=os.path.join("modelos_ia", "significado-transformer"))
    ap.add_argument("--sem-quantizar", action="store_true")
    ap.add_argument("--de-pasta", help="usar model.onnx + tokenizer.json JÁ BAIXADOS do Hugging Face (pasta onnx/ do modelo): "
                                       "não precisa de optimum nem transformers, só onnxruntime, tokenizers, onnx e numpy")
    a = ap.parse_args()
    if a.de_pasta:
        tmp = a.de_pasta
        for f in ("model.onnx", "tokenizer.json"):
            if not os.path.isfile(os.path.join(tmp, f)):
                print(f"Falta {f} em {tmp}. Baixe da pasta onnx/ do modelo no Hugging Face.")
                return 1
        print(f"1/4 usando os arquivos já baixados em {tmp}")
    else:
        try:
            from optimum.onnxruntime import ORTModelForFeatureExtraction
            from transformers import AutoTokenizer
        except ImportError:
            print('Instale antes:  pip install "optimum[onnxruntime]" transformers   (ou use --de-pasta com os arquivos já baixados)')
            return 1
        tmp = a.saida + "-tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"1/4 baixando e exportando {a.modelo} para ONNX…")
        ORTModelForFeatureExtraction.from_pretrained(a.modelo, export=True).save_pretrained(tmp)
        AutoTokenizer.from_pretrained(a.modelo).save_pretrained(tmp)
    os.makedirs(a.saida, exist_ok=True)
    origem = os.path.join(tmp, "model.onnx")
    if a.sem_quantizar:
        shutil.copy(origem, os.path.join(a.saida, "model.onnx"))
    else:
        print("2/4 quantizando em 8 bits (menor e mais rápido no celular)…")
        from onnxruntime.quantization import quantize_dynamic, QuantType
        quantize_dynamic(origem, os.path.join(a.saida, "model.onnx"), weight_type=QuantType.QInt8)
    shutil.copy(os.path.join(tmp, "tokenizer.json"), os.path.join(a.saida, "tokenizer.json"))
    if not a.de_pasta:
        shutil.rmtree(tmp, ignore_errors=True)                     # só a pasta temporária que o próprio script criou

    print("3/4 calibrando o limiar com pares aleatórios de palavras comuns…")
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    sess = ort.InferenceSession(os.path.join(a.saida, "model.onnx"), providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(os.path.join(a.saida, "tokenizer.json"))
    nomes = {i.name for i in sess.get_inputs()}

    def vetor(t):                                   # o mesmo cálculo que a FRIDAY faz (significado._base_transformer)
        e = tok.encode(a.prefixo + t.lower())
        ids, mask = np.array([e.ids], dtype=np.int64), np.array([e.attention_mask], dtype=np.int64)
        ent = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        h = sess.run(None, {k: v for k, v in ent.items() if k in nomes})[0][0]
        v = (h * mask[0][:, None]).sum(0) / mask.sum()
        return v / np.linalg.norm(v)

    V0 = np.stack([vetor(w) for w in CALIBRAR])
    # CENTRALIZAR: modelos de embeddings dão nota alta para quase tudo (todos os vetores apontam para o mesmo lado). Tirar a direção
    # comum separa de verdade o relacionado do sem relação (medido no e5 e no MiniLM: 7/12 → 9–10/12 acertos). A FRIDAY faz o mesmo.
    centro = V0.mean(0).astype(np.float32)
    np.save(os.path.join(a.saida, "centro.npy"), centro)
    V = V0 - centro
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    sims = (V @ V.T)[np.triu_indices(len(V), 1)]
    meta = {"modelo": a.modelo, "prefixo": a.prefixo, "dim": int(V.shape[1]), "centralizar": True,
            "limiar": round(float(np.quantile(sims, 0.97)), 3), "acaso_media": round(float(sims.mean()), 3), "quantizado": not a.sem_quantizar}
    with open(os.path.join(a.saida, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    tam = os.path.getsize(os.path.join(a.saida, "model.onnx")) / 1e6
    print(f"4/4 pronto: {a.saida}  ({tam:.0f} MB, {meta['dim']} dimensões, limiar calibrado {meta['limiar']}, acaso ≈ {meta['acaso_media']})")
    def c(x):
        u = vetor(x) - centro
        return u / np.linalg.norm(u)
    for x, y in (("sql", "banco de dados"), ("prova", "estudo"), ("sono ruim", "cansaço"), ("treino", "banco"), ("prova", "cachorro")):
        print(f"   {x} ~ {y}: {float(c(x) @ c(y)):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
