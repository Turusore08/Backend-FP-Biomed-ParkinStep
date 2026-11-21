from dataclasses import dataclass
from typing import Final
from uuid import UUID

from src.domain.enums import UserRole


class UnsetType:
    """Sentinel type distinguishing an omitted key from an explicit JSON null."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final[UnsetType] = UnsetType()

type PatchField[T] = T | UnsetType


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Authenticated principal extracted from Bearer JWT."""

    user_id: UUID
    role: UserRole
    device_id: str
