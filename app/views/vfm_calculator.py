import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
well = UI.well()
p = ws.model.params.get(well)
UI.header("Rate calculator", f"{well} · enter a downhole pressure reading to get the rates the flow meter expects. "
                             "For what-if checks and for days without a well test.")
if p is None:
    UI.note(f"{well} has no well tests, so the flow meter cannot be calibrated for it.", "warn")
    st.stop()

d = ws.vfm_daily[ws.vfm_daily.well_name == well].assign(date=lambda x: pd.to_datetime(x.date))
tmax = d.date.max()
left, right = st.columns([1.15, 1.6], gap="large")
with left:
    date_in = st.date_input("Date", value=tmax.date())
    last_pwf = float(d.pwf_psia.dropna().iloc[-1]) if d.pwf_psia.notna().any() else 2500.0
    pwf_in = st.number_input("Flowing bottom-hole pressure, Pwf (psia)", value=round(last_pwf, 0), step=10.0, format="%.0f",
                             help="Pre-filled with the latest daily median from the downhole gauge")
    hours = st.slider("Hours on stream", 0.0, 24.0, 24.0, step=0.5)
    tdays = V.days_since_ref([pd.Timestamp(date_in) + pd.Timedelta(hours=12)])
    r = ws.model.predict_rates(well, tdays, pwf_in).iloc[0]
    frac = hours / 24
    out = []
    for ph in V.PHASES:
        q = ws.model.rel_err_q.get(ph, {"q05": 0, "q95": 0})
        v = r[ph] * frac
        out.append({"Phase": PLT.PHASE_LABEL[ph], "Expected": v, "Low": v * (1 + q["q05"]), "High": v * (1 + q["q95"])})
    UI.table(pd.DataFrame(out), labels={"Low": "90% low", "High": "90% high"},
             formats={c: "{:,.0f}" for c in ("Expected", "Low", "High")}, key_col="Phase", nowrap=("Phase",))
    st.caption(f"Water cut {r.water_cut_pct:.1f}% · GOR {p.gor:,.0f} scf/STB")
    if pd.Timestamp(date_in) > tmax + pd.Timedelta(days=60):
        UI.note("More than 60 days past the last data. Reservoir-pressure and water-cut trends are being extrapolated; "
                "check against a new well test.", "warn")

with right:
    pres = float(p.reservoir_pressure(tdays)[0])
    if np.isfinite(pres) and p.J > 0:
        pw = np.linspace(max(pres - 2500, 14.7), pres, 60)
        liq = p.J * (pres - pw)
        wc = r.water_cut_pct / 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=liq, y=pw, mode="lines", line=dict(color=PLT.MUTED, width=2), name="Liquid"))
        fig.add_trace(go.Scatter(x=liq * (1 - wc), y=pw, mode="lines", line=dict(color=PLT.ORANGE, width=2), name="Oil"))
        fig.add_trace(go.Scatter(x=[r.oil_rate_stbd], y=[pwf_in], mode="markers", name="Your reading",
                                 marker=dict(size=11, color=PLT.ORANGE, line=dict(width=2, color=PLT.BG))))
        fig.update_layout(title=dict(text=f"Inflow performance, {date_in:%d %b %Y}", x=0, font_size=13),
                          xaxis_title="Rate (STB/d)", yaxis_title="Pwf (psia)", hovermode="closest")
        st.plotly_chart(PLT._style(fig, 380), width="stretch")
        UI.howto(f"How much the well delivers at each bottom-hole pressure. At Pwf = {pres:,.0f} psia (the reservoir "
                 f"pressure on this date) nothing flows; every psi below it adds J = {p.J:.2f} STB/d of liquid.")
    else:
        UI.note("Productivity could not be identified for this well, so the inflow curve is not drawn.", "warn")
