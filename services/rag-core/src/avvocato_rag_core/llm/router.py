"""LLM router. Wrapper attorno a LiteLLM con fallback chain e Langfuse tracing."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class LLMChunk:
    """Un delta di streaming."""

    content: str
    finish_reason: str | None = None


class LLMRouter:
    """Entry point unificato per chiamate LLM.

    Usa LiteLLM come multiplexer. La catena di fallback è configurata in-place:
    se il modello primario fallisce (rate limit / errore / content filter), passa
    al fallback. Langfuse traccia tutto se configurato.
    """

    def __init__(
        self,
        *,
        primary_model: str,
        fallback_model: str | None = None,
        default_temperature: float = 0.1,
        default_max_tokens: int = 2048,
        extra_params: dict[str, Any] | None = None,
    ) -> None:
        # Import lazy: LiteLLM è pesante e non serve ai worker di solo embedding.
        import litellm

        self._litellm = litellm
        self._primary = primary_model
        self._fallback = fallback_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._extra = extra_params or {}

        litellm.drop_params = True  # compatibilità tra provider con schema differenti
        litellm.set_verbose = False

    async def chat(
        self,
        messages: Iterable[LLMMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        """Chat non-streaming. Ritorna l'intero output concatenato."""
        messages_list = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict[str, Any] = {
            "messages": messages_list,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
            **self._extra,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if trace_id is not None:
            kwargs.setdefault("metadata", {})["trace_id"] = trace_id

        models = [m for m in (model or self._primary, self._fallback) if m]
        resp = await self._litellm.acompletion(
            model=models[0],
            fallbacks=models[1:] or None,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: Iterable[LLMMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        trace_id: str | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Chat streaming. Yielda chunk del delta."""
        messages_list = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict[str, Any] = {
            "messages": messages_list,
            "stream": True,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "max_tokens": max_tokens or self._default_max_tokens,
            **self._extra,
        }
        if trace_id is not None:
            kwargs.setdefault("metadata", {})["trace_id"] = trace_id

        models = [m for m in (model or self._primary, self._fallback) if m]
        stream = await self._litellm.acompletion(
            model=models[0],
            fallbacks=models[1:] or None,
            **kwargs,
        )
        async for part in stream:
            choice = part.choices[0]
            delta = getattr(choice, "delta", None) or {}
            content = getattr(delta, "content", None) or ""
            finish = getattr(choice, "finish_reason", None)
            if content or finish:
                yield LLMChunk(content=content, finish_reason=finish)
