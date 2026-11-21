"""Smoke test: every page of the Streamlit app runs on the bundled data without exceptions."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
PAGES = ["views/overview.py", "views/data_quality.py", "views/production.py", "views/buildups.py",
         "views/export.py"]


def _ok(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_all_pages_and_wells():
    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    _ok(at)
    for well in ["GL-01", "GL-03", "GL-04"]:          # GL-03 has no build-up: exercises the empty state
        at.selectbox(key="well").set_value(well).run()
        for page in PAGES:
            at.switch_page(page).run()
            _ok(at)


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
