"""Importa especificações OpenAPI locais e cria catálogo seguro de endpoints.

Não baixa URLs automaticamente, não executa código da especificação e não coleta chaves.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlparse

MAX_SPEC_BYTES = 2_000_000
ALLOWED_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}

def analisar_openapi(arquivo: str | Path) -> dict:
    path = Path(arquivo)
    if path.is_symlink() or not path.is_file():
        raise ValueError("A especificação deve ser um arquivo local regular, não um link simbólico.")
    data = path.read_bytes()
    if len(data) > MAX_SPEC_BYTES:
        raise ValueError("Especificação maior que 2 MB.")
    try:
        spec = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("Nesta versão, forneça OpenAPI em JSON UTF-8 válido.") from e
    if not isinstance(spec, dict) or not isinstance(spec.get("openapi"), str) or not isinstance(spec.get("paths"), dict):
        raise ValueError("Documento não parece ser uma especificação OpenAPI 3.x.")
    servers = []
    for server in spec.get("servers", [])[:10]:
        url = server.get("url") if isinstance(server, dict) else None
        if isinstance(url, str):
            p = urlparse(url)
            if p.scheme in ("http", "https") and p.hostname and not p.username and not p.password:
                servers.append(url)
    endpoints = []
    for path_name, path_item in list(spec["paths"].items())[:1000]:
        if not isinstance(path_name, str) or not path_name.startswith("/") or ".." in path_name.split("/"):
            continue
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in ALLOWED_METHODS or not isinstance(operation, dict):
                continue
            endpoints.append({
                "method": method.upper(),
                "path": path_name,
                "operation_id": operation.get("operationId"),
                "summary": operation.get("summary", ""),
                "parameters": [
                    {"name": p.get("name"), "in": p.get("in"), "required": bool(p.get("required", False))}
                    for p in operation.get("parameters", []) if isinstance(p, dict)
                ][:100],
            })
    return {
        "title": spec.get("info", {}).get("title", "API sem título"),
        "version": spec.get("info", {}).get("version", "desconhecida"),
        "openapi": spec["openapi"],
        "servers": servers,
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
        "execution": "nenhum código executado; catálogo somente descritivo",
    }

def salvar_catalogo(arquivo_spec: str | Path, destino: str | Path) -> dict:
    catalogo = analisar_openapi(arquivo_spec)
    out = Path(destino)
    if out.is_symlink():
        raise ValueError("Destino não pode ser link simbólico.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"destino": str(out), "endpoints": catalogo["endpoint_count"], "titulo": catalogo["title"]}
