"""End-to-end workflow: data -> QC -> VFM (train/validate/predict) -> shut-in detection -> PTA -> exports.

Two ways in:
  * train()  : fit on the training data in data/raw, validate, and save the model bundle (models/vfm_model.pkl)
  * load_bundle() + build()/apply_to_new_hf() : use the saved model, no retraining (what the app does)
"""
from __future__ import annotations

import io
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config as C
from . import data as D
from . import features as F
from . import pta as P
from . import vfm as V
from .interpret import interpret_text

TEST_KEEP = ["well_name", "test_start", "test_end", "test_mid", "oil_rate_stbd", "water_rate_stbd",
             "gas_rate_mscfd", "liquid_rate_stbd", "water_cut_pct", "gor_scf_stb"]
BUNDLE_VERSION = 1


@dataclass
class Workspace:
    static: pd.DataFrame
    tests: pd.DataFrame
    test_issues: pd.DataFrame
    hf_qc: pd.DataFrame
    minute: pd.DataFrame
    daily: pd.DataFrame
    tests_feat: pd.DataFrame
    events: pd.DataFrame
    model: V.VFMModel
    backtest_forward: pd.DataFrame
    backtest_loto: pd.DataFrame
    vfm_daily: pd.DataFrame
    pta: pd.DataFrame
    pta_objs: dict = field(default_factory=dict)
    test_eval: pd.DataFrame | None = None      # trained model scored on well tests uploaded with new data
    source: str = "training data"


# --------------------------------------------------------------------------- model bundle (.pkl)
def save_bundle(ws: Workspace, path: Path | None = None) -> Path:
    """Everything the app needs to run on new data without the training files."""
    path = Path(path or C.MODEL_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"version": BUNDLE_VERSION, "created": pd.Timestamp.now().isoformat(timespec="seconds"),
              "model": ws.model, "static": ws.static, "tests": ws.tests, "test_issues": ws.test_issues,
              "tests_feat": ws.tests_feat, "backtest_forward": ws.backtest_forward,
              "backtest_loto": ws.backtest_loto, "history_daily": ws.vfm_daily}
    with open(path, "wb") as f:
        pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
    return path


def load_bundle(path: Path | None = None) -> dict:
    with open(Path(path or C.MODEL_FILE), "rb") as f:
        b = pickle.load(f)
    if b.get("version") != BUNDLE_VERSION:
        raise ValueError(f"Model file version {b.get('version')} is not supported (expected {BUNDLE_VERSION}).")
    return b


def workspace_from_bundle(b: dict) -> Workspace:
    """A workspace with the trained model and history but no sensor data: the starting point for uploads."""
    empty = pd.DataFrame()
    return Workspace(b["static"], b["tests"], b["test_issues"], empty, empty, empty, b["tests_feat"], empty,
                     b["model"], b["backtest_forward"], b["backtest_loto"], b["history_daily"], empty,
                     source="trained model only")


def training_data_available(data_dir: Path | None = None) -> bool:
    d = Path(data_dir or C.DATA_RAW)
    return all((d / f).exists() for f in (C.HF_FILE, C.TESTS_FILE, C.PVT_FILE, C.COMPLETION_FILE))


# --------------------------------------------------------------------------- build
def train_vfm(tests_feat: pd.DataFrame, static: pd.DataFrame):
    bt_f = V.backtest(tests_feat, static, "forward")
    bt_l = V.backtest(tests_feat, static, "loto")
    model = V.VFMModel().fit(tests_feat, static)
    model.rel_err_q = V.relative_error_quantiles(bt_f)
    model.meta = {"n_tests": int(len(tests_feat)), "wells": sorted(tests_feat.well_name.unique()),
                  "train_period": [str(tests_feat.test_start.min()), str(tests_feat.test_end.max())],
                  "score_forward": V.score(bt_f).round(3).to_dict("records"),
                  "score_loto": V.score(bt_l).round(3).to_dict("records")}
    return model, bt_f, bt_l


def build(data_dir: Path | None = None, hf_path: Path | None = None, use_cache: bool = True,
          bundle: dict | None = None) -> Workspace:
    """Full workflow on the training dataset. With a bundle, the saved model is used instead of retraining."""
    static = D.load_static(data_dir)
    tests, test_issues = D.clean_tests(D.load_tests_raw(data_dir))
    minute, hf_qc = D.load_clean_hf(hf_path, data_dir, use_cache)
    minute = F.add_flow_state(minute)
    daily = F.daily_features(minute, static)
    win = F.window_features(minute, tests, static)
    tests_feat = tests[TEST_KEEP].merge(win, on=["well_name", "test_start"])
    if bundle is not None:
        model, bt_f, bt_l = bundle["model"], bundle["backtest_forward"], bundle["backtest_loto"]
    else:
        model, bt_f, bt_l = train_vfm(tests_feat, static)
    vfm_daily = model.predict_daily(daily)
    events = F.detect_shutins(minute)
    pta_df, pta_objs = P.run_all(minute, events, vfm_daily, static) if len(events) else (pd.DataFrame(), {})
    return Workspace(static, tests, test_issues, hf_qc, minute, daily, tests_feat, events, model, bt_f, bt_l,
                     vfm_daily, pta_df, pta_objs)


