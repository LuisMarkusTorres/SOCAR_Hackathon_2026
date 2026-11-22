import streamlit as st

from views import pta_common as PC
from wellperf import plots as PLT
from wellperf import ui as UI

ws = UI.ws()
well = UI.well()
if ws.pta.empty:
    UI.header("Diagnostic plots (PTA)")
    UI.note("No shut-ins of 1 hour or longer were found in this data, so there is nothing to plot.", "info")
    st.stop()

key, r0 = PC.current_event(ws, well)
UI.header("Diagnostic plots (PTA)", PC.subtitle(r0, well))
PC.event_pills(ws)
if r0 is None:
    PC.no_event_note(well)
    st.stop()
ev, props = PC.event_inputs(ws, r0)

with st.expander("Adjust the radial-flow window", expanded=False):
    PC.window_slider(key, r0)
r, manual = PC.result(ws, key, r0, ev, props)
if manual:
    PC.manual_note(r, r0)

g1, g2 = st.columns(2, gap="medium")
with g1:
    st.plotly_chart(PLT.loglog_plot(r), width="stretch")
    UI.howto("<b>Start here.</b> Blue is the pressure rise since shut-in; orange is its derivative. The early hump "
             "is <b>wellbore storage</b> (fluid still entering the well), which says nothing about the rock. A "
             "<b>flat orange stretch</b> is radial flow in the reservoir: its height gives k. The shaded band is "
             "the window used for every result. The thin grey curves are the matched storage + skin "
             "model, a cross-check that uses the whole build-up including the early time.")
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
st.page_link("views/buildups.py", label="Results and interpretation", icon=":material/arrow_forward:")
