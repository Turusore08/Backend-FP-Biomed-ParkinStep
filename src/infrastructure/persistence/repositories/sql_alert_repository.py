from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import EmergencyAlert
from src.domain.enums import EmergencyTrigger
from src.infrastructure.persistence.models import EmergencyAlertORM


def _to_entity(row: EmergencyAlertORM) -> EmergencyAlert:
    return EmergencyAlert(
        alert_id=row.alert_id,
        patient_id=row.patient_id,
        session_id=row.session_id,
        trigger_type=EmergencyTrigger(row.trigger_type),
        triggered_at_utc=row.triggered_at_utc,
        cancelled_by_user=row.cancelled_by_user,
        dispatched_at_utc=row.dispatched_at_utc,
    )


class SqlAlertRepository:
    """SQLAlchemy async repository for EmergencyAlert records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, alert: EmergencyAlert) -> None:
        self._session.add(
            EmergencyAlertORM(
                alert_id=alert.alert_id,
                patient_id=alert.patient_id,
                session_id=alert.session_id,
                trigger_type=alert.trigger_type.value,
                triggered_at_utc=alert.triggered_at_utc,
                cancelled_by_user=alert.cancelled_by_user,
                dispatched_at_utc=alert.dispatched_at_utc,
            )
        )
        await self._session.flush()

    async def get_by_id(self, alert_id: UUID) -> EmergencyAlert | None:
        row = await self._session.get(EmergencyAlertORM, alert_id)
        return _to_entity(row) if row is not None else None
