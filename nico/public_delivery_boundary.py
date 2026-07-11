from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any

from fastapi import FastAPI
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PUBLIC_DELIVERY_PATHS = {
    "/delivery/approved/inspect": "inspect",
    "/delivery/approved/redeem": "redeem",
    "/delivery/approved/acknowledge": "acknowledge",
}
DEFAULT_LIMITS = {"inspect": 30, "redeem": 20, "acknowledge": 20}
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_BODY_BYTES = 16 * 1024
MAX_BODY_BYTES_CAP = 64 * 1024
MAX_LIMIT_CAP = 1000
MAX_WINDOW_SECONDS = 3600
PUBLIC_FIELD_LIMITS = {
    "token": 4096,
    "receipt_id": 200,
    "acknowledged_by": 160,
}

_RATE_LIMIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS approved_delivery_rate_limits (
  bucket_key TEXT PRIMARY KEY,
  route TEXT NOT NULL,
  window_started_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  request_count INTEGER NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_approved_delivery_rate_limits_expiry
  ON approved_delivery_rate_limits (expires_at);
"""

_PROCESS_SECRET = secrets.token_bytes(32)
_MEMORY_LOCK = threading.RLock()
_MEMORY_BUCKETS: dict[str, dict[str, int | str]] = {}
_LAST_CLEANUP = 0
_SCHEMA_LOCK = threading.RLock()
_SCHEMA_READY_URL = ""
_SCHEMA_RETRY_AT = 0.0


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def rate_limit_window_seconds() -> int:
    return _bounded_int(
        os.getenv("NICO_DELIVERY_RATE_LIMIT_WINDOW_SECONDS"),
        DEFAULT_WINDOW_SECONDS,
        1,
        MAX_WINDOW_SECONDS,
    )


def public_delivery_max_body_bytes() -> int:
    return _bounded_int(
        os.getenv("NICO_DELIVERY_MAX_BODY_BYTES"),
        DEFAULT_MAX_BODY_BYTES,
        1024,
        MAX_BODY_BYTES_CAP,
    )


def route_limit(route_name: str) -> int:
    env_key = f"NICO_DELIVERY_{route_name.upper()}_RATE_LIMIT"
    return _bounded_int(os.getenv(env_key), DEFAULT_LIMITS.get(route_name, 20), 1, MAX_LIMIT_CAP)


def _secret() -> bytes:
    configured = (
        os.getenv("NICO_DELIVERY_RATE_LIMIT_SECRET", "").strip()
        or os.getenv("NICO_ADMIN_TOKEN", "").strip()
    )
    return configured.encode("utf-8") if configured else _PROCESS_SECRET


def _database_url() -> str:
    if os.getenv("NICO_DISABLE_POSTGRES", "false").lower() == "true":
        return ""
    return os.getenv("DATABASE_URL", "").strip()


def _connect() -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_database_url(), row_factory=dict_row)


def _ensure_schema() -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_RATE_LIMIT_SCHEMA)
        conn.commit()


def _postgres_available() -> bool:
    global _SCHEMA_READY_URL, _SCHEMA_RETRY_AT
    database_url = _database_url()
    if not database_url:
        return False
    monotonic_now = time.monotonic()
    with _SCHEMA_LOCK:
        if _SCHEMA_READY_URL == database_url:
            return True
        if monotonic_now < _SCHEMA_RETRY_AT:
            return False
        try:
            _ensure_schema()
            _SCHEMA_READY_URL = database_url
            _SCHEMA_RETRY_AT = 0.0
            return True
        except Exception:
            _SCHEMA_READY_URL = ""
            _SCHEMA_RETRY_AT = monotonic_now + 30.0
            return False


def _header_map(scope: Scope) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        result[key.decode("latin-1").lower()] = value.decode("latin-1")
    return result


def _normalize_network_identifier(value: str) -> str:
    cleaned = "".join(character for character in str(value or "") if character.isalnum() or character in ".:-_")
    return cleaned[:160] or "unknown"


def client_network_identifier(scope: Scope) -> str:
    headers = _header_map(scope)
    trust_proxy = os.getenv("NICO_TRUST_PROXY_HEADERS", "false").strip().lower() in {"1", "true", "yes", "on"}
    if trust_proxy:
        forwarded = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        candidate = forwarded or headers.get("cf-connecting-ip", "").strip() or headers.get("x-real-ip", "").strip()
        if candidate:
            return _normalize_network_identifier(candidate)
    client = scope.get("client")
    if isinstance(client, tuple) and client:
        return _normalize_network_identifier(str(client[0]))
    return "unknown"


def client_fingerprint(scope: Scope) -> str:
    identifier = client_network_identifier(scope)
    return hmac.new(_secret(), identifier.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _bucket_key(path: str, fingerprint: str, window_started_at: int) -> str:
    material = f"{path}|{fingerprint}|{window_started_at}".encode("utf-8")
    return hmac.new(_secret(), material, hashlib.sha256).hexdigest()


def _increment_memory(bucket_key: str, route: str, expires_at: int, now_epoch: int) -> int:
    global _LAST_CLEANUP
    with _MEMORY_LOCK:
        if now_epoch - _LAST_CLEANUP >= 60:
            expired = [key for key, item in _MEMORY_BUCKETS.items() if int(item.get("expires_at") or 0) <= now_epoch]
            for key in expired:
                _MEMORY_BUCKETS.pop(key, None)
            _LAST_CLEANUP = now_epoch
        item = _MEMORY_BUCKETS.setdefault(
            bucket_key,
            {"route": route, "expires_at": expires_at, "request_count": 0},
        )
        item["request_count"] = int(item.get("request_count") or 0) + 1
        return int(item["request_count"])


def _increment_postgres(bucket_key: str, route: str, window_started_at: int, expires_at: int, now_epoch: int) -> int:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO approved_delivery_rate_limits
                  (bucket_key, route, window_started_at, expires_at, request_count, updated_at)
                VALUES (%s, %s, %s, %s, 1, NOW())
                ON CONFLICT (bucket_key)
                DO UPDATE SET request_count=approved_delivery_rate_limits.request_count + 1,
                              updated_at=NOW()
                RETURNING request_count
                """,
                (bucket_key, route, window_started_at, expires_at),
            )
            row = cur.fetchone()
            if now_epoch % 97 == 0:
                cur.execute("DELETE FROM approved_delivery_rate_limits WHERE expires_at < %s", (now_epoch - 3600,))
        conn.commit()
    return int((row or {}).get("request_count") or 0)


