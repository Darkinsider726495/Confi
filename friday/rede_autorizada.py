"""Descoberta limitada a pares explicitamente autorizados; não varre sub-redes.

FRIDAY_PEERS deve ser uma lista JSON de URLs /health previamente emparelhadas,
por exemplo: ["http://192.168.1.20:8765/health"].
Este módulo só verifica presença/identidade básica; não copia nem executa código remoto.
"""
from __future__ import annotations
import ipaddress
import json
import os
import urllib.error
import urllib.parse
import urllib.request

MAX_PEERS = 32
TIMEOUT = 2.5

def _url_autorizada(url: str) -> bool:
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        if p.username or p.password or p.query or p.fragment:
            return False
        if p.path not in ("", "/", "/health"):
            return False
        # LAN/local only. For HTTPS hostnames, explicit allowlisting is still required.
        try:
            ip = ipaddress.ip_address(p.hostname)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return p.scheme == "https" and "." in p.hostname
    except (ValueError, TypeError):
        return False

def pares_configurados() -> list[str]:
    raw = os.getenv("FRIDAY_PEERS", "[]")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("FRIDAY_PEERS precisa ser uma lista JSON válida.") from e
    if not isinstance(values, list) or len(values) > MAX_PEERS:
        raise ValueError(f"FRIDAY_PEERS deve ser uma lista de até {MAX_PEERS} URLs.")
    peers = []
    for value in values:
        if not isinstance(value, str) or not _url_autorizada(value):
            raise ValueError(f"Peer não permitido: {value!r}. Use somente URL local/LAN previamente autorizada.")
        normalized = value.rstrip("/")
        if normalized.endswith("/health"):
            normalized = normalized[:-7]
        if normalized not in peers:
            peers.append(normalized)
    return peers

def descobrir() -> list[dict]:
    """Verifica somente peers pré-configurados; nunca faz varredura de IPs."""
    encontrados = []
    for base in pares_configurados():
        url = base + "/health"
        req = urllib.request.Request(url, headers={"User-Agent": "FRIDAY-peer-check/1"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                body = response.read(4096)
                ok = response.status == 200
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = {}
                encontrados.append({"url": base, "online": ok, "service": payload.get("service", "unknown")})
        except (urllib.error.URLError, TimeoutError, OSError):
            encontrados.append({"url": base, "online": False, "service": None})
    return encontrados
