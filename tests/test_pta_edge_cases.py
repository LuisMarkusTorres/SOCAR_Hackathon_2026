"""PTA must degrade gracefully: no rate before the shut-in, a shut-in on the first day, too few gauge readings."""
import numpy as np
import pandas as pd
import pytest

from wellperf import pta as P
from test_pta_synthetic import run_case


def _daily(dates, rate, frac=1.0):
    return pd.DataFrame({"date": [str(d.date()) for d in dates], "well_name": "SYN", "oil_rate_stbd": rate,
                         "on_stream_frac": frac})


def test_rate_before_shutin_fallbacks():
    t = pd.Timestamp("2025-01-10 08:00")
    days = pd.date_range("2025-01-08", periods=5)
    # last full day before the shut-in
    q, src = P.rate_before_shutin(_daily(days, 500.0), "SYN", t)
    assert q == 500.0 and src == "2025-01-09"
    # only a partial day before it: the volume is scaled back to a flowing rate
    d = _daily(days, 500.0); d.loc[1, ["oil_rate_stbd", "on_stream_frac"]] = [250.0, 0.5]
    q, src = P.rate_before_shutin(d.iloc[:2], "SYN", t)
    assert q == 500.0
    # shut-in on the first day of the data: first full day after it, labelled as such
    q, src = P.rate_before_shutin(_daily(days[2:], 480.0), "SYN", t)
    assert q == 480.0 and "after" in src
    # nothing usable at all
    q, src = P.rate_before_shutin(_daily(days, np.nan), "SYN", t)
    assert np.isnan(q)


def test_missing_rate_gives_slope_but_no_k():
    r = run_case(110.0, 6.0, 0.01, q_interp=float("nan"))
    assert np.isfinite(r.m_psi_cycle) and r.m_psi_cycle > 0
    assert np.isnan(r.k_md) and np.isnan(r.skin)
    assert any("no VFM oil rate" in f for f in r.flags)


def test_too_few_readings_raises():
    with pytest.raises(ValueError):
        run_case(110.0, 6.0, 0.01, shut_hr=0.1)


def test_storage_dominated_short_shutin_is_flagged_not_wrong():
    """6 h shut-in with large storage: no radial flow in the record. The old picker returned k 50-90 % low with no
    flag; now the model match takes over and says so."""
    r = run_case(110.0, 6.0, 0.15, shut_hr=6.0, tp_hr=200000.0, noise=0.5)
    assert r.result_source == "model match"
    assert any("storage-dominated" in f for f in r.flags)
    assert abs(r.k_md / 110.0 - 1) < 0.35
    assert np.isfinite(r.k_match_p10_md) and r.k_match_p10_md <= r.k_md <= r.k_match_p90_md


def test_long_shutin_keeps_horner_and_match_agrees():
    r = run_case(110.0, 6.0, 0.01, shut_hr=72.0)
    assert r.result_source == "Horner"
    assert abs(r.k_match_md / 110.0 - 1) < 0.1 and abs(r.skin_match - 6.0) < 0.5
