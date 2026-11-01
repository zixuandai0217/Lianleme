"""Content-free observability at the provider boundary.

Only counts and allowlisted metadata cross this boundary. Never pass an exception
message, prompt, provider response or credentials to the logger: SDK exceptions
can embed all of those, and the catch-all logger renders exception text into the
stack field. Upstream failures therefore cross this boundary as ``LLMCallError``
(category label only), never as the original SDK exception.

A successful transport is not the same as usable output, so callers record
degradation separately through :func:`degraded`.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.core.logging import (
    EVENT_LLM_COMPLETED,
    EVENT_LLM_DEGRADED,
    EVENT_LLM_FAILED,
    FIELD_DEPENDENCY,
    FIELD_DURATION_MS,
    FIELD_ERROR_CATEGORY,
    FIELD_ERROR_CLASS,
    FIELD_ERROR_CODE,
    FIELD_IMAGE_SIZE_BYTES,
    FIELD_LLM_MODE,
    FIELD_MODEL_PURPOSE,
    FIELD_PROMPT_CHARS,
    log_event,
)

logger = logging.getLogger("app.llm")

PURPOSE_CHAT = "chat"
PURPOSE_VISION = "vision"
PURPOSE_VOICE = "voice"

MODE_BYOK = "byok"
MODE_SYSTEM = "system"

ERROR_CATEGORY_AUTH = "auth"
ERROR_CATEGORY_RATE_LIMIT = "rate_limit"
ERROR_CATEGORY_TIMEOUT = "timeout"
ERROR_CATEGORY_NETWORK = "network"
ERROR_CATEGORY_OUTPUT_PARSE = "output_parse"
ERROR_CATEGORY_UNKNOWN = "unknown"

# Degradation reasons: output-quality classifications, not task error codes.
DEGRADED_OUTPUT_UNPARSEABLE = "output_parse"
DEGRADED_MARKDOWN_WRAPPED = "markdown_wrapped"

_SAFE_CATEGORY_LABELS = {
    ERROR_CATEGORY_AUTH: "authentication",
    ERROR_CATEGORY_RATE_LIMIT: "rate limit",
    ERROR_CATEGORY_TIMEOUT: "timeout",
    ERROR_CATEGORY_NETWORK: "connection",
    ERROR_CATEGORY_OUTPUT_PARSE: "output parse",
}


class LLMCallError(RuntimeError):
    """Safe failure crossing into route/task exception logging."""

    def __init__(self, category: str):
        self.category = category
        label = _SAFE_CATEGORY_LABELS.get(category, "unknown")
        super().__init__(f"LLM {label} failure")


@dataclass(frozen=True)
class ClientProvenance:
    """Non-secret provider identity; safe to carry in Graph state."""

    dependency: str = "unknown"
    llm_mode: str = "unknown"


@dataclass(frozen=True)
class MessageMetadata:
    """Content-free size facts about an outgoing prompt."""

    prompt_chars: int = 0
    image_size_bytes: int = 0


def error_category(exc: BaseException) -> str:
    """Classify SDK failures without ever rendering their content in a log."""
    name = type(exc).__name__.lower()
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403) or "authentication" in name or "permissiondenied" in name:
        return ERROR_CATEGORY_AUTH
    if status == 429 or "ratelimit" in name:
        return ERROR_CATEGORY_RATE_LIMIT
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or "timeout" in name:
        return ERROR_CATEGORY_TIMEOUT
    if isinstance(exc, ConnectionError) or "connection" in name or "network" in name:
        return ERROR_CATEGORY_NETWORK
    if "parser" in name or "jsondecode" in name:
        return ERROR_CATEGORY_OUTPUT_PARSE
    return ERROR_CATEGORY_UNKNOWN


def client_provenance(client: Any) -> ClientProvenance:
    """Snapshot provider + credential provenance from a client or a snapshot."""
    if isinstance(client, ClientProvenance):
        return client
    return ClientProvenance(
        dependency=getattr(client, "llm_provider", "unknown"),
        llm_mode=getattr(client, "llm_mode", "unknown"),
    )


def message_metadata(messages: Any) -> MessageMetadata:
    """Count prompt characters and embedded image bytes, never return content."""
    chars = images = 0
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    chars += len(str(block.get("text", "")))
                elif block.get("type") == "image_url":
                    url = block.get("image_url", {}).get("url", "")
                    if isinstance(url, str) and url.startswith("data:") and "," in url:
                        encoded = url.split(",", 1)[1]
                        padding = len(encoded) - len(encoded.rstrip("="))
                        images += max(0, len(encoded) * 3 // 4 - padding)
    return MessageMetadata(prompt_chars=chars, image_size_bytes=images)


def _log_outcome(
    provenance: ClientProvenance,
    purpose: str,
    *,
    started: float,
    metadata: MessageMetadata,
    exc: BaseException | None = None,
) -> None:
    fields: dict[str, Any] = {
        FIELD_DEPENDENCY: provenance.dependency,
        FIELD_MODEL_PURPOSE: purpose,
        FIELD_LLM_MODE: provenance.llm_mode,
        FIELD_DURATION_MS: round((time.perf_counter() - started) * 1000, 3),
        FIELD_PROMPT_CHARS: metadata.prompt_chars,
        FIELD_IMAGE_SIZE_BYTES: metadata.image_size_bytes,
    }
    if exc is not None:
        fields[FIELD_ERROR_CATEGORY] = error_category(exc)
        fields[FIELD_ERROR_CLASS] = type(exc).__name__
    log_event(
        logger,
        EVENT_LLM_FAILED if exc else EVENT_LLM_COMPLETED,
        message="模型调用失败" if exc else "模型调用完成",
        level=logging.WARNING if exc else logging.INFO,
        **fields,
    )


async def invoke(client: Any, messages: Any, *, purpose: str = PURPOSE_CHAT) -> Any:
    """Invoke a provider and emit exactly one content-free outcome event."""
    provenance = client_provenance(client)
    metadata = message_metadata(messages)
    started = time.perf_counter()
    try:
        response = await client.ainvoke(messages)
    except Exception as exc:
        _log_outcome(provenance, purpose, started=started, metadata=metadata, exc=exc)
        raise LLMCallError(error_category(exc)) from None
    _log_outcome(provenance, purpose, started=started, metadata=metadata)
    return response


async def stream(client: Any, messages: Any, *, purpose: str = PURPOSE_CHAT) -> AsyncIterator[Any]:
    """Observe the whole stream, not each token (no per-token log spam)."""
    provenance = client_provenance(client)
    metadata = message_metadata(messages)
    started = time.perf_counter()
    try:
        async for chunk in client.astream(messages):
            yield chunk
    except Exception as exc:
        _log_outcome(provenance, purpose, started=started, metadata=metadata, exc=exc)
        raise LLMCallError(error_category(exc)) from None
    _log_outcome(provenance, purpose, started=started, metadata=metadata)


@contextmanager
def voice_call(*, mode: str, prompt_chars: int):
    """Observe the REST speech provider using the same outcome vocabulary.

    ``mode`` is resolved by the caller from the credential it actually used; the
    speech runtime must not guess provenance from "is an api_key passed".
    """
    provenance = ClientProvenance(dependency="qwen", llm_mode=mode)
    metadata = MessageMetadata(prompt_chars=prompt_chars)
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        # Qwen wraps HTTP errors; inspect only the cause's type/status, never text.
        cause = exc.__cause__ or exc
        _log_outcome(provenance, PURPOSE_VOICE, started=started, metadata=metadata, exc=cause)
        raise LLMCallError(error_category(cause)) from None
    _log_outcome(provenance, PURPOSE_VOICE, started=started, metadata=metadata)


def degraded(
    client: Any,
    *,
    purpose: str = PURPOSE_CHAT,
    reason: str = DEGRADED_OUTPUT_UNPARSEABLE,
) -> None:
    """Record an unusable/wrapped response independently of transport success."""
    provenance = client_provenance(client)
    log_event(
        logger,
        EVENT_LLM_DEGRADED,
        message="模型输出降级",
        level=logging.WARNING,
        **{
            FIELD_DEPENDENCY: provenance.dependency,
            FIELD_MODEL_PURPOSE: purpose,
            FIELD_LLM_MODE: provenance.llm_mode,
            FIELD_ERROR_CODE: reason,
            FIELD_ERROR_CATEGORY: ERROR_CATEGORY_OUTPUT_PARSE,
        },
    )
