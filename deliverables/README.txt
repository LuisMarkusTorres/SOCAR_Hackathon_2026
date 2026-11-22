VFMonitor - SOCAR Hackathon 2026 - Intelligent Well Performance Analysis
Submission folder. The same files are written by scripts/run_pipeline.py to results/, models/ and notebooks/.

1. Result files
   vfm_daily_predictions.csv / .xlsx   Phase 1 (VFM): date, well_name, oil_rate_stbd, water_rate_stbd, gas_rate_mscfd
                                       one row per well per day, 10 wells x 273 days (1 Jan - 30 Sep 2025)
   pta_results.csv / .xlsx             Phase 2 (PTA): well_name, t_shut, duration_hr, m_psi_cycle, k_md, skin, dP_skin
                                       one row per shut-in (6 build-ups)
   vfm_report.xlsx, pta_report.xlsx    full reports: 90% ranges, validation, model comparison, every PTA input,
                                       p* at gauge and datum depth, model-match cross-check, flags, interpretation
2. model/vfm_model.pkl                 trained flow-meter model (load with wellperf.pipeline.load_bundle())
3. notebook/well_performance_workflow.ipynb   all cells executed, outputs included
4. pta_plots/                          per build-up: log-log diagnostic, Horner, semilog (MDH), shut-in history,
                                       and a one-page summary (30 PNG files)
5. VFMonitor_App_Guide.pdf             user guide for the application (every page, chart and export explained)

Run the app:  pip install -r requirements.txt && pip install -e . && streamlit run app/streamlit_app.py
