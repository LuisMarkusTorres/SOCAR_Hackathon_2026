"""Shared by the three build-up pages: the shut-in picker (kept in step with the sidebar well), the radial-flow window
and the recomputation when the window has been moved by hand on the Diagnostic plots page."""
import numpy as np
import streamlit as st

from wellperf import pta as P
from wellperf import ui as UI


def current_event(ws, well):
    """(key, automatic result) for the selected shut-in, or (None, None) when the active well has none."""
    evs = list(ws.pta_objs)
    mine = [k for k in evs if UI.event_well(k) == well]
    cur = st.session_state.get("bu_event")
    if cur not in evs or UI.event_well(cur) != well:
        st.session_state["bu_event"] = mine[0] if mine else None
    key = st.session_state.get("bu_event")
    return key, (ws.pta_objs[key] if key else None)


def subtitle(r0, well) -> str:
    return (f"{r0.well_name} · shut in {r0.t_shut:%d %b %Y, %H:%M} for {r0.duration_hr:.0f} h · "
            f"rate before shut-in {r0.q_stbd:,.0f} STB/d (flow meter)" if r0 is not None
            else f"{well} was not shut in during this period")


def _sync_well():
    k = st.session_state.get("bu_event")
    if k:
        UI.set_well(UI.event_well(k))


def event_pills(ws) -> None:
    st.pills(":red[Shut-in events]", list(ws.pta_objs), key="bu_event", format_func=lambda k: UI.event_label(k, ws),
             on_change=_sync_well, help="Choosing an event also makes its well the active well")


def no_event_note(well) -> None:
    UI.note(f"{well} has no shut-in of 1 hour or longer, so there is no build-up to interpret. "
            f"Pick one of the events above.", "info")


def event_inputs(ws, r0):
    ev = ws.events[(ws.events.well_name == r0.well_name) & (ws.events.t_shut == r0.t_shut)].iloc[0]
    return ev, ws.static.loc[r0.well_name]


def _auto(r0):
    return float(np.log10(r0.window_start_hr)), float(np.log10(r0.window_end_hr))


def window(key, r0):
    """(lo, hi) in log10 hours and whether it differs from the automatic pick. The hand-set value survives page
    changes because the slider copies it into a plain session key."""
    auto = _auto(r0)
    lo, hi = st.session_state.get(f"winv_{key}", auto)
    return lo, hi, abs(lo - auto[0]) > 1e-6 or abs(hi - auto[1]) > 1e-6


def window_slider(key, r0) -> None:
    dtmin, dtmax = float(r0.data["dt"].min()), float(r0.data["dt"].max())
    auto = _auto(r0)
    skey, pkey = f"win_{key}", f"winv_{key}"

    def _reset():
        st.session_state[skey] = auto
        st.session_state[pkey] = auto

    def _keep():
        st.session_state[pkey] = st.session_state[skey]

    if skey not in st.session_state:
        st.session_state[skey] = st.session_state.get(pkey, auto)
    lo, hi = st.slider("Window, log₁₀ of shut-in time in hours", float(np.log10(dtmin)), float(np.log10(dtmax)),
                       step=0.05, key=skey, on_change=_keep)
    st.session_state[pkey] = (lo, hi)
    _, _, manual = window(key, r0)
    a, b = st.columns([3, 1])
    a.caption(f"Using {10 ** lo:.3g} h to {10 ** hi:.3g} h. Automatic choice: {r0.window_start_hr:.3g}–"
              f"{r0.window_end_hr:.3g} h, the flattest stretch of the derivative after wellbore storage, at least half a "
              f"log cycle long.")
    b.button("Reset to automatic", on_click=_reset, disabled=not manual, width="stretch")


def result(ws, key, r0, ev, props):
    """The interpretation for the current window: the automatic one, or recomputed for a hand-set window."""
    lo, hi, manual = window(key, r0)
    if not manual:
        return r0, False
    r = P.interpret_buildup(ws.minute, ev, r0.q_stbd, r0.np_stb, props, window=(10 ** lo, 10 ** hi))
    r.data["q_date"] = r0.data.get("q_date")
    return r, True


def manual_note(r, r0, where: str | None = None) -> None:
    UI.note(f"Manual window ({r.window_start_hr:.3g}–{r.window_end_hr:.3g} h). These numbers differ from the automatic "
            f"result in the export (k {r0.k_md:.1f} md, skin {r0.skin:.2f})." + (f" {where}" if where else ""), "warn")
