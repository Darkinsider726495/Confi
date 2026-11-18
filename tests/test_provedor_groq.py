import unittest
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


class Resp400(Response):
    status_code = 400


def test_modelo_que_raciocina_pede_pouco_raciocinio_escondido_e_folga(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "segredo-de-teste")
    session = Mock()
    session.post.return_value = Response({"choices": [{"message": {"role": "assistant", "content": "conectada."}}]})
    G.chat_completion([{"role": "user", "content": "oi"}], model="openai/gpt-oss-120b", max_tokens=40, session=session)
    corpo = session.post.call_args.kwargs["json"]
    assert corpo["reasoning_effort"] == "low" and corpo["include_reasoning"] is False
    assert corpo["max_tokens"] == 40 + G.RACIOCINIO_FOLGA          # senão os 40 tokens vão todos para o raciocínio e a resposta vem vazia


def test_modelo_comum_nao_recebe_opcoes_de_raciocinio(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "segredo-de-teste")
    session = Mock()
    session.post.return_value = Response({"choices": [{"message": {"role": "assistant", "content": "oi"}}]})
    G.chat_completion([{"role": "user", "content": "oi"}], model="llama-3.3-70b-versatile", max_tokens=40, session=session)
    corpo = session.post.call_args.kwargs["json"]
    assert "reasoning_effort" not in corpo and "reasoning_format" not in corpo and corpo["max_tokens"] == 40


def test_se_a_groq_recusar_as_opcoes_tenta_de_novo_sem_elas(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "segredo-de-teste")
    session = Mock()
    session.post.side_effect = [Resp400({}), Response({"choices": [{"message": {"role": "assistant", "content": "oi"}}]})]
    r = G.chat_completion([{"role": "user", "content": "oi"}], model="qwen/qwen3-32b", session=session)
    assert r["choices"][0]["message"]["content"] == "oi"
    assert session.post.call_count == 2
    assert "reasoning_format" in session.post.call_args_list[0].kwargs["json"]
    assert "reasoning_format" not in session.post.call_args_list[1].kwargs["json"]


class LimiteDaGroq(unittest.TestCase):
    def test_429_anota_o_limite_estudo_espera_e_a_conversa_explica(self):
        import provedor_groq as G, cerebro as C
        from unittest import mock as _m
        resp = _m.Mock(status_code=429, headers={"retry-after": "120"})
        resp.raise_for_status.side_effect = G.requests.HTTPError(response=resp)
        sess = _m.Mock(post=_m.Mock(return_value=resp))
        G.LIMITE["ate"] = 0.0
        self.addCleanup(lambda: G.LIMITE.update(ate=0.0))
        with _m.patch.dict(os.environ, {"GROQ_API_KEY": "gsk_teste"}):
            with self.assertRaises(G.GroqError):
                G.chat_completion([{"role": "user", "content": "oi"}], session=sess)
        self.assertGreater(G.limitada(), 100)
        with _m.patch.dict(os.environ, {"IA_PROVEDOR": "groq", "GROQ_API_KEY": "gsk_teste"}), _m.patch.object(C.F, "contar_llm", return_value=True) as cont:
            self.assertIsNone(C.resumir("x", "texto", fracao=0.5))          # estudo dela: nem tenta, deixa a cota para o dono
            cont.assert_not_called()
            with _m.patch.object(C, "_nuvem", side_effect=G.GroqError("HTTP 429")), _m.patch.object(C, "_local", return_value=C._SEM_LOCAL):
                r = C._responder("oi")
        self.assertIn("limite de uso", r)
        self.assertNotIn("sem conexão", r)

