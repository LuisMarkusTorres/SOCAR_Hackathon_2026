"""Upload readers: CSV, Excel and zip files are recognised by their columns and their dates parsed. No dataset needed."""
import io
import zipfile

import pandas as pd

from wellperf import pipeline as PL


def _sensors(n=5):
    return pd.DataFrame({"timestamp": pd.date_range("2025-10-01", periods=n, freq="min"), "well_name": "W-1",
                         "whp_psia": 300.0, "whp_downstream_psia": 180.0, "dh_pressure_psia": 3000.0,
                         "dh_temperature_degf": 200.0, "annulus_pressure_psia": 1100.0, "gas_lift_rate_mscfd": 800.0})


def _tests():
    return pd.DataFrame({"well_name": ["W-1"], "test_start": ["2025-10-02 08:00"], "test_end": ["2025-10-03 08:00"],
                         "oil_rate_stbd": [900.0]})


def test_csv_excel_and_zip_are_recognised():
    s = _sensors().copy()
    s.columns = [c.upper() for c in s.columns]                       # column names are normalised
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("export/Sensors Oct.csv", s.to_csv(index=False))
        z.writestr("__MACOSX/._Sensors.csv", b"junk")
        z.writestr("notes.txt", "not a table")
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf) as xw:
        _tests().to_excel(xw, sheet_name="tests", index=False)
        pd.DataFrame({"a": [1]}).to_excel(xw, sheet_name="other", index=False)
    choke = pd.DataFrame({"timestamp": ["2025-10-01 00:00"], "well_name": ["W-1"], "choke_opening_pct": [40.0]})
    found, notes = PL.read_uploads([("data.zip", zbuf.getvalue()), ("tests.xlsx", xbuf.getvalue()),
                                    ("choke.csv", choke.to_csv(index=False).encode())])
    assert set(found) == {"sensors", "tests", "choke"}
    assert pd.api.types.is_datetime64_any_dtype(found["sensors"]["timestamp"])
    assert pd.api.types.is_datetime64_any_dtype(found["tests"]["test_end"])
    assert "timestamp" in found["sensors"].columns                   # lower-cased
    assert len(notes) == 2                                           # notes.txt and the 'other' sheet were skipped


def test_unreadable_file_is_reported_not_raised():
    found, notes = PL.read_uploads([("broken.xlsx", b"\x00\x01not an excel file")])
    assert not found and notes and "broken.xlsx" in notes[0]
