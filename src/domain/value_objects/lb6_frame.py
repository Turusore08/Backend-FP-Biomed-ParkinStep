import math
from dataclasses import dataclass

from src.domain.exceptions import DomainValidationError


@dataclass(frozen=True, slots=True)
class Lb6Frame:
    """Immutable single frame of 6 lower-body keypoints (x, y, conf)."""

    keypoints: tuple[tuple[float, float, float], ...]

    def __post_init__(self) -> None:
        if len(self.keypoints) != 6:
            raise DomainValidationError("LB6 frame must contain exactly 6 keypoints.")
        for idx, joint in enumerate(self.keypoints):
            if len(joint) != 3:
                raise DomainValidationError(
                    f"LB6 joint at index {idx} must have exactly 3 values (x, y, conf)."
                )
            x, y, conf = joint
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(conf)):
                raise DomainValidationError(
                    f"LB6 joint at index {idx} contains non-finite numeric values."
                )
            if conf < 0.0 or conf > 1.0:
                raise DomainValidationError(
                    f"LB6 confidence at index {idx} must be within [0.0, 1.0]."
                )
