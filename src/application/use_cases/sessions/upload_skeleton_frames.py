from src.application.dtos import (
    ActorContext,
    SkeletonBatchAckOutputDTO,
    SkeletonBatchUploadDTO,
)
from src.application.interfaces import SkeletonCodecPort, UnitOfWorkFactory
from src.application.use_cases.patients.access import (
    ensure_patient_access,
    require_sync_consent,
)
from src.domain.entities import SkeletonChunk
from src.domain.exceptions import (
    ConflictError,
    DomainValidationError,
    EntityNotFoundError,
)
from src.domain.value_objects import Lb6Frame, utc_now

MAX_FRAMES_PER_BATCH = 3600


class UploadSkeletonBatchUseCase:
    """Validate and compress anonymous LB6 [T][6][3] keypoint batches (zero video)."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        skeleton_codec: SkeletonCodecPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._skeleton_codec = skeleton_codec

    async def execute(
        self,
        actor: ActorContext,
        request: SkeletonBatchUploadDTO,
    ) -> SkeletonBatchAckOutputDTO:
        if request.chunk_index < 0:
            raise DomainValidationError("chunk_index must be >= 0.")
        if request.sampling_hz not in (15.0, 30.0):
            raise DomainValidationError("sampling_hz must be 15.0 or 30.0.")

        frame_count = len(request.lb6_xyc)
        if frame_count < 1 or frame_count > MAX_FRAMES_PER_BATCH:
            raise DomainValidationError(
                f"lb6_xyc batch must contain between 1 and {MAX_FRAMES_PER_BATCH} frames."
            )
        if len(request.frame_timestamps_ms) != frame_count:
            raise DomainValidationError(
                "frame_timestamps_ms length must match lb6_xyc frame count."
            )

        for frame_idx, raw_frame in enumerate(request.lb6_xyc):
            if len(raw_frame) != 6 or any(len(joint) != 3 for joint in raw_frame):
                raise DomainValidationError(
                    f"Frame at index {frame_idx} must have exact shape [6][3]."
                )
            Lb6Frame(
                keypoints=tuple(
                    (float(joint[0]), float(joint[1]), float(joint[2]))
                    for joint in raw_frame
                )
            )

        compressed_blob = self._skeleton_codec.pack(
            request.frame_timestamps_ms,
            request.lb6_xyc,
        )
        now = utc_now()

        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_id(request.session_id)
            if session is None:
                raise EntityNotFoundError(
                    f"Clinical session {request.session_id} was not found.",
                    error_code="SESSION_NOT_FOUND",
                )

            patient = await ensure_patient_access(uow, actor, session.patient_id)
            require_sync_consent(patient)

            if await uow.sessions.has_skeleton_chunk(request.session_id, request.chunk_index):
                raise ConflictError(
                    f"Skeleton chunk_index={request.chunk_index} was already uploaded.",
                    error_code="SKELETON_CHUNK_EXISTS",
                )

            chunk = SkeletonChunk(
                session_id=request.session_id,
                chunk_index=request.chunk_index,
                sampling_hz=request.sampling_hz,
                frame_count=frame_count,
                compression="ZLIB",
                payload_blob=compressed_blob,
                byte_size=len(compressed_blob),
                received_at_utc=now,
            )
            await uow.sessions.add_skeleton_chunk(chunk)
            await uow.commit()

        return SkeletonBatchAckOutputDTO(
            session_id=request.session_id,
            chunk_index=request.chunk_index,
            frame_count=frame_count,
            compressed_bytes=len(compressed_blob),
            received_at_utc=now,
        )
