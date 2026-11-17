#!/usr/bin/env python3
"""Exporta um Transformer de embeddings do Hugging Face para a FRIDAY (rode no PC ou no Google Colab, não no celular):

    pip install "optimum[onnxruntime]" transformers
    python scripts/exportar_transformer.py                         # padrão: intfloat/multilingual-e5-small
    python scripts/exportar_transformer.py --modelo sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --prefixo ""

Gera modelos_ia/significado-transformer/ com:
  model.onnx      o Transformer, quantizado em 8 bits (~4× menor, roda no CPU do celular)
  tokenizer.json  o tokenizador
  meta.json       o modelo de origem, o prefixo e o LIMIAR calibrado (quanto «parecido» é parecido de verdade para ESTE modelo)
Copie a pasta para friday-pi/modelos_ia/ no aparelho. A FRIDAY passa a usar o Transformer sozinha; sem a pasta, usa a rede própria.
"""
import argparse, json, os, shutil, sys

# palavras comuns em português para calibrar: pares aleatórios entre elas mostram quanto «parecido» o modelo dá ao acaso
CALIBRAR = ("casa carro comida trabalho escola prova estudo treino academia sono música filme série livro viagem praia chuva sol frio calor "
            "dinheiro conta banco mercado cozinha café almoço jantar família amigo cachorro gato médico remédio cabeça celular computador "
            "programa código internet jogo futebol corrida bicicleta ônibus cidade rua parque igreja festa aniversário presente roupa sapato "
            "cama quarto banheiro janela porta mesa cadeira tempo hora semana mês ano manhã noite projeto reunião chefe salário férias "
            "matemática história física química inglês python sql dados tabela consulta memória cérebro ideia sonho medo alegria cansaço").split()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="intfloat/multilingual-e5-small")
    ap.add_argument("--prefixo", default="query: ", help="e5 usa «query: »; MiniLM/sentence-transformers usam vazio")
    ap.add_argument("--saida", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modelos_ia", "significado-transformer"))
    ap.add_argument("--sem-quantizar", action="store_true")
    a = ap.parse_args()
    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from transformers import AutoTokenizer
    except ImportError:
        print('Instale antes:  pip install "optimum[onnxruntime]" transformers')
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
    shutil.rmtree(tmp, ignore_errors=True)

    print("3/4 calibrando o limiar com pares aleatórios de palavras comuns…")
    os.environ["SIGNIFICADO_TRANSFORMER"] = a.saida
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "friday"))
    with open(os.path.join(a.saida, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"modelo": a.modelo, "prefixo": a.prefixo}, f)
    import numpy as np
    import significado as S
    V = np.stack([S._base_transformer(w) for w in CALIBRAR])
    sims = (V @ V.T)[np.triu_indices(len(V), 1)]
    limiar = float(np.quantile(sims, 0.99))
    meta = {"modelo": a.modelo, "prefixo": a.prefixo, "dim": int(V.shape[1]), "limiar": round(limiar, 3),
            "acaso_media": round(float(sims.mean()), 3), "quantizado": not a.sem_quantizar}
    with open(os.path.join(a.saida, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    tam = os.path.getsize(os.path.join(a.saida, "model.onnx")) / 1e6
    print(f"4/4 pronto: {a.saida}  ({tam:.0f} MB, {meta['dim']} dimensões, limiar calibrado {meta['limiar']}, acaso ≈ {meta['acaso_media']})")
    S._tr.update(dir=None)
    for x, y in (("treino", "academia"), ("prova", "estudo"), ("treino", "banco")):
        print(f"   {x} ~ {y}: {float(S._base_transformer(x) @ S._base_transformer(y)):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
