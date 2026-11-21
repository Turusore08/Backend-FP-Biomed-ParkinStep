import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

from src.application.interfaces import CloudKeypointClassifierPort
from src.domain.constants import DEFAULT_THRESHOLDS_B15HZ
from src.domain.enums import ClassifierName

logger = logging.getLogger(__name__)


class DeterministicFreezeIndexClassifier:
    """Deterministic fallback classifier calibrated around B_15hz LightGBM threshold 0.26."""

    def __init__(self, threshold_val: float | None = None) -> None:
        self._threshold_val = (
            threshold_val
            if threshold_val is not None
            else DEFAULT_THRESHOLDS_B15HZ[ClassifierName.LIGHTGBM_FFT]
        )

    @property
    def threshold_val(self) -> float:
        return self._threshold_val

    def predict_window_prob(
        self,
        features_126: list[float],
        freeze_index_ankle: float,
    ) -> float:
        mean_conf = sum(features_126[120:126]) / 6.0 if len(features_126) >= 126 else 1.0
        if mean_conf < 0.20:
            return 0.05
        asym_ankle = features_126[118] if len(features_126) > 118 else 0.0
        logit = 1.65 * (freeze_index_ankle - 1.5) + 0.5 * min(max(asym_ankle, 0.0), 1.0)
        logit = max(-20.0, min(20.0, logit))
        return 1.0 / (1.0 + math.exp(-logit))


class OnnxKeypointClassifier:
    """Optional ONNX Runtime classifier loaded when CLOUD_FALLBACK_ONNX_PATH is set."""

    def __init__(self, model_path: Path, threshold_val: float | None = None) -> None:
        import onnxruntime as ort

        self._session: Any = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self._input_name = str(self._session.get_inputs()[0].name)
        self._threshold_val = (
            threshold_val
            if threshold_val is not None
            else DEFAULT_THRESHOLDS_B15HZ[ClassifierName.LIGHTGBM_FFT]
        )

    @property
    def threshold_val(self) -> float:
        return self._threshold_val

    def predict_window_prob(
        self,
        features_126: list[float],
        freeze_index_ankle: float,
    ) -> float:
        tensor = np.asarray(features_126, dtype=np.float32).reshape(1, 126)
        outputs = self._session.run(None, {self._input_name: tensor})
        prob_output = np.asarray(outputs[-1], dtype=np.float64).ravel()
        if prob_output.size >= 2:
            return float(prob_output[1])
        return float(prob_output[0])


def build_cloud_classifier(onnx_path: str | None = None) -> CloudKeypointClassifierPort:
    """Construct ONNX classifier if configured & available, else deterministic fallback."""
    if onnx_path:
        candidate = Path(onnx_path)
        if candidate.is_file():
            try:
                return OnnxKeypointClassifier(candidate)
            except Exception:
                logger.warning("Failed to load ONNX fallback model; using deterministic scorer.")
    return DeterministicFreezeIndexClassifier()
