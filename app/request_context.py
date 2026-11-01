from contextvars import ContextVar

current_request_id: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)