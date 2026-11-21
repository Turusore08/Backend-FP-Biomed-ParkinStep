import logging

from src.domain.entities import EmergencyAlert, EmergencyContact

logger = logging.getLogger(__name__)


class LoggingEmergencyNotifier:
    """Emergency alert dispatcher logging non-PII dispatch metadata."""

    async def notify_caregivers(
        self,
        alert: EmergencyAlert,
        contacts: list[EmergencyContact],
    ) -> int:
        ordered = sorted(contacts, key=lambda c: not c.is_primary)
        logger.warning(
            "Emergency escalation dispatched",
            extra={
                "extra_data": {
                    "alert_id": str(alert.alert_id),
                    "session_id": str(alert.session_id),
                    "trigger_type": alert.trigger_type.value,
                    "contact_count": len(ordered),
                }
            },
        )
        return len(ordered)
