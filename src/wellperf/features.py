"""Shut-in detection and feature aggregation (daily and per well-test window)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

AGG_COLS = C.SENSOR_COLS + ["choke_opening_pct", "choke_size_64ths"]


def add_flow_state(clean: pd.DataFrame) -> pd.DataFrame:
    """Mark each minute as flowing / shut-in.

    Gas-lift injection stops when a gas-lifted well is shut in, so GL rate ~ 0 is the primary signal;
    a choke setting of 0 % (when the choke log covers the period) is used as a second signal.
    Missing GL readings inherit the state of the preceding minutes. Readings missing at the very start of a file
    are treated as flowing (not back-filled): a file that starts just before a shut-in must not look shut from
    its first minute.
    """
    df = clean.sort_values(["well_name", "timestamp"]).copy()
    gl_off = df["gas_lift_rate_mscfd"] < C.SHUTIN_GL_MAX_MSCFD
    gl_off = gl_off.where(df["gas_lift_rate_mscfd"].notna())
    gl_off = gl_off.groupby(df["well_name"]).transform(lambda s: s.ffill().fillna(False)).astype(bool)
    choke_closed = df.get("choke_opening_pct", pd.Series(np.nan, index=df.index)).eq(0)
    df["shut_in"] = gl_off | choke_closed
    return df


def detect_shutins(df: pd.DataFrame) -> pd.DataFrame:
    """Contiguous shut-in periods longer than SHUTIN_MIN_DURATION_HR -> event table."""
    events = []
    for well, d in df.groupby("well_name", sort=True):
        s = d["shut_in"].to_numpy()
        ts = d["timestamp"].to_numpy()
        if not s.any():
            continue
        edges = np.diff(np.r_[0, s.astype(int), 0])
        starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
        for a, b in zip(starts, ends):
            dur = (b - a) / 60.0
            if dur >= C.SHUTIN_MIN_DURATION_HR:
                events.append(dict(well_name=well, t_shut=pd.Timestamp(ts[a]),
                                   t_reopen=pd.Timestamp(ts[b - 1]) + pd.Timedelta(minutes=1),
                                   duration_hr=round(dur, 2),
                                   ended_in_data=bool(b < len(s))))
    return pd.DataFrame(events)


def _aggregate(d: pd.DataFrame) -> dict:
    """Aggregate one block of minutes into model features (flowing minutes only)."""
    flow = d[~d["shut_in"]]
    out = {"n_minutes": len(d), "flow_minutes": len(flow)}
    for col in AGG_COLS:
        if col in flow:
            out[col] = flow[col].median()
    out["valid_dh_frac"] = flow["dh_pressure_psia"].notna().mean() if len(flow) else 0.0
    out["whp_std"] = flow["whp_psia"].std()
    return out


def add_derived(f: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
    """Physics-motivated derived features (all from sensors + static data, no targets)."""
    f = f.copy()
    st = static.reindex(f["well_name"])
    f["dp_choke_psi"] = f["whp_psia"] - f["whp_downstream_psia"]
    f["p_ratio_choke"] = f["whp_downstream_psia"] / f["whp_psia"]
    # gauge -> datum correction is a constant offset per well; kept as a feature input
    f["gauge_to_datum_ft"] = (st["datum_tvd_ft"] - st["gauge_tvd_ft"]).to_numpy()
    # tubing pressure gradient between gauge and wellhead (lift efficiency / fluid density proxy)
    f["tubing_grad_psi_ft"] = ((f["dh_pressure_psia"] - f["whp_psia"]) / st["gauge_tvd_ft"].to_numpy())
    # annulus-to-tubing differential at surface (gas-lift injection driving force proxy)
    f["dp_annulus_whp"] = f["annulus_pressure_psia"] - f["whp_psia"]
    # Bernoulli-type choke term: A * sqrt(dP)
    f["choke_bernoulli"] = (f["choke_size_64ths"] ** 2) * np.sqrt(f["dp_choke_psi"].clip(lower=0))
    return f


def daily_features(df: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
    """One row per well per calendar day."""
    d = df.copy()
    d["date"] = d["timestamp"].dt.normalize()
    rows = []
    for (well, day), g in d.groupby(["well_name", "date"], sort=True):
        r = _aggregate(g)
        r.update(well_name=well, date=day, shutin_minutes=int(g["shut_in"].sum()))
        rows.append(r)
    f = pd.DataFrame(rows)
    f["on_stream_frac"] = 1.0 - f["shutin_minutes"] / 1440.0
    return add_derived(f, static)


def window_features(df: pd.DataFrame, tests: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the cleaned HF data over each well-test window (train features = serve features)."""
    rows = []
    by_well = {w: g.set_index("timestamp") for w, g in df.groupby("well_name")}
    for _, t in tests.iterrows():
        g = by_well[t.well_name].loc[t.test_start: t.test_end - pd.Timedelta(minutes=1)].reset_index()
        r = _aggregate(g)
        r.update(well_name=t.well_name, test_start=t.test_start)
        rows.append(r)
    f = pd.DataFrame(rows)
    return add_derived(f, static)
