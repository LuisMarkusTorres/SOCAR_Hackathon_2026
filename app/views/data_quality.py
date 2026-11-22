import pandas as pd
import streamlit as st

from wellperf import config as C
from wellperf import pipeline as PL
from wellperf import plots as PLT
from wellperf import ui as UI

ws = UI.ws()
well = UI.well()
UI.header("Data", f"{well} · what was loaded, the cleaned sensor signals, the corrections applied, and the shut-ins found")

# ---------------------------------------------------------------- what is loaded
found = st.session_state.get("_upload_found") or {}
src = {k: v.attrs.get("source", "") for k, v in found.items()}
mn = ws.minute
inv = [(PL.UPLOAD_KINDS["sensors"] + " (per minute)", src.get("sensors", C.HF_FILE if ws.source == "training data" else ""), len(mn),
        mn.well_name.nunique(), mn.timestamp.min(), mn.timestamp.max())]
if len(ws.tests):
    inv.append(("Well tests", src.get("tests", C.TESTS_FILE if ws.source == "training data" else ""), len(ws.tests),
                ws.tests.well_name.nunique(), ws.tests.test_start.min(), ws.tests.test_end.max()))
if "choke" in found or ws.source == "training data":
    ch = found.get("choke")
    if ch is None and (C.DATA_RAW / C.CHOKE_FILE).exists():
        ch = pd.read_csv(C.DATA_RAW / C.CHOKE_FILE)
    inv.append(("Choke events", src.get("choke", C.CHOKE_FILE), len(ch) if ch is not None else None,
                ch.well_name.nunique() if ch is not None else None, None, None))
inv.append(("Reservoir / PVT and completion", ", ".join(x for x in (src.get("pvt"), src.get("completion")) if x)
            or (f"{C.PVT_FILE}, {C.COMPLETION_FILE}" if ws.source == "training data" else "from the model file"),
            len(ws.static), len(ws.static), None, None))
UI.section("Loaded data", "Source: " + ws.source + ". Tables are recognised by their columns.")
UI.table(pd.DataFrame(inv, columns=["Table", "File", "Rows", "Wells", "From", "To"]), key_col="Table",
         formats={"Rows": "{:,.0f}", "Wells": "{:,.0f}"}, date_fmt="%d %b %Y")

# ---------------------------------------------------------------- sensor chart
UI.section("Sensor signals", f"{well}, cleaned 1-minute data drawn as 10-minute medians. Grey bands are shut-ins.")
short = {"dh_pressure_psia": "Downhole pressure", "whp_psia": "Wellhead pressure", "whp_downstream_psia": "Downstream pressure",
         "annulus_pressure_psia": "Annulus pressure", "gas_lift_rate_mscfd": "Gas-lift rate",
         "dh_temperature_degf": "Downhole temperature", "choke_opening_pct": "Choke opening"}
cols = st.pills("Signals", list(short), selection_mode="multi", format_func=short.get, key="dq_signals",
                default=["dh_pressure_psia", "whp_psia", "gas_lift_rate_mscfd", "choke_opening_pct"])
if cols:
    st.plotly_chart(PLT.sensor_panels(ws.minute, well, cols), width="stretch")
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
    UI.kpis([{"label": labels.get(k, k.replace("_", " ").capitalize()), "value": f"{int(v):,}", "unit": "min"}
             for k, v in tot.items()], min_width=140)

t0, t1, t2, t3 = st.tabs(["Well tests, measured", "Sensor cleaning, all wells", "Well-test corrections", ":red[Shut-in events]"])
with t0:
    if not len(ws.tests):
        UI.note("No well-test file came with this data.", "info")
    else:
        tt = ws.tests[ws.tests.well_name == well][["test_start", "test_hours", "oil_rate_stbd", "water_rate_stbd",
                                                   "gas_rate_mscfd", "water_cut_pct", "gor_scf_stb", "dh_pressure_psia",
                                                   "whp_psia", "gas_lift_rate_mscfd"]]
        UI.table(tt, date_fmt="%d %b %Y, %H:%M",
                 labels={"test_start": "Test start", "test_hours": "Hours", "oil_rate_stbd": "Oil, STB/d",
                         "water_rate_stbd": "Water, STB/d", "gas_rate_mscfd": "Gas, Mscf/d", "water_cut_pct": "WC, %",
                         "gor_scf_stb": "GOR, scf/STB", "dh_pressure_psia": "Pwf, psia", "whp_psia": "WHP, psia",
                         "gas_lift_rate_mscfd": "Lift gas, Mscf/d"},
                 formats={"test_hours": "{:.0f}", "oil_rate_stbd": "{:,.0f}", "water_rate_stbd": "{:,.0f}",
                          "gas_rate_mscfd": "{:,.0f}", "water_cut_pct": "{:.1f}", "gor_scf_stb": "{:,.0f}",
                          "dh_pressure_psia": "{:,.0f}", "whp_psia": "{:,.0f}", "gas_lift_rate_mscfd": "{:,.0f}"})
        UI.howto(f"The separator tests for {well} after cleaning. They calibrate the flow meter and are the only "
                 "measured rates; every other day is predicted.")
with t1:
    allw = by_issue.groupby(level="issue").sum().T
    allw = allw[[k for k in labels if k in allw.columns]].rename(columns=labels)
    allw.index.name = "Well"
    UI.table(allw.reset_index(), key_col="Well", formats={c: "{:,.0f}" for c in labels.values()})
    UI.howto(f"Minutes affected per well. Spikes: Hampel filter (31-minute window, 6σ). Frozen: the same value for "
             f"≥ {C.FROZEN_MIN_RUN} min. Gaps ≤ {C.MAX_INTERP_GAP_MIN} min are interpolated; longer gaps stay empty "
             f"and are excluded from the daily medians. Duplicate timestamps averaged: "
             f"{int(rep['duplicates_averaged'].iloc[0]):,}.")
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
    UI.howto(f"A shut-in is any stop of gas-lift injection (< {C.SHUTIN_GL_MAX_MSCFD:g} Mscf/d) or a closed choke "
             f"lasting at least {C.SHUTIN_MIN_DURATION_HR:g} hour. Each one is analysed on the Build-up page.")