def train(data_dir: Path | None = None) -> Workspace:
    return build(data_dir)


UPLOAD_KINDS = {"sensors": "Per-minute sensor data", "choke": "Choke events", "tests": "Well tests",
                "pvt": "Reservoir / PVT properties", "completion": "Well completion"}


def classify_upload(df: pd.DataFrame) -> str | None:
    """Recognise an uploaded CSV by its columns, so users can drop all files at once under any name."""
    cols = set(df.columns)
    if {"timestamp", "well_name", "dh_pressure_psia"} <= cols:
        return "sensors"
    if {"timestamp", "well_name", "choke_opening_pct"} <= cols:
        return "choke"
    if {"well_name", "test_start", "test_end", "oil_rate_stbd"} <= cols:
        return "tests"
    if {"well_name", "porosity_frac", "net_pay_thickness_ft"} <= cols:
        return "pvt"
    if {"well_name", "gauge_tvd_ft"} <= cols:
        return "completion"
    return None


def _read(f, **kw) -> pd.DataFrame:
    return f if isinstance(f, pd.DataFrame) else pd.read_csv(f, **kw)


def _override_static(static: pd.DataFrame, pvt_file=None, completion_file=None) -> pd.DataFrame:
    s = static.copy()
    for f, dates in [(pvt_file, None), (completion_file, ["first_production_date"])]:
        if f is not None:
            s = _read(f, parse_dates=dates).set_index("well_name").combine_first(s)
    return s


def apply_to_new_hf(ws: Workspace, hf_file, choke_file=None, tests_file=None, pvt_file=None,
                    completion_file=None) -> Workspace:
    """Run the trained VFM + PTA on newly uploaded raw data (e.g. the evaluation period).

    hf_file is required. Optional: choke events, well tests for the same period (to score the model),
    and updated PVT / completion tables (override the training values well by well).
    """
    raw = _read(hf_file, parse_dates=["timestamp"])
    missing = [c for c in ["timestamp", "well_name"] + C.SENSOR_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"The sensor file is missing required columns: {missing}")
    static = _override_static(ws.static, pvt_file, completion_file)
    minute, hf_qc = D.clean_hf(raw)
    choke = _read(choke_file, parse_dates=["timestamp"]) if choke_file is not None else (
        D.load_choke() if (C.DATA_RAW / C.CHOKE_FILE).exists() else None)
    minute = F.add_flow_state(D.add_choke(minute, choke, static))
    daily = F.daily_features(minute, static)
    vfm_daily = ws.model.predict_daily(daily)
    t0, t1 = minute.timestamp.min(), minute.timestamp.max()

    # cumulative production for Horner tp: history (training period) + new period
    history = ws.vfm_daily[pd.to_datetime(ws.vfm_daily.date) < pd.to_datetime(vfm_daily.date).min()]
    combined = pd.concat([history, vfm_daily], ignore_index=True)
    events = F.detect_shutins(minute)
    pta_df, pta_objs = P.run_all(minute, events, combined, static) if len(events) else (pd.DataFrame(), {})

    tests = ws.tests[(ws.tests.test_mid >= t0) & (ws.tests.test_mid <= t1)]
    test_issues, test_eval = ws.test_issues.iloc[0:0], None
    if tests_file is not None:
        tests, test_issues = D.clean_tests(_read(tests_file, parse_dates=["test_start", "test_end"]))
        win = F.window_features(minute, tests, static)
        new_feat = tests[TEST_KEEP].merge(win, on=["well_name", "test_start"])
        test_eval = V.evaluate(ws.model, new_feat, ws.tests_feat)
    return Workspace(static, tests, test_issues, hf_qc, minute, daily, ws.tests_feat, events, ws.model,
                     ws.backtest_forward, ws.backtest_loto, vfm_daily, pta_df, pta_objs, test_eval,
                     source="uploaded data")


# --------------------------------------------------------------------------- deliverables
def vfm_deliverable(vfm_daily: pd.DataFrame) -> pd.DataFrame:
    out = vfm_daily[C.VFM_OUTPUT_COLS].copy()
    for c in C.VFM_OUTPUT_COLS[2:]:
        out[c] = out[c].round(2)
    return out


