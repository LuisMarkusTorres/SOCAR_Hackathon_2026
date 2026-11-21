"""SYNTHETIC analytical build-ups for verifying the PTA engine (clearly labelled test fixtures, not field data).

Wellbore storage + skin, infinite-acting radial flow (Agarwal-Ramey), Laplace solution inverted with Stehfest.
"""
from __future__ import annotations

from math import factorial, log

import numpy as np
import pandas as pd
from scipy.special import kv


def _stehfest_weights(N: int = 12) -> np.ndarray:
    V = np.zeros(N)
    for i in range(1, N + 1):
        s = 0.0
        for k in range((i + 1) // 2, min(i, N // 2) + 1):
            s += (k ** (N // 2) * factorial(2 * k)) / (
                factorial(N // 2 - k) * factorial(k) * factorial(k - 1) * factorial(i - k) * factorial(2 * k - i))
        V[i - 1] = (-1) ** (N // 2 + i) * s
    return V


_V = _stehfest_weights()


def pwd(td: np.ndarray, cd: float, skin: float) -> np.ndarray:
    """Dimensionless wellbore pressure for a constant-rate drawdown."""
    td = np.atleast_1d(td).astype(float)
    out = np.empty_like(td)
    for j, t in enumerate(td):
        acc = 0.0
        for i in range(1, len(_V) + 1):
            u = i * log(2) / t
            su = np.sqrt(u)
            k0, k1 = kv(0, su), kv(1, su)
            num = k0 + skin * su * k1
            acc += _V[i - 1] * num / (u * (su * k1 + cd * u * num))
        out[j] = acc * log(2) / t
    return out


def buildup_minutes(k: float, skin: float, C: float, q: float, tp_hr: float, shut_hr: float, props: dict,
                    p_i: float = 4000.0, noise_psi: float = 0.0, seed: int = 0) -> tuple[pd.DataFrame, float]:
    """Per-minute downhole pressure for a build-up after producing q for tp hours. Returns (frame, p_wf)."""
    h, phi, mu, B, ct, rw = (props[x] for x in ["h", "phi", "mu", "B", "ct", "rw"])
    td_per_hr = 0.0002637 * k / (phi * mu * ct * rw ** 2)
    cd = 0.8936 * C / (phi * ct * h * rw ** 2)
    pscale = 141.2 * q * B * mu / (k * h)
    dt = np.arange(1, int(shut_hr * 60) + 1) / 60.0
    p_ws = p_i - pscale * (pwd((tp_hr + dt) * td_per_hr, cd, skin) - pwd(dt * td_per_hr, cd, skin))
    p_wf = p_i - pscale * pwd(np.array([tp_hr * td_per_hr]), cd, skin)[0]
    if noise_psi:
        p_ws = p_ws + np.random.default_rng(seed).normal(0, noise_psi, len(p_ws))
    return pd.DataFrame({"dt_hr": dt, "p_psia": p_ws}), float(p_wf)
