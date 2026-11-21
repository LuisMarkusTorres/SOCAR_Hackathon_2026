"""Build and execute notebooks/well_performance_workflow.ipynb (all cells run, outputs saved).

    python scripts/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "well_performance_workflow.ipynb"

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# Well performance workflow: virtual flow metering and build-up analysis

SOCAR Hackathon 2026, *Intelligent Well Performance Analysis*.

1. **Data quality**: clean the per-minute sensor data and repair the well tests.
2. **Phase 1, VFM**: predict daily oil, water and gas for every well from the downhole pressure, calibrated on the periodic well tests.
3. **Phase 2, PTA**: find every shut-in and interpret the pressure build-up (Horner slope m, permeability k, skin, Δp skin), using the VFM oil rate.
4. **Export**: result files (CSV + Excel), reports, PTA plots and the trained model (`models/vfm_model.pkl`).
5. **Using the saved model on new data**: the path the application uses.

All code lives in the `wellperf` package (`src/wellperf`); this notebook runs it end to end. The tables show aggregated
results, not raw data rows."""),
    code("""import sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

from wellperf import config as C, pipeline as PL, vfm as V, static_plots as SP
from wellperf.interpret import interpret_text

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30); pd.set_option("display.precision", 3)
%matplotlib inline"""),
    md("## 1. Train on the training data and run the full workflow"),
    code("""import time
t = time.time()
ws = PL.train()
print(f"Workflow finished in {time.time() - t:.0f} s")
print(f"Wells: {ws.vfm_daily.well_name.nunique()} · well tests used for calibration: {len(ws.tests_feat)} · "
      f"well-days predicted: {len(ws.vfm_daily):,} · shut-ins interpreted: {len(ws.pta)}")"""),
    md("""### Data quality

Per-minute data are put on a regular 1-minute grid per well. Duplicates are averaged; the −999.25 missing-value code and
physically impossible values are removed; spikes are caught by a Hampel filter; frozen sensors are removed; gaps up to
10 minutes are interpolated. Minutes affected, per issue and well:"""),
    code("""rep = ws.hf_qc.set_index("well_name")
issue = rep[[c for c in rep.columns if "|" in c]].T
issue.index = pd.MultiIndex.from_tuples([tuple(i.split("|")) for i in issue.index], names=["signal", "issue"])
issue.groupby(level="issue").sum().T"""),
    md("Well tests carry redundant columns (oil, water, liquid, water cut, GOR, gas), so errors show up as inconsistencies. Corrections applied:"),
    code("""ws.test_issues.groupby(["issue", "column"]).size().rename("tests corrected").reset_index()"""),
    md("""## 2. Phase 1: virtual flow metering

The wells produce undersaturated oil (flowing bottom-hole pressure 2,300–3,700 psia, bubble point about 1,200–1,600 psia), so
per well:

* liquid rate $q_L = J\\,(\\bar p_r(t) - p_{wf})$ with reservoir pressure $\\bar p_r$ drifting linearly in time, $J$ ridge-regularised toward a pooled value;
* water cut follows a linear trend; GOR is the test mean shrunk toward the solution GOR $R_s(p_b)$;
* oil = $q_L(1-WC)$, water = $q_L\\,WC$, gas = oil × GOR (lift gas excluded); daily volume = rate × hours on stream.

**Validation.** Forward-chaining: every test is predicted from earlier tests only (as in deployment). Leave-one-test-out:
interpolation between tests. Baseline: carry the last well test forward."""),
    code("""print("Forward-chaining"); display(V.score(ws.backtest_forward).round(2))
print("Leave-one-test-out"); display(V.score(ws.backtest_loto).round(2))"""),
    code("""fig, axes = plt.subplots(1, 3, figsize=(14, 4.4))
for ax, (ph, label, col) in zip(axes, SP.PHASES):
    bt = ws.backtest_forward.dropna(subset=[ph + "_vfm"])
    lo, hi = bt[[ph, ph + "_vfm"]].min().min() * 0.9, bt[[ph, ph + "_vfm"]].max().max() * 1.05
    ax.plot([lo, hi], [lo, hi], ":", color=SP.MUTED)
    ax.scatter(bt[ph], bt[ph + "_vfm"], s=28, color=col, edgecolor="white", linewidth=0.8)
    mape = (abs(bt[ph + "_vfm"] - bt[ph]) / bt[ph]).mean() * 100
    ax.set(xlim=(lo, hi), ylim=(lo, hi), xlabel="measured (well test)", ylabel="VFM, out of sample",
           title=f"{label} · error {mape:.1f}%")
    ax.set_aspect("equal")
plt.tight_layout(); plt.show()"""),
    md("Prediction ranges (5th and 95th percentile of the out-of-sample relative errors) and per-well parameters:"),
    code("""display(pd.DataFrame(ws.model.rel_err_q).T.rename(columns={"q05": "low", "q95": "high"}))
pd.DataFrame([vars(p) for p in ws.model.params.values()])[
    ["well_name", "n_tests", "J", "J_source", "wc_c", "wc_d", "gor", "rs_pb"]].round(3)"""),
    md("Daily rates for each well (line, with the 90% range shaded) against the measured well tests (circles):"),
    code("""for w in sorted(ws.model.params):
    fig = SP.rate_figure(ws.vfm_daily, ws.tests, w); plt.show()"""),
    code("""print("Phase 1 result: average daily volumes per well over the period")
PL.vfm_deliverable(ws.vfm_daily).groupby("well_name")[["oil_rate_stbd", "water_rate_stbd", "gas_rate_mscfd"]].mean().round(1)"""),
    md("""## 3. Phase 2: build-up analysis

Shut-ins are found where gas-lift injection stops (or the choke closes) for at least an hour. For each build-up:
log-resampled pressure → Bourdet derivative on equivalent time → radial-flow window = flattest derivative stretch after
wellbore storage → Horner fit gives m, p* and p1hr, and from them

$k = 162.6\\,qB\\mu/(mh)$, $\\;s = 1.151[(p_{1hr}-p_{wf})/m - \\log(k/(\\phi\\mu c_t r_w^2)) + 3.23]$, $\\;\\Delta p_{skin} = 0.87\\,m\\,s$.

q is the VFM oil rate of the last full day before the shut-in; $t_p = 24 N_p/q$."""),
    code("""PL.pta_deliverable(ws.pta)"""),
    code("""ws.pta[["event", "q_stbd", "tp_hr", "p_star_psia", "flow_efficiency", "window_start_hr", "window_end_hr", "r2", "flags"]]"""),
    md("Diagnostic plots and interpretation for every build-up:"),
    code("""for key, r in ws.pta_objs.items():
    fig = SP.event_figure(ws.minute, r); plt.show()
    print(interpret_text(r, ws.static), "\\n")"""),
    md("""**Check of the PTA engine on synthetic build-ups with known answers** (analytical wellbore-storage + skin solution,
Stehfest inversion, 0.3 psi gauge noise). Permeability is recovered within a few percent and skin within about 0.2:"""),
    code("""sys.path.insert(0, str(C.ROOT / "tests"))
from test_pta_synthetic import run_case, CASES     # same cases as the automated test
rows = []
for k_true, s_true, c_storage in CASES:
    r = run_case(k_true, s_true, c_storage)
    rows.append({"true k (md)": k_true, "recovered k": round(r.k_md, 1), "k error %": round(100 * (r.k_md / k_true - 1), 1),
                 "true skin": s_true, "recovered skin": round(r.skin, 2)})
pd.DataFrame(rows)"""),
    md("## 4. Export the submission files"),
    code("""paths = PL.export_all(ws)
for k, v in paths.items():
    print(f"{k:<11} {Path(v).relative_to(C.ROOT)}")"""),
    md("""## 5. Using the saved model on new data

The application loads `models/vfm_model.pkl` and runs it on uploaded raw files without retraining. Here the last six
weeks of sensor data stand in for new data. **These well tests were part of the training set**, so the score below only
shows that the mechanics work; the honest accuracy estimate is the forward-chaining validation in section 2. With the
evaluation data, the same call scores the model on genuinely unseen tests."""),
    code("""bundle = PL.load_bundle()
base = PL.workspace_from_bundle(bundle)              # model + reference tables only, no sensor data
raw = PL.D.load_hf_raw()
new_hf = raw[raw.timestamp >= raw.timestamp.max() - pd.Timedelta(days=42)]
new_tests = PL.D.load_tests_raw(); new_tests = new_tests[new_tests.test_start >= new_hf.timestamp.min()]
new = PL.apply_to_new_hf(base, new_hf, tests_file=new_tests)
print(f"{len(new.vfm_daily):,} well-days predicted, {len(new.pta)} shut-ins interpreted")
V.score(new.test_eval).round(2)"""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3",
                                                                "language": "python"}})
OUT.parent.mkdir(parents=True, exist_ok=True)
NotebookClient(nb, timeout=1800, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
nbf.write(nb, OUT)
print("written", OUT)