def consume_public_delivery_limit(path: str, fingerprint: str, now_epoch: int | None = None) -> dict[str, Any]:
    route_name = PUBLIC_DELIVERY_PATHS.get(path)
    if not route_name:
        return {"allowed": True, "limited": False}
    now_value = int(time.time()) if now_epoch is None else int(now_epoch)
    window = rate_limit_window_seconds()
    limit = route_limit(route_name)
    window_started_at = now_value - (now_value % window)
    expires_at = window_started_at + window
    bucket_key = _bucket_key(path, fingerprint, window_started_at)
    adapter = "memory"
    try:
        if _postgres_available():
            count = _increment_postgres(bucket_key, route_name, window_started_at, expires_at, now_value)
            adapter = "postgres"
        else:
            count = _increment_memory(bucket_key, route_name, expires_at, now_value)
    except Exception:
        count = _increment_memory(bucket_key, route_name, expires_at, now_value)
        adapter = "memory_fallback"
    remaining = max(0, limit - count)
    return {
        "allowed": count <= limit,
        "limited": True,
        "route": route_name,
        "limit": limit,
        "remaining": remaining,
        "reset_epoch": expires_at,
        "retry_after": max(1, expires_at - now_value),
        "adapter": adapter,
    }


def _security_headers(limit: dict[str, Any] | None = None) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"cache-control", b"no-store, private, max-age=0"),
        (b"pragma", b"no-cache"),
        (b"referrer-policy", b"no-referrer"),
        (b"x-content-type-options", b"nosniff"),
        (b"cross-origin-resource-policy", b"same-site"),
    ]
    if limit and limit.get("limited"):
        headers.extend(
            [
                (b"x-ratelimit-limit", str(limit.get("limit") or 0).encode("ascii")),
                (b"x-ratelimit-remaining", str(limit.get("remaining") or 0).encode("ascii")),
                (b"x-ratelimit-reset", str(limit.get("reset_epoch") or 0).encode("ascii")),
            ]
        )
    return headers


