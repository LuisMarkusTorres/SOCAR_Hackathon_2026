"""Paths, column contracts and QC thresholds. Every hard-coded assumption lives here.

Paths can be redirected with environment variables (useful for a second dataset or for tests):
    WELLPERF_DATA_DIR     folder with the raw CSV files        (default data/raw)
    WELLPERF_WORK_DIR     folder for the cache, results, model (default: the repository)
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_WORK = Path(os.environ.get("WELLPERF_WORK_DIR", ROOT))
DATA_RAW = Path(os.environ.get("WELLPERF_DATA_DIR", ROOT / "data" / "raw"))
DATA_INTERIM = _WORK / "data" / "interim"
RESULTS = _WORK / "results"                    # submission: result files + PTA plots
MODELS = _WORK / "models"                      # submission: trained model (.pkl)
MODEL_FILE = MODELS / "vfm_model.pkl"

# ---- file contracts -------------------------------------------------------
HF_FILE = "high_freq_data.csv"
TESTS_FILE = "well_tests.csv"
CHOKE_FILE = "choke_events.csv"
PVT_FILE = "reservoir_pvt.csv"
COMPLETION_FILE = "well_completion.csv"

SENSOR_COLS = [
    "whp_psia",
    "whp_downstream_psia",
    "dh_pressure_psia",
    "dh_temperature_degf",
    "annulus_pressure_psia",
    "gas_lift_rate_mscfd",
]

# Raw logger null value (LAS convention)
SENTINEL_THRESHOLD = -999.0

# Hard physical bounds (outside -> invalid). Deliberately wide; spikes are handled by the Hampel filter.
PHYS_BOUNDS = {
    "whp_psia": (14.0, 5000.0),
    "whp_downstream_psia": (14.0, 5000.0),
    "dh_pressure_psia": (14.0, 15000.0),
    "dh_temperature_degf": (32.0, 400.0),
    "annulus_pressure_psia": (14.0, 5000.0),
    "gas_lift_rate_mscfd": (0.0, 10000.0),
}

# Hampel spike filter: rolling window (minutes) and minimum absolute deviation to call a spike.
HAMPEL_WINDOW = 31
HAMPEL_NSIGMA = 6.0
HAMPEL_MIN_ABS = {
    "whp_psia": 25.0,
    "whp_downstream_psia": 25.0,
    "dh_pressure_psia": 25.0,
    "dh_temperature_degf": 5.0,
    "annulus_pressure_psia": 25.0,
    "gas_lift_rate_mscfd": 150.0,
}

# A run of identical readings this long (minutes) is treated as a frozen sensor.
FROZEN_MIN_RUN = 60

# Short gaps (minutes) that may be linearly interpolated after cleaning.
MAX_INTERP_GAP_MIN = 10

# Shut-in detection: gas-lift injection stops when the well is shut in.
SHUTIN_GL_MAX_MSCFD = 5.0
SHUTIN_MIN_DURATION_HR = 1.0

# PTA behaviour. PTA_LEGACY_WINDOW=True restores the original window picker (flattest derivative after the first
# slope < 0.25 past the peak) exactly; the model match then only comments. PTA_MODEL_FALLBACK lets the analytical
# storage+skin match supply k and skin (flagged) when the record has no radial-flow plateau at all.
PTA_LEGACY_WINDOW = False
PTA_MODEL_FALLBACK = True

# Unit conversions
SM3_PER_MSCF = 1000.0 / 35.3147  # 1 Mscf = 28.3168 sm3

# Output contract (README deliverable)
VFM_OUTPUT_COLS = ["date", "well_name", "oil_rate_stbd", "water_rate_stbd", "gas_rate_mscfd"]
PTA_OUTPUT_COLS = ["well_name", "t_shut", "duration_hr", "m_psi_cycle", "k_md", "skin", "dP_skin"]
