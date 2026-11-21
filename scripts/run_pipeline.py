"""Train on the data in data/raw, validate, and write the submission files.

    results/   vfm_daily_predictions.csv/.xlsx, pta_results.csv/.xlsx, vfm_report.xlsx, pta_report.xlsx, pta_plots/
    models/    vfm_model.pkl (the trained model the app loads)
"""
import sys
import time

import pandas as pd

from wellperf import pipeline, vfm

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)

t = time.time()
ws = pipeline.train()
print(f"trained in {time.time() - t:.1f}s")
print("\nVFM validation (forward-chaining):\n", vfm.score(ws.backtest_forward).round(2).to_string(index=False))
print("\nVFM validation (leave-one-test-out):\n", vfm.score(ws.backtest_loto).round(2).to_string(index=False))
print("\nPrediction bands:", ws.model.rel_err_q)
cols = ["event", "q_stbd", "tp_hr", "pwf_psia", "m_psi_cycle", "k_md", "skin", "dP_skin", "p_star_psia",
        "window_start_hr", "window_end_hr", "r2", "flags"]
print("\nPTA:\n", ws.pta[cols].round(3).to_string(index=False))
paths = pipeline.export_all(ws)
print("\nwritten:")
for k, v in paths.items():
    print(f"  {k:<11} {v}")
