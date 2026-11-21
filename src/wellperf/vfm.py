"""Virtual Flow Metering: physics-structured regression calibrated on periodic well tests.

Model (per well w, t = days since reference date, Pwf = downhole gauge pressure while flowing):

    liquid rate   q_L(t) = J_w * (Pres_w(t) - Pwf(t)),   Pres_w(t) = p0_w + p1_w * t
                         = a_w + b_w * t - J_w * Pwf        (linear IPR, undersaturated oil: Pwf >> Pb)
    water cut     WC_w(t) = c_w + d_w * t                   (water breakthrough trend)
    GOR           GOR_w   = shrink(mean of tests -> Rs at Pb)   (single-phase above Pb => GOR ~ Rs)

    oil = q_L (1 - WC),  water = q_L WC,  formation gas = oil * GOR / 1000
    daily volume = rate while flowing * on-stream fraction of the day

Uncertainty: empirical (split-conformal style) relative error quantiles from forward-chaining backtests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

T_REF = pd.Timestamp("2025-01-01")
PHASES = ["oil_rate_stbd", "water_rate_stbd", "gas_rate_mscfd"]


def days_since_ref(ts) -> np.ndarray:
    return ((pd.to_datetime(ts) - T_REF) / pd.Timedelta(days=1)).to_numpy(dtype=float)


@dataclass
class WellParams:
    well_name: str
    n_tests: int
    a: float            # liquid intercept  [stb/d]
    b: float            # liquid time trend [stb/d/day]
    J: float            # productivity index [stb/d/psi]
    J_source: str       # 'well regression' | 'pooled prior'
    wc_c: float         # water cut intercept [%]
    wc_d: float         # water cut trend [%/day]
    gor: float          # [scf/stb]
    rs_pb: float        # solution GOR at Pb (static data) [scf/stb]
    last_test: str
    resid_liq_std: float

    def reservoir_pressure(self, t_days: np.ndarray) -> np.ndarray:
        """Average reservoir pressure (gauge depth) implied by the calibrated IPR."""
        if not self.J or self.J <= 0:
            return np.full_like(np.asarray(t_days, dtype=float), np.nan)
        return (self.a + self.b * np.asarray(t_days, dtype=float)) / self.J


@dataclass
class VFMModel:
    gor_shrink_k: float = 5.0          # pseudo-count pulling the GOR estimate toward Rs(Pb)
    recency_halflife_days: float | None = None
    min_tests_for_J: int = 5
    J_prior_rel_sd: float = 1.0        # prior uncertainty of J (fraction of the pooled prior)
    params: dict = field(default_factory=dict)
    pooled_J_rel: float = np.nan       # pooled J / mean liquid rate (prior for sparse wells) [1/psi]
    rel_err_q: dict = field(default_factory=dict)   # {phase: {"q05":..,"q95":..}} relative errors
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ fitting
    def _weights(self, t: np.ndarray) -> np.ndarray:
        if not self.recency_halflife_days:
            return np.ones_like(t)
        return 0.5 ** ((t.max() - t) / self.recency_halflife_days)

    @staticmethod
    def _wls(X, y, w):
        sw = np.sqrt(w)
        beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
        return beta

    def _pooled_J_rel(self, train: pd.DataFrame) -> float:
        """Within-well regression of liquid on Pwf after removing each well's level+trend, rates normalised by well mean."""
        rp_all, ry_all = [], []
        for _, h in train.groupby("well_name"):
            if len(h) < 4:
                continue
            t = days_since_ref(h["test_mid"])
            X = np.c_[np.ones(len(h)), t - t.mean()]
            y = h["liquid_rate_stbd"].to_numpy() / h["liquid_rate_stbd"].mean()
            p = h["dh_pressure_psia"].to_numpy()
            ry_all.append(y - X @ np.linalg.lstsq(X, y, rcond=None)[0])
            rp_all.append(p - X @ np.linalg.lstsq(X, p, rcond=None)[0])
        if not rp_all:
            return 0.0
        rp, ry = np.concatenate(rp_all), np.concatenate(ry_all)
        return float(max(-(rp @ ry) / (rp @ rp), 0.0))

    def fit(self, train: pd.DataFrame, static: pd.DataFrame) -> "VFMModel":
        """train: one row per well test with targets + HF window features (dh_pressure_psia, test_mid)."""
        train = train.dropna(subset=["dh_pressure_psia", "liquid_rate_stbd"]).sort_values("test_mid")
        self.pooled_J_rel = self._pooled_J_rel(train)
        self.params = {}
        for well, h in train.groupby("well_name"):
            t = days_since_ref(h["test_mid"])
            w = self._weights(t)
            pwf = h["dh_pressure_psia"].to_numpy()
            liq = h["liquid_rate_stbd"].to_numpy()
            J_prior = self.pooled_J_rel * liq.mean()
            J, src = J_prior, "pooled prior"
            if len(h) >= self.min_tests_for_J and J_prior > 0:
                # ridge toward the prior: the data dominate only when Pwf varied enough in the tests to identify J
                X = np.c_[np.ones(len(h)), t, -pwf]
                sw = np.sqrt(w)
                Xw, yw = X * sw[:, None], liq * sw
                beta0 = np.linalg.lstsq(Xw, yw, rcond=None)[0]
                s2 = max(np.sum((yw - Xw @ beta0) ** 2) / max(len(h) - 3, 1), 1e-6)
                lam = s2 / (self.J_prior_rel_sd * J_prior) ** 2
                Xa = np.vstack([Xw, [0.0, 0.0, np.sqrt(lam)]])
                ya = np.r_[yw, np.sqrt(lam) * J_prior]
                J_post = float(np.linalg.lstsq(Xa, ya, rcond=None)[0][2])
                if J_post > 0:
                    J, src = J_post, "well regression + prior"
            if not np.isfinite(J) or J <= 0:
                J, src = 0.0, "none (trend only)"
            if len(h) >= 2:
                a, b = self._wls(np.c_[np.ones(len(h)), t], liq + J * pwf, w)
            else:
                a, b = liq[0] + J * pwf[0], 0.0
            resid = liq - (a + b * t - J * pwf)
            wc = h["water_cut_pct"].to_numpy()
            wc_c, wc_d = self._wls(np.c_[np.ones(len(h)), t], wc, w) if len(h) >= 2 else (wc[0], 0.0)
            rs = float(static.loc[well, "solution_gor_at_pb_scf_stb"]) if well in static.index else np.nan
            gm = h["gor_scf_stb"].mean()
            n = len(h)
            gor = (n * gm + self.gor_shrink_k * rs) / (n + self.gor_shrink_k) if np.isfinite(rs) else gm
            self.params[well] = WellParams(well, n, float(a), float(b), float(J), src, float(wc_c), float(wc_d),
                                           float(gor), rs, str(h["test_mid"].max()),
                                           float(resid.std(ddof=min(3, n - 1)) if n > 3 else np.nan))
        return self

    # ------------------------------------------------------------------ prediction
    def predict_rates(self, well: str | pd.Series, t_days, pwf) -> pd.DataFrame:
        """Instantaneous rates while flowing (stb/d, Mscf/d)."""
        wells = pd.Series(well) if np.isscalar(well) else pd.Series(well).reset_index(drop=True)
        t_days = np.broadcast_to(np.asarray(t_days, dtype=float), (len(wells),)) if np.ndim(t_days) == 0 else np.asarray(t_days, float)
        pwf = np.broadcast_to(np.asarray(pwf, dtype=float), (len(wells),)) if np.ndim(pwf) == 0 else np.asarray(pwf, float)
        out = np.full((len(wells), 6), np.nan)
        for i, w in enumerate(wells):
            p = self.params.get(w)
            if p is None:
                continue
            liq = max(p.a + p.b * t_days[i] - p.J * pwf[i], 0.0)
            wc = float(np.clip(p.wc_c + p.wc_d * t_days[i], 0, 99.9))
            oil = liq * (1 - wc / 100)
            out[i] = [oil, liq * wc / 100, oil * p.gor / 1000, liq, wc, p.reservoir_pressure(t_days[i])]
        return pd.DataFrame(out, columns=PHASES + ["liquid_rate_stbd", "water_cut_pct", "p_res_implied_psia"])

    def predict_daily(self, daily: pd.DataFrame, history: pd.DataFrame | None = None) -> pd.DataFrame:
        """daily: output of features.daily_features. Returns daily volumes (rate x on-stream fraction) + bands.

        history: earlier predict_daily output (well_name, date, pwf_psia). When the gauge is missing on every day
        of a well in `daily`, the last known Pwf from the history is used so the well still gets a rate (flagged).
        """
        d = daily.sort_values(["well_name", "date"]).reset_index(drop=True)
        # whole-day sensor outages: bridge Pwf linearly in time from the neighbouring days (flagged for review)
        pwf_missing = d["dh_pressure_psia"].isna()
        pwf_used = d.groupby("well_name")["dh_pressure_psia"].transform(
            lambda s: s.interpolate(limit_direction="both"))
        from_history = pd.Series(False, index=d.index)
        if history is not None and len(history) and pwf_used.isna().any():
            last = (history.dropna(subset=["pwf_psia"]).sort_values("date").groupby("well_name")["pwf_psia"].last())
            fill = d["well_name"].map(last)
            from_history = pwf_used.isna() & fill.notna()
            pwf_used = pwf_used.where(~from_history, fill)
        r = self.predict_rates(d["well_name"], days_since_ref(d["date"] + pd.Timedelta(hours=12)), pwf_used)
        frac = d["on_stream_frac"].clip(0, 1).to_numpy()
        out = pd.DataFrame({"date": d["date"].dt.date, "well_name": d["well_name"]})
        for ph in PHASES:
            out[ph] = r[ph].to_numpy() * frac
            q = self.rel_err_q.get(ph)
            if q:
                out[ph + "_p05"] = out[ph] * (1 + q["q05"])
                out[ph + "_p95"] = out[ph] * (1 + q["q95"])
        out["liquid_rate_stbd"] = r["liquid_rate_stbd"].to_numpy() * frac
        out["water_cut_pct"] = r["water_cut_pct"].to_numpy()
        out["p_res_implied_psia"] = r["p_res_implied_psia"].to_numpy()
        out["pwf_psia"] = pwf_used.to_numpy()
        out["on_stream_frac"] = frac
        out["flag"] = np.where(from_history & (frac > 0), "no downhole pressure in this data: last known Pwf used",
                      np.where(pwf_missing & (frac > 0), "sensor outage: Pwf interpolated from adjacent days",
                               np.where(frac <= 0, "shut in all day",
                                        np.where(frac < 1, "partial day (shut-in)", ""))))
        out.loc[out["well_name"].map(lambda w: w not in self.params), "flag"] = "well not calibrated (no tests)"
        return out

    # ------------------------------------------------------------------ persistence
    def to_json(self) -> str:
        return json.dumps({"gor_shrink_k": self.gor_shrink_k, "recency_halflife_days": self.recency_halflife_days,
                           "min_tests_for_J": self.min_tests_for_J, "J_prior_rel_sd": self.J_prior_rel_sd,
                           "pooled_J_rel": self.pooled_J_rel,
                           "rel_err_q": self.rel_err_q, "meta": self.meta,
                           "params": {k: asdict(v) for k, v in self.params.items()}}, indent=2, default=str)

    @classmethod
    def from_json(cls, s: str) -> "VFMModel":
        o = json.loads(s)
        m = cls(o["gor_shrink_k"], o["recency_halflife_days"], o["min_tests_for_J"], o.get("J_prior_rel_sd", 0.5))
        m.pooled_J_rel, m.rel_err_q, m.meta = o["pooled_J_rel"], o["rel_err_q"], o.get("meta", {})
        m.params = {k: WellParams(**v) for k, v in o["params"].items()}
        return m


