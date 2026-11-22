import streamlit as st

from wellperf import ui as UI

ws = UI.ws()
UI.header("All build-ups", "Automatic interpretation of every shut-in. This is what the PTA export contains.")
if ws.pta.empty:
    UI.note("No shut-ins of 1 hour or longer were found in this data.", "info")
    st.stop()

show = ["well_name", "t_shut", "duration_hr", "q_stbd", "m_psi_cycle", "k_md", "skin", "dP_skin", "p_star_psia",
        "p_star_datum_psia", "k_match_md", "skin_match", "result_source", "r2", "flags"]
t = ws.pta[[c for c in show if c in ws.pta]].copy()
t["flags"] = t["flags"].replace("", None)
UI.table(t, key_col="well_name",
         labels={"well_name": "Well", "t_shut": "Shut in", "duration_hr": "Hours", "q_stbd": "q, STB/d",
                 "m_psi_cycle": "m, psi/cycle", "k_md": "k, md", "skin": "Skin", "dP_skin": "Δp skin, psi",
                 "p_star_psia": "p* gauge, psia", "p_star_datum_psia": "p* datum, psia",
                 "k_match_md": "k match, md", "skin_match": "Skin match", "result_source": "Source",
                 "r2": "R²", "flags": "Flags"},
         formats={"duration_hr": "{:.1f}", "q_stbd": "{:,.0f}", "m_psi_cycle": "{:.2f}", "k_md": "{:.1f}",
                  "skin": "{:.2f}", "dP_skin": "{:.1f}", "p_star_psia": "{:,.0f}", "p_star_datum_psia": "{:,.0f}",
                  "k_match_md": "{:.1f}", "skin_match": "{:.2f}", "r2": "{:.4f}"})
UI.howto("<b>Source</b>: Horner line in the radial-flow window, or the analytical model match when the shut-in never "
         "reaches radial flow. <b>Flags</b> name what limits the confidence in a row (short shut-in, poor line fit, "
         "disagreement with the model match). Pick a row's event on the Results page to see the details.")