def pta_deliverable(pta_df: pd.DataFrame) -> pd.DataFrame:
    if pta_df.empty:
        return pd.DataFrame(columns=C.PTA_OUTPUT_COLS)
    out = pta_df[C.PTA_OUTPUT_COLS].copy()
    return out.round({"duration_hr": 2, "m_psi_cycle": 3, "k_md": 3, "skin": 3, "dP_skin": 3})


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
    return buf.getvalue()


def vfm_report_sheets(ws: Workspace) -> dict[str, pd.DataFrame]:
    sheets = {"Daily rates (90% range)": ws.vfm_daily,
              "Validation forward": V.score(ws.backtest_forward).round(3),
              "Validation leave-one-out": V.score(ws.backtest_loto).round(3),
              "Backtest per test": ws.backtest_forward,
              "Well parameters": pd.DataFrame([vars(p) for p in ws.model.params.values()])}
    if ws.test_eval is not None and len(ws.test_eval):
        sheets["Uploaded tests - score"] = V.score(ws.test_eval).round(3)
        sheets["Uploaded tests - per test"] = ws.test_eval
    return sheets


def pta_inputs(ws: Workspace) -> pd.DataFrame:
    rows = []
    for key, r in ws.pta_objs.items():
        s = ws.static.loc[r.well_name]
        rows.append({"event": key, "q_stbd": r.q_stbd, "q_from_date": r.data.get("q_date"), "Np_stb": r.np_stb,
                     "tp_hr": r.tp_hr, "pwf_psia": r.pwf_psia, "h_ft": s.net_pay_thickness_ft, "porosity": s.porosity_frac,
                     "mu_cp": s.oil_viscosity_cp, "Bo_rb_stb": s.oil_fvf_rb_stb, "ct_1_psi": s.total_compressibility_1_psi,
                     "rw_ft": s.wellbore_radius_ft, "window_start_hr": r.window_start_hr, "window_end_hr": r.window_end_hr})
    return pd.DataFrame(rows)


def pta_report_sheets(ws: Workspace) -> dict[str, pd.DataFrame]:
    interp = pd.DataFrame([{"event": k, "interpretation": interpret_text(r, ws.static)} for k, r in ws.pta_objs.items()])
    return {"Results": pta_deliverable(ws.pta), "Results (full)": ws.pta, "Inputs": pta_inputs(ws),
            "Interpretation": interp, "Shut-in events": ws.events}


def report_sheets(ws: Workspace) -> dict[str, pd.DataFrame]:
    return {**{f"VFM {k}"[:31]: v for k, v in vfm_report_sheets(ws).items()},
            **{f"PTA {k}"[:31]: v for k, v in pta_report_sheets(ws).items()},
            "Well-test corrections": ws.test_issues, "Sensor QC": ws.hf_qc}


def export_all(ws: Workspace, out_dir: Path | None = None, model_path: Path | None = None,
               save_model: bool = True) -> dict[str, Path]:
    """Write the submission: result files (CSV + Excel), reports, PTA plots, and the trained model (.pkl)."""
    from . import static_plots as SP

    out_dir = Path(out_dir or C.RESULTS)
    out_dir.mkdir(parents=True, exist_ok=True)
    vfm, pta = vfm_deliverable(ws.vfm_daily), pta_deliverable(ws.pta)
    paths = {"vfm_csv": out_dir / "vfm_daily_predictions.csv", "vfm_xlsx": out_dir / "vfm_daily_predictions.xlsx",
             "pta_csv": out_dir / "pta_results.csv", "pta_xlsx": out_dir / "pta_results.xlsx",
             "vfm_report": out_dir / "vfm_report.xlsx", "pta_report": out_dir / "pta_report.xlsx"}
    vfm.to_csv(paths["vfm_csv"], index=False)
    paths["vfm_xlsx"].write_bytes(to_excel_bytes({"predictions": vfm}))
    pta.to_csv(paths["pta_csv"], index=False)
    paths["pta_xlsx"].write_bytes(to_excel_bytes({"pta_results": pta}))
    paths["vfm_report"].write_bytes(to_excel_bytes(vfm_report_sheets(ws)))
    paths["pta_report"].write_bytes(to_excel_bytes(pta_report_sheets(ws)))
    paths["pta_plots"] = out_dir / "pta_plots"
    SP.save_pta_plots(ws.minute, ws.pta_objs, paths["pta_plots"])
    if save_model:
        paths["model"] = save_bundle(ws, model_path)
    return paths
