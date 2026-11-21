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
from scipy.optimize import least_squares

from . import config as C
from .analytical import buildup_dp


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
    # analytical model match (storage + skin + k), always run as a cross-check; primary only when no radial flow
    k_match_md: float = np.nan
    skin_match: float = np.nan
    storage_bbl_psi: float = np.nan
    match_nrmse: float = np.nan       # RMS misfit / pressure-rise range (0 = perfect)
    t_iarf_model_hr: float = np.nan   # when radial flow starts according to the matched model
    k_match_p10_md: float = np.nan    # 80% range of the matched k (from the fit's Jacobian)
    k_match_p90_md: float = np.nan
    result_source: str = "Horner"     # 'Horner' | 'model match'

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


def storage_end_index(g: np.ndarray, slope: np.ndarray) -> int | None:
    """Index after which radial flow may be looked for, or None when the data is still storage-dominated.

    Wellbore storage shows as a rising derivative (unit slope) that peaks in a hump and comes back down before
    the radial-flow plateau. A flat stretch at the TOP of the hump is not radial flow, so when a storage rise is
    visible the window may only start once the derivative has fallen clearly below its peak and flattened again.
    When no rise is visible (the data starts after storage) the first flat point is used.
    """
    n = len(g)
    early = slice(0, max(3, n // 2))
    if C.PTA_LEGACY_WINDOW:                     # original picker, bit for bit: raw derivative, raw slope
        for i in range(int(np.argmax(g[early])), n):
            if slope[i] < 0.25:
                return i
        return 0
    gs = pd.Series(g).rolling(5, center=True, min_periods=1).median().to_numpy()   # noise-robust level
    peak = int(np.argmax(gs[early]))
    # a storage rise is a sustained unit-slope-like climb (not one noisy point) before the peak
    rising = peak >= 2 and np.sum(slope[:peak] > 0.5) >= 2 and gs[peak] > 1.5 * gs[0]
    if not rising:
        for i in range(n):
            if abs(slope[i]) < 0.25:
                return i
        return None
    # a storage hump is visible: radial flow can only begin after the derivative has come down from it
    g_peak = gs[peak]
    for i in range(peak + 1, n):
        if gs[i] < 0.75 * g_peak and slope[i] > -0.15:
            return i
    # never came down by a quarter: accept a flat tail at the end of the record, otherwise storage-dominated
    tail = slice(max(peak + 1, int(0.8 * n)), n)
    if n - tail.start >= 3 and np.nanmean(np.abs(slope[tail])) < 0.15:
        return tail.start
    return None


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
    sm = pd.Series(slope).rolling(5, center=True, min_periods=1).mean().to_numpy()   # ~0.2 log cycle
    wbs_end_idx = storage_end_index(g, slope if C.PTA_LEGACY_WINDOW else sm)
    if wbs_end_idx is None:
        return (np.nan, np.nan, np.inf)
    best = (np.nan, np.nan, np.inf)
    gs = pd.Series(g).rolling(5, center=True, min_periods=1).median().to_numpy()
    for i in range(wbs_end_idx, len(t)):
        for j in range(i + 2, len(t)):
            span = lt[j] - lt[i]
            if span < min_span_cycles:
                continue
            # The top of a storage hump can look flat. It is entered on a RISING derivative and left on a falling
            # one; a true plateau is entered after the descent. A late-time decline after a true plateau (boundary,
            # pressure support) must not reject it, so both signs are required.
            if not C.PTA_LEGACY_WINDOW:
                # a hump top is reached by a rise (or sits at the very start of the record); a true plateau is
                # reached by a descent. A steep fall within half a cycle after the window completes the hump.
                before = sm[max(0, i - 6): i]
                descended_into = len(before) >= 3 and np.nanmin(before) < -0.3
                later = gs[(lt > lt[j]) & (lt <= lt[j] + 0.5)]
                falls_after = len(later) >= 3 and np.median(gs[i: j + 1]) > 1.5 * later.min()
                if falls_after and not descended_into:
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
    sel = (dt >= t0) & (dt <= t1) & np.isfinite(p)
    if sel.sum() < 3:
        return np.nan, np.nan, np.nan, np.nan
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


# --------------------------------------------------------------------------- analytical model match
def model_match(dt: np.ndarray, dp: np.ndarray, te: np.ndarray, der: np.ndarray, q: float, tp: float,
                props: dict, k0: float | None = None) -> dict:
    """Fit k, skin and wellbore storage C of the storage+skin radial-flow model to the whole build-up.

    Residuals: pressure rise (scaled by its range) and the log of the Bourdet derivative, so both the level
    and the shape of the curve count. Three physical parameters against the full record, no tuning constants
    beyond the parameter bounds. Returns the fit and the time at which the matched model reaches radial flow.
    """
    ok = np.isfinite(dp) & (dp > 0) & np.isfinite(dt)
    dt, dp, te = dt[ok], dp[ok], te[ok]
    der_ok = np.isfinite(der[ok]) & (der[ok] > 0)
    rng = float(dp.max() - dp.min()) or 1.0
    h, B, mu = props["h"], props["B"], props["mu"]
    C0 = float(np.clip(np.median(q * B * dt[:5] / (24.0 * dp[:5])), 1e-4, 5.0))
    if not k0 or not np.isfinite(k0) or k0 <= 0:
        late = der[ok][der_ok][-5:]
        k0 = float(np.clip(70.6 * q * B * mu / (h * np.median(late)), 0.5, 5000)) if len(late) else 50.0

    def resid(x):
        k, sk, C = 10 ** x[0], x[1], 10 ** x[2]
        m_dp = buildup_dp(dt, k, sk, C, q, tp, props)
        r = [(m_dp - dp) / rng]
        if der_ok.sum() >= 5:
            m_der = bourdet_derivative(te, m_dp)
            both = der_ok & np.isfinite(m_der) & (m_der > 0)
            r.append(0.5 * (np.log(m_der[both]) - np.log(der[ok][both])) / np.sqrt(max(both.sum(), 1) / max(len(dp), 1)))
        return np.concatenate(r)

    late = der[ok][der_ok][-5:]
    k_late = float(np.clip(70.6 * q * B * mu / (h * np.median(late)), 0.5, 5000)) if len(late) else k0
    starts = {(round(np.log10(kk), 2), s0) for kk in (k0, k_late, 1.0, 10.0, 100.0, 1000.0) for s0 in (0.0, 5.0)}
    fit = None
    for lk, s0 in sorted(starts):
        f = least_squares(resid, np.array([lk, s0, np.log10(C0)]), bounds=([-1.0, -6.0, -4.5], [4.5, 60.0, 1.0]),
                          method="trf", max_nfev=150)
        if fit is None or f.cost < fit.cost:
            fit = f
    k, sk, C = 10 ** fit.x[0], float(fit.x[1]), 10 ** fit.x[2]
    # uncertainty from the Jacobian: when only the storage hump is in the record, k and skin trade off
    try:
        J = fit.jac
        dof = max(len(fit.fun) - 3, 1)
        cov = np.linalg.inv(J.T @ J) * (2 * fit.cost / dof)
        sd_logk, sd_skin = float(np.sqrt(cov[0, 0])), float(np.sqrt(cov[1, 1]))
    except np.linalg.LinAlgError:
        sd_logk = sd_skin = np.nan
    m_dp = buildup_dp(dt, k, sk, C, q, tp, props)
    nrmse = float(np.sqrt(np.mean((m_dp - dp) ** 2)) / rng)
    # start of radial flow in the matched model: derivative within 5% of its plateau 70.6 qB mu/(kh)
    grid = np.logspace(np.log10(dt.min()), np.log10(dt.max()) + 2.0, 300)
    tgrid = tp * grid / (tp + grid)
    g_der = bourdet_derivative(tgrid, buildup_dp(grid, k, sk, C, q, tp, props))
    plateau = 70.6 * q * B * mu / (k * h)
    off = np.isfinite(g_der) & (np.abs(g_der / plateau - 1) > 0.05)
    t_iarf = float(grid[off].max()) if off.any() else float(grid[np.isfinite(g_der)].min())
    return dict(k=float(k), skin=sk, C=float(C), nrmse=nrmse, t_iarf=t_iarf, dp_model=m_dp, dt_model=dt,
                der_model=bourdet_derivative(te, m_dp), ok=fit.success,
                k_p10=float(10 ** (np.log10(k) - 1.2816 * sd_logk)), k_p90=float(10 ** (np.log10(k) + 1.2816 * sd_logk)),
                skin_sd=sd_skin, sd_logk=sd_logk)


# --------------------------------------------------------------------------- main interpretation
def interpret_buildup(minute: pd.DataFrame, event: pd.Series, q_stbd: float, np_stb: float,
                      props: pd.Series, window: tuple[float, float] | None = None,
                      tp_override_hr: float | None = None) -> BuildupResult:
    bu, pwf = extract_buildup(minute, event.well_name, event.t_shut, event.t_reopen)
    flags = []
    dt_raw, p_raw = bu["dt_hr"].to_numpy(), bu["p_psia"].to_numpy()
    if len(dt_raw) < 10:
        raise ValueError(f"{event.well_name} {event.t_shut}: only {len(dt_raw)} valid gauge readings during the shut-in")
    if tp_override_hr:
        tp = float(tp_override_hr)
    elif np.isfinite(q_stbd) and q_stbd > 0 and np.isfinite(np_stb) and np_stb > 0:
        tp = 24.0 * np_stb / q_stbd
    else:
        # no usable rate: Horner time with a very long tp is almost MDH; k then cannot be scaled from m
        tp = 24.0 * 365.0 * 10
        flags.append("no VFM oil rate before the shut-in: tp set to 10 years, k and skin not available")
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

    q_ok = np.isfinite(q_stbd) and q_stbd > 0
    mprops = dict(h=h, phi=phi, mu=mu, B=B, ct=ct, rw=rw)
    t0 = t1 = np.nan
    if window is None:
        t0, t1, score = find_iarf_window(dt, der)
        src = "auto (flattest derivative after storage)"
    else:
        t0, t1 = window
        src = "manual"

    # analytical model match: always computed as a cross-check (needs pwf and a rate)
    match = None
    if q_ok and np.isfinite(pwf):
        try:
            k_guess = None
            if np.isfinite(t0):
                m0 = horner_fit(dt, p, tp, t0, t1)[0]
                k_guess = 162.6 * q_stbd * B * mu / (m0 * h) if np.isfinite(m0) and m0 > 0 else None
            match = model_match(dt, dp, te, der, q_stbd, tp, mprops, k_guess)
        except Exception:
            match = None
    credible = match is not None and match["ok"] and match["nrmse"] < 0.04
    half_cycle_left = lambda t_start: np.log10(dt.max() / t_start) >= 0.5

    # When the data show a plateau, the Horner line on it is the result; the model match only comments on it.
    # Only when the data offer no plateau at all does the match supply the estimate (and says so).
    source = "Horner"
    if window is None and not np.isfinite(t0) and credible and half_cycle_left(match["t_iarf"]):
        # the data picker found nothing; take the model's radial-flow start, at most one log cycle, and only
        # if the data derivative is actually flat there
        t_a, t_b = match["t_iarf"], min(dt.max(), match["t_iarf"] * 10.0)
        okd = np.isfinite(der) & (der > 0) & (dt >= t_a) & (dt <= t_b)
        if okd.sum() >= 4:
            sl = np.gradient(np.log10(der[okd]), np.log10(dt[okd]))
            if np.mean(np.abs(sl)) < 0.2:
                t0, t1, src = t_a, t_b, "auto (start from model match)"
    if not np.isfinite(t0):
        t0, t1, src = dt.max() / (10 if C.PTA_LEGACY_WINDOW else 10 ** 0.5), dt.max(), "none (storage-dominated)"
        if credible and C.PTA_MODEL_FALLBACK:
            source = "model match"
            flags.append(f"storage-dominated shut-in: no radial-flow plateau in the data; k and skin come from the "
                         f"analytical model match (storage + skin), not from a Horner line; k 80% range "
                         f"{match['k_p10']:.0f}–{match['k_p90']:.0f} md")
        else:
            flags.append("no radial-flow plateau found and no credible model match: results are unreliable")

    m, p_star, p1hr, r2 = horner_fit(dt, p, tp, t0, t1)
    if not np.isfinite(m) or m <= 0:
        t0, t1, src = dt.max() / 10, dt.max(), "fallback (last log cycle)"
        m, p_star, p1hr, r2 = horner_fit(dt, p, tp, t0, t1)
        flags.append("straight-line fit failed in the chosen window; last log cycle used instead")
    if source == "model match":
        k = match["k"]
        skin = match["skin"]
        m = 162.6 * q_stbd * B * mu / (k * h)
    else:
        k = 162.6 * q_stbd * B * mu / (m * h) if q_ok else np.nan
        skin = 1.151 * ((p1hr - pwf) / m - np.log10(k / (phi * mu * ct * rw ** 2)) + 3.23)
    dps = 0.87 * m * skin
    fe = (p_star - pwf - dps) / (p_star - pwf) if p_star > pwf else np.nan
    r_inv = float(np.sqrt(k * t1 / (948.0 * phi * mu * ct)))
    sel = (dt >= t0) & (dt <= t1) & np.isfinite(der)
    deriv_m = float(np.median(der[sel]) * np.log(10)) if sel.any() else np.nan

    if source == "Horner" and np.isfinite(r2) and r2 < 0.98:
        flags.append(f"Horner fit R2 {r2:.3f} < 0.98")
    if source == "Horner" and np.isfinite(deriv_m) and abs(deriv_m / m - 1) > 0.15:
        flags.append(f"derivative-plateau m differs from Horner m by {100 * (deriv_m / m - 1):+.0f}%")
    if np.isfinite(r_inv) and r_inv > re:
        flags.append("radius of investigation exceeds drainage radius in window (boundary effects possible)")
    if source == "Horner" and np.log10(t1 / t0) < 0.5:
        flags.append("radial-flow window shorter than half a log cycle")
    if event.duration_hr < 6:
        flags.append("short shut-in (< 6 h)")
    if source == "Horner" and credible and np.isfinite(k) and abs(match["k"] / k - 1) > 0.3:
        flags.append(f"model match gives k = {match['k']:.0f} md, skin {match['skin']:.1f} "
                     f"({100 * (match['k'] / k - 1):+.0f}% on k): the plateau may not be true radial flow")

    data = dict(dt_raw=dt_raw, p_raw=p_raw, dt=dt, p=p, dp=dp, te=te, der=der,
                horner_x=(tp + dt) / dt, tp=tp)
    if match is not None:
        data.update(dt_model=match["dt_model"], dp_model=match["dp_model"], der_model=match["der_model"])
    r = BuildupResult(event.well_name, event.t_shut, float(event.duration_hr), float(q_stbd), float(tp),
                      float(np_stb), float(pwf), m, p_star, p1hr, float(k), float(skin), float(dps), float(fe),
                      float(t0), float(t1), src, r2, r_inv, re, deriv_m, flags, data)
    if match is not None:
        r.k_match_md, r.skin_match, r.storage_bbl_psi = match["k"], match["skin"], match["C"]
        r.match_nrmse, r.t_iarf_model_hr = match["nrmse"], match["t_iarf"]
        r.k_match_p10_md, r.k_match_p90_md = match["k_p10"], match["k_p90"]
        if source == "model match" and np.isfinite(match["sd_logk"]) and match["sd_logk"] > 0.15:
            r.flags.append(f"k and skin are poorly separable from this record (k 80% range "
                           f"{match['k_p10']:.0f}–{match['k_p90']:.0f} md): a longer shut-in is needed")
    r.result_source = source
    return r


def cumulative_oil_at(vfm_daily: pd.DataFrame, static: pd.DataFrame, well: str, t: pd.Timestamp) -> float:
    """Np at time t = cumulative at 1 Jan 2025 (completion data) + sum of VFM daily oil since then."""
    d = vfm_daily[(vfm_daily.well_name == well) & (pd.to_datetime(vfm_daily.date) < t.normalize())]
    base = float(static.loc[well, "cum_oil_at_2025_01_01_stb"]) if "cum_oil_at_2025_01_01_stb" in static else 0.0
    return base + float(d["oil_rate_stbd"].fillna(0).sum())


def rate_before_shutin(vfm_daily: pd.DataFrame, well: str, t: pd.Timestamp) -> tuple[float, str]:
    """VFM daily oil rate of the last full production day before the shut-in.

    Falls back to the last partly flowing day, and when the shut-in starts on the first day of the data, to the
    first flowing day after it (the rate is then labelled so the report shows where it came from).
    """
    w = vfm_daily[vfm_daily.well_name == well].assign(_d=lambda x: pd.to_datetime(x.date)).sort_values("_d")
    w = w[w["oil_rate_stbd"].notna()]
    before = w[w._d < t.normalize()]
    full = before[before.on_stream_frac >= 0.999]
    flowing = before[before.on_stream_frac > 0]
    if len(full):
        row = full.iloc[-1]
    elif len(flowing):
        row = flowing.iloc[-1]
    else:
        after = w[(w._d > t.normalize()) & (w.on_stream_frac >= 0.999)]
        if not len(after):
            return float("nan"), "no flowing day in the data"
        row = after.iloc[0]
        return float(row["oil_rate_stbd"]), f"{row['date']} (first full day after the shut-in)"
    # a partial day's volume is scaled back to a flowing rate
    frac = float(row["on_stream_frac"]) if row["on_stream_frac"] > 0 else 1.0
    return float(row["oil_rate_stbd"]) / frac, str(row["date"])


def run_all(minute: pd.DataFrame, events: pd.DataFrame, vfm_daily: pd.DataFrame, static: pd.DataFrame,
            windows: dict | None = None) -> tuple[pd.DataFrame, dict]:
    results, objs = [], {}
    for _, ev in events.iterrows():
        q, qdate = rate_before_shutin(vfm_daily, ev.well_name, ev.t_shut)
        npv = cumulative_oil_at(vfm_daily, static, ev.well_name, ev.t_shut)
        key = f"{ev.well_name} {ev.t_shut:%Y-%m-%d %H:%M}"
        props = static.loc[ev.well_name]
        try:
            r = interpret_buildup(minute, ev, q, npv, props, window=(windows or {}).get(key))
        except ValueError:                          # too few gauge readings during the shut-in: nothing to interpret
            continue
        r.data["q_date"] = qdate
        # p* moved from gauge depth to datum depth with the live-oil gradient (pipeline.datum_gradient)
        grad = float(props.get("fluid_gradient_psi_ft", np.nan))
        dz = float(props.get("datum_tvd_ft", np.nan)) - float(props.get("gauge_tvd_ft", np.nan))
        r.data["gradient_psi_ft"], r.data["gauge_to_datum_ft"] = grad, dz
        r.data["p_star_datum_psia"] = r.p_star_psia + grad * dz if np.isfinite(grad) and np.isfinite(dz) else np.nan
        objs[key] = r
        results.append({"event": key, **r.as_row(), "q_from_date": qdate,
                        "p_star_datum_psia": r.data["p_star_datum_psia"], "fluid_gradient_psi_ft": grad})
    return pd.DataFrame(results), objs
