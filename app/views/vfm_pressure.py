import numpy as np
import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
well = UI.well()
p = ws.model.params.get(well)
UI.header("Reservoir pressure", f"{well} · two independent estimates: the inflow model behind the flow meter, and "
                                "p* from each build-up test")
if p is None:
    UI.note(f"{well} has no well tests, so the flow meter cannot be calibrated for it.", "warn")
    st.stop()

d = ws.vfm_daily[ws.vfm_daily.well_name == well].assign(date=lambda x: pd.to_datetime(x.date))
tmax = d.date.max()
pres_now = float(p.reservoir_pressure(V.days_since_ref([tmax]))[0])
pta_rows = ws.pta[ws.pta.well_name == well] if len(ws.pta) else None
cards = [{"label": "Reservoir pressure, flow meter", "value": f"{pres_now:,.0f}" if np.isfinite(pres_now) else "n/a",
          "unit": "psia", "tone": "blue", "sub": f"latest day {tmax:%d %b %Y}, implied by the inflow model, at gauge depth"}]
if pta_rows is not None and len(pta_rows):
    last = pta_rows.sort_values("t_shut").iloc[-1]
    cards.append({"label": "p*, latest build-up", "value": f"{last.p_star_psia:,.0f}" if np.isfinite(last.p_star_psia) else "n/a",
                  "unit": "psia", "tone": "oil", "sub": f"shut-in of {last.t_shut:%d %b %Y}, Horner line extrapolated"})
UI.kpis(cards, min_width=260)

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