def _json_response(status_code: int, payload: dict[str, Any], limit: dict[str, Any] | None = None) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]
    headers.extend(_security_headers(limit))
    if status_code == 429 and limit:
        headers.append((b"retry-after", str(limit.get("retry_after") or 1).encode("ascii")))
    return body, headers


def _oversized_public_field(path: str, body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    fields = ["token"]
    if path == "/delivery/approved/acknowledge":
        fields.extend(["receipt_id", "acknowledged_by"])
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and len(value) > PUBLIC_FIELD_LIMITS[field]:
            return field
    return ""


class PublicDeliveryBoundaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "").rstrip("/") or "/"
        method = str(scope.get("method") or "GET").upper()
        if path not in PUBLIC_DELIVERY_PATHS or method != "POST":
            await self.app(scope, receive, send)
            return

        limit = consume_public_delivery_limit(path, client_fingerprint(scope))
        if not limit.get("allowed"):
            body, headers = _json_response(
                429,
                {
                    "status": "blocked",
                    "code": "public_delivery_rate_limited",
                    "message": "This delivery request is temporarily unavailable. Retry after the indicated interval.",
                },
                limit,
            )
            await send({"type": "http.response.start", "status": 429, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        headers = _header_map(scope)
        max_body = public_delivery_max_body_bytes()
        declared_length = headers.get("content-length", "").strip()
        if declared_length:
            try:
                if int(declared_length) > max_body:
                    body, response_headers = _json_response(
                        413,
                        {
                            "status": "blocked",
                            "code": "public_delivery_request_too_large",
                            "message": "This delivery request exceeds the allowed size.",
                        },
                        limit,
                    )
                    await send({"type": "http.response.start", "status": 413, "headers": response_headers})
                    await send({"type": "http.response.body", "body": body})
                    return
            except ValueError:
                pass

        buffered = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                continue
            buffered.extend(message.get("body") or b"")
            more_body = bool(message.get("more_body"))
            if len(buffered) > max_body:
                body, response_headers = _json_response(
                    413,
                    {
                        "status": "blocked",
                        "code": "public_delivery_request_too_large",
                        "message": "This delivery request exceeds the allowed size.",
                    },
                    limit,
                )
                await send({"type": "http.response.start", "status": 413, "headers": response_headers})
                await send({"type": "http.response.body", "body": body})
                return

        oversized_field = _oversized_public_field(path, bytes(buffered))
        if oversized_field:
            body, response_headers = _json_response(
                413,
                {
                    "status": "blocked",
                    "code": "public_delivery_field_too_large",
                    "message": "This delivery request contains a field that exceeds the allowed size.",
                },
                limit,
            )
            await send({"type": "http.response.start", "status": 413, "headers": response_headers})
            await send({"type": "http.response.body", "body": body})
            return

        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": bytes(buffered), "more_body": False}

        async def secured_send(message: Message) -> None:
            if message.get("type") == "http.response.start":
                existing = list(message.get("headers") or [])
                existing_names = {key.lower() for key, _ in existing}
                for key, value in _security_headers(limit):
                    if key not in existing_names:
                        existing.append((key, value))
                message = {**message, "headers": existing}
            await send(message)

        await self.app(scope, replay_receive, secured_send)


def install_public_delivery_boundary(target: FastAPI) -> FastAPI:
    if bool(getattr(target.state, "nico_public_delivery_boundary", False)):
        return target
    target.user_middleware.append(Middleware(PublicDeliveryBoundaryMiddleware))
    target.middleware_stack = None
    target.state.nico_public_delivery_boundary = True
    target.openapi_schema = None
    return target


def public_delivery_boundary_status() -> dict[str, Any]:
    return {
        "status": "ready",
        "paths": sorted(PUBLIC_DELIVERY_PATHS),
        "window_seconds": rate_limit_window_seconds(),
        "limits": {name: route_limit(name) for name in sorted(DEFAULT_LIMITS)},
        "max_body_bytes": public_delivery_max_body_bytes(),
        "field_limits": dict(PUBLIC_FIELD_LIMITS),
        "trusted_proxy_headers": os.getenv("NICO_TRUST_PROXY_HEADERS", "false").strip().lower() in {"1", "true", "yes", "on"},
        "persistence": "postgres_when_available_with_memory_fallback",
        "privacy": "Client network identifiers are HMAC-fingerprinted and are not stored or audited in raw form.",
    }
