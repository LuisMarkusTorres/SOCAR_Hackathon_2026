# Well Performance Studio: VFM × PTA

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
| Upload raw data | Sidebar → **Upload**: drop all CSV files at once; they are recognised by their columns |
| Visualise field measurements | **Data quality**: sensor plots with shut-ins shaded, corrections applied |
| Predict production rates with the trained VFM | **Production (VFM)**: daily rates with 90% ranges, rate calculator, inflow curve |
| Generate well-test plots | **Build-up tests (PTA)**: log-log derivative, Horner, MDH, event history |
| Estimate reservoir properties | **Build-up tests (PTA)**: m, k, skin, Δp skin, p*, flow efficiency |
| Interpret reservoir behaviour | **Build-up tests (PTA)**: written interpretation; reservoir-pressure cross-check on Production |
| Export results and reports, VFM and PTA | **Export**: result files (Excel/CSV), VFM report, PTA report, PTA plots (zip), model (.pkl) |

## Running the evaluation demo

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\streamlit run app\streamlit_app.py
```

The app loads the trained model from `models/vfm_model.pkl`; it does not retrain. In the sidebar choose **Upload** and drop
the test-data CSV files:

- **required**: per-minute sensor data (same columns as `high_freq_data.csv`)
- optional: choke events, well tests for the same period (the model is then scored against them on the Overview page and
  in the VFM report), reservoir/PVT and completion tables (override the training values well by well)

Without the training data in `data/raw` the app opens directly in upload mode.

## Reproducing everything from the training data

```powershell
# put the dataset CSVs in data\raw\  (never committed)
.venv\Scripts\python scripts\run_pipeline.py      # train, validate, write results\ and models\vfm_model.pkl
.venv\Scripts\python scripts\build_notebook.py    # rebuild and execute the notebook
.venv\Scripts\python -m pytest tests              # synthetic PTA check, upload path, app smoke tests
```

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
   - log-resampled build-up, Bourdet derivative, automatic radial-flow window (flattest derivative after wellbore storage)
   - Horner fit gives m, p* and p₁ₕᵣ, and from them `k = 162.6qBμ/(mh)`, skin and `Δp_skin = 0.87·m·s`
   - q = VFM daily oil rate of the last full day before shut-in; `tp = 24·Np/q`
5. **Interpretation**: damaged wells, flow efficiency, data and fit flags.

## Validation

| VFM, out-of-sample MAPE | Oil | Water | Gas |
|---|---|---|---|
| Last test carried forward (baseline) | 6.0% | 5.9% | 9.2% |
| **VFM, forward-chaining** (predict each test from earlier ones) | **3.5%** | **4.8%** | **5.9%** |
| **VFM, leave-one-test-out** | **2.5%** | **3.6%** | **5.6%** |

PTA engine on analytical build-ups with known answers: k within 2.3%, skin within 0.15 (`tests/test_pta_synthetic.py`).

## Repository layout

```
app/streamlit_app.py     UI entry point (sidebar, upload, navigation)
app/views/               one file per page
src/wellperf/            config · data (load+QC) · features · vfm · pta · interpret · plots (interactive)
                         static_plots (PNG) · pipeline · ui (page helpers) · synthetic (test fixtures)
scripts/                 run_pipeline.py (train + export) · build_notebook.py
notebooks/               executed workflow notebook
results/                 submission result files, reports, pta_plots/
models/                  vfm_model.pkl
tests/                   PTA verification, upload path, app smoke tests
docs/GUIDE.md            beginner guide to the problem, the theory and the method
```

`data/` and `*.zip` are git-ignored: the raw dataset is confidential.
