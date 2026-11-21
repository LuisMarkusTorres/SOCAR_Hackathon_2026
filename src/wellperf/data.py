"""Loading + data-quality cleaning. Raw files are never modified; every correction is logged."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _path(name: str, data_dir: Path | None) -> Path:
    return Path(data_dir or C.DATA_RAW) / name


def load_hf_raw(path: Path | str | None = None) -> pd.DataFrame:
    """Per-minute sensor data. Uses a parquet cache next to the interim data for speed."""
    path = Path(path or _path(C.HF_FILE, None))
    cache = C.DATA_INTERIM / (path.stem + ".parquet")
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return pd.read_parquet(cache)
    df = pd.read_csv(path, parse_dates=["timestamp"])
    C.DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def load_static(data_dir: Path | None = None) -> pd.DataFrame:
    """PVT + completion data, one row per well."""
    pvt = pd.read_csv(_path(C.PVT_FILE, data_dir))
    comp = pd.read_csv(_path(C.COMPLETION_FILE, data_dir), parse_dates=["first_production_date"])
    return pvt.merge(comp, on="well_name", how="outer").set_index("well_name")


def load_choke(data_dir: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(_path(C.CHOKE_FILE, data_dir), parse_dates=["timestamp"]).sort_values(["well_name", "timestamp"])


def load_tests_raw(data_dir: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(_path(C.TESTS_FILE, data_dir), parse_dates=["test_start", "test_end"])


# ---------------------------------------------------------------------------
# Well-test reconciliation
# ---------------------------------------------------------------------------
_TEST_POSITIVE = [
    "whp_psia", "whp_downstream_psia", "dh_pressure_psia", "dh_temperature_degf", "annulus_pressure_psia",
    "gas_lift_rate_mscfd", "separator_pressure_psia", "separator_temperature_degf", "oil_rate_stbd",
    "water_rate_stbd", "gas_rate_mscfd", "total_gas_rate_mscfd", "liquid_rate_stbd", "water_cut_pct",
    "gor_scf_stb", "glr_scf_stb", "bsw_pct",
]


def clean_tests(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fix sign flips and unit errors using the redundant columns (liquid=oil+water, total=formation+lift, ...).

    Returns (clean_tests, issue_log).
    """
    df = raw.copy()
    log: list[dict] = []

    def note(i, col, issue, before, after):
        log.append(dict(well_name=df.at[i, "well_name"], test_start=df.at[i, "test_start"], column=col,
                        issue=issue, original=before, corrected=after))

    # 1) sign flips: these quantities cannot be negative
    for col in _TEST_POSITIVE:
        if col not in df:
            continue
        for i in df.index[df[col] < 0]:
            before = df.at[i, col]
            df.at[i, col] = abs(before)
            note(i, col, "negative value (sign flip) -> abs", before, df.at[i, col])

    # 2) gas unit errors: formation gas should equal oil * GOR / 1000 [Mscf/d]
    expected_gas = df["oil_rate_stbd"] * df["gor_scf_stb"] / 1000.0
    ratio = df["gas_rate_mscfd"] / expected_gas
    is_sm3 = (ratio / C.SM3_PER_MSCF).between(0.95, 1.05)
    for i in df.index[is_sm3]:
        for col in ["gas_rate_mscfd", "total_gas_rate_mscfd"]:
            before = df.at[i, col]
            df.at[i, col] = before / C.SM3_PER_MSCF
            note(i, col, "reported in sm3/d -> converted to Mscf/d", before, df.at[i, col])

    # 3) redundancy checks (flag, and repair a single inconsistent member from the other two)
    def repair(target, value, tol, label):
        bad = (df[target] - value).abs() > tol * value.abs().clip(lower=1)
        for i in df.index[bad]:
            before = df.at[i, target]
            df.at[i, target] = value[i]
            note(i, target, f"inconsistent with {label} -> recomputed", before, value[i])

    repair("liquid_rate_stbd", df["oil_rate_stbd"] + df["water_rate_stbd"], 0.02, "oil+water")
    repair("total_gas_rate_mscfd", df["gas_rate_mscfd"] + df["gas_lift_rate_mscfd"], 0.03, "formation+lift gas")
    repair("water_cut_pct", 100 * df["water_rate_stbd"] / df["liquid_rate_stbd"], 0.02, "water/liquid")

    df["test_mid"] = df["test_start"] + (df["test_end"] - df["test_start"]) / 2
    df["test_hours"] = (df["test_end"] - df["test_start"]).dt.total_seconds() / 3600
    return df.sort_values(["well_name", "test_start"]).reset_index(drop=True), pd.DataFrame(log)


# ---------------------------------------------------------------------------
# High-frequency cleaning
# ---------------------------------------------------------------------------
def _hampel(s: pd.Series, window: int, nsig: float, min_abs: float) -> pd.Series:
    med = s.rolling(window, center=True, min_periods=5).median()
    dev = (s - med).abs()
    mad = dev.rolling(window, center=True, min_periods=5).median()
    return dev > np.maximum(nsig * 1.4826 * mad, min_abs)


