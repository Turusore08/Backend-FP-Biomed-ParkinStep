from collections import deque
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from src.application.interfaces import CloudKeypointClassifierPort
from src.domain.constants import (
    CONF_VALID_THRES,
    HAMPEL_SIGMA,
    HAMPEL_WINDOW,
    MIN_RUN_WINDOWS,
    TARGET_FS_HZ,
)
from src.domain.enums import AlertTier
from src.domain.value_objects import Lb6Frame, compute_calibrated_score

_BONE_PARENTS: tuple[tuple[int, int], ...] = (
    (2, 0),  # L_Knee <- L_Hip
    (3, 1),  # R_Knee <- R_Hip
    (4, 2),  # L_Ankle <- L_Knee
    (5, 3),  # R_Ankle <- R_Knee
)


def interpolate_low_conf_lb6(
    xyc: NDArray[np.float64],
    conf_thres: float = CONF_VALID_THRES,
) -> NDArray[np.float64]:
    """Linearly interpolate (x, y) keypoints where conf < conf_thres (matches Mode A/B)."""
    out = xyc.copy()
    t_len = out.shape[0]
    if t_len == 0:
        return out

    idx = np.arange(t_len, dtype=np.float64)
    for joint_idx in range(6):
        valid_mask = out[:, joint_idx, 2] >= conf_thres
        if not np.any(valid_mask):
            out[:, joint_idx, 0:2] = 0.0
        elif not np.all(valid_mask):
            valid_idx = idx[valid_mask]
            out[:, joint_idx, 0] = np.interp(idx, valid_idx, out[valid_mask, joint_idx, 0])
            out[:, joint_idx, 1] = np.interp(idx, valid_idx, out[valid_mask, joint_idx, 1])
    return out


def hampel_filter_1d(
    values: NDArray[np.float64],
    window: int = HAMPEL_WINDOW,
    n_sigma: float = HAMPEL_SIGMA,
) -> NDArray[np.float64]:
    """Apply centered rolling Hampel spike filter with min_periods=1."""
    out = values.copy()
    n = out.shape[0]
    if n == 0:
        return out

    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        win_slice = values[lo:hi]
        med = float(np.median(win_slice))
        mad = float(np.median(np.abs(win_slice - med)))
        thresh = n_sigma * 1.4826 * mad
        if abs(float(values[i]) - med) > thresh:
            out[i] = med
    return out


def build_lb6_tensor_9ch(
    xyc: NDArray[np.float64],
    *,
    scale_ref: float | None = None,
) -> tuple[NDArray[np.float32], float]:
    """Build Scenario B 9-channel tensor of shape (9, T, 6) from raw LB6 (T, 6, 3)."""
    t_len = xyc.shape[0]
    interp = interpolate_low_conf_lb6(xyc, CONF_VALID_THRES)

    xy = interp[:, :, 0:2].copy()
    for joint_idx in range(6):
        xy[:, joint_idx, 0] = hampel_filter_1d(xy[:, joint_idx, 0], HAMPEL_WINDOW, HAMPEL_SIGMA)
        xy[:, joint_idx, 1] = hampel_filter_1d(xy[:, joint_idx, 1], HAMPEL_WINDOW, HAMPEL_SIGMA)

    pelvis_series = 0.5 * (xy[:, 0, :] + xy[:, 1, :])
    pelvis_center = np.median(pelvis_series, axis=0)

    leg_l = np.linalg.norm(xy[:, 0, :] - xy[:, 2, :], axis=1) + np.linalg.norm(
        xy[:, 2, :] - xy[:, 4, :], axis=1
    )
    leg_r = np.linalg.norm(xy[:, 1, :] - xy[:, 3, :], axis=1) + np.linalg.norm(
        xy[:, 3, :] - xy[:, 5, :], axis=1
    )
    raw_scale = max(float(np.median(0.5 * (leg_l + leg_r))), 1e-4)
    scale = (
        float(np.clip(raw_scale, 0.5 * scale_ref, 1.5 * scale_ref))
        if scale_ref is not None
        else raw_scale
    )

    xy_norm = (xy - pelvis_center) / scale
    bones = np.zeros_like(xy_norm)
    for child, parent in _BONE_PARENTS:
        bones[:, child, :] = xy_norm[:, child, :] - xy_norm[:, parent, :]

    if t_len >= 2:
        dx = np.gradient(xy_norm[:, :, 0], axis=0)
        dy = np.gradient(xy_norm[:, :, 1], axis=0)
        ddx = np.gradient(dx, axis=0)
        ddy = np.gradient(dy, axis=0)
    else:
        dx = np.zeros((t_len, 6), dtype=np.float64)
        dy = np.zeros((t_len, 6), dtype=np.float64)
        ddx = np.zeros((t_len, 6), dtype=np.float64)
        ddy = np.zeros((t_len, 6), dtype=np.float64)

    tensor = np.stack(
        [
            xy_norm[:, :, 0],
            xy_norm[:, :, 1],
            xyc[:, :, 2],
            dx,
            dy,
            ddx,
            ddy,
            bones[:, :, 0],
            bones[:, :, 1],
        ],
        axis=0,
    ).astype(np.float32)
    return tensor, scale


