"""Static (matplotlib) versions of the diagnostic plots, for the PTA plot folder, the notebook and the zip export.

Same content and colours as the interactive Plotly figures in plots.py.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import matplotlib

if "ipykernel" not in sys.modules:      # headless (app server, scripts); notebooks keep their inline backend
    matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE, AQUA, MUTED, GRID, INK = "#2a78d6", "#eb6834", "#1baf7a", "#898781", "#e1e0d9", "#3a3936"
PHASES = [("oil_rate_stbd", "Oil (STB/d)", "#d97706"), ("water_rate_stbd", "Water (STB/d)", "#4f46e5"),
          ("gas_rate_mscfd", "Gas (Mscf/d)", "#0d9488")]

plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK, "xtick.color": INK,
                     "ytick.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.7,
                     "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
                     "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight"})


def _title(r) -> str:
    return f"{r.well_name} · shut in {r.t_shut:%d %b %Y %H:%M} · {r.duration_hr:.0f} h"


def loglog(r, ax=None):
    ax = ax or plt.subplots(figsize=(6.4, 4.6))[1]
    d = r.data
    ax.axvspan(r.window_start_hr, r.window_end_hr, color=BLUE, alpha=0.10, lw=0, label="radial-flow window")
    ax.loglog(d["dt"], d["dp"], "o", ms=4, color=BLUE, label="Δp = p_ws − p_wf")
    ok = np.isfinite(d["der"]) & (d["der"] > 0)
    ax.loglog(d["dt"][ok], d["der"][ok], "^", ms=4, color=ORANGE, label="Bourdet derivative Δp′")
    lvl = r.m_psi_cycle / np.log(10)
    ax.axhline(lvl, color=ORANGE, lw=1, ls="--", label=f"radial-flow level m/2.303 = {lvl:.1f} psi")
    ax.set(xlabel="Shut-in time Δt (h)", ylabel="Δp, Δp′ (psi)", title="Log-log diagnostic")
    ax.legend(loc="lower right", fontsize=8)
    return ax


def horner(r, ax=None):
    ax = ax or plt.subplots(figsize=(6.4, 4.6))[1]
    d = r.data
    x = np.asarray(d["horner_x"])
    sel = (d["dt"] >= r.window_start_hr) & (d["dt"] <= r.window_end_hr)
    ax.semilogx(x[~sel], np.asarray(d["p"])[~sel], "o", ms=3.5, color=MUTED, label="build-up pressure")
    ax.semilogx(x[sel], np.asarray(d["p"])[sel], "o", ms=4, color=BLUE, label="points used in fit")
    xl = np.logspace(0, np.log10(x.max()), 50)
    ax.semilogx(xl, r.p_star_psia - r.m_psi_cycle * np.log10(xl), color=ORANGE, lw=1.6,
                label=f"m = {r.m_psi_cycle:.2f} psi/cycle, p* = {r.p_star_psia:,.0f} psia")
    ax.plot([1], [r.p_star_psia], "D", color=ORANGE, ms=6)
    ax.invert_xaxis()
    ax.set(xlabel="Horner time (tp + Δt)/Δt", ylabel="p_ws (psia)", title="Horner plot")
    ax.legend(loc="lower right", fontsize=8)
    return ax


def mdh(r, ax=None):
    ax = ax or plt.subplots(figsize=(6.4, 4.6))[1]
    d = r.data
    dt, p = np.asarray(d["dt"]), np.asarray(d["p"])
    sel = (dt >= r.window_start_hr) & (dt <= r.window_end_hr)
    ax.semilogx(dt, p, "o", ms=3.5, color=MUTED, label="build-up pressure")
    ax.semilogx(dt[sel], p[sel], "o", ms=4, color=BLUE, label="radial-flow window")
    dtl = np.logspace(np.log10(max(dt.min(), 1e-3)), np.log10(dt.max()), 60)
    ax.semilogx(dtl, r.p_star_psia - r.m_psi_cycle * np.log10((r.tp_hr + dtl) / dtl), color=ORANGE, lw=1.6,
                label="straight-line fit")
    ax.axhline(r.p1hr_psia, color=MUTED, lw=0.8, ls=":")
    ax.annotate(f"p1hr = {r.p1hr_psia:,.1f} psia", (1, r.p1hr_psia), textcoords="offset points", xytext=(6, -12),
                fontsize=8, color=INK)
    ax.set(xlabel="Shut-in time Δt (h)", ylabel="p_ws (psia)", title="Semilog (MDH) plot")
    ax.legend(loc="lower right", fontsize=8)
    return ax


def history(minute: pd.DataFrame, r, axes=None, pad_hr: float = 12):
    if axes is None:
        _, axes = plt.subplots(2, 1, figsize=(6.4, 4.6), sharex=True)
    w = minute[minute.well_name == r.well_name].set_index("timestamp")
    w = w.loc[r.t_shut - pd.Timedelta(hours=pad_hr): r.t_shut + pd.Timedelta(hours=r.duration_hr + pad_hr)]
    t1 = r.t_shut + pd.Timedelta(hours=r.duration_hr)
    axes[0].plot(w.index, w.dh_pressure_psia, color=BLUE, lw=1.2)
    axes[0].set(ylabel="Downhole p (psia)", title="Shut-in event")
    axes[1].plot(w.index, w.gas_lift_rate_mscfd, color=MUTED, lw=1.2)
    axes[1].set(ylabel="Gas lift (Mscf/d)")
    for ax in axes:
        ax.axvspan(r.t_shut, t1, color=MUTED, alpha=0.15, lw=0)
    loc = mdates.AutoDateLocator(minticks=3, maxticks=8)
    axes[1].xaxis.set_major_locator(loc)
    axes[1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    return axes


def event_figure(minute: pd.DataFrame, r) -> plt.Figure:
    """All four diagnostic plots for one build-up on one page, with the results in the title."""
    fig = plt.figure(figsize=(13, 9.2))
    gs = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.22)
    loglog(r, fig.add_subplot(gs[0, 0]))
    horner(r, fig.add_subplot(gs[0, 1]))
    mdh(r, fig.add_subplot(gs[1, 0]))
    sub = gs[1, 1].subgridspec(2, 1, hspace=0.12)
    a1 = fig.add_subplot(sub[0])
    history(minute, r, [a1, fig.add_subplot(sub[1], sharex=a1)])
    a1.tick_params(labelbottom=False)
    fig.suptitle(f"{_title(r)}\nm = {r.m_psi_cycle:.2f} psi/cycle · k = {r.k_md:.1f} md · skin = {r.skin:.2f} · "
                 f"Δp skin = {r.dP_skin:.1f} psi · p* = {r.p_star_psia:,.0f} psia", fontsize=11.5, color=INK)
    return fig


def rate_figure(vfm_daily: pd.DataFrame, tests: pd.DataFrame | None, well: str) -> plt.Figure:
    d = vfm_daily[vfm_daily.well_name == well].assign(date=lambda x: pd.to_datetime(x.date))
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    for ax, (ph, label, col) in zip(axes, PHASES):
        if ph + "_p05" in d:
            ax.fill_between(d.date, d[ph + "_p05"], d[ph + "_p95"], color=MUTED, alpha=0.2, lw=0, step="post")
        ax.step(d.date, d[ph], where="post", color=col, lw=1.6)
        if tests is not None:
            t = tests[tests.well_name == well]
            ax.plot(t.test_mid, t[ph], "o", mfc="white", mec="#0b0b0b", ms=5)
        ax.set_ylabel(label)
    axes[0].set_title(f"{well} · flow-meter daily volumes (line, 90% range shaded) and well tests (circles)")
    return fig


def save_pta_plots(minute: pd.DataFrame, pta_objs: dict, out_dir: Path) -> list[Path]:
    """One combined page plus the four individual plots per build-up."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for r in pta_objs.values():
        stem = f"{r.well_name}_{r.t_shut:%Y%m%d_%H%M}"
        for name, fn in [("summary", lambda: event_figure(minute, r)),
                         ("loglog", lambda: loglog(r).figure), ("horner", lambda: horner(r).figure),
                         ("mdh", lambda: mdh(r).figure), ("history", lambda: history(minute, r)[0].figure)]:
            fig = fn()
            if name != "summary":
                fig.suptitle(_title(r), fontsize=10, color=INK)
            p = out_dir / f"{stem}_{name}.png"
            fig.savefig(p)
            plt.close(fig)
            paths.append(p)
    return paths


def pta_plots_zip(minute: pd.DataFrame, pta_objs: dict) -> bytes:
    import tempfile
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        files = save_pta_plots(minute, pta_objs, Path(tmp))
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, arcname=f"pta_plots/{f.name}")
    return buf.getvalue()
