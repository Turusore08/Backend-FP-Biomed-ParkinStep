import hashlib
import json
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.application.interfaces import TokenProviderPort, UnitOfWorkFactory
from src.domain.entities import IdempotencyRecord
from src.domain.enums import IdempotencyState
from src.domain.exceptions import (
    DomainError,
    IdempotencyInProgressError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyMissingError,
    IdempotencyPayloadMismatchError,
    TokenInvalidError,
)
from src.domain.value_objects import utc_now
from src.presentation.api.middleware.error_handler import problem_json_response

IDEMPOTENT_ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^/api/v1/sessions$"),
    re.compile(r"^/api/v1/sessions/[^/]+/skeleton-frames$"),
    re.compile(r"^/api/v1/sessions/[^/]+/results$"),
    re.compile(r"^/api/v1/patients/[^/]+/medications$"),
    re.compile(r"^/api/v1/alerts/emergency$"),
)


def _get_header(headers: list[tuple[bytes, bytes]], name: str) -> str | None:
    target = name.lower().encode("latin-1")
    for raw_name, raw_val in headers:
        if raw_name.lower() == target:
            return raw_val.decode("latin-1")
    return None


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        msg_type = message.get("type")
        if msg_type == "http.disconnect":
            break
        body = message.get("body", b"")
        if body:
            chunks.append(body)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _make_replay_receive(body_bytes: bytes) -> Receive:
    sent = False

    async def replay_receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return replay_receive


class IdempotencyMiddleware:
    """Pure ASGI middleware enforcing offline-first Idempotency-Key semantics on POST routes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        uow_factory: UnitOfWorkFactory,
        token_provider: TokenProviderPort,
        ttl_hours: int = 168,
        extra_patterns: list[str] | None = None,
    ) -> None:
        self.app = app
        self._uow_factory = uow_factory
        self._token_provider = token_provider
        self._ttl_hours = ttl_hours
        compiled_extra = tuple(re.compile(p) for p in (extra_patterns or []))
        self._patterns: tuple[re.Pattern[str], ...] = IDEMPOTENT_ROUTE_PATTERNS + compiled_extra

    def _matches(self, method: str, path: str) -> bool:
        if method != "POST":
            return False
        return any(pattern.match(path) for pattern in self._patterns)

    async def _send_domain_error(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        exc: DomainError,
        path: str,
    ) -> None:
        response = problem_json_response(
            status_code=exc.status_code,
            problem_type=exc.problem_type,
            title=exc.title,
            detail=exc.detail,
            instance=path,
            error_code=exc.error_code,
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope.get("method", "GET").upper()
        path: str = scope.get("path", "")
        if not self._matches(method, path):
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        auth_header = _get_header(headers, "authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            await self._send_domain_error(
                scope,
                receive,
                send,
                TokenInvalidError("Bearer authentication token is required."),
                path,
            )
            return

        raw_jwt = auth_header[7:].strip()
        try:
            claims = self._token_provider.decode_access_token(raw_jwt)
        except DomainError as exc:
            await self._send_domain_error(scope, receive, send, exc, path)
            return

        raw_idem_key = _get_header(headers, "idempotency-key")
        if not raw_idem_key or not raw_idem_key.strip():
            await self._send_domain_error(
                scope,
                receive,
                send,
                IdempotencyKeyMissingError(
                    "Idempotency-Key UUID header is required on this mutating endpoint."
                ),
                path,
            )
            return

        try:
            idem_uuid = UUID(raw_idem_key.strip())
        except ValueError:
            await self._send_domain_error(
                scope,
                receive,
                send,
                IdempotencyKeyInvalidError("Idempotency-Key header must be a valid UUID."),
                path,
            )
            return

        body_bytes = await _read_body(receive)
        request_hash = hashlib.sha256(body_bytes).hexdigest()
        now = utc_now()

        acquire_record = IdempotencyRecord(
            actor_user_id=claims.user_id,
            method=method,
            path=path,
            idempotency_key=idem_uuid,
            request_hash=request_hash,
            state=IdempotencyState.IN_PROGRESS,
            status_code=None,
            response_body=None,
            created_at_utc=now,
            expires_at_utc=now + timedelta(hours=self._ttl_hours),
        )

        async with self._uow_factory() as uow:
            acquired, existing = await uow.idempotency.try_acquire(acquire_record)
            await uow.commit()

        if not acquired:
            if existing is None or existing.state == IdempotencyState.IN_PROGRESS:
                await self._send_domain_error(
                    scope,
                    receive,
                    send,
                    IdempotencyInProgressError(
                        "A request with this Idempotency-Key is currently in progress."
                    ),
                    path,
                )
                return

            if existing.request_hash != request_hash:
                await self._send_domain_error(
                    scope,
                    receive,
                    send,
                    IdempotencyPayloadMismatchError(
                        "Idempotency-Key was already used with a different request payload."
                    ),
                    path,
                )
                return

            await self._send_cached_response(
                scope,
                receive,
                send,
                status_code=existing.status_code or 200,
                body=existing.response_body,
            )
            return

        captured_start: Message | None = None
        captured_chunks: list[bytes] = []

        async def capture_send(message: Message) -> None:
            nonlocal captured_start
            if message["type"] == "http.response.start":
                captured_start = message
            elif message["type"] == "http.response.body":
                body_part = message.get("body", b"")
                if body_part:
                    captured_chunks.append(body_part)

        replay_receive = _make_replay_receive(body_bytes)
        try:
            await self.app(scope, replay_receive, capture_send)
        except Exception:
            await self._release_lock(claims.user_id, method, path, idem_uuid)
            raise

        if captured_start is None:
            await self._release_lock(claims.user_id, method, path, idem_uuid)
            return

        status_code: int = int(captured_start["status"])
        full_body = b"".join(captured_chunks)

        if 200 <= status_code < 500:
            parsed_body: dict[str, Any] | list[Any] | None = None
            if full_body:
                try:
                    loaded = json.loads(full_body.decode("utf-8"))
                    if isinstance(loaded, (dict, list)):
                        parsed_body = loaded
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parsed_body = None

            async with self._uow_factory() as uow:
                await uow.idempotency.mark_completed(
                    actor_user_id=claims.user_id,
                    method=method,
                    path=path,
                    idempotency_key=idem_uuid,
                    status_code=status_code,
                    response_body=parsed_body,
                )
                await uow.commit()
        else:
            await self._release_lock(claims.user_id, method, path, idem_uuid)

        await send(captured_start)
        await send({"type": "http.response.body", "body": full_body, "more_body": False})

    async def _release_lock(
        self,
        actor_user_id: UUID,
        method: str,
        path: str,
        idempotency_key: UUID,
    ) -> None:
        async with self._uow_factory() as uow:
            await uow.idempotency.delete_in_progress(
                actor_user_id=actor_user_id,
                method=method,
                path=path,
                idempotency_key=idempotency_key,
            )
            await uow.commit()

    async def _send_cached_response(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        body: dict[str, Any] | list[Any] | None,
    ) -> None:
        headers = {"X-Idempotency-Replayed": "true"}
        if body is None:
            resp: Response = Response(status_code=status_code, headers=headers)
        else:
            resp = JSONResponse(status_code=status_code, content=body, headers=headers)
        await resp(scope, receive, send)