def _frozen(s: pd.Series, min_run: int, ignore_value: float | None = None) -> pd.Series:
    same = s.eq(s.shift()) & s.notna()
    run_id = (~same).cumsum()
    run_len = s.groupby(run_id).transform("size")
    mask = run_len >= min_run
    if ignore_value is not None:
        mask &= s.ne(ignore_value)
    return mask


def clean_hf(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Regularise to a 1-minute grid per well and remove invalid readings.

    Steps: duplicates averaged -> sentinel/negative/out-of-bounds -> NaN -> Hampel spikes -> NaN ->
    frozen runs -> NaN -> short gaps (<= MAX_INTERP_GAP_MIN) linearly interpolated.
    Returns (clean minute data, per-well/column issue counts).
    """
    df = raw.copy()
    n_dup = int(df.duplicated(["well_name", "timestamp"]).sum())
    df = df.groupby(["well_name", "timestamp"], as_index=False)[C.SENSOR_COLS].mean()

    out, counts = [], []
    for well, d in df.groupby("well_name", sort=True):
        d = d.set_index("timestamp").sort_index()
        grid = pd.date_range(d.index.min().floor("D"), d.index.max().ceil("D") - pd.Timedelta(minutes=1), freq="min")
        d = d.reindex(grid)
        d.index.name = "timestamp"
        rec = {"well_name": well, "duplicates_averaged": None, "missing_minutes": int(d[C.SENSOR_COLS[0]].isna().sum())}
        for col in C.SENSOR_COLS:
            s = d[col]
            sentinel = s <= C.SENTINEL_THRESHOLD
            lo, hi = C.PHYS_BOUNDS[col]
            oob = ~sentinel & s.notna() & ((s < lo) | (s > hi))
            s = s.mask(sentinel | oob)
            spikes = _hampel(s, C.HAMPEL_WINDOW, C.HAMPEL_NSIGMA, C.HAMPEL_MIN_ABS[col]) & s.notna()
            s = s.mask(spikes)
            frozen = _frozen(s, C.FROZEN_MIN_RUN, ignore_value=0.0 if col == "gas_lift_rate_mscfd" else None)
            s = s.mask(frozen)
            n_invalid_before_interp = int(s.isna().sum())
            s = s.interpolate(limit=C.MAX_INTERP_GAP_MIN, limit_area="inside")
            d[col] = s
            rec.update({f"{col}|sentinel": int(sentinel.sum()), f"{col}|out_of_bounds": int(oob.sum()),
                        f"{col}|spikes": int(spikes.sum()), f"{col}|frozen": int(frozen.sum()),
                        f"{col}|still_missing": int(s.isna().sum()),
                        f"{col}|interpolated": n_invalid_before_interp - int(s.isna().sum())})
        d["well_name"] = well
        out.append(d.reset_index())
        counts.append(rec)
    clean = pd.concat(out, ignore_index=True)
    rep = pd.DataFrame(counts)
    rep["duplicates_averaged"] = n_dup  # dataset-level count
    return clean, rep


def add_choke(clean: pd.DataFrame, choke: pd.DataFrame | None, static: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach the step-wise choke opening (%) and bean size (1/64 in) to every minute."""
    df = clean.copy()
    df["choke_opening_pct"] = np.nan
    if choke is not None and len(choke):
        parts = []
        for well, d in df.groupby("well_name", sort=False):
            ch = choke[choke.well_name == well][["timestamp", "choke_opening_pct"]].sort_values("timestamp")
            d = d.drop(columns="choke_opening_pct").sort_values("timestamp")
            if len(ch):
                d = pd.merge_asof(d, ch, on="timestamp", direction="backward")
            else:
                d["choke_opening_pct"] = np.nan
            parts.append(d)
        df = pd.concat(parts, ignore_index=True)
    if static is not None and "choke_max_size_64ths" in static:
        df["choke_size_64ths"] = df["choke_opening_pct"] / 100.0 * df["well_name"].map(static["choke_max_size_64ths"])
    return df


def load_clean_hf(hf_path: Path | str | None = None, data_dir: Path | None = None, use_cache: bool = True):
    """Full HF preparation with a parquet cache. Returns (minute data, qc report)."""
    hf_path = Path(hf_path or _path(C.HF_FILE, data_dir))
    cache = C.DATA_INTERIM / (hf_path.stem + "_clean.parquet")
    cache_rep = C.DATA_INTERIM / (hf_path.stem + "_qc.parquet")
    if use_cache and cache.exists() and cache.stat().st_mtime >= hf_path.stat().st_mtime:
        return pd.read_parquet(cache), pd.read_parquet(cache_rep)
    raw = pd.read_csv(hf_path, parse_dates=["timestamp"]) if hf_path.suffix == ".csv" else pd.read_parquet(hf_path)
    clean, rep = clean_hf(raw)
    choke_path = Path(data_dir or C.DATA_RAW) / C.CHOKE_FILE
    choke = load_choke(data_dir) if choke_path.exists() else None
    static = load_static(data_dir)
    clean = add_choke(clean, choke, static)
    C.DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(cache, index=False)
    rep.to_parquet(cache_rep, index=False)
    return clean, rep
