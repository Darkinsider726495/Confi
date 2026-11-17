"""Busca semântica (RAG) sobre a memória da FRIDAY, com LightRAG, tudo local pelo Ollama.

O que faz: indexa as notas da memória da FRIDAY (Memorias, Conversas, Topicos, Eu) num índice
LightRAG e responde a «lembrar» também por SIGNIFICADO, não só por palavra igual. O embedding e o
LLM rodam no Ollama local — nada sai da máquina.

Princípios (iguais aos do resto da FRIDAY):
- Opcional e degradável: se o LightRAG não estiver instalado, ou o Ollama fora do ar, a FRIDAY
  continua com a busca por palavra de sempre (memoria.buscar). Este módulo NUNCA derruba a memória.
- Só leitura da sua memória: lê as notas do cofre, nunca escreve nem apaga nada do cofre. O índice
  fica numa pasta à parte (.cerebro/rag), fora do Obsidian. Este módulo não apaga arquivo nenhum.
- Confiança preservada: indexa só a memória confiável (o que você contou e as conversas), NÃO o que
  ela estudou na internet (Estudos) nem o que viu pela câmera (Visao) — aquilo continua entrando pela
  busca normal, rotulado e tratado como dado de terceiros.
- Pesado no indexar: o LightRAG extrai entidades/relações com o LLM a cada nota nova. Num modelo
  pequeno (llama3.2:3b) isso é lento, então o indexar roda de madrugada, quando a FRIDAY "dorme".

Configuração (ambiente):
  CEREBRO_RAG=0            desliga de vez (padrão: ligado se o lightrag estiver instalado)
  OLLAMA_URL              padrão http://127.0.0.1:11434
  OLLAMA_MODEL            LLM do grafo (padrão llama3.2:3b)
  CEREBRO_EMBED_MODEL     modelo de embedding (padrão bge-m3:latest — multilíngue, bom em português)
  CEREBRO_EMBED_DIM       dimensão do embedding (padrão 1024, a do bge-m3)
  CEREBRO_RAG_DIR         pasta do índice (padrão <projeto>/.cerebro/rag)
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path

import memoria as MEM

BASE = os.path.dirname(os.path.abspath(__file__))

# Pastas da memória que entram no índice semântico: só a memória CONFIÁVEL.
# (Estudos/Visao ficam de fora de propósito — são dado de terceiros e continuam na busca normal.)
PASTAS_INDEX = ("Memorias", "Conversas", "Topicos", "Eu")

_trava = threading.RLock()
# Funções do LLM e do embedding — substituíveis nos testes (injeção), senão usam o Ollama.
_LLM_FUNC = None
_EMBED_FUNC = None


# ---------------------------------------------------------------- configuração
def ligado() -> bool:
    return (os.getenv("CEREBRO_RAG", "1").strip().lower() not in ("0", "off", "nao", "não", "false"))


def _dir_indice() -> str:
    d = os.getenv("CEREBRO_RAG_DIR") or os.path.join(BASE, "..", ".cerebro", "rag")
    d = os.path.abspath(d)
    os.makedirs(d, exist_ok=True)              # cria a pasta do índice (não apaga nada)
    return d


def _manifesto_path() -> str:
    return os.path.join(_dir_indice(), "manifesto.json")


def _ler_manifesto() -> dict:
    try:
        with open(_manifesto_path(), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _salvar_manifesto(m: dict) -> None:
    with open(_manifesto_path(), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)


def disponivel() -> bool:
    """True se dá para usar a busca semântica: ligado, lightrag instalado e memória ativa."""
    if not (ligado() and MEM.ativo()):
        return False
    try:
        import lightrag  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- Ollama (LLM + embedding)
def _funcs_ollama():
    """Monta as funções de LLM e embedding do Ollama a partir do ambiente. Só é chamado se o lightrag existe."""
    from functools import partial
    from lightrag.llm.ollama import ollama_model_complete, ollama_embed
    from lightrag.utils import EmbeddingFunc

    host = (os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    llm_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    embed_model = os.getenv("CEREBRO_EMBED_MODEL", "bge-m3:latest")
    dim = int(os.getenv("CEREBRO_EMBED_DIM", "1024"))

    llm = _LLM_FUNC or ollama_model_complete
    if _EMBED_FUNC is not None:
        embed = _EMBED_FUNC
    else:
        embed = EmbeddingFunc(
            embedding_dim=dim, max_token_size=8192,
            func=partial(ollama_embed.func, embed_model=embed_model, host=host),
        )
    return llm, llm_model, embed, host


def _tokenizer_local():
    """Tokenizer em bytes (UTF-8), local: o LightRAG conta tokens SEM baixar o tiktoken da internet.
    A FRIDAY é offline por padrão; isto evita uma chamada de rede surpresa na primeira indexação.
    (Conta em bytes, ~4x o número real de tokens, então os trechos ficam um pouco menores — seguro.)"""
    from lightrag.utils import Tokenizer

    class _Bytes:
        def encode(self, content):
            return list(str(content).encode("utf-8"))

        def decode(self, tokens):
            try:
                return bytes(int(t) & 0xFF for t in tokens).decode("utf-8", "ignore")
            except Exception:
                return ""

    return Tokenizer(model_name="friday-bytes-local", tokenizer=_Bytes())


# ---------------------------------------------------------------- índice
# IMPORTANTE: o LightRAG prende suas filas internas ao loop de evento que o inicializou. Como a FRIDAY é
# síncrona e cada chamada roda num loop próprio (asyncio.run), a instância é criada e FINALIZADA dentro de
# cada chamada — nunca guardada entre chamadas (senão: "bound to a different event loop"). O índice no disco
# é que persiste; recarregá-lo é rápido (nano-vectordb local).
async def _novo_rag():
    from lightrag import LightRAG
    llm, llm_model, embed, host = _funcs_ollama()
    extra = {}
    if os.getenv("CEREBRO_TOKENIZER", "local").strip().lower() == "local":
        extra["tokenizer"] = _tokenizer_local()     # offline; CEREBRO_TOKENIZER=tiktoken volta ao padrão da lib
    rag = LightRAG(
        working_dir=_dir_indice(),
        llm_model_func=llm,
        llm_model_name=llm_model,
        llm_model_kwargs={"host": host, "options": {"num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096"))},
                          "timeout": int(os.getenv("OLLAMA_TIMEOUT", "300"))},
        embedding_func=embed,
        **extra,
    )
    await rag.initialize_storages()
    return rag


def _notas_para_indexar():
    """(id, caminho_rel, texto) de cada nota de memória confiável, pública, que mudou desde a última indexação."""
    if not MEM.ativo():
        return []
    manifesto = _ler_manifesto()
    saida = []
    raiz = MEM.base()
    for pasta in PASTAS_INDEX:
        d = raiz / pasta
        if not d.is_dir():
            continue
        for caminho in MEM._listar(d):
            nota = MEM._ler_nota(caminho)
            if not nota or nota.get("privado"):
                continue
            rel = f"{pasta}/{caminho.name}"
            mtime = nota.get("mtime", 0)
            if manifesto.get(rel) == mtime:        # já indexada e não mudou
                continue
            titulo = caminho.stem
            corpo = nota.get("corpo", "")
            texto = f"# {titulo}\n({pasta})\n\n{corpo}".strip()
            if texto:
                saida.append((rel, mtime, texto))
    return saida


async def _indexar_async(forcar: bool) -> dict:
    pend = _notas_para_indexar() if not forcar else [
        (f"{p}/{c.name}", (MEM._ler_nota(c) or {}).get("mtime", 0),
         f"# {c.stem}\n({p})\n\n{(MEM._ler_nota(c) or {}).get('corpo','')}".strip())
        for p in PASTAS_INDEX if (MEM.base() / p).is_dir() for c in MEM._listar(MEM.base() / p)
        if (MEM._ler_nota(c) or {}).get("corpo") and not (MEM._ler_nota(c) or {}).get("privado")
    ]
    if not pend:
        return {"indexadas": 0, "total_na_fila": 0}
    rag = await _novo_rag()
    try:
        manifesto = _ler_manifesto()
        feitas = 0
        for rel, mtime, texto in pend:
            try:
                await rag.ainsert(texto, ids=[rel], file_paths=[rel])
                manifesto[rel] = mtime
                feitas += 1
            except Exception:
                continue                            # uma nota problemática não derruba o lote
        _salvar_manifesto(manifesto)
        return {"indexadas": feitas, "total_na_fila": len(pend)}
    finally:
        await rag.finalize_storages()


async def _buscar_async(consulta: str, limite: int) -> list[dict]:
    from lightrag import QueryParam
    rag = await _novo_rag()
    try:
        param = QueryParam(mode=os.getenv("CEREBRO_RAG_MODO", "mix"), only_need_context=True, top_k=max(1, limite))
        ctx = await rag.aquery(str(consulta), param=param)
    finally:
        await rag.finalize_storages()
    texto = (ctx or "").strip() if isinstance(ctx, str) else ""
    if not texto:
        return []
    return [{"titulo": "busca semântica", "origem": "Memória (semântica)", "tipo": "rag",
             "trecho": texto[:1600], "externo": False, "score": None, "caminho": ""}]


# ---------------------------------------------------------------- API síncrona (a FRIDAY é síncrona)
def _rodar(coro):
    """Roda uma corrotina numa thread de trabalho (a FRIDAY não usa asyncio no laço principal)."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # já existe um loop nesta thread: cria um próprio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def indexar(forcar: bool = False) -> dict:
    """Indexa as notas novas/alteradas da memória. Pesado (usa o LLM): chamar de madrugada. Degradável."""
    if not disponivel():
        return {"indexadas": 0, "erro": "indisponível (lightrag ausente ou memória desligada)"}
    try:
        return _rodar(_indexar_async(forcar))
    except Exception as e:
        return {"indexadas": 0, "erro": f"{type(e).__name__}: {e}"[:200]}


def buscar(consulta: str, limite: int = 5) -> list[dict]:
    """Busca semântica na memória. Devolve itens no mesmo formato de memoria.buscar. [] se indisponível ou falhar."""
    if not disponivel() or not str(consulta).strip():
        return []
    try:
        return _rodar(_buscar_async(consulta, limite))
    except Exception:
        return []                                   # Ollama fora, índice vazio etc.: cai para a busca por palavra


def resumo() -> dict:
    """Para o painel: estado da busca semântica."""
    man = _ler_manifesto() if ligado() else {}
    return {"ligado": ligado(), "disponivel": disponivel(), "notas_indexadas": len(man),
            "indice": os.path.basename(_dir_indice().rstrip("/")),
            "embed": os.getenv("CEREBRO_EMBED_MODEL", "bge-m3:latest")}
