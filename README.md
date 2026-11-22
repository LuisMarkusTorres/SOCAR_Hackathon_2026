# VFMonitor: VFM × PTA

SOCAR Hackathon 2026, *Intelligent Well Performance Analysis*. One application that takes raw well data through to daily
oil, water and gas rates (Virtual Flow Metering) and on to automated build-up interpretation (Pressure Transient Analysis).

## Deliverables

| Requested | Where |
|---|---|
| 1. Result files, Phase 1 (VFM) and Phase 2 (PTA), CSV or Excel | `results/vfm_daily_predictions.csv` / `.xlsx`, `results/pta_results.csv` / `.xlsx`; full reports in `results/vfm_report.xlsx` and `results/pta_report.xlsx` |
| 2. Trained model, `.pkl` | `models/vfm_model.pkl` (load with `wellperf.pipeline.load_bundle()`) |
| 3. Notebook with all cells run | `notebooks/well_performance_workflow.ipynb` |
| 4. Folder with the PTA plots | `results/pta_plots/`: for each build-up, a summary page plus log-log, Horner, semilog (MDH) and shut-in history |

Application requirements → app pages:

| Requirement | In the app |
|---|---|
| Upload raw data | Sidebar → **Upload**: drop all files at once (CSV, Excel, Parquet or a zip of them); tables are recognised by their columns |
| Visualise field measurements | **Data**: sensor plots with shut-ins shaded, corrections applied |
| Predict production rates with the trained VFM | **Production · VFM** (Daily rates, Rate calculator, Reservoir pressure): daily rates with 90% ranges, rate calculator with inflow curve; optional recalibration on uploaded tests |
| Generate well-test plots | **Build-up · PTA › Diagnostic plots**: log-log derivative, Horner, MDH, event history |
| Estimate reservoir properties | **Build-up · PTA › Results**: m, k, skin, Δp skin, p* at gauge and datum depth, flow efficiency |
| Interpret reservoir behaviour | **Build-up · PTA › Results**: written interpretation; reservoir-pressure cross-check under Production · VFM |
| Export results and reports, VFM and PTA | **Export**: one zip with everything, or the result files (Excel/CSV), VFM report, PTA report, PTA plots (zip), model (.pkl) |
| (method and evidence for the jury) | **Method**: equations, validation vs baseline, parity plots, model comparison, synthetic PTA check |

## Running the evaluation demo

Python 3.10 or newer.

```powershell
# Windows
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\streamlit run app\streamlit_app.py
```

```bash
# Linux / macOS
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
.venv/bin/streamlit run app/streamlit_app.py
```

The app loads the trained model from `models/vfm_model.pkl`; it does not retrain. In the sidebar choose **Upload** and drop
the test-data files (CSV, Excel, Parquet, or a zip of them; column names are matched case-insensitively):

- **required**: per-minute sensor data (same columns as `high_freq_data.csv`)
- optional: choke events, well tests for the same period (the model is then scored against them on the Overview and
  Method pages and in the VFM report; a checkbox lets you recalibrate the flow meter on them afterwards), reservoir/PVT
  and completion tables (override the training values well by well)

Without the training data in `data/raw` the app opens directly in upload mode. Wells with no downhole pressure in the
upload are predicted from their last known pressure and flagged; a shut-in that starts on the first day of the data uses
the first full flowing day after it as its rate, and says so.

Paths can be redirected with `WELLPERF_DATA_DIR` (raw files) and `WELLPERF_WORK_DIR` (cache, results, model), which is how
the test suite runs on a second dataset.

## Reproducing everything from the training data

```powershell
# put the dataset CSVs in data\raw\  (never committed)
.venv\Scripts\python scripts\run_pipeline.py      # train, validate, benchmark, write results\ and models\vfm_model.pkl
.venv\Scripts\python scripts\build_notebook.py    # rebuild and execute the notebook
.venv\Scripts\python -m pytest tests              # PTA checks, upload readers, upload path, app smoke tests
```

Run these three again before the final upload: the pipeline now also stores the model-comparison table in the model
file (the Method page and the VFM report read it from there) and the notebook has two new sections (model comparison,
check against the reference PTA file when it is present in `data/raw`).

## Workflow

