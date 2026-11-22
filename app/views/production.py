import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
well = UI.well()
p = ws.model.params.get(well)
n_tests = int((ws.tests_feat.well_name == well).sum())
UI.header("Daily rates (VFM)", f"{well} · daily oil, water and gas from the virtual flow meter, calibrated on "
                               f"{n_tests} production well tests")
if p is None:
    UI.note(f"{well} has no well tests, so the flow meter cannot be calibrated for it.", "warn")
    st.stop()

d = ws.vfm_daily[ws.vfm_daily.well_name == well].assign(date=lambda x: pd.to_datetime(x.date))
UI.kpis([
    {"label": "Oil produced, period", "value": f"{d.oil_rate_stbd.sum():,.0f}", "unit": "STB", "tone": "oil",
     "sub": f"{len(d)} days"},
    {"label": "Average oil rate", "value": f"{d.oil_rate_stbd.mean():,.0f}", "unit": "STB/d", "tone": "oil",
     "sub": f"latest day <b>{d.oil_rate_stbd.iloc[-1]:,.0f}</b>"},
    {"label": "Water cut, latest", "value": f"{d.water_cut_pct.iloc[-1]:.1f}", "unit": "%", "tone": "water",
     "sub": f"trend <b>{p.wc_d * 30:+.2f}</b> pts/month, fitted to this well's tests"},
    {"label": "Gas, latest day", "value": f"{d.gas_rate_mscfd.iloc[-1]:,.0f}", "unit": "Mscf/d", "tone": "gas",
     "sub": f"GOR <b>{p.gor:,.0f}</b> scf/STB, lift gas excluded"},
    {"label": "Productivity index J", "value": f"{p.J:.2f}", "unit": "STB/d/psi", "tone": "blue",
     "sub": f"liquid per psi of drawdown · {p.J_source}"},
])

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
