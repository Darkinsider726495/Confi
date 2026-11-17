"""API HTTP local para a evolução controlada da FRIDAY.

A API só enfileira código como candidato; não executa nem promove código recebido.
A promoção continua sendo uma ação local explícita via scripts/evoluir.py.
Use bind em 127.0.0.1 e um token forte. Código de candidato deve ser tratado como não confiável.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import gerador_local, evolucao

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 8765
MAX_BODY = 600_000


def _token_configurado() -> str:
    token = os.getenv("FRIDAY_API_TOKEN", "").strip()
    if len(token) < 24:
        raise RuntimeError(
            "FRIDAY_API_TOKEN precisa ter pelo menos 24 caracteres. "
            "Gere um token aleatório e configure-o no ambiente."
        )
    return token


def _authorized(headers: Any, expected: str) -> bool:
    value = headers.get("Authorization", "")
    scheme, _, supplied = value.partition(" ")
    return scheme.lower() == "bearer" and bool(supplied) and hmac.compare_digest(supplied, expected)


def _status() -> dict:
    return {
        "service": "FRIDAY local evolution API",
        "mode": "queue-only",
        "promotion_over_http": False,
        "candidate_count": len(gerador_local.listar()),
        "allowed_targets": sorted(evolucao.ALVOS_PERMITIDOS),
        "protected_targets": sorted(evolucao.ALVOS_PROTEGIDOS),
        "hybrid_bridge": True,
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "FRIDAY-Evolution/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        # Não registrar corpo, Authorization, código ou dados pessoais.
        return

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _auth(self) -> bool:
        if not _authorized(self.headers, self.server.api_token):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _body(self) -> dict:
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            raise ValueError("Content-Length obrigatório.")
        size = int(length)
        if size < 1 or size > MAX_BODY:
            raise ValueError("Corpo vazio ou maior que o limite permitido.")
        raw = self.rfile.read(size)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("O corpo deve ser um objeto JSON.")
        return data

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "friday-evolution-api"})
            return
        if not self._auth():
            return
        if self.path == "/v1/status":
            self._send(200, _status())
        elif self.path == "/v1/candidates":
            self._send(200, {"candidates": gerador_local.listar()})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._auth():
            return
        if self.path == "/v1/ia/chat":
            try:
                data = self._body()
                prompt = data.get("prompt")
                system = data.get("system")
                if not isinstance(prompt, str) or not prompt.strip():
                    raise ValueError("'prompt' precisa ser texto não vazio.")
                if system is not None and not isinstance(system, str):
                    raise ValueError("'system' precisa ser texto.")
                from . import ponte_ia
                result = ponte_ia.responder(prompt, system=system)
                self._send(200, {"ok": True, **result})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})
            except Exception:
                self._send(503, {"error": "ai_provider_unavailable", "note": "Nenhum provedor respondeu; detalhes internos omitidos."})
            return
        if self.path != "/v1/candidates":
            self._send(404, {"error": "not_found"})
            return
        temp_path = None
        try:
            data = self._body()
            target = data.get("target")
            code = data.get("source")
            description = data.get("description", "")
            if not isinstance(target, str) or not isinstance(code, str):
                raise ValueError("'target' e 'source' precisam ser strings.")
            if not isinstance(description, str):
                raise ValueError("'description' precisa ser texto.")
            evolucao._alvo(target)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".py", prefix="friday-candidate-", delete=False
            ) as temp:
                temp.write(code)
                temp_path = temp.name
            candidate = gerador_local.preparar_arquivo(target, temp_path, description)
            self._send(201, {
                "accepted": True,
                "candidate": candidate,
                "note": "Candidato apenas enfileirado; não foi executado nem promovido.",
            })
        except PermissionError as exc:
            self._send(403, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception:
            self._send(500, {"error": "internal_error"})
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def do_PUT(self) -> None:
        self._send(405, {"error": "method_not_allowed", "note": "Promoção não é permitida por HTTP."})

    def do_DELETE(self) -> None:
        self._send(405, {"error": "method_not_allowed", "note": "Exclusão de candidatos/backups não é permitida por HTTP."})


class EvolutionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, server_address: tuple[str, int], api_token: str):
        self.api_token = api_token
        super().__init__(server_address, _Handler)


def create_server(host: str | None = None, port: int | None = None, token: str | None = None):
    """Cria servidor. Por segurança, o padrão é localhost; exposição externa exige decisão explícita."""
    api_token = token or _token_configurado()
    if len(api_token) < 24:
        raise ValueError("Token deve ter pelo menos 24 caracteres.")
    bind_host = host or os.getenv("FRIDAY_API_HOST", HOST_DEFAULT)
    bind_port = int(port if port is not None else os.getenv("FRIDAY_API_PORT", PORT_DEFAULT))
    if not 0 <= bind_port <= 65535:
        raise ValueError("Porta inválida.")
    if bind_host in ("0.0.0.0", "::"):
        if os.getenv("FRIDAY_API_ALLOW_REMOTE", "").lower() != "yes":
            raise RuntimeError("Bind externo bloqueado. Configure FRIDAY_API_ALLOW_REMOTE=yes conscientemente.")
    return EvolutionHTTPServer((bind_host, bind_port), api_token)


def main() -> None:
    server = create_server()
    print(f"FRIDAY Evolution API ouvindo em http://{server.server_address[0]}:{server.server_address[1]}")
    print("Modo queue-only: candidatos não são executados/promovidos via HTTP.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
