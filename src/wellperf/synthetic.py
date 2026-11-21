"""SYNTHETIC analytical build-ups for verifying the PTA engine (clearly labelled test fixtures, not field data)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analytical import pwd  # noqa: F401  (re-exported for older imports)
from .analytical import buildup_dp


def buildup_minutes(k: float, skin: float, C: float, q: float, tp_hr: float, shut_hr: float, props: dict,
                    p_i: float = 4000.0, noise_psi: float = 0.0, seed: int = 0) -> tuple[pd.DataFrame, float]:
    """Per-minute downhole pressure for a build-up after producing q for tp hours. Returns (frame, p_wf)."""
    h, phi, mu, B, ct, rw = (props[x] for x in ["h", "phi", "mu", "B", "ct", "rw"])
    td_per_hr = 0.0002637 * k / (phi * mu * ct * rw ** 2)
    cd = 0.8936 * C / (phi * ct * h * rw ** 2)
    pscale = 141.2 * q * B * mu / (k * h)
    dt = np.arange(1, int(shut_hr * 60) + 1) / 60.0
    p_wf = p_i - pscale * pwd(np.array([tp_hr * td_per_hr]), cd, skin)[0]
    p_ws = p_wf + buildup_dp(dt, k, skin, C, q, tp_hr, props)
    if noise_psi:
        p_ws = p_ws + np.random.default_rng(seed).normal(0, noise_psi, len(p_ws))
    return pd.DataFrame({"dt_hr": dt, "p_psia": p_ws}), float(p_wf)
