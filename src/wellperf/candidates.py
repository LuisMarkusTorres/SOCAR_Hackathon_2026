"""Benchmark models for the virtual flow meter, scored with the same forward-chaining backtest as the physics model.

Every candidate predicts a well test from the tests that were completed before it (the deployment situation), with
the same minimum history as vfm.backtest, so the numbers are directly comparable:

    Last test carried forward     what engineers do today (baseline)
    Per-well time trend           liquid, water cut and GOR drift linearly in time; ignores the sensors
    Choke-flow ridge (pooled)     Gilbert-type terms (choke size, wellhead pressure, downhole minus wellhead pressure,
                                  gas-lift rate, temperature) with a ridge penalty and one offset per well
    Gradient-boosted trees        a general-purpose learner on all sensor features plus the well identity and time
    Physics IPR model (VFM)       the model in vfm.py: q_L = J (p_res(t) - p_wf), per well

Run `python -m wellperf.candidates` or see the notebook for the table on the training data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import vfm as V

SENSOR_FEATURES = ["whp_psia", "whp_downstream_psia", "dh_pressure_psia", "dh_temperature_degf",
                   "annulus_pressure_psia", "gas_lift_rate_mscfd", "choke_opening_pct", "dp_choke_psi",
                   "tubing_grad_psi_ft", "dp_annulus_whp", "choke_bernoulli"]
CHOKE_FEATURES = ["choke_size_64ths", "whp_psia", "dp_dh_whp", "gas_lift_rate_mscfd", "dh_temperature_degf"]


def _split_liquid(liq: float, wc: float, gor: float) -> list[float]:
    liq, wc = max(liq, 0.0), float(np.clip(wc, 0, 99.9))
    oil = liq * (1 - wc / 100)
    return [oil, liq * wc / 100, oil * gor / 1000]


def _time_trend(train: pd.DataFrame, r: pd.Series) -> list[float]:
    h = train[train.well_name == r.well_name]
    t = V.days_since_ref(h["test_mid"])
    X = np.c_[np.ones(len(h)), t]
    t_new = float(V.days_since_ref([r.test_mid])[0])
    liq = np.array([1.0, t_new]) @ np.linalg.lstsq(X, h["liquid_rate_stbd"].to_numpy(), rcond=None)[0]
    wc = np.array([1.0, t_new]) @ np.linalg.lstsq(X, h["water_cut_pct"].to_numpy(), rcond=None)[0]
    return _split_liquid(float(liq), float(wc), float(h["gor_scf_stb"].mean()))


def _choke_ridge(train: pd.DataFrame, r: pd.Series, alpha: float = 1.0) -> list[float]:
    """Pooled ridge regression of liquid rate on Gilbert-type terms, with a per-well offset. Features are
    standardised on the training rows; the ridge penalty is not applied to the well offsets."""
    def feats(df):
        f = df.copy()
        f["dp_dh_whp"] = f["dh_pressure_psia"] - f["whp_psia"]
        return f[CHOKE_FEATURES].astype(float)
    Xtr, Xte = feats(train), feats(pd.DataFrame([r]))
    mu, sd = Xtr.mean(), Xtr.std().replace(0, 1.0)
    Xtr, Xte = ((Xtr - mu) / sd).fillna(0).to_numpy(), ((Xte - mu) / sd).fillna(0).to_numpy()
    wells = sorted(train.well_name.unique())
    D = lambda names: np.array([[1.0 if w == v else 0.0 for v in wells] for w in names])
    A = np.c_[Xtr, D(train.well_name)]
    y = train["liquid_rate_stbd"].to_numpy(dtype=float)
    pen = np.diag(np.r_[np.full(Xtr.shape[1], alpha), np.zeros(len(wells))])
    beta = np.linalg.solve(A.T @ A + pen, A.T @ y)
    liq = float(np.r_[Xte[0], D([r.well_name])[0]] @ beta)
    h = train[train.well_name == r.well_name].sort_values("test_mid")
    wc, gor = float(h["water_cut_pct"].iloc[-1]), float(h["gor_scf_stb"].mean())
    return _split_liquid(liq, wc, gor)


def _gbt(train: pd.DataFrame, r: pd.Series) -> list[float]:
    from sklearn.ensemble import HistGradientBoostingRegressor
    wells = sorted(train.well_name.unique())
    def X(df):
        f = df[SENSOR_FEATURES].astype(float).copy()
        f["t_days"] = V.days_since_ref(df["test_mid"])
        f["well"] = pd.Categorical(df["well_name"], categories=wells).codes
        return f
    Xtr, Xte = X(train), X(pd.DataFrame([r]))
    out = []
    for ph in V.PHASES:
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_depth=3, min_samples_leaf=3,
                                          categorical_features=[Xtr.columns.get_loc("well")], random_state=0)
        m.fit(Xtr, train[ph].to_numpy(dtype=float))
        out.append(float(m.predict(Xte)[0]))
    return out


CANDIDATES = {"Per-well time trend": _time_trend, "Choke-flow ridge (pooled)": _choke_ridge,
              "Gradient-boosted trees": _gbt}


def backtest_candidates(tests_feat: pd.DataFrame, static: pd.DataFrame, min_history: int = 3,
                        candidates: dict | None = None) -> pd.DataFrame:
    """One row per predicted well test; columns <phase>, <phase>_base, <phase>_vfm and <phase>_<candidate>."""
    bt = V.backtest(tests_feat, static, "forward", min_history=min_history)
    df = tests_feat.sort_values("test_mid").reset_index(drop=True)
    keys = set(zip(bt.well_name, bt.test_mid))
    cands = candidates or CANDIDATES
    extra = {name: [] for name in cands}
    for _, r in df.iterrows():
        if (r.well_name, r.test_mid) not in keys:
            continue
        tr = df[df.test_end <= r.test_start].dropna(subset=["dh_pressure_psia", "liquid_rate_stbd"])
        for name, fn in cands.items():
            try:
                extra[name].append(fn(tr, r))
            except Exception:                      # a candidate that cannot be fitted scores as missing
                extra[name].append([np.nan] * 3)
    for name, rows in extra.items():
        arr = np.array(rows, dtype=float).reshape(len(bt), 3)
        for j, ph in enumerate(V.PHASES):
            bt[f"{ph}_{name}"] = arr[:, j]
    return bt


def score_candidates(bt: pd.DataFrame) -> pd.DataFrame:
    """MAPE per phase for every model in a backtest_candidates() frame, best first."""
    models = {"Last test carried forward": "_base", **{n: f"_{n}" for n in CANDIDATES if f"oil_rate_stbd_{n}" in bt},
              "Physics IPR model (VFM)": "_vfm"}
    rows = []
    for name, sfx in models.items():
        rec = {"model": name, "n_tests": int(bt["oil_rate_stbd" + sfx].notna().sum())}
        for ph in V.PHASES:
            ok = bt[ph + sfx].notna()
            rec[f"{ph.split('_')[0]} MAPE %"] = float(((bt.loc[ok, ph + sfx] - bt.loc[ok, ph]).abs()
                                                       / bt.loc[ok, ph]).mean() * 100)
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("oil MAPE %").reset_index(drop=True)


if __name__ == "__main__":
    from . import pipeline as PL
    ws = PL.build()
    bt = backtest_candidates(ws.tests_feat, ws.static)
    pd.set_option("display.width", 200)
    print(score_candidates(bt).round(2).to_string(index=False))
