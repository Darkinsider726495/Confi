import os
from unittest.mock import Mock, patch
import pytest
from friday import ponte_ia

class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)
    def json(self):
        return self.data

def test_prompt_vazio_rejeitado():
    with pytest.raises(ValueError):
        ponte_ia.responder("  ")

def test_limite_de_prompt():
    with pytest.raises(ValueError):
        ponte_ia.responder("x" * (ponte_ia.MAX_PROMPT_CHARS + 1))

def test_local_primeiro_sem_chamar_nuvem(monkeypatch):
    monkeypatch.setenv("FRIDAY_HYBRID_ORDER", "local_first")
    monkeypatch.setenv("FRIDAY_HYBRID_CLOUD_FALLBACK", "yes")
    session = Mock()
    session.post.return_value = Response({"message": {"content": "resposta local"}})
    with patch.object(ponte_ia, "_groq") as groq:
        result = ponte_ia.responder("oi", session=session)
    assert result == {"text": "resposta local", "provider": "ollama"}
    groq.assert_not_called()

def test_fallback_para_groq_quando_local_falha(monkeypatch):
    monkeypatch.setenv("FRIDAY_HYBRID_ORDER", "local_first")
    monkeypatch.setenv("FRIDAY_HYBRID_CLOUD_FALLBACK", "yes")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    session = Mock()
    session.post.side_effect = OSError("offline")
    with patch.object(ponte_ia, "_groq", return_value="resposta nuvem") as groq:
        result = ponte_ia.responder("oi", session=session)
    assert result == {"text": "resposta nuvem", "provider": "groq"}
    groq.assert_called_once()

def test_fallback_nuvem_desativado(monkeypatch):
    monkeypatch.setenv("FRIDAY_HYBRID_ORDER", "local_first")
    monkeypatch.setenv("FRIDAY_HYBRID_CLOUD_FALLBACK", "no")
    session = Mock()
    session.post.side_effect = OSError("offline")
    with pytest.raises(ponte_ia.PonteIAError):
        ponte_ia.responder("segredo", session=session)

def test_api_chat_exige_autenticacao(monkeypatch):
    from friday.api_evolutiva import create_server
    from threading import Thread
    import urllib.request, urllib.error, json
    token = "t" * 32
    server = create_server("127.0.0.1", 0, token)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/v1/ia/chat"
        req = urllib.request.Request(url, data=json.dumps({"prompt":"oi"}).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=2)
        assert exc.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
