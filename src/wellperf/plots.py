"""Plotly figures. Palette: validated reference slots 1-3 (all-pairs CVD safe), recessive chrome, one y-axis per panel."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Phase colours on the dark theme: oil amber, gas teal, water indigo (distinct in hue and lightness)
PHASE_COLOR = {"oil_rate_stbd": "#f59e0b", "water_rate_stbd": "#818cf8", "gas_rate_mscfd": "#2dd4bf"}
PHASE_LABEL = {"oil_rate_stbd": "Oil (STB/d)", "water_rate_stbd": "Water (STB/d)", "gas_rate_mscfd": "Gas (Mscf/d)"}
BLUE, ORANGE, AQUA = "#60a5fa", "#f59e0b", "#2dd4bf"
INK2, MUTED, GRID, AXIS = "#b7c0d1", "#8a94a8", "rgba(255,255,255,0.07)", "rgba(255,255,255,0.18)"
SHADE = "rgba(255,255,255,0.06)"
WINDOW = "rgba(96,165,250,0.12)"
BAND = "rgba(255,255,255,0.08)"
STEP = "hv"          # daily values are step-wise: a square line reads them honestly


def _style(fig: go.Figure, height: int = 420, legend_below: bool = False) -> go.Figure:
    legend = (dict(orientation="h", y=-0.2, yanchor="top", x=0, bgcolor="rgba(0,0,0,0)") if legend_below
              else dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)"))
    fig.update_layout(template="plotly_dark", height=height + (60 if legend_below else 0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=60, r=20, t=40, b=40 + (70 if legend_below else 0)),
                      font=dict(family="Inter, system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK2),
                      hovermode="x unified", hoverlabel=dict(bgcolor="#1a2236", bordercolor="rgba(255,255,255,0.15)",
                                                             font=dict(color="#e6eaf2")),
                      legend=legend, transition=dict(duration=300, easing="cubic-in-out"))
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, tickfont=dict(color=MUTED))
    fig.update_annotations(font_color=INK2)
    return fig


def _shutin_spans(flags: pd.Series, ts: pd.Series):
    s = flags.to_numpy().astype(int)
    edges = np.diff(np.r_[0, s, 0])
    for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
        yield ts.iloc[a], ts.iloc[b - 1]


# ----------------------------------------------------------------------------- data view
SENSOR_LABEL = {
    "dh_pressure_psia": "Downhole pressure (psia)",
    "whp_psia": "Wellhead pressure, upstream (psia)",
    "whp_downstream_psia": "Wellhead pressure, downstream (psia)",
    "annulus_pressure_psia": "Annulus pressure (psia)",
    "gas_lift_rate_mscfd": "Gas-lift rate (Mscf/d)",
    "dh_temperature_degf": "Downhole temperature (°F)",
    "choke_opening_pct": "Choke opening (%)",
}


def sensor_panels(minute: pd.DataFrame, well: str, cols: list[str], resample: str = "10min") -> go.Figure:
    d = minute[minute.well_name == well].set_index("timestamp")
    agg = d[cols].resample(resample).median()
    shut = d["shut_in"].resample(resample).max().fillna(0).astype(bool) if "shut_in" in d else None
    fig = make_subplots(rows=len(cols), cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        subplot_titles=[SENSOR_LABEL.get(c, c) for c in cols])
    for i, c in enumerate(cols, start=1):
        fig.add_trace(go.Scattergl(x=agg.index, y=agg[c], mode="lines", line=dict(width=1.5, color=BLUE, shape=STEP),
                                   name=SENSOR_LABEL.get(c, c), showlegend=False,
                                   hovertemplate="%{y:.1f}<extra>" + c + "</extra>"), row=i, col=1)
        if shut is not None:
            for a, b in _shutin_spans(shut, shut.index.to_series()):
                fig.add_vrect(x0=a, x1=b, fillcolor=SHADE, line_width=0, row=i, col=1)
    fig.update_annotations(font_size=12, x=0, xanchor="left")
    return _style(fig, height=170 * len(cols) + 60)


# ----------------------------------------------------------------------------- VFM
def vfm_rate_panels(vfm_daily: pd.DataFrame, tests: pd.DataFrame, well: str, events: pd.DataFrame | None = None,
                    height: int = 640) -> go.Figure:
    d = vfm_daily[vfm_daily.well_name == well].copy()
    d["date"] = pd.to_datetime(d["date"])
    t = tests[tests.well_name == well]
    phases = list(PHASE_COLOR)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=[PHASE_LABEL[p] for p in phases])
    # shut-ins: the daily volume drops because the well was closed (e.g. for a build-up test), not a model failure
    if events is not None and len(events):
        for _, ev in events[events.well_name == well].iterrows():
            for i in range(1, 4):
                fig.add_vrect(x0=ev.t_shut, x1=ev.t_reopen, fillcolor=SHADE, line_width=0, row=i, col=1)
            fig.add_annotation(x=ev.t_reopen, y=0.08, yref="y domain", row=1, col=1, xanchor="left", xshift=4,
                               text=f"shut in {ev.duration_hr:.0f} h", showarrow=False, yanchor="bottom",
                               font=dict(size=10, color=INK2), bgcolor="rgba(17,24,39,0.85)")
    for i, ph in enumerate(phases, start=1):
        col = PHASE_COLOR[ph]
        if ph + "_p05" in d:
            fig.add_trace(go.Scatter(x=pd.concat([d.date, d.date[::-1]]),
                                     y=pd.concat([d[ph + "_p95"], d[ph + "_p05"][::-1]]),
                                     fill="toself", fillcolor=BAND, line=dict(width=0, shape=STEP),
                                     hoverinfo="skip", name="90% prediction band", showlegend=(i == 1)), row=i, col=1)
        fig.add_trace(go.Scatter(x=d.date, y=d[ph], mode="lines", line=dict(width=2, color=col, shape=STEP),
                                 name="VFM daily" if i == 1 else PHASE_LABEL[ph], showlegend=(i == 1),
                                 hovertemplate="%{y:.0f}<extra>VFM</extra>"), row=i, col=1)
        fig.add_trace(go.Scatter(x=t.test_mid, y=t[ph], mode="markers",
                                 marker=dict(size=8, color="#0b0f1a", line=dict(width=2, color=col)),
                                 name="Well test (measured)", showlegend=(i == 1),
                                 hovertemplate="%{y:.0f}<extra>well test</extra>"), row=i, col=1)
    for a in fig.layout.annotations[:3]:          # subplot titles only
        a.update(font_size=12, x=0, xanchor="left")
    fig = _style(fig, height=height - 60, legend_below=True)
    fig.update_layout(legend_y=-0.08, margin_b=70)
    return fig


def parity_plot(bt: pd.DataFrame, phase: str) -> go.Figure:
    ok = bt[phase + "_vfm"].notna()
    a, p = bt.loc[ok, phase], bt.loc[ok, phase + "_vfm"]
    lo, hi = float(min(a.min(), p.min())) * 0.9, float(max(a.max(), p.max())) * 1.05
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=AXIS, width=1, dash="dot"),
                             name="perfect", hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=a, y=p, mode="markers", marker=dict(size=9, color=PHASE_COLOR[phase],
                                                                   line=dict(width=1.5, color="#0b0f1a")),
                             text=bt.loc[ok, "well_name"] + " " + bt.loc[ok, "test_mid"].dt.strftime("%Y-%m-%d"),
                             hovertemplate="%{text}<br>measured %{x:.0f}<br>predicted %{y:.0f}<extra></extra>",
                             showlegend=False))
    fig.update_layout(title=dict(text=PHASE_LABEL[phase], font_size=13, x=0),
                      xaxis_title="Measured (well test)", yaxis_title="VFM (out-of-sample)", hovermode="closest")
    fig.update_xaxes(range=[lo, hi])
    fig.update_yaxes(range=[lo, hi], scaleanchor="x", scaleratio=1)
    return _style(fig, height=360)


def reservoir_pressure_plot(vfm_daily: pd.DataFrame, well: str, pta_rows: pd.DataFrame | None) -> go.Figure:
    d = vfm_daily[vfm_daily.well_name == well].copy()
    d["date"] = pd.to_datetime(d["date"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.date, y=d.p_res_implied_psia, mode="lines", line=dict(width=2, color=BLUE, shape=STEP),
                             name="Reservoir pressure implied by VFM inflow model"))
    fig.add_trace(go.Scatter(x=d.date, y=d.pwf_psia, mode="lines", line=dict(width=1.5, color=MUTED, shape=STEP),
                             name="Flowing bottom-hole pressure (gauge)"))
    if pta_rows is not None and len(pta_rows):
        fig.add_trace(go.Scatter(x=pta_rows.t_shut, y=pta_rows.p_star_psia, mode="markers",
                                 marker=dict(size=11, color=ORANGE, symbol="diamond", line=dict(width=1.5, color="#0b0f1a")),
                                 name="p* from build-up (PTA)"))
    fig.update_yaxes(title="psia (gauge depth)")
    return _style(fig, height=360)


# ----------------------------------------------------------------------------- PTA
def loglog_plot(r) -> go.Figure:
    d = r.data
    m = r.m_psi_cycle
    fig = go.Figure()
    fig.add_vrect(x0=r.window_start_hr, x1=r.window_end_hr, fillcolor=WINDOW, line_width=0,
                  annotation_text="radial-flow window", annotation_position="top left",
                  annotation_font=dict(size=11, color=INK2))
    fig.add_trace(go.Scatter(x=d["dt"], y=d["dp"], mode="markers", marker=dict(size=7, color=BLUE),
                             name="Δp = p<sub>ws</sub> − p<sub>wf</sub>", hovertemplate="Δt %{x:.3g} h<br>Δp %{y:.1f} psi<extra></extra>"))
    ok = np.isfinite(d["der"]) & (d["der"] > 0)
    fig.add_trace(go.Scatter(x=d["dt"][ok], y=d["der"][ok], mode="markers", marker=dict(size=7, color=ORANGE, symbol="triangle-up"),
                             name="Bourdet derivative Δp′", hovertemplate="Δt %{x:.3g} h<br>Δp′ %{y:.2f} psi<extra></extra>"))
    lvl = m / np.log(10)
    fig.add_trace(go.Scatter(x=[d["dt"].min(), d["dt"].max()], y=[lvl, lvl], mode="lines",
                             line=dict(color=ORANGE, width=1, dash="dash"), name=f"IARF level m/2.303 = {lvl:.1f} psi"))
    if "dp_model" in d:
        fig.add_trace(go.Scatter(x=d["dt_model"], y=d["dp_model"], mode="lines", line=dict(color=INK2, width=1.2),
                                 name=f"model match: k {r.k_match_md:.0f} md, s {r.skin_match:.1f}", hoverinfo="skip"))
        okm = np.isfinite(d["der_model"]) & (d["der_model"] > 0)
        fig.add_trace(go.Scatter(x=d["dt_model"][okm], y=d["der_model"][okm], mode="lines",
                                 line=dict(color=INK2, width=1.2, dash="dot"), name="model derivative", hoverinfo="skip"))
    fig.update_xaxes(type="log", title="Shut-in time Δt (h)", dtick=1,
                     range=[np.log10(float(np.min(d["dt"])) * 0.7), np.log10(float(np.max(d["dt"])) * 1.5)])
    fig.update_yaxes(type="log", title="Δp, Δp′ (psi)", dtick=1)
    fig.update_layout(title=dict(text="Log-log diagnostic plot", x=0, font_size=13), hovermode="closest")
    return _style(fig, legend_below=True)


def horner_plot(r) -> go.Figure:
    d = r.data
    x = d["horner_x"]
    sel = (d["dt"] >= r.window_start_hr) & (d["dt"] <= r.window_end_hr)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x[~sel], y=d["p"][~sel], mode="markers", marker=dict(size=6, color=MUTED),
                             name="Build-up pressure", hovertemplate="(tp+Δt)/Δt %{x:.3g}<br>p %{y:.1f} psia<extra></extra>"))
    fig.add_trace(go.Scatter(x=x[sel], y=d["p"][sel], mode="markers", marker=dict(size=7, color=BLUE),
                             name="Points used in fit", hovertemplate="(tp+Δt)/Δt %{x:.3g}<br>p %{y:.1f} psia<extra></extra>"))
    xl = np.logspace(0, np.log10(x.max()), 50)
    fig.add_trace(go.Scatter(x=xl, y=r.p_star_psia - r.m_psi_cycle * np.log10(xl), mode="lines",
                             line=dict(color=ORANGE, width=2),
                             name=f"Horner line: m = {r.m_psi_cycle:.2f} psi/cycle, p* = {r.p_star_psia:.0f} psia"))
    fig.add_trace(go.Scatter(x=[1], y=[r.p_star_psia], mode="markers",
                             marker=dict(size=11, color=ORANGE, symbol="diamond", line=dict(width=1.5, color="#0b0f1a")),
                             name="p* (extrapolated)", showlegend=False))
    fig.update_xaxes(type="log", autorange="reversed", title="Horner time (tp + Δt)/Δt", dtick=1)
    fig.update_yaxes(title="Shut-in pressure p<sub>ws</sub> (psia)")
    fig.update_layout(title=dict(text="Horner plot", x=0, font_size=13), hovermode="closest")
    return _style(fig, legend_below=True)


def mdh_plot(r) -> go.Figure:
    d = r.data
    sel = (d["dt"] >= r.window_start_hr) & (d["dt"] <= r.window_end_hr)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["dt"], y=d["p"], mode="markers", marker=dict(size=6, color=MUTED), name="Build-up pressure"))
    fig.add_trace(go.Scatter(x=d["dt"][sel], y=d["p"][sel], mode="markers", marker=dict(size=7, color=BLUE), name="Radial-flow window"))
    # the Horner line mapped onto Δt (same fit, so p1hr lies on it at Δt = 1 h)
    dtl = np.logspace(np.log10(max(float(np.min(d["dt"])), 1e-3)), np.log10(float(np.max(d["dt"]))), 60)
    fig.add_trace(go.Scatter(x=dtl, y=r.p_star_psia - r.m_psi_cycle * np.log10((r.tp_hr + dtl) / dtl), mode="lines",
                             line=dict(color=ORANGE, width=2), name="Straight-line fit", hoverinfo="skip"))
    fig.add_hline(y=r.p1hr_psia, line=dict(color=AXIS, width=1, dash="dot"),
                  annotation_text=f"p₁ₕᵣ = {r.p1hr_psia:.1f} psia", annotation_position="bottom right")
    fig.update_xaxes(type="log", title="Shut-in time Δt (h)", dtick=1,
                     range=[np.log10(float(np.min(d["dt"])) * 0.7), np.log10(float(np.max(d["dt"])) * 1.5)])
    fig.update_yaxes(title="p<sub>ws</sub> (psia)")
    fig.update_layout(title=dict(text="Semilog (MDH) plot", x=0, font_size=13), hovermode="closest")
    return _style(fig, height=380, legend_below=True)


def event_history_plot(minute: pd.DataFrame, r, pad_hr: float = 12) -> go.Figure:
    d = minute[minute.well_name == r.well_name].set_index("timestamp")
    w = d.loc[r.t_shut - pd.Timedelta(hours=pad_hr): r.t_shut + pd.Timedelta(hours=r.duration_hr + pad_hr)]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=["Downhole pressure (psia)", "Gas-lift rate (Mscf/d)"])
    fig.add_trace(go.Scattergl(x=w.index, y=w.dh_pressure_psia, mode="lines", line=dict(width=1.5, color=BLUE),
                               showlegend=False), row=1, col=1)
    fig.add_trace(go.Scattergl(x=w.index, y=w.gas_lift_rate_mscfd, mode="lines", line=dict(width=1.5, color=MUTED, shape=STEP),
                               showlegend=False), row=2, col=1)
    for row in (1, 2):
        fig.add_vrect(x0=r.t_shut, x1=r.t_shut + pd.Timedelta(hours=r.duration_hr), fillcolor=SHADE, line_width=0,
                      row=row, col=1)
    fig.update_annotations(font_size=12, x=0, xanchor="left")
    fig = _style(fig, height=380 + 60)
    fig.update_layout(title=dict(text="Shut-in event", x=0, font_size=13), margin_t=70)
    return fig


def field_rates_plot(vfm_daily: pd.DataFrame, days: int = 90, height: int = 340) -> go.Figure:
    """Field totals of the daily VFM rates over the last `days` days: oil and water (left axis), gas (right axis)."""
    d = vfm_daily.assign(date=pd.to_datetime(vfm_daily.date))
    d = d[d.date >= d.date.max() - pd.Timedelta(days=days)]
    f = d.groupby("date")[list(PHASE_COLOR)].sum()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for ph in ["oil_rate_stbd", "water_rate_stbd"]:
        fig.add_trace(go.Scatter(x=f.index, y=f[ph], mode="lines", line=dict(width=2, color=PHASE_COLOR[ph], shape=STEP),
                                 name=PHASE_LABEL[ph], hovertemplate="%{y:,.0f}<extra>" + PHASE_LABEL[ph] + "</extra>"),
                      secondary_y=False)
    fig.add_trace(go.Scatter(x=f.index, y=f["gas_rate_mscfd"], mode="lines",
                             line=dict(width=2, color=PHASE_COLOR["gas_rate_mscfd"], shape=STEP),
                             name=PHASE_LABEL["gas_rate_mscfd"],
                             hovertemplate="%{y:,.0f}<extra>Gas (Mscf/d)</extra>"), secondary_y=True)
    fig.update_yaxes(title_text="STB/d", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Mscf/d", secondary_y=True, rangemode="tozero", showgrid=False)
    fig = _style(fig, height)
    fig.update_layout(margin=dict(l=50, r=50, t=30, b=30), legend=dict(orientation="h", y=1.1, x=0))
    return fig
