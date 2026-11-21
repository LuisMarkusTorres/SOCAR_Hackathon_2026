import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
vd = ws.vfm_daily.assign(date=pd.to_datetime(ws.vfm_daily.date))
last = vd.date.max()
UI.header("Field overview", f"{vd.well_name.nunique()} wells · {vd.date.min():%d %b} – {last:%d %b %Y} · "
                            f"rates for the latest day ({last:%d %b %Y})")

# ---------------------------------------------------------------- KPIs
field = vd.groupby("date")[["oil_rate_stbd", "water_rate_stbd", "gas_rate_mscfd"]].sum()
weekly = field.resample("W").mean()
sc = V.score(ws.backtest_forward).set_index("model")
card = dict(border=True, height="stretch")
c = st.columns(4)
c[0].metric("Oil, field", f"{field.oil_rate_stbd.iloc[-1]:,.0f} STB/d", **card,
            chart_data=weekly.oil_rate_stbd.round(0).tolist(), help="Sparkline: weekly average over the period")
c[1].metric("Water, field", f"{field.water_rate_stbd.iloc[-1]:,.0f} STB/d", **card,
            chart_data=weekly.water_rate_stbd.round(0).tolist(), help="Sparkline: weekly average over the period")
c[2].metric("Gas, field", f"{field.gas_rate_mscfd.iloc[-1]:,.0f} Mscf/d", **card,
            chart_data=weekly.gas_rate_mscfd.round(0).tolist(), help="Produced gas, excluding injected lift gas")
if ws.test_eval is not None and len(ws.test_eval):
    se = V.score(ws.test_eval).set_index("model")
    c[3].metric("Flow-meter oil error, uploaded tests", f"{se.loc['VFM', 'oil MAPE %']:.1f}%", **card,
                delta=f"{se.loc['VFM', 'oil MAPE %'] - se.loc['Last test carried forward', 'oil MAPE %']:.1f} pts vs baseline",
                delta_color="inverse",
                help=f"The trained model, unchanged, scored on the {int(se.loc['VFM', 'n_tests'])} well tests in the "
                     f"uploaded file (water {se.loc['VFM', 'water MAPE %']:.1f}%, gas {se.loc['VFM', 'gas MAPE %']:.1f}%). "
                     "Baseline: repeat the last training test.")
else:
    c[3].metric("Flow-meter oil error", f"{sc.loc['VFM', 'oil MAPE %']:.1f}%", **card,
                delta=f"{sc.loc['VFM', 'oil MAPE %'] - sc.loc['Last test carried forward', 'oil MAPE %']:.1f} pts vs baseline",
                delta_color="inverse",
                help="Mean absolute % error when each training well test is predicted from earlier tests only "
                     f"(water {sc.loc['VFM', 'water MAPE %']:.1f}%, gas {sc.loc['VFM', 'gas MAPE %']:.1f}%). "
                     "Baseline: repeat the last well test.")


# ---------------------------------------------------------------- pop-up for one well
def well_dialog_body(w: str) -> None:
    d = vd[vd.well_name == w]
    if w not in ws.model.params:
        UI.note(f"{w} has no well tests, so the flow meter is not calibrated for it.", "warn")
        return
    latest = d.iloc[-1]
    k = st.columns(4)
    k[0].metric("Oil, latest day", f"{latest.oil_rate_stbd:,.0f} STB/d", **card)
    k[1].metric("Water, latest day", f"{latest.water_rate_stbd:,.0f} STB/d", **card)
    k[2].metric("Gas, latest day", f"{latest.gas_rate_mscfd:,.0f} Mscf/d", **card)
    k[3].metric("Oil produced in period", f"{d.oil_rate_stbd.sum():,.0f} STB", **card)
    st.plotly_chart(PLT.vfm_rate_panels(ws.vfm_daily, ws.tests, w, ws.events, height=520), width="stretch")
    UI.howto("Lines: flow-meter daily volumes, with the 90% range in grey. Circles: measured production well tests. "
             "Shaded: the well was shut in, so nothing was produced.")
    a, b = st.columns(2)
    a.page_link("views/production.py", label="Open in Production (VFM)", icon=":material/arrow_forward:")
    b.page_link("views/buildups.py", label="Open in Build-up tests (PTA)", icon=":material/arrow_forward:")