1. **Data QC**
   - Per-minute data: regularised to a 1-minute grid. Duplicates are averaged; the −999.25 sentinel and out-of-range values become missing; spikes are caught by a Hampel filter, frozen runs are removed, and short gaps are interpolated.
   - Well tests: repaired using their redundant columns (sign flips, gas reported in sm³/d).
   - Every correction is logged.
2. **Shut-in detection**: gas-lift injection stops (backed up by choke = 0 %).
3. **VFM**: physics-structured, calibrated per well on the tests. Undersaturated oil (Pwf ≫ Pb), so:
   - `q_liquid = J·(p_res(t) − Pwf)`, with p_res linear in time and J ridge-regularised
   - water cut follows a per-well trend
   - GOR is shrunk toward Rs(Pb)
   - daily volume = rate × on-stream fraction
4. **PTA** for each shut-in:
   - log-resampled build-up, Bourdet derivative, automatic radial-flow window: the flattest derivative stretch that lies
     after the storage hump has come down and not above the derivative seen later in the record
   - analytical storage + skin model matched to the whole build-up as a cross-check; when the record has no radial-flow
     plateau at all (short shut-in, large storage) the match supplies k and skin instead, flagged and with an 80% range.
     The data window is never moved by the model. `PTA_LEGACY_WINDOW = True` in `config.py` restores the original
     window picker exactly (the match then only comments); `PTA_MODEL_FALLBACK = False` disables the fallback.
   - Horner fit gives m, p* and p₁ₕᵣ, and from them `k = 162.6qBμ/(mh)`, skin and `Δp_skin = 0.87·m·s`
   - q = VFM daily oil rate of the last full day before shut-in; `tp = 24·Np/q`
5. **Interpretation**: damaged wells, flow efficiency, data and fit flags.

## Validation

| VFM, out-of-sample MAPE | Oil | Water | Gas |
|---|---|---|---|
| Last test carried forward (baseline) | 6.0% | 5.9% | 9.2% |
| **VFM, forward-chaining** (predict each test from earlier ones) | **3.5%** | **4.8%** | **5.9%** |
| **VFM, leave-one-test-out** | **2.5%** | **3.6%** | **5.6%** |

Candidates scored with the same forward-chaining backtest (`wellperf/candidates.py`; the table is produced by
`scripts/run_pipeline.py` and shown on the Method page): carrying the last test forward, a per-well time trend, a
pooled choke-flow (Gilbert-type) ridge regression, gradient-boosted trees on all sensor features, and the physics IPR
model. In the previous run the physics model won (oil 3.5% against 5.1% for gradient-boosted trees and 6.0% for the
baseline); the notebook has the current numbers.

PTA against the organisers' reference answers (`data/raw/pta_results.csv`, used only to check, never to fit): on the six
build-ups inside the training period, Horner slope within 1.2%, permeability within 3.6% and skin within 0.09 on average.
The remaining k difference is the oil rate (our VFM rate is 2.7% above the rate the reference implies), not the slope.
PTA engine on analytical build-ups with known answers: k within 2.3%, skin within 0.15 (`tests/test_pta_synthetic.py`);
on a 144-case grid of short and storage-heavy shut-ins the window rules cut the mean k error from 19.8% to 5.8% and left
no error above 20% unflagged.
p* is also reported at datum depth, using a live-oil gradient estimated from the tests' oil and gas gravity with Rs and Bo
from the PVT table (about 0.34 psi/ft); m, k, skin and Δp skin are differences and do not depend on it.

## Repository layout

```
app/streamlit_app.py     UI entry point (sidebar, upload, navigation)
app/views/               one file per page
app/static/fonts/        Geist and Geist Mono, served by Streamlit so the UI looks the same offline
src/wellperf/            config · data (load+QC) · features · vfm · candidates (benchmarks) · pta · interpret
                         plots (interactive) · static_plots (PNG) · pipeline · ui (page helpers) · synthetic (fixtures)
scripts/                 run_pipeline.py (train + export) · build_notebook.py
notebooks/               executed workflow notebook
results/                 submission result files, reports, pta_plots/
models/                  vfm_model.pkl
tests/                   PTA verification and edge cases, upload readers, upload path, app smoke tests
docs/GUIDE.md            beginner guide to the problem, the theory and the method
```

`data/` and `*.zip` are git-ignored: the raw dataset is confidential. Note that `models/vfm_model.pkl` and
`results/vfm_report.xlsx` contain the training well tests (the model needs them to score new tests and to recalibrate),
so keep the repository private to the team and the organisers.
