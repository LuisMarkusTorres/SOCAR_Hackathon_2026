import numpy as np
import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import pta as P
from wellperf import ui as UI

ws = UI.ws()
well = UI.well()


def all_events_table():
    UI.section("All build-ups", "Automatic interpretation of every shut-in. This is what the PTA export contains.")
    show = ["well_name", "t_shut", "duration_hr", "q_stbd", "m_psi_cycle", "k_md", "skin", "dP_skin", "p_star_psia",
            "flow_efficiency", "r2", "flags"]
    t = ws.pta[show].copy()
    t["flags"] = t["flags"].replace("", None)
    UI.table(t, key_col="well_name",
             labels={"well_name": "Well", "t_shut": "Shut in", "duration_hr": "Hours", "q_stbd": "q, STB/d",
                     "m_psi_cycle": "m, psi/cycle", "k_md": "k, md", "skin": "Skin", "dP_skin": "Δp skin, psi",
                     "p_star_psia": "p*, psia", "flow_efficiency": "Flow eff.", "r2": "R²", "flags": "Flags"},
             formats={"duration_hr": "{:.1f}", "q_stbd": "{:,.0f}", "m_psi_cycle": "{:.2f}", "k_md": "{:.1f}",
                      "skin": "{:.2f}", "dP_skin": "{:.1f}", "p_star_psia": "{:,.0f}", "flow_efficiency": "{:.2f}",
                      "r2": "{:.4f}"})


if ws.pta.empty:
    UI.header("Build-up tests (PTA)")
    UI.note("No shut-ins of 1 hour or longer were found in this data, so there is nothing to interpret.", "info")
    st.stop()

# ---------------------------------------------------------------- event selection (synchronised with the sidebar well)
evs = list(ws.pta_objs)
mine = [k for k in evs if UI.event_well(k) == well]
cur = st.session_state.get("bu_event")
if cur not in evs or UI.event_well(cur) != well:
    st.session_state["bu_event"] = mine[0] if mine else None


def _sync_well():
    k = st.session_state.get("bu_event")
    if k:
        UI.set_well(UI.event_well(k))


key = st.session_state.get("bu_event")
r0 = ws.pta_objs[key] if key else None
UI.header("Build-up tests (PTA)",
          f"{r0.well_name} · shut in {r0.t_shut:%d %b %Y, %H:%M} for {r0.duration_hr:.0f} h · "
          f"rate before shut-in {r0.q_stbd:,.0f} STB/d (flow meter)" if r0 else
          f"{well} was not shut in during this period")
st.pills("Shut-in events", evs, key="bu_event", format_func=lambda k: UI.event_label(k, ws), on_change=_sync_well,
         help="Choosing an event also makes its well the active well")
if r0 is None:
    UI.note(f"{well} has no shut-in of 1 hour or longer, so there is no build-up to interpret. "
            f"Pick one of the events above.", "info")
    all_events_table()
    st.stop()

ev = ws.events[(ws.events.well_name == r0.well_name) & (ws.events.t_shut == r0.t_shut)].iloc[0]
props = ws.static.loc[r0.well_name]

# Layout slots in reading order; the window control is filled first because every result depends on it.
results_box = st.container()
plots_box = st.container()
window_box = st.expander("Adjust the radial-flow window", expanded=False)

with window_box:
    dtmin, dtmax = float(r0.data["dt"].min()), float(r0.data["dt"].max())
    auto = (float(np.log10(r0.window_start_hr)), float(np.log10(r0.window_end_hr)))
    skey = f"win_{key}"

    def _reset():
        st.session_state[skey] = auto

    if skey not in st.session_state:
        st.session_state[skey] = auto
    lo, hi = st.slider("Window, log₁₀ of shut-in time in hours", float(np.log10(dtmin)), float(np.log10(dtmax)),
                       step=0.05, key=skey)
    manual = abs(lo - auto[0]) > 1e-6 or abs(hi - auto[1]) > 1e-6
    a, b = st.columns([3, 1])
    a.caption(f"Using {10 ** lo:.3g} h to {10 ** hi:.3g} h. Automatic choice: {r0.window_start_hr:.3g}–"
              f"{r0.window_end_hr:.3g} h, the flattest stretch of the derivative after wellbore storage, at least half a "
              f"log cycle long.")
    b.button("Reset to automatic", on_click=_reset, disabled=not manual, width="stretch")

if manual:
    r = P.interpret_buildup(ws.minute, ev, r0.q_stbd, r0.np_stb, props, window=(10 ** lo, 10 ** hi))
    r.data["q_date"] = r0.data.get("q_date")
else:
    r = r0