# ---------------------------------------------------------------------- validation
def baseline_ltcf(train: pd.DataFrame, test_rows: pd.DataFrame) -> np.ndarray:
    """What engineers do today: carry the last well test forward."""
    out = np.full((len(test_rows), 3), np.nan)
    for i, (_, r) in enumerate(test_rows.iterrows()):
        h = train[train.well_name == r.well_name]
        if len(h):
            out[i] = h.sort_values("test_mid").iloc[-1][PHASES].to_numpy(dtype=float)
    return out


def backtest(tests_feat: pd.DataFrame, static: pd.DataFrame, scheme: str = "forward", min_history: int = 3,
             **model_kw) -> pd.DataFrame:
    """Per-test out-of-sample predictions for the VFM and the LTCF baseline.

    forward: each test is predicted from tests completed before it (deployment-realistic).
    loto:    leave-one-test-out (interpolation between tests).
    """
    df = tests_feat.sort_values("test_mid").reset_index(drop=True)
    rows = []
    for i, r in df.iterrows():
        if scheme == "forward":
            tr = df[df.test_end <= r.test_start]
            prev = tr
        else:
            tr = df.drop(index=i)
            prev = tr[tr.test_end <= r.test_start]
        if (tr.well_name == r.well_name).sum() < min_history:
            continue
        m = VFMModel(**model_kw).fit(tr, static)
        p = m.predict_rates(r.well_name, days_since_ref([r.test_mid]), r.dh_pressure_psia).iloc[0]
        b = baseline_ltcf(prev, df.loc[[i]])[0]
        rec = {"well_name": r.well_name, "test_mid": r.test_mid,
               "n_hist": int((tr.well_name == r.well_name).sum()),
               "horizon_days": float((r.test_mid - prev[prev.well_name == r.well_name].test_mid.max()) / pd.Timedelta(days=1))
               if (prev.well_name == r.well_name).any() else np.nan}
        for j, ph in enumerate(PHASES):
            rec[ph] = r[ph]
            rec[ph + "_vfm"] = p[ph]
            rec[ph + "_base"] = b[j]
        rows.append(rec)
    return pd.DataFrame(rows)


