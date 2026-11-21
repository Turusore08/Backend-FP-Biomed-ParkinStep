import math

from src.domain.exceptions import DomainValidationError


def compute_calibrated_score(raw_prob: float, threshold: float) -> float:
    """Map raw classifier probability to calibrated UI score [0..100] with threshold -> 50."""
    if not math.isfinite(raw_prob) or raw_prob < 0.0 or raw_prob > 1.0:
        raise DomainValidationError("raw_prob must be a finite float in [0.0, 1.0].")
    if not math.isfinite(threshold) or threshold <= 0.0 or threshold >= 1.0:
        raise DomainValidationError("threshold must be a finite float strictly within (0.0, 1.0).")

    if raw_prob < threshold:
        score = 50.0 * (raw_prob / threshold)
    else:
        score = 50.0 + 50.0 * ((raw_prob - threshold) / max(1.0 - threshold, 1e-6))

    return round(min(100.0, max(0.0, score)), 4)
