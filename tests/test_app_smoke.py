"""Smoke test: every page of the Streamlit app runs on the bundled data without exceptions."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from wellperf import pipeline as _PL

needs_data = pytest.mark.skipif(not _PL.training_data_available(), reason="needs the training data in data/raw")
APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
PAGES = ["views/overview.py", "views/data_quality.py", "views/production.py", "views/buildups.py",
         "views/method.py", "views/export.py"]


def _ok(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


@needs_data
def test_all_pages_and_wells():
    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    _ok(at)
    options = list(at.selectbox(key="well").options)
    ws = at.session_state["_ws"]
    no_buildup = [w for w in options if not (len(ws.pta) and (ws.pta.well_name == w).any())]
    wells = list(dict.fromkeys(options[:1] + no_buildup[:1] + options[-1:]))   # first, one without a build-up, last
    for well in wells:
        at.selectbox(key="well").set_value(well).run()
        for page in PAGES:
            at.switch_page(page).run()
            _ok(at)


@needs_data
def test_manual_window_override():
    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    at.switch_page("views/buildups.py").run()
    _ok(at)
    s = at.slider[0]
    lo, hi = s.value
    s.set_value((lo + 0.1, hi)).run()
    _ok(at)
    assert any("Manual window" in m.value for m in at.markdown)


def test_starts_without_training_data(monkeypatch):
    """On a machine with only the repository (model file, no data/raw) the app opens in upload mode."""
    from wellperf import pipeline as PL
    monkeypatch.setattr(PL, "training_data_available", lambda *a, **k: False)
    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    _ok(at)
    assert any("Upload raw well data" in m.value for m in at.markdown)


if __name__ == "__main__":
    test_all_pages_and_wells()
    test_manual_window_override()
    print("app smoke tests passed")
