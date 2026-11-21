import streamlit as st

from wellperf import config as C
from wellperf import pipeline as PL
from wellperf import static_plots as SP
from wellperf import ui as UI

ws = UI.ws()
UI.header("Export", f"Files are built from the data currently loaded ({ws.source}) when you click download.")

vfm = PL.vfm_deliverable(ws.vfm_daily)
pta = PL.pta_deliverable(ws.pta)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def card(title, what, n, downloads, preview=None):
    """downloads: list of (label, data, file name, mime, primary)."""
    with st.container(border=True):
        a, b = st.columns([3, 1.3], vertical_alignment="center")
        a.markdown(f"**{title}**  \n{what}")
        a.caption(n)
        with b:
            for label, data, fname, mime, primary in downloads:
                st.download_button(label, data, fname, mime=mime, type="primary" if primary else "secondary",
                                   on_click="ignore", width="stretch", icon=":material/download:", key=f"dl_{fname}")
        if preview is not None and len(preview):
            with st.expander("Preview, first 50 rows"):
                UI.table(preview.head(50), max_height=360, key_col="well_name")


UI.section("Results")
card("Daily production rates (VFM)", "One row per well per day: oil and water in STB/d, gas in Mscf/d "
     "(excluding injected lift gas).", f"{len(vfm):,} rows",
     [("Excel", lambda: PL.to_excel_bytes({"predictions": vfm}), "vfm_daily_predictions.xlsx", XLSX, True),
      ("CSV", lambda: vfm.to_csv(index=False), "vfm_daily_predictions.csv", "text/csv", False)], vfm)
card("Build-up interpretation (PTA)", "One row per shut-in: Horner slope m, permeability k, skin and pressure drop "
     "due to skin.", f"{len(pta):,} row" + ("" if len(pta) == 1 else "s"),
     [("Excel", lambda: PL.to_excel_bytes({"pta_results": pta}), "pta_results.xlsx", XLSX, True),
      ("CSV", lambda: pta.to_csv(index=False), "pta_results.csv", "text/csv", False)], pta)

UI.section("Reports")
card("VFM report", "Daily rates with 90% ranges, validation against well tests, per-test errors and per-well "
     "model parameters" + (", plus the score on the uploaded well tests." if ws.test_eval is not None else "."),
     "Excel, one sheet each", [("Excel", lambda: PL.to_excel_bytes(PL.vfm_report_sheets(ws)), "vfm_report.xlsx",
                                XLSX, False)])
card("PTA report", "Results, every input used (rate, cumulative oil, tp, rock and fluid properties, analysis window), "
     "the written interpretation and the shut-in list.", "Excel, one sheet each",
     [("Excel", lambda: PL.to_excel_bytes(PL.pta_report_sheets(ws)), "pta_report.xlsx", XLSX, False)])
if ws.pta_objs:
    card("PTA plots", "Log-log diagnostic, Horner, semilog (MDH) and shut-in history for every build-up, plus one "
         "summary page per build-up with the results.", f"{len(ws.pta_objs) * 5} PNG images in a zip",
         [("Zip", lambda: SP.pta_plots_zip(ws.minute, ws.pta_objs), "pta_plots.zip", "application/zip", False)])

UI.section("Model")
if C.MODEL_FILE.exists():
    card("Trained flow-meter model", "The model this app uses: per-well parameters, error ranges, validation results "
         "and the reference tables it needs. Load it with wellperf.pipeline.load_bundle().",
         f"{len(ws.model.params)} wells · {C.MODEL_FILE.name}",
         [("Download .pkl", lambda: C.MODEL_FILE.read_bytes(), C.MODEL_FILE.name, "application/octet-stream", False)])
