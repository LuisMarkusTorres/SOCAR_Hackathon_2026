"""Analytical well-test model: constant wellbore storage + skin, infinite-acting radial flow (Agarwal-Ramey).

Laplace-space solution inverted with the Stehfest algorithm. Used to generate verification build-ups (synthetic.py)
and to match real build-ups (pta.model_match) as a cross-check or as the fallback when no radial-flow window exists.
"""
from __future__ import annotations

from math import factorial, log

import numpy as np
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
_I = np.arange(1, len(_V) + 1)


def pwd(td, cd: float, skin: float) -> np.ndarray:
    """Dimensionless wellbore pressure for a constant-rate drawdown (vectorised over td)."""
    td = np.atleast_1d(np.asarray(td, dtype=float))
    u = (_I[None, :] * log(2)) / td[:, None]          # (n, N)
    su = np.sqrt(u)
    k0, k1 = kv(0, su), kv(1, su)
    num = k0 + skin * su * k1
    f = num / (u * (su * k1 + cd * u * num))
    return (f @ _V) * log(2) / td


def buildup_dp(dt_hr, k: float, skin: float, C: float, q: float, tp_hr: float, props: dict) -> np.ndarray:
    """Pressure rise p_ws(dt) - p_wf for a build-up after producing q for tp hours (field units, psi).

    props: h [ft], phi, mu [cp], B [rb/stb], ct [1/psi], rw [ft]; C in bbl/psi.
    """
    h, phi, mu, B, ct, rw = (props[x] for x in ["h", "phi", "mu", "B", "ct", "rw"])
    td_per_hr = 0.0002637 * k / (phi * mu * ct * rw ** 2)
    cd = 0.8936 * C / (phi * ct * h * rw ** 2)
    pscale = 141.2 * q * B * mu / (k * h)
    dt = np.asarray(dt_hr, dtype=float)
    return pscale * (pwd(tp_hr * td_per_hr, cd, skin)[0] + pwd(dt * td_per_hr, cd, skin)
                     - pwd((tp_hr + dt) * td_per_hr, cd, skin))
