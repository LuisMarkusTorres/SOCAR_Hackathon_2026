import numpy as np
import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
vd = ws.vfm_daily.assign(date=pd.to_datetime(ws.vfm_daily.date))
last = vd.date.max()
n_tests = int(len(ws.tests))
last_test = pd.to_datetime(ws.tests.test_end).max() if n_tests else None
UI.header("Field overview",
          f"{vd.well_name.nunique()} wells · {vd.date.min():%d %b} – {last:%d %b %Y} · latest day {last:%d %b %Y}"
          + (f" · last well test {last_test:%d %b %Y}" if last_test is not None else ""))

# ---------------------------------------------------------------- KPIs
field = vd.groupby("date")[["oil_rate_stbd", "water_rate_stbd", "gas_rate_mscfd"]].sum()


def _change(col):
    """Latest day against the mean of the previous 7 days, as html for the KPI sub-line."""
    if len(field) < 3:
        return ""
    prev = field[col].iloc[-8:-1].mean()
    if not prev:
        return ""
    pct = (field[col].iloc[-1] - prev) / prev * 100
    return f"<b>{pct:+.1f}%</b> vs previous 7 days"


sc = V.score(ws.backtest_forward).set_index("model")
if ws.test_eval is not None and len(ws.test_eval):
    se = V.score(ws.test_eval).set_index("model")
    err = {"label": "Flow-meter oil error, uploaded tests", "value": f"{se.loc['VFM', 'oil MAPE %']:.1f}", "unit": "%",
           "tone": "blue", "sub": f"baseline <b>{se.loc['Last test carried forward', 'oil MAPE %']:.1f}%</b> · "
                                  f"{int(se.loc['VFM', 'n_tests'])} tests, model unchanged"}
else:
    err = {"label": "Flow-meter oil error", "value": f"{sc.loc['VFM', 'oil MAPE %']:.1f}", "unit": "%", "tone": "blue",
           "sub": f"baseline <b>{sc.loc['Last test carried forward', 'oil MAPE %']:.1f}%</b> · forward-chaining, "
                  f"{int(sc.loc['VFM', 'n_tests'])} tests"}
UI.kpis([
    {"label": "Oil, field", "value": f"{field.oil_rate_stbd.iloc[-1]:,.0f}", "unit": "STB/d", "tone": "oil",
     "sub": _change("oil_rate_stbd")},
    {"label": "Gas, field", "value": f"{field.gas_rate_mscfd.iloc[-1]:,.0f}", "unit": "Mscf/d", "tone": "gas",
     "sub": _change("gas_rate_mscfd") or "produced gas, lift gas excluded"},
    {"label": "Water, field", "value": f"{field.water_rate_stbd.iloc[-1]:,.0f}", "unit": "STB/d", "tone": "water",
     "sub": _change("water_rate_stbd")},
    err,
])

# ---------------------------------------------------------------- chart + latest build-up
left, right = st.columns([1.75, 1], gap="medium")
with left:
    with st.container(border=True):
        UI.card_title("Last 90 days", "Field daily rates from the flow meter")
        st.plotly_chart(PLT.field_rates_plot(ws.vfm_daily, 90), width="stretch")
        st.page_link("views/production.py", label="Details, per well", icon=":material/arrow_forward:")
with right:
    with st.container(border=True):
        if len(ws.pta):
            r = ws.pta.sort_values("t_shut").iloc[-1]
            UI.card_title("Latest build-up", f"{r.well_name} · {r.t_shut:%d %b %Y} · {r.duration_hr:.0f} h")
            fmt = lambda v, f: f"{v:{f}}" if np.isfinite(v) else "n/a"
            UI.mini_stats([("Permeability k", fmt(r.k_md, ",.0f"), "mD", f"R² {r.r2:.3f}"),
                           ("Skin s", fmt(r.skin, ".2f"), "", "> 0 damaged"),
                           ("Slope m", fmt(r.m_psi_cycle, ".1f"), "psi/cycle", "Horner line"),
                           ("Δp skin", fmt(r.dP_skin, ",.0f"), "psi", "0.87·m·s")])
            st.caption(f"p* {r.p_star_psia:,.0f} psia at gauge"
                       + (f" · {r.p_star_datum_psia:,.0f} at datum" if "p_star_datum_psia" in r and np.isfinite(r.p_star_datum_psia) else "")
                       + f" · rate {r.q_stbd:,.0f} STB/d")
        else:
            UI.card_title("Latest build-up", "no shut-in in this period")
            st.caption("k and skin can only be measured when a well is shut in.")
        st.page_link("views/buildups.py", label="Details, all build-ups", icon=":material/arrow_forward:")

