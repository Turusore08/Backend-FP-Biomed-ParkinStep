from collections.abc import AsyncIterator
from uuid import UUID

from src.application.dtos import ActorContext, VideoFallbackResultOutputDTO
from src.application.interfaces import (
    CloudVideoAnalyzerPort,
    UnitOfWorkFactory,
    VideoDisposalPort,
)
from src.application.use_cases.patients.access import (
    ensure_patient_access,
    require_cloud_video_consent,
    require_sync_consent,
)
from src.domain.exceptions import EntityNotFoundError, UnsupportedMediaTypeError

ALLOWED_VIDEO_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "application/octet-stream",
    }
)


class AnalyzeVideoFallbackUseCase:
    """Process opt-in encrypted cloud video fallback with guaranteed zero retention."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        video_disposal: VideoDisposalPort,
        analyzer: CloudVideoAnalyzerPort,
        *,
        max_upload_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._video_disposal = video_disposal
        self._analyzer = analyzer
        self._max_upload_bytes = max_upload_bytes

    async def execute(
        self,
        actor: ActorContext,
        session_id: UUID,
        *,
        content_type: str | None,
        data_stream: AsyncIterator[bytes],
    ) -> VideoFallbackResultOutputDTO:
        normalized_mime = (content_type or "").split(";")[0].strip().lower()
        if normalized_mime not in ALLOWED_VIDEO_CONTENT_TYPES:
            raise UnsupportedMediaTypeError(
                "Video fallback accepts only video/mp4, video/quicktime, "
                "or application/octet-stream."
            )

        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_id(session_id)
            if session is None:
                raise EntityNotFoundError(
                    f"Clinical session {session_id} was not found.",
                    error_code="SESSION_NOT_FOUND",
                )
            patient = await ensure_patient_access(uow, actor, session.patient_id)
            require_sync_consent(patient)
            require_cloud_video_consent(patient)

        async with self._video_disposal.secure_temp_video(
            data_stream,
            max_bytes=self._max_upload_bytes,
        ) as temp_video_path:
            outcome = await self._analyzer.analyze_video_file(temp_video_path, session_id)

        return VideoFallbackResultOutputDTO(
            session_id=session_id,
            status="COMPLETED",
            frames_analyzed=outcome.frames_analyzed,
            auto_delete_after_inference=True,
            video_securely_deleted=True,
            detail=outcome.detail,
        )