# ---------------------------------------------------------------- well table
UI.section("Wells", "Click a row to open that well's production chart. It also becomes the active well on every page.")
today = vd[vd.date == last].set_index("well_name")
tbl = today[["oil_rate_stbd", "water_rate_stbd", "gas_rate_mscfd", "water_cut_pct", "pwf_psia"]].copy()
trend = (vd.set_index("date").groupby("well_name").oil_rate_stbd.resample("W").mean()
         .groupby(level=0).apply(lambda s: s.round(0).tolist()))
tbl.insert(1, "oil_trend", trend)
if len(ws.pta):
    lastbu = ws.pta.sort_values("t_shut").groupby("well_name").last()
    tbl = tbl.join(lastbu[["t_shut", "k_md", "skin"]])
else:
    tbl[["t_shut", "k_md", "skin"]] = float("nan")
# k and skin need a shut-in; wells that flowed the whole period have none
tbl.insert(tbl.columns.get_loc("t_shut"), "build_up",
           tbl.pop("t_shut").map(lambda t: f"{t:%d %b}" if pd.notna(t) else "not shut in"))
tbl = tbl.reset_index().rename(columns={"index": "well_name"})
tbl = tbl.round({"oil_rate_stbd": 0, "water_rate_stbd": 0, "gas_rate_mscfd": 0, "pwf_psia": 0})
order = tbl.well_name.tolist()

# A click on any cell opens that row's well. The key changes after every click so the table comes back
# with nothing selected, and clicking the same row again opens the pop-up again.
n = st.session_state.get("ov_n", 0)
tkey = f"ov_wells_{n}"


def _open_well():
    sel = st.session_state[tkey].selection
    cells = sel.get("cells") or []
    rows = sel.get("rows") or []
    row = cells[0][0] if cells else (rows[0] if rows else None)
    if row is not None:
        w = order[int(row)]
        UI.set_well(w)
        st.session_state["ov_open"] = w
    st.session_state["ov_n"] = n + 1


ROW = 38
st.dataframe(
    tbl, hide_index=True, placeholder="–", row_height=ROW, height=ROW * (len(tbl) + 1) + 3,
    key=tkey, on_select=_open_well, selection_mode="single-cell",
    column_config={
        "well_name": st.column_config.TextColumn("Well", width=90),
        "oil_rate_stbd": st.column_config.NumberColumn("Oil, STB/d", format="localized", width=85),
        "oil_trend": st.column_config.LineChartColumn("Oil trend", width=110, help="Weekly average over the period"),
        "water_rate_stbd": st.column_config.NumberColumn("Water, STB/d", format="localized", width=95),
        "gas_rate_mscfd": st.column_config.NumberColumn("Gas, Mscf/d", format="localized", width=90),
        "water_cut_pct": st.column_config.ProgressColumn("Water cut", format="%.0f%%", min_value=0, max_value=100,
                                                         width=120),
        "pwf_psia": st.column_config.NumberColumn("Pwf, psia", format="localized", width=80,
                                                  help="Flowing bottom-hole pressure, daily median at the gauge"),
        "build_up": st.column_config.TextColumn("Build-up test", width=100,
                                                help="Date of the latest shut-in. k and skin can only be measured "
                                                     "when the well is shut in."),
        "k_md": st.column_config.NumberColumn("k, md", format="%.0f", width=60,
                                              help="Permeability from the latest build-up test"),
        "skin": st.column_config.NumberColumn("Skin", format="%.2f", width=60, help="From the latest build-up test"),
    })

if st.session_state.pop("ov_open", None):
    w = UI.well()
    st.dialog(f"{w} · production", width="large")(well_dialog_body)(w)
