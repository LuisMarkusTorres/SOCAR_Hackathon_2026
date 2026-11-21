"""Well Performance Studio: virtual flow metering and automated build-up analysis in one workflow.

Run from the project root:  streamlit run app/streamlit_app.py
The trained model is loaded from models/vfm_model.pkl (created by scripts/run_pipeline.py).
"""
from __future__ import annotations


import pandas as pd
import streamlit as st

from wellperf import config as C
from wellperf import pipeline as PL
from wellperf import ui as UI

st.set_page_config(page_title="Well Performance Studio", page_icon=":material/oil_barrel:", layout="wide")
UI.apply_css()


@st.cache_resource(show_spinner="Loading the trained model…")
def load_model() -> dict | None:
    return PL.load_bundle() if C.MODEL_FILE.exists() else None


@st.cache_resource(show_spinner="Running the trained model on the training-period data…")
def training_workspace(_bundle: dict | None) -> PL.Workspace:
    return PL.build(bundle=_bundle)           # trains from scratch only if no model file exists


@st.cache_resource(show_spinner="Reading the uploaded files…")
def read_uploads(files: tuple) -> tuple[dict, list]:
    return PL.read_uploads(list(files))


@st.cache_resource(show_spinner="Cleaning the uploaded data and running the flow meter and build-up analysis…")
def uploaded_workspace(files: tuple, recalibrate: bool, _base: PL.Workspace) -> PL.Workspace:
    kinds, _ = read_uploads(files)
    return PL.apply_to_new_hf(_base, kinds["sensors"], kinds.get("choke"), kinds.get("tests"), kinds.get("pvt"),
                              kinds.get("completion"), recalibrate=recalibrate)


bundle = load_model()
has_training = PL.training_data_available()
if bundle is None and not has_training:
    st.error("No trained model found (models/vfm_model.pkl) and no training data in data/raw. "
             "Run `python scripts/run_pipeline.py` once to create the model.")
    st.stop()
base = training_workspace(bundle) if has_training else PL.workspace_from_bundle(bundle)
ws = base if has_training else None

with st.sidebar:
    st.markdown("<div class='brand'>Well Performance Studio</div>"
                "<div class='brand-sub'>Virtual flow metering · build-up analysis</div>", unsafe_allow_html=True)

    st.markdown("<div class='side-label'>Data</div>", unsafe_allow_html=True)
    options = (["Training period", "Upload"] if has_training else ["Upload"])
    source = st.segmented_control("Data source", options, default=options[0], required=True, key="source",
                                  label_visibility="collapsed")
    if source == "Upload":
        ups = st.file_uploader("Raw well data", type=list(PL.UPLOAD_EXTENSIONS), accept_multiple_files=True,
                               help="Drop all files at once: CSV, Excel, Parquet, or a zip of them. Required: "
                                    "per-minute sensor data. Optional: choke events, well tests (to score the model), "
                                    "reservoir/PVT and completion tables. Tables are recognised by their columns.")
        found, notes = {}, []
        if ups:
            files = tuple((f.name, f.getvalue()) for f in ups)
            found, notes = read_uploads(files)
            if found:
                st.markdown("<div class='facts'>" + "<br>".join(
                    f"<span>{PL.UPLOAD_KINDS[k]}</span> {len(found[k]):,} rows" for k in PL.UPLOAD_KINDS if k in found)
                    + "</div>", unsafe_allow_html=True)
            for n in notes:
                st.caption(n)
        recal = False
        if "tests" in found:
            recal = st.checkbox("Recalibrate the flow meter with these well tests", value=False, key="recalibrate",
                                help="The uploaded tests are always scored first with the model as trained (out of "
                                     "sample). With this on, the model is then refitted on the training tests plus "
                                     "the uploaded ones before the daily rates are predicted.")
        if "sensors" in found:
            try:
                ws = uploaded_workspace(files, recal, base)
            except Exception as e:  # clear error state instead of a stack trace
                st.error(f"Could not process the upload: {e}")
                ws = None
        elif ups:
            st.warning("The per-minute sensor table is required (columns timestamp, well_name, dh_pressure_psia, …).")
        if ws is None and has_training:
            st.caption("Showing the training period until a sensor file is uploaded.")
            ws = base

    if ws is not None:
        d0, d1 = pd.to_datetime(ws.vfm_daily.date).min(), pd.to_datetime(ws.vfm_daily.date).max()
        st.caption(f"{ws.source.capitalize()}: {d0:%d %b} – {d1:%d %b %Y} · {ws.vfm_daily.well_name.nunique()} wells"
                   + (" · flow meter recalibrated" if ws.recalibrated else ""))

        st.markdown("<div class='side-label'>Well</div>", unsafe_allow_html=True)
        wells = sorted(ws.vfm_daily.well_name.unique())
        if st.session_state.get("well") not in wells:
            st.session_state["well"] = wells[0]
        well = st.selectbox("Well", wells, key="well", label_visibility="collapsed")

        p = ws.model.params.get(well)
        n_tests = int((ws.tests.well_name == well).sum()) if len(ws.tests) else 0
        bu = ws.pta[ws.pta.well_name == well] if len(ws.pta) else ws.pta
        last_test = pd.to_datetime(ws.tests.loc[ws.tests.well_name == well, "test_end"]).max() if n_tests else None
        facts = [f"<span>Production tests</span> {n_tests}" + (f" (last {last_test:%d %b})" if n_tests else ""),
                 "<span>Build-up tests</span> " + (", ".join(f"{t:%d %b}" for t in bu.t_shut) if len(bu)
                                                   else "none in period")]
        if p is None:
            facts.append("<span>Flow meter</span> not calibrated")
        st.markdown("<div class='facts'>" + "<br>".join(facts) + "</div>", unsafe_allow_html=True)

if ws is None:
    UI.header("Well Performance Studio", "Upload raw well data in the sidebar to start")
    UI.note("The trained flow-meter model is loaded. Drop the raw files (CSV, Excel or a zip) into the sidebar: the "
            "per-minute sensor table is required; choke events, well tests, reservoir/PVT and completion tables are "
            "optional.", "info")
    st.stop()

st.session_state["_ws"] = ws
pages = [
    st.Page("views/overview.py", title="Overview", default=True),
    st.Page("views/data_quality.py", title="Data quality"),
    st.Page("views/production.py", title="Production (VFM)"),
    st.Page("views/buildups.py", title="Build-up tests (PTA)"),
    st.Page("views/method.py", title="Method & validation"),
    st.Page("views/export.py", title="Export"),
]
st.navigation(pages, position="top").run()
