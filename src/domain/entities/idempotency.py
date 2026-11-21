from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.enums.clinical_enums import IdempotencyState
from src.domain.value_objects.utc_timestamp import ensure_utc


@dataclass(slots=True)
class IdempotencyRecord:
    """Persisted idempotency lock and cached response for offline-first retries."""

    actor_user_id: UUID
    method: str
    path: str
    idempotency_key: UUID
    request_hash: str
    state: IdempotencyState
    status_code: int | None
    response_body: dict[str, Any] | list[Any] | None
    created_at_utc: datetime
    expires_at_utc: datetime

    def __post_init__(self) -> None:
        self.created_at_utc = ensure_utc(self.created_at_utc)
        self.expires_at_utc = ensure_utc(self.expires_at_utc)
