"""Automated build-up pressure transient analysis (single-phase oil, field units).

    Horner:   p_ws = p* - m log10((tp + dt)/dt)
    k   = 162.6 q B mu / (m h)                                         [md]
    s   = 1.151 [ (p_1hr - p_wf)/m - log10(k / (phi mu ct rw^2)) + 3.23 ]
    dP_skin = 0.87 m s                                                 [psi]
    tp  = 24 Np / q   (Horner pseudo-producing time, hours)
    radius of investigation r_inv = sqrt(k dt / (948 phi mu ct))       [ft, dt in hours]

q is the VFM-predicted daily oil rate of the last full production day before shut-in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BuildupResult:
    well_name: str
    t_shut: pd.Timestamp
    duration_hr: float
    q_stbd: float
    tp_hr: float
    np_stb: float
    pwf_psia: float
    m_psi_cycle: float
    p_star_psia: float
    p1hr_psia: float
    k_md: float
    skin: float
    dP_skin: float
    flow_efficiency: float
    window_start_hr: float
    window_end_hr: float
    window_source: str
    r2: float
    r_inv_window_end_ft: float
    drainage_radius_ft: float
    deriv_m_psi_cycle: float          # m implied by the derivative plateau (cross-check)
    flags: list = field(default_factory=list)
    data: dict = field(default_factory=dict)   # arrays for plots

    def as_row(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("data", "flags")}
        d["flags"] = "; ".join(self.flags)
        return d


# --------------------------------------------------------------------------- helpers
def extract_buildup(minute: pd.DataFrame, well: str, t_shut, t_reopen) -> tuple[pd.DataFrame, float]:
    """Pressure vs shut-in time (hours) and the last flowing pressure p_wf(dt=0)."""
    d = minute[minute.well_name == well].set_index("timestamp")["dh_pressure_psia"].sort_index()
    pre = d.loc[t_shut - pd.Timedelta(minutes=15): t_shut - pd.Timedelta(minutes=1)].dropna()
    pwf = float(pre.iloc[-3:].median()) if len(pre) else np.nan
    bu = d.loc[t_shut + pd.Timedelta(minutes=1): t_reopen - pd.Timedelta(minutes=1)].dropna()
    dt = (bu.index - t_shut).total_seconds() / 3600.0
    return pd.DataFrame({"dt_hr": dt, "p_psia": bu.to_numpy()}), pwf


def log_resample(dt: np.ndarray, p: np.ndarray, per_cycle: int = 25) -> tuple[np.ndarray, np.ndarray]:
    """Median pressure in log-spaced dt bins (suppresses gauge noise at late time)."""
    edges = np.logspace(np.log10(dt.min()), np.log10(dt.max()) + 1e-9,
                        int(np.ceil(np.log10(dt.max() / dt.min()) * per_cycle)) + 1)
    idx = np.digitize(dt, edges)
    t_out, p_out = [], []
    for i in np.unique(idx):
        sel = idx == i
        t_out.append(np.exp(np.mean(np.log(dt[sel]))))
        p_out.append(np.median(p[sel]))
    return np.array(t_out), np.array(p_out)


def bourdet_derivative(te: np.ndarray, dp: np.ndarray, L: float = 0.15) -> np.ndarray:
    """Bourdet (1989) derivative d(dp)/d ln(te) with smoothing window L (natural-log units)."""
    x = np.log(te)
    n = len(x)
    der = np.full(n, np.nan)
    for i in range(n):
        j = i - 1
        while j >= 0 and x[i] - x[j] < L:
            j -= 1
        k = i + 1
        while k < n and x[k] - x[i] < L:
            k += 1
        if j < 0 or k >= n:
            continue
        dxl, dxr = x[i] - x[j], x[k] - x[i]
        dl, dr = (dp[i] - dp[j]) / dxl, (dp[k] - dp[i]) / dxr
        der[i] = (dl * dxr + dr * dxl) / (dxl + dxr)
    return der


def find_iarf_window(dt: np.ndarray, der: np.ndarray, min_span_cycles: float = 0.5,
                     t_max: float | None = None) -> tuple[float, float, float]:
    """Infinite-acting radial flow = flattest stretch of the log-log derivative.

    Scans windows spanning >= min_span_cycles, after the derivative has left wellbore-storage (unit-slope)
    behaviour, and scores them by the mean |d log(der) / d log(dt)| (0 for a perfect plateau).
    Returns (t_start, t_end, score).
    """
    ok = np.isfinite(der) & (der > 0)
    if t_max is not None:
        ok &= dt <= t_max
    t, g = dt[ok], der[ok]
    if len(t) < 6:
        return (np.nan, np.nan, np.inf)
    lt, lg = np.log10(t), np.log10(g)
    slope = np.gradient(lg, lt)
    # end of wellbore storage: first time the local derivative slope falls below 0.25 after any hump
    wbs_end_idx = 0
    peak = int(np.argmax(g[: max(3, len(g) // 2)]))
    for i in range(peak, len(slope)):
        if slope[i] < 0.25:
            wbs_end_idx = i
            break
    best = (np.nan, np.nan, np.inf)
    for i in range(wbs_end_idx, len(t)):
        for j in range(i + 2, len(t)):
            span = lt[j] - lt[i]
            if span < min_span_cycles:
                continue
            seg = slope[i: j + 1]
            score = np.mean(np.abs(seg)) + 0.02 / span   # favour flat, then longer windows
            if score < best[2]:
                best = (t[i], t[j], score)
            break_long = span > 1.5
            if break_long:
                break
    return best


def horner_fit(dt: np.ndarray, p: np.ndarray, tp: float, t0: float, t1: float):
    sel = (dt >= t0) & (dt <= t1)
    x = np.log10((tp + dt[sel]) / dt[sel])
    A = np.c_[np.ones(sel.sum()), x]
    (p_star, neg_m), *_ = np.linalg.lstsq(A, p[sel], rcond=None)
    m = -neg_m
    pred = A @ np.array([p_star, neg_m])
    ss_res = np.sum((p[sel] - pred) ** 2)
    ss_tot = np.sum((p[sel] - p[sel].mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    p1hr = p_star - m * np.log10(tp + 1.0)
    return float(m), float(p_star), float(p1hr), float(r2)


# --------------------------------------------------------------------------- main interpretation
def interpret_buildup(minute: pd.DataFrame, event: pd.Series, q_stbd: float, np_stb: float,
                      props: pd.Series, window: tuple[float, float] | None = None,
                      tp_override_hr: float | None = None) -> BuildupResult:
    bu, pwf = extract_buildup(minute, event.well_name, event.t_shut, event.t_reopen)
    flags = []
    dt_raw, p_raw = bu["dt_hr"].to_numpy(), bu["p_psia"].to_numpy()
    tp = tp_override_hr if tp_override_hr else 24.0 * np_stb / q_stbd
    dt, p = log_resample(dt_raw, p_raw)
    dp = p - pwf
    te = tp * dt / (tp + dt)                      # Agarwal equivalent time
    # the derivative does not depend on pwf (a constant), so it can be computed even when pwf is unknown
    der = bourdet_derivative(te, dp if np.isfinite(pwf) else p - p[0])
    if not np.isfinite(pwf):
        flags.append(f"no flowing pressure before the shut-in (data start {dt_raw.min():.1f} h after it): "
                     f"skin and Δp skin cannot be computed; k comes from the late-time Horner line")

    h, phi, mu = props.net_pay_thickness_ft, props.porosity_frac, props.oil_viscosity_cp
    B, ct, rw = props.oil_fvf_rb_stb, props.total_compressibility_1_psi, props.wellbore_radius_ft
    re = float(np.sqrt(props.estimated_drainage_area_acres * 43560.0 / np.pi))

    if window is None:
        t0, t1, score = find_iarf_window(dt, der)
        src = "auto (flattest derivative)"
        if not np.isfinite(t0):
            t0, t1, src = dt.max() / 10, dt.max(), "fallback (last log cycle)"
            flags.append("no derivative plateau found")
    else:
        t0, t1 = window
        src = "manual"

    m, p_star, p1hr, r2 = horner_fit(dt, p, tp, t0, t1)
    k = 162.6 * q_stbd * B * mu / (m * h)
    skin = 1.151 * ((p1hr - pwf) / m - np.log10(k / (phi * mu * ct * rw ** 2)) + 3.23)
    dps = 0.87 * m * skin
    fe = (p_star - pwf - dps) / (p_star - pwf) if p_star > pwf else np.nan
    r_inv = float(np.sqrt(k * t1 / (948.0 * phi * mu * ct)))
    sel = (dt >= t0) & (dt <= t1) & np.isfinite(der)
    deriv_m = float(np.median(der[sel]) * np.log(10)) if sel.any() else np.nan

    if r2 < 0.98:
        flags.append(f"Horner fit R2 {r2:.3f} < 0.98")
    if np.isfinite(deriv_m) and abs(deriv_m / m - 1) > 0.15:
        flags.append(f"derivative-plateau m differs from Horner m by {100 * (deriv_m / m - 1):+.0f}%")
    if r_inv > re:
        flags.append("radius of investigation exceeds drainage radius in window (boundary effects possible)")
    if np.log10(t1 / t0) < 0.5:
        flags.append("radial-flow window shorter than half a log cycle")
    if event.duration_hr < 6:
        flags.append("short shut-in (< 6 h)")

    data = dict(dt_raw=dt_raw, p_raw=p_raw, dt=dt, p=p, dp=dp, te=te, der=der,
                horner_x=(tp + dt) / dt, tp=tp)
    return BuildupResult(event.well_name, event.t_shut, float(event.duration_hr), float(q_stbd), float(tp),
                         float(np_stb), float(pwf), m, p_star, p1hr, float(k), float(skin), float(dps), float(fe),
                         float(t0), float(t1), src, r2, r_inv, re, deriv_m, flags, data)


def cumulative_oil_at(vfm_daily: pd.DataFrame, static: pd.DataFrame, well: str, t: pd.Timestamp) -> float:
    """Np at time t = cumulative at 1 Jan 2025 (completion data) + sum of VFM daily oil since then."""
    d = vfm_daily[(vfm_daily.well_name == well) & (pd.to_datetime(vfm_daily.date) < t.normalize())]
    base = float(static.loc[well, "cum_oil_at_2025_01_01_stb"]) if "cum_oil_at_2025_01_01_stb" in static else 0.0
    return base + float(d["oil_rate_stbd"].fillna(0).sum())


def rate_before_shutin(vfm_daily: pd.DataFrame, well: str, t: pd.Timestamp) -> tuple[float, str]:
    """VFM daily oil rate of the last full production day before the shut-in."""
    d = vfm_daily[(vfm_daily.well_name == well) & (pd.to_datetime(vfm_daily.date) < t.normalize())]
    full = d[d.on_stream_frac >= 0.999]
    row = (full if len(full) else d).sort_values("date").iloc[-1]
    return float(row["oil_rate_stbd"]), str(row["date"])


def run_all(minute: pd.DataFrame, events: pd.DataFrame, vfm_daily: pd.DataFrame, static: pd.DataFrame,
            windows: dict | None = None) -> tuple[pd.DataFrame, dict]:
    results, objs = [], {}
    for _, ev in events.iterrows():
        q, qdate = rate_before_shutin(vfm_daily, ev.well_name, ev.t_shut)
        npv = cumulative_oil_at(vfm_daily, static, ev.well_name, ev.t_shut)
        key = f"{ev.well_name} {ev.t_shut:%Y-%m-%d %H:%M}"
        r = interpret_buildup(minute, ev, q, npv, static.loc[ev.well_name], window=(windows or {}).get(key))
        r.data["q_date"] = qdate
        objs[key] = r
        results.append({"event": key, **r.as_row(), "q_from_date": qdate})
    return pd.DataFrame(results), objs
