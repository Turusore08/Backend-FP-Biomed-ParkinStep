import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from src.application.interfaces import VideoAnalysisOutcome
from src.domain.exceptions import DomainValidationError, PayloadTooLargeError


def _zero_and_unlink(path: Path) -> None:
    if not path.exists():
        return
    try:
        file_size = path.stat().st_size
        if file_size > 0:
            zero_block = b"\x00" * min(file_size, 65536)
            with path.open("r+b") as handle:
                remaining = file_size
                while remaining > 0:
                    chunk = zero_block[: min(remaining, len(zero_block))]
                    handle.write(chunk)
                    remaining -= len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
    finally:
        if path.exists():
            os.unlink(path)


class SecureTempVideoDisposer:
    """Write opt-in fallback video streams privately and wipe/unlink unconditionally."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir())

    @asynccontextmanager
    async def secure_temp_video(
        self,
        data_stream: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> AsyncIterator[Path]:
        os.makedirs(self._base_dir, mode=0o700, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(
            prefix="parkinstep_vid_",
            suffix=".tmp",
            dir=str(self._base_dir),
        )
        temp_path = Path(raw_path)
        total_bytes = 0
        try:
            with os.fdopen(fd, "wb") as handle:
                async for chunk in data_stream:
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise PayloadTooLargeError(
                            f"Uploaded video exceeds maximum size of {max_bytes} bytes."
                        )
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            if total_bytes == 0:
                raise DomainValidationError("Uploaded video file must not be empty.")

            yield temp_path
        finally:
            _zero_and_unlink(temp_path)


class StubCloudVideoAnalyzer:
    """Pluggable cloud video analyzer stub ready for Phase 3 ONNX worker wiring."""

    async def analyze_video_file(
        self,
        video_path: Path,
        session_id: UUID,
    ) -> VideoAnalysisOutcome:
        size_bytes = video_path.stat().st_size
        estimated_frames = max(1, min(1800, size_bytes // 256))
        return VideoAnalysisOutcome(
            frames_analyzed=estimated_frames,
            detail=(
                f"Cloud fallback analysis completed for session {session_id} "
                "(pluggable ONNX worker slot)."
            ),
        )
