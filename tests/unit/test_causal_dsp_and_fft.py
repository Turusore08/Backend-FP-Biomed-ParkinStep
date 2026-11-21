import math

import numpy as np

from src.domain.enums import AlertTier
from src.domain.value_objects import Lb6Frame
from src.infrastructure.ml import (
    CausalLb6SlidingWindowProcessor,
    DeterministicFreezeIndexClassifier,
    TwoTierAlertStateMachine,
    build_lb6_tensor_9ch,
    extract_fft_kinematic_features,
    hampel_filter_1d,
    interpolate_low_conf_lb6,
)


def _make_synthetic_lb6_sequence(
    num_frames: int,
    *,
    freq_hz: float,
    amplitude_px: float,
    fs_hz: float = 15.0,
) -> list[Lb6Frame]:
    frames: list[Lb6Frame] = []
    for t in range(num_frames):
        sec = t / fs_hz
        osc_l = amplitude_px * math.sin(2.0 * math.pi * freq_hz * sec)
        osc_r = amplitude_px * math.sin(2.0 * math.pi * freq_hz * sec + math.pi)
        joints = (
            (500.0, 300.0, 0.95),  # L_Hip
            (560.0, 300.0, 0.95),  # R_Hip
            (500.0 + 0.3 * osc_l, 420.0, 0.92),  # L_Knee
            (560.0 + 0.3 * osc_r, 420.0, 0.92),  # R_Knee
            (500.0 + osc_l, 540.0 + 0.2 * osc_l, 0.90),  # L_Ankle
            (560.0 + osc_r, 540.0 + 0.2 * osc_r, 0.90),  # R_Ankle
        )
        frames.append(Lb6Frame(keypoints=joints))
    return frames


def test_hampel_and_low_conf_interpolation_parity() -> None:
    arr = np.array([10.0, 10.5, 11.0, 999.0, 11.5, 12.0, 12.5], dtype=np.float64)
    denoised = hampel_filter_1d(arr, window=7, n_sigma=3.0)
    assert denoised[3] < 20.0

    xyc = np.zeros((5, 6, 3), dtype=np.float64)
    for j in range(6):
        xyc[:, j, 0] = np.array([0.0, 10.0, 999.0, 30.0, 40.0])
        xyc[:, j, 1] = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
        xyc[:, j, 2] = np.array([0.9, 0.9, 0.05, 0.9, 0.9])  # frame 2 occluded
    interp = interpolate_low_conf_lb6(xyc, conf_thres=0.20)
    assert interp[2, 0, 0] == np.float64(20.0)


def test_extract_126_fft_features_exact_shape_ddof0_and_nyquist_exclusion() -> None:
    rng = np.random.default_rng(42)
    window_raw = rng.normal(loc=0.1, scale=0.3, size=(9, 30, 6)).astype(np.float32)
    window_raw[2, :, :] = 0.88  # confidence channel

    # Inject a pure 7.5 Hz Nyquist oscillation into dx (channel 3) for L_Ankle (joint 4);
    # bin 15 (7.5 Hz > 0.49 * 15.0 = 7.35 Hz) MUST be excluded from freeze_bins.
    t_idx = np.arange(30, dtype=np.float32)
    nyquist_wave = ((-1.0) ** t_idx) * 5.0
    window_without_nyq = window_raw.copy()
    window_without_nyq[3, :, 4] = 0.0
    window_with_nyq = window_without_nyq.copy()
    window_with_nyq[3, :, 4] = nyquist_wave

    feat_no_nyq, _ = extract_fft_kinematic_features(window_without_nyq, fs=15.0)
    feat_nyq, _ = extract_fft_kinematic_features(window_with_nyq, fs=15.0)

    assert feat_nyq.shape == (126,)
    assert feat_nyq.dtype == np.float32
    assert np.all(np.isfinite(feat_nyq))

    # Population std (ddof=0) check for c_idx=0 (x), joint=0 (index 6 in 0..71 block)
    expected_std_x0 = float(np.std(window_raw[0, :, 0].astype(np.float64), ddof=0))
    assert np.isclose(feat_nyq[6], expected_std_x0, atol=1e-5)

    # e_freeze for dx joint 4 sits at base 72 + 6 (e_loco) + 4 = index 82
    assert np.isclose(feat_nyq[82], feat_no_nyq[82], atol=1e-6)


def test_two_tier_alert_fsm_and_causal_streaming_distinguish_gait_vs_freeze() -> None:
    fsm = TwoTierAlertStateMachine(threshold_val=0.26, min_run_windows=2)
    assert fsm.step(0.10) == AlertTier.NORMAL
    assert fsm.step(0.30) == AlertTier.EARLY_WARNING
    assert fsm.step(0.10) == AlertTier.NORMAL  # single spike resets
    assert fsm.step(0.30) == AlertTier.EARLY_WARNING
    assert fsm.step(0.35) == AlertTier.FOG_CONFIRMED
    assert fsm.step(0.10) == AlertTier.FOG_CONFIRMED  # 1 negative window holds (hysteresis)
    assert fsm.step(0.10) == AlertTier.NORMAL  # 2 consecutive negative windows clear

    classifier = DeterministicFreezeIndexClassifier(threshold_val=0.26)
    gait_proc = CausalLb6SlidingWindowProcessor(classifier)
    gait_frames = _make_synthetic_lb6_sequence(48, freq_hz=1.5, amplitude_px=40.0)
    gait_preds = [p for f in gait_frames if (p := gait_proc.push_frame(f)) is not None]
    assert len(gait_preds) == 2
    assert all(p.alert_tier == AlertTier.NORMAL for p in gait_preds)

    freeze_proc = CausalLb6SlidingWindowProcessor(classifier)
    freeze_frames = _make_synthetic_lb6_sequence(48, freq_hz=5.5, amplitude_px=15.0)
    freeze_preds = [p for f in freeze_frames if (p := freeze_proc.push_frame(f)) is not None]
    assert len(freeze_preds) == 2
    assert freeze_preds[0].freeze_index_ankle > gait_preds[0].freeze_index_ankle
    assert freeze_preds[0].alert_tier == AlertTier.EARLY_WARNING
    assert freeze_preds[1].alert_tier == AlertTier.FOG_CONFIRMED

    # Verify tensor build directly for 33 frames
    raw_arr = np.asarray(
        [[[x, y, c] for x, y, c in f.keypoints] for f in freeze_frames[:33]],
        dtype=np.float64,
    )
    tensor, scale = build_lb6_tensor_9ch(raw_arr)
    assert tensor.shape == (9, 33, 6)
    assert scale > 0.0
