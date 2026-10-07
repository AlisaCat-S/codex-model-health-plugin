from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit

import httpx

from .errors import RequestError, http_error_detail, network_failure
from .proxies import http_client_options
from .rate_limit import RateLimitGate
from .security import SecretGuard
from .utils import normalize_api_base_url, recognized_provider

from .protocol import build_payload, parse_stream, GPT_USER_AGENT, CLAUDE_USER_AGENT

MAX_RESPONSE_BYTES = 1024 * 1024


class AsyncTransport:
    def __init__(self, secrets: list[str] = (), *, timeout: float = 120, concurrency: int = 32, gates=None):
        self.guard = SecretGuard(secrets)
        self.timeout = timeout
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._gates: dict[str, RateLimitGate] = gates if gates is not None else {}
        self._slots = asyncio.Semaphore(concurrency)

    async def close(self) -> None:
        try:
            failures = await asyncio.gather(*(client.aclose() for client in self._clients.values()), return_exceptions=True)
            for error in failures:
                if isinstance(error,BaseException):
                    raise error
        finally:
            self._clients.clear()
            self.guard = SecretGuard()

    async def models(self, base_url, key, *, allow_insecure=False):
        from .model_list import parse_models
        base = normalize_api_base_url(base_url, allow_insecure=allow_insecure)
        guard = self.guard.including(key)
        guard.check(base, code='credential_in_configuration')
        status = None
        try:
            async with self._slots, asyncio.timeout(30):
                async with self._client(base).stream('GET', base + '/models',
                        headers={'Authorization': 'Bearer ' + key}) as response:
                    status = response.status_code
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise RequestError('response_too_large', status=status)
                decoded = raw.decode('utf-8', errors='strict' if status == 200 else 'replace')
                guard.check(decoded)
                if status != 200:
                    raise RequestError('upstream_http_error', status=status,
                                       evidence={'upstream': http_error_detail(decoded, guard)})
                return parse_models(decoded, guard)
        except RequestError as exc:
            exc.status = status
            raise
        except (httpx.HTTPError, OSError, UnicodeError) as exc:
            raise network_failure(exc, guard, status=status) from exc

    def _client(self, base: str) -> httpx.AsyncClient:
        if base not in self._clients:
            self._clients[base] = httpx.AsyncClient(
                **http_client_options(base),
                timeout=httpx.Timeout(self.timeout, connect=min(15, self.timeout)),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return self._clients[base]

    async def request(self, mode: str, base_url: str, key: str, model: str, cell: dict,
                      *, allow_insecure: bool = False, on_dispatch=None) -> dict:
        return await self._request(mode, base_url, key, model, cell, allow_insecure=allow_insecure, on_dispatch=on_dispatch)

    async def _request(self, mode: str, base_url: str, key: str, model: str, cell: dict,
                      *, allow_insecure: bool = False, on_dispatch=None) -> dict:
        base = normalize_api_base_url(base_url, allow_insecure=allow_insecure)
        guard = self.guard.including(key)
        payload = build_payload(mode, model, cell)
        guard.check({"base":base, "payload":payload}, code="credential_in_configuration")
        origin = urlsplit(base)
        if origin.port == {"http": 80, "https": 443}.get(origin.scheme):
            host = origin.hostname
            origin = origin._replace(netloc=f"[{host}]" if ":" in host else host)
        gate = self._gates.setdefault(origin.geturl(), RateLimitGate(max_in_flight=4 if recognized_provider(base) == "openrouter" else None))
        await gate.acquire()
        response_headers, status = {}, None
        started = time.monotonic()
        raw, body_complete = bytearray(), False
        credential_echo = False

        def exchange():
            if credential_echo:
                return {"http_status": status, "body_complete": False, "redacted": True}
            return guard.redact({"request_json": payload, "response_utf8": bytes(raw).decode("utf-8", errors="replace"),
                "headers": response_headers, "http_status": status, "body_complete": body_complete})

        try:
            async with self._slots, asyncio.timeout(self.timeout):
                path = {"gpt":"/responses", "claude":"/messages", "chat":"/chat/completions"}[mode]
                headers = {"Authorization": "Bearer " + key, "Content-Type":"application/json",
                           "Accept":"text/event-stream", "User-Agent": {"gpt": GPT_USER_AGENT, "claude": CLAUDE_USER_AGENT}.get(mode, "meow-llm-detector/4.5.0")}
                if mode == "claude":
                    headers["anthropic-version"] = "2023-06-01"
                client = self._client(base)
                if on_dispatch:
                    on_dispatch()
                async with client.stream("POST", base + path, json=payload, headers=headers) as response:
                    status = response.status_code
                    response_headers = dict(response.headers)
                    guard.check(response_headers)
                    async for chunk in response.aiter_bytes():
                        if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                            raw.extend(chunk[:MAX_RESPONSE_BYTES - len(raw)])
                            raise RequestError("response_too_large")
                        raw.extend(chunk)
                body_complete = True
                raw = bytes(raw)
                decoded = raw.decode("utf-8", errors="strict" if status is not None and 200 <= status < 300 else "replace")
                guard.check(decoded)
                if status is None or not 200 <= status < 300:
                    evidence = {"upstream": http_error_detail(decoded, guard)}
                    raise RequestError("redirect_rejected" if status and 300 <= status < 400 else "upstream_http_error",
                                       status=status,
                                       headers=response_headers, evidence=evidence)
                result = parse_stream(decoded, mode, guard)
                guard.check(result)
                result.update({"http_status":status, "elapsed_ms":round((time.monotonic() - started) * 1000),
                               "request_json":payload, "response_utf8":decoded,
                               "headers":guard.redact(response_headers), "body_complete": True})
                return result
        except RequestError as exc:
            credential_echo = exc.code == "credential_echo"
            guard.check(exc.evidence)
            exc.exchange = exchange()
            if status is not None:
                exc.status = status
            status = exc.rate_status
            if not exc.headers:
                exc.headers = response_headers
            exc.headers = guard.redact(exc.headers)
            raise
        except (httpx.HTTPError, OSError, UnicodeError) as exc:
            error = network_failure(exc, guard, status=status)
            error.exchange = exchange()
            raise error from exc
        except asyncio.CancelledError as exc:
            exc.exchange = exchange()
            raise
        finally:
            await gate.observe(response_headers, status)