# ---------------------------------------------------------------- results
with results_box:
    if manual:
        UI.note(f"Manual window ({10 ** lo:.3g}–{10 ** hi:.3g} h). These numbers differ from the automatic result in "
                f"the export (k {r0.k_md:.1f} md, skin {r0.skin:.2f}).", "warn")
    qb = ws.model.rel_err_q.get("oil_rate_stbd")
    k_help = (f"k is proportional to the flow-meter rate. Over the rate's 90% range it spans "
              f"{r.k_md * (1 + qb['q05']):.0f}–{r.k_md * (1 + qb['q95']):.0f} md." if qb else None)
    c = st.columns(4)
    def fmt(v, spec, unit=""):
        return f"{v:{spec}}{unit}" if np.isfinite(v) else "n/a"

    c[0].metric("Horner slope m", fmt(r.m_psi_cycle, ".2f", " psi/cycle"), border=True,
                help="Pressure rise per tenfold increase in time during radial flow")
    c[1].metric("Permeability k", fmt(r.k_md, ".1f", " md"), border=True, help=k_help)
    c[2].metric("Skin s", fmt(r.skin, ".2f"), border=True, help="> 0 damaged, < 0 stimulated")
    c[3].metric("Pressure drop due to skin", fmt(r.dP_skin, ".1f", " psi"), border=True, help="Δp_skin = 0.87·m·s")
    st.caption(f"p* {fmt(r.p_star_psia, ',.0f', ' psia')} at gauge depth · flow efficiency "
               f"{fmt(r.flow_efficiency, '.2f')} · Pwf at shut-in {fmt(r.pwf_psia, ',.0f', ' psia')} · "
               f"Horner fit R² {r.r2:.4f} · window {r.window_start_hr:.3g}–{r.window_end_hr:.3g} h")

# ---------------------------------------------------------------- diagnostic plots
with plots_box:
    g1, g2 = st.columns(2, gap="medium")
    with g1:
        st.plotly_chart(PLT.loglog_plot(r), width="stretch")
        UI.howto("<b>Start here.</b> Blue is the pressure rise since shut-in; orange is its derivative. The early hump "
                 "is <b>wellbore storage</b> (fluid still entering the well), which says nothing about the rock. A "
                 "<b>flat orange stretch</b> is radial flow in the reservoir: its height gives k. The shaded band is "
                 "the window used for every number above.")
    with g2:
        st.plotly_chart(PLT.horner_plot(r), width="stretch")
        UI.howto("Pressure against Horner time (t<sub>p</sub>+Δt)/Δt. Shut-in time runs left to right; 1 means infinite "
                 "shut-in. The line through the blue points has slope <b>m</b>, which gives k. Extended to 1 it gives "
                 "<b>p*</b>, an estimate of reservoir pressure.")
    g3, g4 = st.columns(2, gap="medium")
    with g3:
        st.plotly_chart(PLT.mdh_plot(r), width="stretch")
        UI.howto("The same build-up against log shut-in time. <b>p<sub>1hr</sub></b> is read off the straight line at "
                 "Δt = 1 h. How far it sits above the flowing pressure, relative to m, gives <b>skin</b>.")
    with g4:
        st.plotly_chart(PLT.event_history_plot(ws.minute, r), width="stretch")
        UI.howto("The raw event: the shut-in (shaded) starts when gas-lift injection stops. Pressure climbs back towards "
                 "reservoir pressure until the well reopens.")

# ---------------------------------------------------------------- interpretation and inputs
left, right = st.columns([1, 1], gap="large")
with left:
    UI.section("Interpretation")
    for kind, text in UI.interpret(r, ws.static):
        UI.note(text, kind)
    with st.container(border=True):
        st.markdown("**p\\* at datum depth**")
        dz = float(props.datum_tvd_ft - props.gauge_tvd_ft)
        grad = st.number_input(f"Fluid gradient between gauge and datum ({dz:,.0f} ft below the gauge), psi/ft",
                               min_value=0.20, max_value=0.55, value=None, step=0.01, placeholder="not set",
                               help="Not in the dataset. Take it from a gradient survey or the oil density.")
        if grad:
            st.markdown(f"p\\* = {r.p_star_psia:,.0f} + {grad:.2f} × {dz:,.0f} = **{r.p_star_psia + grad * dz:,.0f} psia** "
                        f"at {props.datum_tvd_ft:,.0f} ft TVD")
        st.caption("Only absolute pressures shift. m, k, skin and Δp skin use pressure differences and do not change.")
with right:
    UI.section("Inputs used")
    rows = [("q, oil rate before shut-in", f"{r.q_stbd:,.0f} STB/d", f"flow meter, {r.data.get('q_date', '')}"),
            ("Np, cumulative oil", f"{r.np_stb:,.0f} STB", "completion file + flow meter"),
            ("tp = 24·Np/q", f"{r.tp_hr:,.0f} h", "Horner pseudo-producing time"),
            ("pwf, pressure at shut-in", f"{r.pwf_psia:,.1f} psia", "downhole gauge"),
            ("h, net pay", f"{props.net_pay_thickness_ft:g} ft", "lab / PVT"),
            ("φ, porosity", f"{props.porosity_frac:g}", "lab / PVT"),
            ("μo, oil viscosity", f"{props.oil_viscosity_cp:g} cp", "lab / PVT"),
            ("Bo, formation volume factor", f"{props.oil_fvf_rb_stb:g} rb/STB", "lab / PVT"),
            ("ct, total compressibility", f"{props.total_compressibility_1_psi:.2e} 1/psi", "lab / PVT"),
            ("rw, wellbore radius", f"{props.wellbore_radius_ft:g} ft", "lab / PVT")]
    UI.table(pd.DataFrame(rows, columns=["Input", "Value", "Source"]), key_col="Input", nowrap=("Value",))

all_events_table()
