"""Rule-based, plain-language reading of a build-up interpretation. Every statement points at a computed number."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .pta import BuildupResult


def interpret(r: BuildupResult, static: pd.DataFrame) -> list[tuple[str, str]]:
    """Returns (kind, html) pairs; kind is 'warn', 'good' or 'info'."""
    out = []
    if not np.isfinite(r.skin):
        why = ("there is no flowing pressure just before this shut-in" if not np.isfinite(r.pwf_psia) else
               "no flow-meter oil rate is available for the days before it" if not (np.isfinite(r.q_stbd) and r.q_stbd > 0)
               else "the straight-line fit failed")
        out.append(("warn", f"<b>Skin not available:</b> {why}, so the near-wellbore condition cannot be judged "
                            "from this build-up."))
    elif r.skin > 3:
        out.append(("warn", f"<b>Damaged well.</b> Skin {r.skin:.2f} costs {r.dP_skin:.0f} psi of drawdown, so only "
                            f"{r.flow_efficiency:.0%} of the pressure drop does useful work (flow efficiency "
                            f"{r.flow_efficiency:.2f}). Candidate for a stimulation review."))
    elif r.skin > 0:
        out.append(("good", f"Mild near-wellbore damage: skin {r.skin:.2f}, Δp<sub>skin</sub> {r.dP_skin:.0f} psi, "
                            f"flow efficiency {r.flow_efficiency:.2f}."))
    else:
        out.append(("good", f"Undamaged or stimulated near-wellbore zone: skin {r.skin:.2f} "
                            f"(Δp<sub>skin</sub> {r.dP_skin:.0f} psi, flow efficiency {r.flow_efficiency:.2f})."))
    h = float(static.loc[r.well_name, "net_pay_thickness_ft"])
    if np.isfinite(r.k_md):
        out.append(("info", f"Permeability {r.k_md:.0f} md over {h:.0f} ft of net pay (kh = {r.k_md * h:,.0f} md·ft), "
                            f"using the VFM oil rate of {r.q_stbd:,.0f} STB/d on {r.data.get('q_date', '')}."))
    else:
        out.append(("warn", f"<b>Permeability not available.</b> The Horner slope is {r.m_psi_cycle:.1f} psi/cycle, but "
                            f"k = 162.6 qBμ/(mh) needs the oil rate before the shut-in, which the flow meter could not "
                            f"provide ({r.data.get('q_date', '')})."))
    if np.isfinite(r.r_inv_window_end_ft) and r.r_inv_window_end_ft < r.drainage_radius_ft:
        out.append(("info", f"By the end of the radial-flow window ({r.window_end_hr:.2g} h) the pressure signal has "
                            f"reached about {r.r_inv_window_end_ft:,.0f} ft, still inside the {r.drainage_radius_ft:,.0f} ft "
                            f"drainage radius, so the window is not distorted by boundaries."))
    for f in r.flags:
        out.append(("warn", f))
    return out


def plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def interpret_text(r: BuildupResult, static: pd.DataFrame) -> str:
    return " ".join(plain(t) for _, t in interpret(r, static))
