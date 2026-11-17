import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "friday"))
import provedor_groq as G


class Response:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


def test_sem_chave_recusa_sem_rede(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    session = Mock()
    try:
        G.chat_completion([{"role": "user", "content": "oi"}], session=session)
        assert False, "deveria exigir chave"
    except G.GroqError as exc:
        assert "GROQ_API_KEY" in str(exc)
    session.post.assert_not_called()


def test_envia_requisicao_sem_vazar_chave_no_retorno(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "segredo-de-teste")
    session = Mock()
    session.post.return_value = Response({"choices": [{"message": {"role": "assistant", "content": "Olá"}}]})
    result = G.chat_completion([{"role": "user", "content": "oi"}], system="sistema", session=session)
    assert result["choices"][0]["message"]["content"] == "Olá"
    args, kwargs = session.post.call_args
    assert args[0] == G.API_URL
    assert kwargs["headers"]["Authorization"] == "Bearer segredo-de-teste"
    assert kwargs["json"]["messages"][0] == {"role": "system", "content": "sistema"}
    assert kwargs["json"]["model"] == G.DEFAULT_MODEL


def test_converte_ferramentas_da_friday(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    session = Mock()
    session.post.return_value = Response({"choices": [{"message": {"content": "ok"}}]})
    G.chat_completion([{"role": "user", "content": "x"}], tools=[{
        "name": "lembrar", "description": "Busca memória", "input_schema": {"type": "object", "properties": {}}
    }], session=session)
    tools = session.post.call_args.kwargs["json"]["tools"]
    assert tools[0]["function"]["name"] == "lembrar"
    assert tools[0]["function"]["parameters"]["type"] == "object"


def test_ciclo_de_ferramenta_so_com_callback_explicito(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    tool_message = {"role": "assistant", "content": None, "tool_calls": [{
        "id": "call-1", "type": "function", "function": {"name": "lembrar", "arguments": json.dumps({"termo": "projeto"})}
    }]}
    final_message = {"role": "assistant", "content": "Encontrei."}
    with patch.object(G, "chat_completion", side_effect=[{"choices": [{"message": tool_message}]}, {"choices": [{"message": final_message}]}]):
        result = G.responder([{"role": "user", "content": "lembra"}], sistema="s", ferramentas=[{"name": "lembrar"}], executar_ferramenta=lambda nome, args: "resultado teste")
    assert result == "Encontrei."


def test_sem_callback_nao_executa_ferramenta(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    tool_message = {"role": "assistant", "content": "", "tool_calls": [{
        "id": "call-1", "type": "function", "function": {"name": "danger", "arguments": "{}"}
    }]}
    with patch.object(G, "chat_completion", return_value={"choices": [{"message": tool_message}]}):
        result = G.responder([{"role": "user", "content": "test"}], sistema="s")
    assert "sem o corretor" in result


def test_cerebro_encaminha_para_groq_sem_chamar_anthropic(monkeypatch):
    import _ambiente as E  # inicializa ambiente isolado dos testes
    import cerebro as C
    import broker as B
    monkeypatch.setenv("IA_PROVEDOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "nao-usar")
    with patch.object(C, "_nuvem_groq", return_value="resposta Groq") as groq, patch.object(C.requests, "post") as post:
        result = C._nuvem([{"role": "user", "content": "oi"}], B.Turno(), "sistema")
    assert result == "resposta Groq"
    groq.assert_called_once()
    post.assert_not_called()


def test_cerebro_groq_exige_chave(monkeypatch):
    import _ambiente as E
    import cerebro as C
    import broker as B
    monkeypatch.setenv("IA_PROVEDOR", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch.object(C, "_nuvem_groq") as groq:
        try:
            C._nuvem([{"role": "user", "content": "oi"}], B.Turno(), "sistema")
            assert False, "deveria exigir a chave Groq"
        except RuntimeError as exc:
            assert "GROQ_API_KEY" in str(exc)
        groq.assert_not_called()
