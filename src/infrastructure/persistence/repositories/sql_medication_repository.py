from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities import MedicationLog
from src.domain.enums import MedicationState
from src.infrastructure.persistence.models import MedicationLogORM


def _to_entity(row: MedicationLogORM) -> MedicationLog:
    return MedicationLog(
        log_id=row.log_id,
        patient_id=row.patient_id,
        drug_name=row.drug_name,
        dosage_mg=row.dosage_mg,
        taken_at_utc=row.taken_at_utc,
        med_state=MedicationState(row.med_state),
        notes=row.notes,
        synced_at_utc=row.synced_at_utc,
    )


class SqlMedicationRepository:
    """SQLAlchemy async repository for Levodopa MedicationLog entries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, log: MedicationLog) -> None:
        self._session.add(
            MedicationLogORM(
                log_id=log.log_id,
                patient_id=log.patient_id,
                drug_name=log.drug_name,
                dosage_mg=log.dosage_mg,
                taken_at_utc=log.taken_at_utc,
                med_state=log.med_state.value,
                notes=log.notes,
                synced_at_utc=log.synced_at_utc,
            )
        )
        await self._session.flush()

    async def get_by_id(self, log_id: UUID) -> MedicationLog | None:
        row = await self._session.get(MedicationLogORM, log_id)
        return _to_entity(row) if row is not None else None

    async def list_by_patient(
        self,
        patient_id: UUID,
        *,
        from_utc: datetime | None,
        to_utc: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[MedicationLog], int]:
        filters: list[ColumnElement[bool]] = [MedicationLogORM.patient_id == patient_id]
        if from_utc is not None:
            filters.append(MedicationLogORM.taken_at_utc >= from_utc)
        if to_utc is not None:
            filters.append(MedicationLogORM.taken_at_utc <= to_utc)

        count_stmt = select(func.count()).select_from(MedicationLogORM).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        items_stmt = (
            select(MedicationLogORM)
            .where(*filters)
            .order_by(MedicationLogORM.taken_at_utc.desc(), MedicationLogORM.log_id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(items_stmt)).scalars().all()
        return [_to_entity(r) for r in rows], total
