import json
import os
import threading
import urllib.request
import urllib.error

import pytest

from friday.api_evolutiva import create_server


@pytest.fixture
def api_server(monkeypatch):
    token = "test-token-for-friday-api-123456789"
    server = create_server("127.0.0.1", 0, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", token
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(url, token=None, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_public(api_server):
    base, _ = api_server
    status, data = request(base + "/health")
    assert status == 200 and data["ok"] is True


def test_requires_token(api_server):
    base, _ = api_server
    status, _ = request(base + "/v1/status")
    assert status == 401


def test_status_with_token(api_server):
    base, token = api_server
    status, data = request(base + "/v1/status", token)
    assert status == 200
    assert data["mode"] == "queue-only"
    assert data["promotion_over_http"] is False


def test_promotion_not_allowed_http(api_server):
    base, token = api_server
    status, data = request(base + "/v1/candidates/x", token, method="PUT", payload={})
    assert status == 404 or status == 405
    assert data["error"] in ("not_found", "method_not_allowed")


def test_external_bind_blocked(monkeypatch):
    monkeypatch.delenv("FRIDAY_API_ALLOW_REMOTE", raising=False)
    with pytest.raises(RuntimeError):
        create_server("0.0.0.0", 8765, "test-token-for-friday-api-123456789")
