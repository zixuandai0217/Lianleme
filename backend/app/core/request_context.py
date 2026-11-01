"""Request-scoped correlation identifiers propagated through context variables.

The middleware writes a request identifier into the current context so every log
event produced while handling that request carries the same value. Background
tasks re-bind the stored values when they start executing, which keeps
"request -> task -> result" on one correlation line.
"""

import contextvars
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

REQUEST_ID_HEADER = "X-Request-ID"

# Accept common trace-id shapes (hex, uuid, w3c-like); reject anything that could
# be reflected verbatim into responses or logs (spaces, markup, overlong values).
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lianleme_request_id", default=None
)
_user_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "lianleme_user_id", default=None
)
_task_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lianleme_task_id", default=None
)
_attempt_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "lianleme_attempt", default=None
)


def new_request_id() -> str:
    """Return an unguessable request identifier."""
    return secrets.token_hex(16)


def is_valid_request_id(value: str | None) -> bool:
    """Report whether an inbound identifier is safe to reuse verbatim."""
    if not value or not isinstance(value, str):
        return False
    return REQUEST_ID_PATTERN.match(value.strip()) is not None


def resolve_request_id(candidate: str | None) -> str:
    """Reuse a well-formed inbound identifier; otherwise mint a fresh one."""
    if isinstance(candidate, str):
        candidate = candidate.strip()
        if is_valid_request_id(candidate):
            return candidate
    return new_request_id()


def get_request_id() -> str | None:
    """Return the identifier of the request currently being handled, if any."""
    return _request_id_var.get()


def get_user_id() -> int | None:
    """Return the authenticated user of the current context, if any."""
    return _user_id_var.get()


def set_user_id(value: int | None) -> contextvars.Token:
    """Bind the authenticated user to the current context."""
    return _user_id_var.set(value)


def get_task_id() -> str | None:
    """Return the background task identifier of the current context."""
    return _task_id_var.get()


def get_attempt() -> int | None:
    """Return the background task attempt number of the current context."""
    return _attempt_var.get()


@contextmanager
def bind_request_context(
    *,
    request_id: str | None = None,
    user_id: int | None = None,
    task_id: str | None = None,
    attempt: int | None = None,
) -> Iterator[None]:
    """Temporarily bind correlation values for the enclosed block."""
    bindings = (
        (_request_id_var, request_id),
        (_user_id_var, user_id),
        (_task_id_var, task_id),
        (_attempt_var, attempt),
    )
    tokens = [(variable, variable.set(value)) for variable, value in bindings]
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