def score(bt: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for src, sfx in [("VFM", "_vfm"), ("Last test carried forward", "_base")]:
        rec = {"model": src, "n_tests": int(bt[PHASES[0] + sfx].notna().sum())}
        for ph in PHASES:
            ok = bt[ph + sfx].notna()
            e = bt.loc[ok, ph + sfx] - bt.loc[ok, ph]
            short = ph.split("_")[0]
            rec[f"{short} MAE"] = e.abs().mean()
            rec[f"{short} MAPE %"] = (e.abs() / bt.loc[ok, ph]).mean() * 100
            rec[f"{short} bias %"] = (e / bt.loc[ok, ph]).mean() * 100
        rows.append(rec)
    return pd.DataFrame(rows)


def evaluate(model: "VFMModel", tests_feat: pd.DataFrame, history_tests: pd.DataFrame) -> pd.DataFrame:
    """Score the fixed, already-trained model on new well tests (e.g. the evaluation period).

    Same layout as backtest(), so score() works on it. Baseline: the last training test carried forward,
    i.e. the same information the model had.
    """
    rows = []
    for _, r in tests_feat.sort_values("test_mid").iterrows():
        if r.well_name not in model.params or not np.isfinite(r.get("dh_pressure_psia", np.nan)):
            continue
        p = model.predict_rates(r.well_name, days_since_ref([r.test_mid]), r.dh_pressure_psia).iloc[0]
        prev = history_tests[(history_tests.well_name == r.well_name) & (history_tests.test_mid < r.test_mid)]
        b = prev.sort_values("test_mid").iloc[-1][PHASES].to_numpy(dtype=float) if len(prev) else np.full(3, np.nan)
        rec = {"well_name": r.well_name, "test_mid": r.test_mid}
        for j, ph in enumerate(PHASES):
            rec[ph] = r[ph]
            rec[ph + "_vfm"] = p[ph]
            rec[ph + "_base"] = b[j]
        rows.append(rec)
    return pd.DataFrame(rows)


def relative_error_quantiles(bt: pd.DataFrame, lo: float = 0.05, hi: float = 0.95) -> dict:
    """Empirical distribution of (actual - predicted)/predicted, used for prediction bands."""
    out = {}
    for ph in PHASES:
        r = ((bt[ph] - bt[ph + "_vfm"]) / bt[ph + "_vfm"]).dropna()
        if len(r) >= 10:
            out[ph] = {"q05": float(r.quantile(lo)), "q95": float(r.quantile(hi)), "n": int(len(r))}
    return out
