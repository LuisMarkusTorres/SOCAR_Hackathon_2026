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
n_tests = int((ws.tests_feat.well_name == well).sum())
UI.header("Production (VFM)", f"{well} · daily oil, water and gas from the virtual flow meter, calibrated on "
                              f"{n_tests} production well tests")
if p is None:
    UI.note(f"{well} has no well tests, so the flow meter cannot be calibrated for it.", "warn")
    st.stop()

d = ws.vfm_daily[ws.vfm_daily.well_name == well].assign(date=lambda x: pd.to_datetime(x.date))
tmax = d.date.max()
pres_now = float(p.reservoir_pressure(V.days_since_ref([tmax]))[0])

card = dict(border=True, height="stretch")
c = st.columns(5)
c[0].metric("Oil produced in period", f"{d.oil_rate_stbd.sum():,.0f} STB", **card)
c[1].metric("Average oil rate", f"{d.oil_rate_stbd.mean():,.0f} STB/d", **card)
c[2].metric("Water cut, latest", f"{d.water_cut_pct.iloc[-1]:.1f}%", f"{p.wc_d * 30:+.2f} pts/month", **card,
            delta_color="inverse", help="Trend fitted to this well's tests")
c[3].metric("Productivity index J", f"{p.J:.2f}", **card,
            help=f"STB/d of liquid per psi of drawdown. Source: {p.J_source}")
c[4].metric("Reservoir pressure", f"{pres_now:,.0f} psia" if np.isfinite(pres_now) else "n/a", **card,
            help="Latest day, implied by the calibrated inflow model, at gauge depth")

st.plotly_chart(PLT.vfm_rate_panels(ws.vfm_daily, ws.tests, well, ws.events), width="stretch")
UI.howto("<b>Lines</b>: predicted daily volumes = rate × hours on stream. <b>Shaded</b>: the well was shut in (for "
         "example for a build-up test), so the daily volume falls to zero on full shut-in days. That drop is real, not "
         "a model failure. <b>Grey band</b>: 90% range from out-of-sample errors. <b>Circles</b>: measured "
         "production well tests. The model is fitted to them, but each was also predicted blind from earlier tests "
         "to measure the error.")
out_days = d[d.flag.str.startswith("sensor outage")]
if len(out_days):
    UI.note(f"Downhole gauge offline all day on {', '.join(out_days.date.dt.strftime('%d %b'))}. The rate for that day "
            f"uses pressure interpolated from the neighbouring days.", "warn")

# ---------------------------------------------------------------- calculator
UI.section("Rate calculator", "Enter a downhole pressure reading to get the rates the model expects. "
                              "Useful for what-if checks and for days without a well test.")
left, right = st.columns([1, 2], gap="large")
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
    UI.table(pd.DataFrame(out), labels={"Low": "90% range, low", "High": "high"},
             formats={c: "{:,.0f}" for c in ("Expected", "Low", "High")}, key_col="Phase")
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
        fig.add_trace(go.Scatter(x=liq * (1 - wc), y=pw, mode="lines", line=dict(color=PLT.AQUA, width=2), name="Oil"))
        fig.add_trace(go.Scatter(x=[r.oil_rate_stbd], y=[pwf_in], mode="markers", name="Your reading",
                                 marker=dict(size=11, color=PLT.AQUA, line=dict(width=2, color="#0b0b0b"))))
        fig.update_layout(title=dict(text=f"Inflow performance, {date_in:%d %b %Y}", x=0, font_size=13),
                          xaxis_title="Rate (STB/d)", yaxis_title="Pwf (psia)", hovermode="closest")
        st.plotly_chart(PLT._style(fig, 380), width="stretch")
        UI.howto(f"How much the well delivers at each bottom-hole pressure. At Pwf = {pres:,.0f} psia (the reservoir "
                 f"pressure on this date) nothing flows; every psi below it adds J = {p.J:.2f} STB/d of liquid.")
    else:
        UI.note("Productivity could not be identified for this well, so the inflow curve is not drawn.", "warn")

# ---------------------------------------------------------------- cross-check
UI.section("Reservoir pressure: two independent estimates")
pta_rows = ws.pta[ws.pta.well_name == well] if len(ws.pta) else None
st.plotly_chart(PLT.reservoir_pressure_plot(ws.vfm_daily, well, pta_rows), width="stretch")
gaps = []
if pta_rows is not None:
    for _, row in pta_rows.iterrows():
        on = d.loc[d.date == row.t_shut.normalize(), "p_res_implied_psia"]
        if len(on) and np.isfinite(on.iloc[0]):
            gaps.append(f"on {row.t_shut:%d %b} the flow meter implies {on.iloc[0]:,.0f} psia against p* "
                        f"{row.p_star_psia:,.0f} psia ({(on.iloc[0] - row.p_star_psia) / row.p_star_psia:+.0%})")
UI.howto("<b>Blue</b>: reservoir pressure implied by the flow meter, from the well tests. <b>Orange diamonds</b>: p* from "
         "build-ups, from the pressure gauge alone. " + (f"For {well}, " + "; ".join(gaps) + ". " if gaps else "") +
         "Close agreement supports both. A large gap usually means the inflow model's reservoir pressure is poorly "
         "constrained, because the test pressures varied little. The rates themselves are still calibrated directly on "
         "the tests. p* is an extrapolation and tends to sit a little above the average drainage-area pressure.")
