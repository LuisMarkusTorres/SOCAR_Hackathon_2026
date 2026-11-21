"""The evaluation path: saved model (.pkl) + newly uploaded raw files, without retraining.

The 'new' data is simulated with the last six weeks of the training-period sensor data and its well tests.
"""
import pandas as pd
import pytest

from wellperf import config as C
from wellperf import data as D
from wellperf import pipeline as PL
from wellperf import vfm as V

pytestmark = pytest.mark.skipif(not (C.MODEL_FILE.exists() and PL.training_data_available()),
                                reason="needs models/vfm_model.pkl and data/raw")


def _slice():
    raw = D.load_hf_raw()
    t1 = raw.timestamp.max()
    hf = raw[raw.timestamp >= t1 - pd.Timedelta(days=42)]
    tests = D.load_tests_raw()
    tests = tests[tests.test_start >= hf.timestamp.min()]
    return hf, tests


def test_classify_upload():
    hf, tests = _slice()
    assert PL.classify_upload(hf.head()) == "sensors"
    assert PL.classify_upload(tests.head()) == "tests"
    assert PL.classify_upload(D.load_choke().head()) == "choke"
    assert PL.classify_upload(pd.read_csv(C.DATA_RAW / C.PVT_FILE)) == "pvt"
    assert PL.classify_upload(pd.read_csv(C.DATA_RAW / C.COMPLETION_FILE)) == "completion"
    assert PL.classify_upload(pd.DataFrame({"a": [1]})) is None


def test_bundle_plus_upload_runs_end_to_end():
    b = PL.load_bundle()
    base = PL.workspace_from_bundle(b)          # no sensor data at all: what the app has without data/raw
    hf, tests = _slice()
    ws = PL.apply_to_new_hf(base, hf, tests_file=tests)
    vfm = PL.vfm_deliverable(ws.vfm_daily)
    assert len(vfm) and vfm[C.VFM_OUTPUT_COLS[2:]].notna().all().all()
    assert set(vfm.well_name) == set(b["model"].params)
    assert ws.test_eval is not None and len(ws.test_eval) > 0
    sc = V.score(ws.test_eval).set_index("model")
    assert sc.loc["VFM", "oil MAPE %"] < 15
    # reports build without errors
    assert PL.to_excel_bytes(PL.vfm_report_sheets(ws))
    assert PL.to_excel_bytes(PL.pta_report_sheets(ws))