def extract_fft_kinematic_features(
    window_raw: NDArray[np.float32],
    fs: float = TARGET_FS_HZ,
) -> tuple[NDArray[np.float32], float]:
    """Extract bit-exact 126 LightGBM+FFT features from unscaled (9, T_win, 6) window."""
    t_len = window_raw.shape[1]
    features: list[float] = []

    # 0..71: 4 channels * 3 stats (mean, std ddof=0, max abs) * 6 joints = 72
    for c_idx in (0, 1, 3, 4):
        arr = window_raw[c_idx].astype(np.float64)
        features.extend(np.mean(arr, axis=0).tolist())
        features.extend(np.std(arr, axis=0, ddof=0).tolist())
        features.extend(np.max(np.abs(arr), axis=0).tolist())

    # 72..107: Spectral bands for dx, dy (2 channels * 3 metrics * 6 joints = 36)
    freqs = np.fft.rfftfreq(t_len, d=1.0 / fs)
    loco_mask = (freqs >= 0.5) & (freqs <= 3.0)
    freeze_mask = (freqs >= 3.5) & (freqs <= min(8.0, 0.49 * fs))
    ankle_fi_terms: list[float] = []

    for c_idx in (3, 4):
        arr = window_raw[c_idx].astype(np.float64)
        sig = arr - np.mean(arr, axis=0, keepdims=True)
        psd = np.abs(np.fft.rfft(sig, axis=0)) ** 2
        e_loco = np.sum(psd[loco_mask, :], axis=0) + 1e-8
        e_freeze = np.sum(psd[freeze_mask, :], axis=0) + 1e-8
        fi_ratio = e_freeze / e_loco
        ankle_fi_terms.extend((float(fi_ratio[4]), float(fi_ratio[5])))
        features.extend(np.log1p(e_loco).tolist())
        features.extend(np.log1p(e_freeze).tolist())
        features.extend(np.log1p(fi_ratio).tolist())

    # 108..119: Bilateral coordination & asymmetry across Hip(0,1), Knee(2,3), Ankle(4,5)
    for left_j, right_j in ((0, 1), (2, 3), (4, 5)):
        dx_lr = window_raw[0, :, left_j].astype(np.float64) - window_raw[0, :, right_j].astype(
            np.float64
        )
        dy_lr = window_raw[1, :, left_j].astype(np.float64) - window_raw[1, :, right_j].astype(
            np.float64
        )
        dist_xy = np.sqrt(dx_lr**2 + dy_lr**2)
        asym_v = np.abs(
            window_raw[3, :, left_j].astype(np.float64)
            - window_raw[3, :, right_j].astype(np.float64)
        ) + np.abs(
            window_raw[4, :, left_j].astype(np.float64)
            - window_raw[4, :, right_j].astype(np.float64)
        )
        features.extend(
            (
                float(np.mean(dist_xy)),
                float(np.std(dist_xy, ddof=0)),
                float(np.mean(asym_v)),
                float(np.std(asym_v, ddof=0)),
            )
        )

    # 120..125: Mean keypoint confidence for 6 joints
    features.extend(np.mean(window_raw[2, :, :].astype(np.float64), axis=0).tolist())

    vec = np.nan_to_num(
        np.asarray(features, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    ).astype(np.float32)
    freeze_index_ankle = round(float(np.mean(ankle_fi_terms)), 4)
    return vec, freeze_index_ankle


class TwoTierAlertStateMachine:
    """Two-tier FoG debounce (min_run=2) with 2-window negative hysteresis."""

    def __init__(self, threshold_val: float, min_run_windows: int = MIN_RUN_WINDOWS) -> None:
        self._threshold_val = threshold_val
        self._min_run = max(1, min_run_windows)
        self._pos_streak = 0
        self._neg_streak = 0
        self._confirmed = False

    def step(self, raw_prob: float) -> AlertTier:
        if raw_prob >= self._threshold_val:
            self._neg_streak = 0
            self._pos_streak += 1
            if self._confirmed or self._pos_streak >= self._min_run:
                self._confirmed = True
                return AlertTier.FOG_CONFIRMED
            return AlertTier.EARLY_WARNING

        self._pos_streak = 0
        if self._confirmed:
            self._neg_streak += 1
            if self._neg_streak >= self._min_run:
                self._confirmed = False
                return AlertTier.NORMAL
            return AlertTier.FOG_CONFIRMED
        return AlertTier.NORMAL


@dataclass(frozen=True, slots=True)
class WindowStreamPrediction:
    window_idx: int
    raw_prob: float
    calibrated_score: float
    alert_tier: AlertTier
    freeze_index_ankle: float


class CausalLb6SlidingWindowProcessor:
    """Causal 33-frame lookahead buffer (30-frame window + 3-frame lookahead, stride=15)."""

    def __init__(
        self,
        classifier: CloudKeypointClassifierPort,
        *,
        fs_hz: float = TARGET_FS_HZ,
        window_frames: int = 30,
        stride_frames: int = 15,
        lookahead_frames: int = 3,
    ) -> None:
        self._classifier = classifier
        self._fs_hz = fs_hz
        self._window_frames = window_frames
        self._stride_frames = stride_frames
        self._lookahead_frames = lookahead_frames
        self._required_frames = window_frames + lookahead_frames
        self._buffer: deque[list[list[float]]] = deque(maxlen=self._required_frames)
        self._frames_since_emit = 0
        self._window_idx = 0
        self._scale_ref: float | None = None
        self._alert_fsm = TwoTierAlertStateMachine(classifier.threshold_val)

    def push_frame(self, frame: Lb6Frame) -> WindowStreamPrediction | None:
        self._buffer.append([[x, y, c] for x, y, c in frame.keypoints])
        if len(self._buffer) < self._required_frames:
            return None

        if self._window_idx > 0:
            self._frames_since_emit += 1
            if self._frames_since_emit < self._stride_frames:
                return None

        self._frames_since_emit = 0
        arr = np.asarray(self._buffer, dtype=np.float64)
        tensor_9ch, scale = build_lb6_tensor_9ch(arr, scale_ref=self._scale_ref)
        if self._scale_ref is None:
            self._scale_ref = scale

        window_slice = tensor_9ch[:, : self._window_frames, :]
        features_126, freeze_index_ankle = extract_fft_kinematic_features(
            window_slice,
            fs=self._fs_hz,
        )
        raw_prob = self._classifier.predict_window_prob(
            features_126.tolist(),
            freeze_index_ankle,
        )
        raw_prob = round(min(1.0, max(0.0, raw_prob)), 4)
        calibrated = compute_calibrated_score(raw_prob, self._classifier.threshold_val)
        alert_tier = self._alert_fsm.step(raw_prob)

        prediction = WindowStreamPrediction(
            window_idx=self._window_idx,
            raw_prob=raw_prob,
            calibrated_score=round(calibrated, 2),
            alert_tier=alert_tier,
            freeze_index_ankle=freeze_index_ankle,
        )
        self._window_idx += 1
        return prediction
