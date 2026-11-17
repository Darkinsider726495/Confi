"""Adaptador opcional da API Groq (modelos Llama), sem SDK e sem dependência de OpenAI/Anthropic.

A chave é lida exclusivamente de GROQ_API_KEY no ambiente/.env. Nunca registrar cabeçalhos,
chave ou conteúdo integral das conversas em logs. A API é externa: os prompts enviados saem do aparelho.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

import requests

API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


RACIOCINIO_FOLGA = 600


def _extras_raciocinio(modelo: str) -> dict[str, Any]:
    """Opções para modelos que raciocinam antes de responder (cada família aceita parâmetros diferentes na Groq)."""
    m = (modelo or "").lower()
    if "gpt-oss" in m:
        return {"reasoning_effort": "low", "include_reasoning": False}
    if "qwen3" in m or "qwq" in m or "deepseek-r1" in m or "reasoning" in m:
        return {"reasoning_format": "hidden"}
    return {}


class GroqError(RuntimeError):
    """Erro de configuração ou resposta da API Groq."""


def _tools_openai(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Converte as definições do corretor da FRIDAY para o formato OpenAI-compatible."""
    result = []
    for tool in tools or []:
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            result.append(tool)
            continue
        name = tool.get("name")
        if not name:
            continue
        result.append({"type": "function", "function": {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        }})
    return result


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    max_tokens: int = 500,
    timeout: float = 40,
    session: Any = requests,
) -> dict[str, Any]:
    """Faz uma chamada Groq e devolve o JSON de chat completion.

    `messages` deve conter mensagens user/assistant (e tool se necessário), sem a chave API.
    """
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        raise GroqError("GROQ_API_KEY não configurada")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages precisa ser uma lista não vazia")
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)
    modelo = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    payload: dict[str, Any] = {
        "model": modelo,
        "messages": payload_messages,
        "max_tokens": max(1, min(int(max_tokens), 8192)),
        "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.3")),
    }
    extras = _extras_raciocinio(modelo)
    if extras:
        # modelo que «pensa» antes de responder: pouco raciocínio, escondido, e folga de tokens — senão uma resposta curta
        # (ex.: os assuntos da assimilação, 40 tokens) volta VAZIA, porque o orçamento todo foi gasto pensando.
        payload.update(extras)
        payload["max_tokens"] = min(8192, payload["max_tokens"] + RACIOCINIO_FOLGA)
    converted = _tools_openai(tools)
    if converted:
        payload["tools"] = converted
        payload["tool_choice"] = "auto"
    try:
        response = session.post(
            os.getenv("GROQ_API_URL", API_URL),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        if extras and getattr(response, "status_code", 200) == 400:
            simples = {k: v for k, v in payload.items() if k not in extras}   # a Groq recusou as opções de raciocínio: uma vez sem elas
            response = session.post(
                os.getenv("GROQ_API_URL", API_URL),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=simples,
                timeout=timeout,
            )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        # Não incluir cabeçalhos ou o objeto request, que pode conter a chave.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        suffix = f" (HTTP {status})" if status else ""
        raise GroqError(f"Falha na chamada à Groq{suffix}") from None
    except (ValueError, TypeError, AttributeError):
        raise GroqError("Resposta inválida da API Groq") from None
    if not isinstance(data, dict) or not data.get("choices"):
        raise GroqError("A API Groq não retornou choices")
    return data


def responder(
    mensagens: list[dict[str, Any]],
    *,
    sistema: str,
    max_tokens: int = 500,
    ferramentas: list[dict[str, Any]] | None = None,
    executar_ferramenta: Callable[[str, dict[str, Any]], str] | None = None,
    max_ciclos_ferramentas: int = 4,
) -> str:
    """Gera uma resposta e, se habilitado, percorre chamadas de ferramentas validadas pelo corretor.

    As ferramentas só são executadas pelo callback fornecido pelo chamador; este módulo não
    importa nem executa comandos arbitrários sugeridos pelo modelo.
    """
    msgs = [dict(m) for m in mensagens]
    for _ in range(max(1, min(max_ciclos_ferramentas, 6))):
        data = chat_completion(msgs, system=sistema, tools=ferramentas, max_tokens=max_tokens)
        message = data["choices"][0].get("message") or {}
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return (content or "").strip()
        if executar_ferramenta is None:
            # Não executar ferramentas se o chamador não forneceu corretor explícito.
            return (content or "Não posso executar ferramentas sem o corretor de segurança.").strip()
        msgs.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name")
            try:
                args = json.loads(function.get("arguments") or "{}")
            except (TypeError, json.JSONDecodeError):
                args = {}
            if not isinstance(args, dict) or not isinstance(name, str) or not name:
                result = "Chamada recusada: argumentos inválidos."
            else:
                try:
                    result = str(executar_ferramenta(name, args))
                except Exception:
                    result = "A ferramenta falhou; nenhum detalhe interno foi exposto."
            msgs.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result[:12000]})
    return "Não consegui concluir isso dentro do limite de chamadas de ferramentas."
