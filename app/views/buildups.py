import numpy as np
import pandas as pd
import streamlit as st

from views import pta_common as PC
from wellperf import ui as UI

ws = UI.ws()
well = UI.well()
if ws.pta.empty:
    UI.header("Build-up results (PTA)")
    UI.note("No shut-ins of 1 hour or longer were found in this data, so there is nothing to interpret.", "info")
    st.stop()

key, r0 = PC.current_event(ws, well)
UI.header("Build-up results (PTA)", PC.subtitle(r0, well))
PC.event_pills(ws)
if r0 is None:
    PC.no_event_note(well)
    st.stop()
ev, props = PC.event_inputs(ws, r0)
r, manual = PC.result(ws, key, r0, ev, props)

# ---------------------------------------------------------------- results
if manual:
    PC.manual_note(r, r0, "The window is set on the Diagnostic plots page.")
qb = ws.model.rel_err_q.get("oil_rate_stbd")
k_help = (f"proportional to the flow-meter rate: <b>{r.k_md * (1 + qb['q05']):.0f}–"
          f"{r.k_md * (1 + qb['q95']):.0f}</b> md over the rate's 90% range" if qb and np.isfinite(r.k_md) else None)


def fmt(v, spec, unit=""):
    return f"{v:{spec}}{unit}" if np.isfinite(v) else "n/a"


UI.kpis([
    {"label": "Horner slope m", "value": fmt(r.m_psi_cycle, ".2f"), "unit": "psi/cycle", "tone": "blue",
     "sub": "pressure rise per log cycle of time in radial flow"},
    {"label": "Permeability k", "value": fmt(r.k_md, ".1f"), "unit": "md", "tone": "oil",
     "sub": k_help or "k = 162.6 qBμ / (m h)"},
    {"label": "Skin s", "value": fmt(r.skin, ".2f"), "tone": "gas", "sub": "> 0 damaged, < 0 stimulated"},
    {"label": "Pressure drop due to skin", "value": fmt(r.dP_skin, ".1f"), "unit": "psi", "tone": "gas",
     "sub": "Δp skin = 0.87 · m · s"},
])
st.caption(f"p* {fmt(r.p_star_psia, ',.0f', ' psia')} at gauge depth · flow efficiency "
           f"{fmt(r.flow_efficiency, '.2f')} · Pwf at shut-in {fmt(r.pwf_psia, ',.0f', ' psia')} · "
           f"Horner fit R² {r.r2:.4f} · window {r.window_start_hr:.3g}–{r.window_end_hr:.3g} h")
if r.result_source == "model match":
    UI.note(f"<b>Result from the analytical model match.</b> The record is storage-dominated (the matched model "
            f"reaches radial flow at {r.t_iarf_model_hr:.3g} h, after the {r.duration_hr:.0f} h shut-in), so no "
            f"Horner line is valid. k and skin come from fitting the storage + skin model to the whole build-up: "
            f"k 80% range {r.k_match_p10_md:,.0f}–{r.k_match_p90_md:,.0f} md, storage C "
            f"{r.storage_bbl_psi:.3f} bbl/psi, misfit {100 * r.match_nrmse:.1f}% of the pressure rise.", "warn")
elif np.isfinite(r.k_match_md):
    agree = abs(r.k_match_md / r.k_md - 1) <= 0.3 if np.isfinite(r.k_md) else False
    UI.note(f"<b>Cross-check, analytical model match:</b> k {r.k_match_md:,.0f} md "
            f"(80% range {r.k_match_p10_md:,.0f}–{r.k_match_p90_md:,.0f}), skin {r.skin_match:.2f}, "
            f"storage C {r.storage_bbl_psi:.3f} bbl/psi, misfit {100 * r.match_nrmse:.1f}% of the pressure rise; "
            f"radial flow from {r.t_iarf_model_hr:.3g} h. "
            + ("Agrees with the Horner result." if agree else "Differs from the Horner result; see the flags."),
            "good" if agree else "warn")
st.page_link("views/pta_plots.py", label="Diagnostic plots and the radial-flow window", icon=":material/arrow_forward:")

# ---------------------------------------------------------------- interpretation and inputs
left, right = st.columns([1, 1], gap="large")
with left:
    UI.section("Interpretation")
    for kind, text in UI.interpret(r, ws.static):
        UI.note(text, kind)
    with st.container(border=True):
        st.markdown("**p\\* at datum depth**")
        dz = float(props.datum_tvd_ft - props.gauge_tvd_ft)
        g0 = float(props.get("fluid_gradient_psi_ft", np.nan))
        grad = st.number_input(f"Live-oil gradient between gauge and datum ({dz:,.0f} ft below the gauge), psi/ft",
                               min_value=0.20, max_value=0.55, value=round(g0, 3) if np.isfinite(g0) else None,
                               step=0.005, format="%.3f", placeholder="not set",
                               help="Pre-filled from the well tests' oil gravity and gas gravity with Rs and Bo from the "
                                    "PVT table: ρ = (62.4·γo + 0.0136·Rs·γg)/Bo, gradient = ρ/144. Override it with a "
                                    "gradient survey if you have one.")
        if grad:
            st.markdown(f"p\\* = {r.p_star_psia:,.0f} + {grad:.3f} × {dz:,.0f} = **{r.p_star_psia + grad * dz:,.0f} psia** "
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
