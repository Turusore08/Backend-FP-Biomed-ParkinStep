from src.domain.enums.clinical_enums import ClassifierName

# Locked DSP constants from EDGE_ML_SPEC.md (Skenario B @ 15 Hz)
TARGET_FS_HZ: float = 15.0
CONF_VALID_THRES: float = 0.20
HAMPEL_WINDOW: int = 7
HAMPEL_SIGMA: float = 3.0
BUTTER_CUTOFF_HZ: float = 9.0
WINDOW_SEC: float = 2.0
STRIDE_SEC: float = 1.0
MIN_RUN_WINDOWS: int = 2

LB6_JOINT_NAMES: tuple[str, ...] = (
    "L_Hip",
    "R_Hip",
    "L_Knee",
    "R_Knee",
    "L_Ankle",
    "R_Ankle",
)

# StandardScaler constants from from_B_denoised_hampel_accel_15hz/scaler_stats.npz
SCALER_MEAN_B15HZ: tuple[float, ...] = (
    0.05256000,
    0.47850001,
    0.88466001,
    -0.00002000,
    -0.00001000,
    -0.00001000,
    0.00000000,
    0.00343000,
    0.31830999,
)

SCALER_STD_B15HZ: tuple[float, ...] = (
    0.32510000,
    0.40507001,
    0.26166001,
    0.07987000,
    0.01337000,
    0.05731000,
    0.00986000,
    0.14646000,
    0.23871999,
)

DEFAULT_THRESHOLDS_B15HZ: dict[ClassifierName, float] = {
    ClassifierName.LIGHTGBM_FFT: 0.26,
    ClassifierName.LIGHT_STGCN: 0.39,
    ClassifierName.PURE_BIMAMBA: 0.15,
}

# Mandatory medical disclaimer from DATA_PRIVACY_AND_CLINICAL_SAFETY.md §1.3
MEDICAL_DISCLAIMER_ID: str = (
    "PERHATIAN MEDIS: ParkinStep merupakan alat bantu skrining dan pemantauan mandiri "
    "gejala Freezing of Gait (FoG) berbasis kecerdasan buatan. Hasil deteksi, skor indeks, "
    "dan grafik pada aplikasi ini BUKAN merupakan diagnosis medis resmi dan tidak dapat "
    "dijadikan dasar perubahan dosis obat tanpa persetujuan dokter spesialis saraf. "
    "Jika pasien mengalami jatuh, cedera, atau gejala memburuk secara mendadak, segera "
    "hubungi tenaga medis atau layanan gawat darurat setempat."
)
