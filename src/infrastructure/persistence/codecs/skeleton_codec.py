import math
import struct
import zlib

from src.domain.exceptions import DomainValidationError

_MAGIC = b"LB61"
_HEADER_STRUCT = struct.Struct("<4sI")


class ZlibSkeletonCodec:
    """Compact ZLIB binary codec for LB6 [T][6][3] float32 coordinates and int64 timestamps."""

    def pack(
        self,
        timestamps_ms: list[int],
        lb6_xyc: list[list[list[float]]],
    ) -> bytes:
        frame_count = len(lb6_xyc)
        if len(timestamps_ms) != frame_count:
            raise DomainValidationError("timestamps_ms length must match lb6_xyc length.")

        header = _HEADER_STRUCT.pack(_MAGIC, frame_count)
        ts_bytes = struct.pack(f"<{frame_count}q", *timestamps_ms) if frame_count else b""

        flat_coords: list[float] = []
        for frame in lb6_xyc:
            if len(frame) != 6:
                raise DomainValidationError("Every LB6 frame must contain exactly 6 joints.")
            for joint in frame:
                if len(joint) != 3:
                    raise DomainValidationError("Every LB6 joint must contain (x, y, conf).")
                x, y, conf = float(joint[0]), float(joint[1]), float(joint[2])
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(conf)):
                    raise DomainValidationError("LB6 coordinates must be finite floats.")
                flat_coords.extend((x, y, conf))

        coord_bytes = (
            struct.pack(f"<{frame_count * 18}f", *flat_coords) if frame_count else b""
        )
        return zlib.compress(header + ts_bytes + coord_bytes, level=6)

    def unpack(self, payload: bytes) -> tuple[list[int], list[list[list[float]]]]:
        try:
            raw = zlib.decompress(payload)
        except zlib.error as exc:
            raise DomainValidationError("Corrupted zlib skeleton blob.") from exc

        if len(raw) < _HEADER_STRUCT.size:
            raise DomainValidationError("Skeleton blob header is truncated.")

        magic, frame_count = _HEADER_STRUCT.unpack_from(raw, 0)
        if magic != _MAGIC:
            raise DomainValidationError("Invalid skeleton blob magic bytes.")

        expected_size = _HEADER_STRUCT.size + frame_count * 8 + frame_count * 18 * 4
        if len(raw) != expected_size:
            raise DomainValidationError("Skeleton blob payload length mismatch.")

        offset = _HEADER_STRUCT.size
        timestamps = (
            list(struct.unpack_from(f"<{frame_count}q", raw, offset))
            if frame_count
            else []
        )
        offset += frame_count * 8

        flat_coords = (
            struct.unpack_from(f"<{frame_count * 18}f", raw, offset)
            if frame_count
            else ()
        )
        frames: list[list[list[float]]] = []
        for t in range(frame_count):
            base = t * 18
            frame = [
                [
                    float(flat_coords[base + j * 3]),
                    float(flat_coords[base + j * 3 + 1]),
                    float(flat_coords[base + j * 3 + 2]),
                ]
                for j in range(6)
            ]
            frames.append(frame)
        return timestamps, frames
