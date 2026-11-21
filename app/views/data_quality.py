import pandas as pd
import streamlit as st

from wellperf import config as C
from wellperf import plots as PLT
from wellperf import ui as UI

ws = UI.ws()
well = UI.well()
UI.header("Data quality", f"{well} · cleaned per-minute sensor data, the corrections applied, and detected shut-ins")

# ---------------------------------------------------------------- sensor chart
short = {"dh_pressure_psia": "Downhole pressure", "whp_psia": "Wellhead pressure", "whp_downstream_psia": "Downstream pressure",
         "annulus_pressure_psia": "Annulus pressure", "gas_lift_rate_mscfd": "Gas-lift rate",
         "dh_temperature_degf": "Downhole temperature", "choke_opening_pct": "Choke opening"}
cols = st.pills("Signals", list(short), selection_mode="multi", format_func=short.get, key="dq_signals",
                default=["dh_pressure_psia", "whp_psia", "gas_lift_rate_mscfd", "choke_opening_pct"])
if cols:
    st.plotly_chart(PLT.sensor_panels(ws.minute, well, cols), width="stretch")
    UI.howto("Cleaned 1-minute data, drawn as 10-minute medians. <b>Grey bands</b> are shut-ins: gas-lift injection "
             "stopped or the choke closed. Each band is analysed on the Build-up tests (PTA) page.")
else:
    st.caption("Pick at least one signal.")

# ---------------------------------------------------------------- what was fixed
rep = ws.hf_qc.set_index("well_name")
issue_cols = [c for c in rep.columns if "|" in c]
by_issue = rep[issue_cols].T
by_issue.index = pd.MultiIndex.from_tuples([tuple(i.split("|")) for i in by_issue.index], names=["signal", "issue"])
mine = by_issue[well] if well in by_issue.columns else None
labels = {"sentinel": "Missing-value code", "out_of_bounds": "Out of range", "spikes": "Spikes removed",
          "frozen": "Frozen sensor", "interpolated": "Short gaps filled", "still_missing": "Still missing"}

UI.section("What was corrected", f"Minutes affected for {well}, summed over all signals")
if mine is not None:
    tot = mine.groupby(level="issue").sum()
    tot = tot.reindex([k for k in labels if k in tot.index])
    c = st.columns(max(len(tot), 1))
    for col, (k, v) in zip(c, tot.items()):
        col.metric(labels.get(k, k.replace("_", " ").capitalize()), f"{int(v):,} min", border=True, height="stretch")

t1, t2, t3 = st.tabs(["Sensor cleaning, all wells", "Well-test corrections", "Shut-in events"])
with t1:
    allw = by_issue.groupby(level="issue").sum().T
    allw = allw[[k for k in labels if k in allw.columns]].rename(columns=labels)
    allw.index.name = "Well"
    UI.table(allw.reset_index(), key_col="Well", formats={c: "{:,.0f}" for c in labels.values()})
    UI.howto(f"Minutes affected per well. Spikes: Hampel filter (31-minute window, 6σ). Frozen: the same value for "
             f"≥ {C.FROZEN_MIN_RUN} min. Gaps ≤ {C.MAX_INTERP_GAP_MIN} min are interpolated; longer gaps stay empty. "
             f"Still missing = gaps too long to fill honestly; they are left empty and excluded from daily medians. "
             f"Duplicate timestamps averaged: {int(rep['duplicates_averaged'].iloc[0]):,}.")
with t2:
    field_name = {"oil_rate_stbd": "Oil rate", "water_rate_stbd": "Water rate", "gas_rate_mscfd": "Gas rate",
                  "liquid_rate_stbd": "Liquid rate", "water_cut_pct": "Water cut", "gor_scf_stb": "GOR",
                  "gas_lift_rate_mscfd": "Gas-lift rate", "total_gas_mscfd": "Total gas"}
    if ws.test_issues.empty:
        UI.note("No corrections: no well-test file came with this data, or every test was consistent.", "info")
    else:
        ti = ws.test_issues.copy()
        ti["column"] = ti["column"].map(lambda c: field_name.get(c, c.replace("_", " ")))
        ti["issue"] = ti["issue"].str.replace(" -> ", " → ", regex=False)
        UI.table(ti, key_col="well_name", max_height=420, date_fmt="%d %b %Y",
                 labels={"well_name": "Well", "test_start": "Test date", "column": "Field", "issue": "Problem and fix",
                         "original": "Reported", "corrected": "Corrected"},
                 formats={"original": "{:,.1f}", "corrected": "{:,.1f}"})
    UI.howto("Each well test reports oil, water, liquid, water cut, GOR and gas, so errors show up as inconsistencies. "
             "Sign flips are made positive, gas reported in sm³/d is converted to Mscf/d, and inconsistent totals are recomputed.")
with t3:
    if ws.events.empty:
        UI.note("No shut-ins of 1 hour or longer in this data.", "info")
    else:
        UI.table(ws.events[["well_name", "t_shut", "t_reopen", "duration_hr"]], key_col="well_name",
                 labels={"well_name": "Well", "t_shut": "Shut in", "t_reopen": "Reopened", "duration_hr": "Hours"},
                 formats={"duration_hr": "{:.1f}"})
    UI.howto("A shut-in is any stop of gas-lift injection (< 5 Mscf/d) or a closed choke lasting at least 1 hour.")