# ---------------------------------------------------------------- needs attention (every line comes from a number)
items = []
if len(ws.pta):
    for w, g in ws.pta.sort_values("t_shut").groupby("well_name"):
        r = g.iloc[-1]
        if np.isfinite(r.skin) and r.skin > 3:
            items.append(("warn", f"{w}: skin {r.skin:.1f}, a damaged well",
                          f"Δp skin {r.dP_skin:,.0f} psi, flow efficiency {r.flow_efficiency:.0%} on {r.t_shut:%d %b}. "
                          f"Candidate for a stimulation review."))
        if len(g) >= 2 and np.isfinite(g.skin.iloc[0]) and np.isfinite(r.skin) and r.skin - g.skin.iloc[0] > 1:
            items.append(("warn", f"{w}: skin rose from {g.skin.iloc[0]:.1f} to {r.skin:.1f}",
                          f"Seen across {len(g)} shut-ins since {g.t_shut.iloc[0]:%d %b}. Damage is building between tests."))
        short = g[g.duration_hr < 6]
        if len(short):
            items.append(("info", f"{w}: short shut-in ({short.duration_hr.iloc[-1]:.1f} h)",
                          "A short radial-flow window makes k and skin less certain. Flagged in the PTA results."))
if n_tests:
    for w, t in ws.tests.groupby("well_name").test_end.max().items():
        age = (last - pd.to_datetime(t)).days
        if age > 28 and w in ws.model.params:
            items.append(("warn", f"{w}: last well test was {age} days ago",
                          "Rates after it rely on the extrapolated reservoir-pressure and water-cut trends."))
outage = vd[vd.flag.str.contains("Pwf", na=False)]
if len(outage):
    wells = ", ".join(sorted(outage.well_name.unique()))
    items.append(("info", f"Downhole gauge missing on {len(outage)} well-day{'s' if len(outage) > 1 else ''}",
                  f"{wells}: the rate uses interpolated or last-known pressure and is flagged in the export."))
for w, p in ws.model.params.items():
    if w in set(vd.well_name) and p.wc_d * 30 > 1.0:
        items.append(("info", f"{w}: water cut rising {p.wc_d * 30:.1f} pts/month",
                      f"Latest {vd[vd.well_name == w].water_cut_pct.iloc[-1]:.0f}%. Fitted to this well's tests."))
uncal = [w for w in sorted(vd.well_name.unique()) if w not in ws.model.params]
if uncal:
    items.append(("warn", f"Not calibrated: {', '.join(uncal)}", "No well tests for these wells, so no flow-meter rate."))
UI.section("Needs attention", "Generated from the results on this page; each line names the number behind it.")
with st.container(border=True):
    UI.attention(items[:8] if items else [("good", "Nothing needs attention", "No damaged wells, stale tests or gauge outages.")])

# ---------------------------------------------------------------- pop-up for one well
card = dict(border=True, height="stretch")


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
    UI.howto("Lines: flow-meter daily volumes, with the 90% range shaded. Circles: measured production well tests. "
             "Shaded: the well was shut in, so nothing was produced.")
    a, b = st.columns(2)
    a.page_link("views/production.py", label="Open in Production", icon=":material/arrow_forward:")
    b.page_link("views/buildups.py", label="Open in Build-up tests", icon=":material/arrow_forward:")


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
        "k_md": st.column_config.NumberColumn("k, mD", format="%.0f", width=60,
                                              help="Permeability from the latest build-up test"),
        "skin": st.column_config.NumberColumn("Skin", format="%.2f", width=60, help="From the latest build-up test"),
    })

if st.session_state.pop("ov_open", None):
    w = UI.well()
    st.dialog(f"{w} · production", width="large")(well_dialog_body)(w)
