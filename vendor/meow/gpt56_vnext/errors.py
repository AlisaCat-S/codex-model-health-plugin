from __future__ import annotations

from typing import Any
import socket
import ssl


SAFETY_STOP_CODES = ("credential_echo", "credential_in_configuration", "unsafe_destination")


class UnsafeDestinationError(OSError):
    """The public service must not connect to a private or reserved address."""


class AppError(ValueError):
    def __init__(self, code: str, *, field: str | None = None, status: int = 400):
        super().__init__(code)
        self.code = code
        self.field = field
        self.status = status

    def public(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field}


class RequestError(Exception):
    def __init__(self, code: str, *, status: int | None = None,
                 retryable: bool = True, headers: dict | None = None,
                 evidence: dict | None = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.headers = headers or {}
        self.evidence = evidence or {}

    def public(self) -> dict[str, Any]:
        return {"code": self.code, "http_status": self.status,
                "retryable": self.retryable,
                **{name: self.evidence[name] for name in ("upstream", "local") if self.evidence.get(name)}}

    @property
    def rate_status(self):
        detail = self.evidence.get("upstream", {})
        return 429 if str(detail.get("code")) == "429" or detail.get("type") == "rate_limit_error" else self.status


def network_failure(exc, guard, *, status=None):
    """Classify the actual cause; retain its redacted text separately from HTTP errors."""
    chain, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__
    kinds = {base.__name__ for error in chain for base in type(error).__mro__}
    rules = (
        ("unsafe_destination", "security", (UnsafeDestinationError,), set()),
        ("dns_error", "dns", (socket.gaierror,), {"ClientConnectorDNSError"}),
        ("tls_error", "tls", (ssl.SSLError,), {"ClientSSLError"}),
        ("response_decode_error", "decode", (UnicodeError,), {"DecodingError", "ContentEncodingError"}),
        ("request_timeout", "timeout", (TimeoutError,), {"TimeoutException"}),
        ("response_read_error", "read", (), {"ClientPayloadError", "RemoteProtocolError", "ServerDisconnectedError"}),
    )
    code, source = "connection_error", "connection"
    cause = chain[-1]
    for candidate, origin, types, names in rules:
        if any(isinstance(error, types) for error in chain) or kinds & names:
            code, source = candidate, origin
            cause = next(error for error in reversed(chain)
                         if isinstance(error, types) or names & {base.__name__ for base in type(error).__mro__})
            break
    return RequestError(code, status=status, retryable=code not in SAFETY_STOP_CODES,
                        evidence={"local": {"source": source, "type": type(cause).__name__,
                                             "message": guard.redact_message(str(cause))}})


def upstream_detail(value, guard=None):
    """Keep bounded diagnostic fields, not arbitrary request/account objects."""
    if isinstance(value, dict):
        value = value.get("error") or value
    if not isinstance(value, dict):
        value = {"message": str(value)}
    result = {name: str(value[name])[:2048] for name in ("type", "code", "message", "reason")
              if value.get(name) is not None and isinstance(value[name], (str, int))}
    if guard is None:
        from .security import SecretGuard
        guard = SecretGuard([])
    return {name: guard.redact_message(text) for name, text in result.items()}


def http_error_detail(body, guard):
    import json
    try:
        value = json.loads(body)
    except (ValueError, TypeError):
        value = body
    return upstream_detail(value, guard)
