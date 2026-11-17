"""Fila local de candidatos da FRIDAY — não usa modelo/API externa.

Este gerador é deliberadamente transparente: oferece substituição textual exata
(uma única ocorrência) ou recebe um arquivo .py local. Não finge criar algoritmos
generais sozinho. Todo candidato fica em quarentena até a validação de evolucao.py.
Candidatos e histórico não têm função de exclusão neste módulo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from . import evolucao as E

RAIZ = E.STATE_DIR / "candidatos"
_ID = re.compile(r"cand-\d{12,20}-[0-9a-f]{12}")


def _pastas() -> None:
    RAIZ.mkdir(parents=True, exist_ok=True, mode=0o700)


def _id_valido(candidate_id: str) -> bool:
    return isinstance(candidate_id, str) and bool(_ID.fullmatch(candidate_id))


def _guardar(alvo: str, conteudo: str, descricao: str = "") -> dict:
    validacao = E.validar_candidato(alvo, conteudo)
    dados = conteudo.encode("utf-8")
    candidate_id = f"cand-{time.time_ns()}-{hashlib.sha256(dados).hexdigest()[:12]}"
    _pastas()
    pasta = RAIZ / candidate_id
    pasta.mkdir(mode=0o700)
    source = pasta / "candidato.py"
    with source.open("xb") as f:
        f.write(dados)
        f.flush()
        os.fsync(f.fileno())
    manifesto = {
        "id": candidate_id,
        "alvo": alvo,
        "criado_em": time.time(),
        "descricao": " ".join(descricao.split())[:240],
        "sha256": hashlib.sha256(dados).hexdigest(),
        "bytes": len(dados),
        "validacao_inicial": validacao,
        "estado": "aguardando_testes",
        "observacao": "Nenhum candidato é ativo antes da promoção validada.",
    }
    meta = pasta / "manifest.json"
    with meta.open("x", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    for p in (source, meta):
        try:
            os.chmod(p, 0o400)
        except OSError:
            pass
    try:
        os.chmod(pasta, 0o500)
    except OSError:
        pass
    E._registro({"evento": "candidato_enfileirado", "id": candidate_id, "alvo": alvo,
                 "hash": manifesto["sha256"], "descricao": manifesto["descricao"]})
    return {k: manifesto[k] for k in ("id", "alvo", "criado_em", "descricao", "sha256", "bytes", "estado")}


def preparar_arquivo(alvo: str, arquivo_candidato: str | Path, descricao: str = "") -> dict:
    """Enfileira um arquivo de código .py, sem executá-lo ou instalá-lo."""
    E._alvo(alvo)
    origem = Path(arquivo_candidato).expanduser()
    if origem.is_symlink() or not origem.is_file() or origem.suffix != ".py":
        raise ValueError("O candidato deve ser um arquivo .py regular, sem link simbólico.")
    conteudo = origem.read_text(encoding="utf-8")
    return _guardar(alvo, conteudo, descricao or f"Candidato importado de {origem.name}")


def gerar_substituicao(alvo: str, busca: str, substituicao: str, descricao: str = "") -> dict:
    """Gera um candidato por substituição literal que deve ocorrer exatamente uma vez."""
    if not isinstance(busca, str) or not busca:
        raise ValueError("O trecho a localizar não pode ser vazio.")
    if not isinstance(substituicao, str):
        raise TypeError("O trecho substituto precisa ser texto.")
    caminho = E._alvo(alvo)
    original = caminho.read_text(encoding="utf-8")
    ocorrencias = original.count(busca)
    if ocorrencias != 1:
        raise ValueError(f"Substituição cancelada: o trecho apareceu {ocorrencias} vez(es); é exigida exatamente 1.")
    candidato = original.replace(busca, substituicao, 1)
    return _guardar(alvo, candidato, descricao or "Substituição literal local")


def obter(candidate_id: str) -> tuple[dict, str]:
    """Lê um candidato da fila com validação de id, caminho e hash."""
    if not _id_valido(candidate_id):
        raise ValueError("ID de candidato inválido.")
    pasta = RAIZ / candidate_id
    if pasta.is_symlink() or not pasta.is_dir() or pasta.resolve().parent != RAIZ.resolve():
        raise ValueError("Pasta de candidato inválida.")
    meta = pasta / "manifest.json"
    source = pasta / "candidato.py"
    if meta.is_symlink() or source.is_symlink() or not meta.is_file() or not source.is_file():
        raise ValueError("Arquivos do candidato ausentes ou inválidos.")
    manifesto = json.loads(meta.read_text(encoding="utf-8"))
    conteudo = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
    if manifesto.get("id") != candidate_id or manifesto.get("sha256") != digest:
        raise ValueError("Hash do candidato não confere; promoção bloqueada.")
    E.validar_candidato(manifesto.get("alvo"), conteudo)
    return manifesto, conteudo


def listar() -> list[dict]:
    """Lista candidatos sem oferecer operação de remoção."""
    if not RAIZ.exists():
        return []
    saida = []
    for pasta in sorted(RAIZ.iterdir()):
        if not _id_valido(pasta.name) or pasta.is_symlink() or not pasta.is_dir():
            continue
        try:
            manifesto, _ = obter(pasta.name)
            saida.append({k: manifesto.get(k) for k in ("id", "alvo", "criado_em", "descricao", "sha256", "bytes", "estado")})
        except (OSError, ValueError, json.JSONDecodeError):
            saida.append({"id": pasta.name, "estado": "inválido; não promover"})
    return saida


def promover(candidate_id: str, comandos_teste, timeout: int = E.TEST_TIMEOUT) -> dict:
    """Promove candidato somente após os testes de baseline, staging e pós-promoção."""
    manifesto, conteudo = obter(candidate_id)
    resultado = E.promover(manifesto["alvo"], conteudo, comandos_teste, timeout=timeout)
    E._registro({"evento": "resultado_fila_candidato", "id": candidate_id,
                 "alvo": manifesto["alvo"], "status": resultado.get("status"),
                 "hash": manifesto.get("sha256")})
    return resultado
