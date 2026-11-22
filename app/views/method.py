"""Method: what the two models are and the evidence that they work. Short on purpose; the details are in the README."""
import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
UI.header("Method", "How the flow meter and the build-up analysis work, and how they were checked")

if ws.candidates is not None and len(ws.candidates):
    UI.section("Models compared", "Blind test on the production well tests: each test predicted from earlier tests only. "
                                  "Lower is better. The inflow model below is the one the app uses.")
    cand = ws.candidates.copy()
    UI.table(cand, key_col="model", formats={c: "{:.1f}" for c in cand.columns if "MAPE" in c},
             labels={**{c: c.replace("MAPE", "error").capitalize() for c in cand.columns}, "model": "Model",
                     "n_tests": "Tests"})
    UI.howto("With under ten tests per well, the model that already knows the shape of inflow needs the least data "
             "and follows the reservoir-pressure decline. Trees flatten outside the training range.")

# ---------------------------------------------------------------- VFM
UI.section("Flow meter", "Inflow model per well, calibrated on its production well tests")
left, right = st.columns([1, 1], gap="large")
with left:
    st.latex(r"q_L = J\,\big(p_{res}(t) - p_{wf}\big)")
    st.markdown("""
- $p_{res}$ and water cut are straight lines in time; GOR is the solution GOR at bubble point.
- $J$ is pulled toward the field average when a well's tests do not pin it down.
- Daily volume = rate × hours on stream. The only live input is the downhole gauge.
- 90% band: 5th and 95th percentile of the blind errors below.
""")
with right:
    par = pd.DataFrame([vars(p) for p in ws.model.params.values()])
    par = par[["well_name", "n_tests", "J", "wc_c", "wc_d", "gor"]]
    UI.table(par, key_col="well_name", max_height=260,
             labels={"well_name": "Well", "n_tests": "Tests", "J": "J, STB/d/psi", "wc_c": "WC, %",
                     "wc_d": "WC trend, %/d", "gor": "GOR, scf/STB"},
             formats={"J": "{:.2f}", "wc_c": "{:.1f}", "wc_d": "{:+.3f}", "gor": "{:,.0f}"})

UI.section("Blind test against the well tests", "Each test predicted from earlier tests only. Baseline: last test carried forward.")
sf, sl = V.score(ws.backtest_forward).round(2), V.score(ws.backtest_loto).round(2)
sf.insert(1, "scheme", "forward-chaining"); sl.insert(1, "scheme", "leave-one-test-out")
val = pd.concat([sf, sl], ignore_index=True)
cols = ["model", "scheme", "n_tests", "oil MAPE %", "water MAPE %", "gas MAPE %", "oil bias %", "water bias %", "gas bias %"]
UI.table(val[cols], key_col="model", formats={c: "{:.1f}" for c in cols[3:]},
         labels={"model": "Model", "scheme": "Scheme", "n_tests": "Tests", "oil MAPE %": "Oil error %",
                 "water MAPE %": "Water error %", "gas MAPE %": "Gas error %", "oil bias %": "Oil bias %",
                 "water bias %": "Water bias %", "gas bias %": "Gas bias %"})
c = st.columns(3)
for col, ph in zip(c, V.PHASES):
    col.plotly_chart(PLT.parity_plot(ws.backtest_forward, ph), width="stretch")
UI.howto("Error = mean absolute error in %, bias = mean signed error in %. Leave-one-test-out hides one test and "
         "predicts it from all the others.")

if ws.test_eval is not None and len(ws.test_eval):
    UI.section("Uploaded well tests", "The model as trained, unchanged, against tests it had never seen")
    se = V.score(ws.test_eval).round(2)
    UI.table(se, key_col="model", formats={c: "{:.1f}" for c in se.columns if "%" in c or "MAE" in c})
    c = st.columns(3)
    for col, ph in zip(c, V.PHASES):
        col.plotly_chart(PLT.parity_plot(ws.test_eval, ph), width="stretch")

# ---------------------------------------------------------------- PTA
UI.section("Build-up analysis", "Horner method, radial-flow window picked from the Bourdet derivative")
left, right = st.columns([1, 1], gap="large")
with left:
    st.markdown("""
1. Shut-in found where gas-lift injection stops or the choke closes for 1 h or more.
2. Pressure resampled in log time; Bourdet derivative on Agarwal equivalent time.
3. Radial-flow window = flattest stretch of the derivative after wellbore storage, at least half a log cycle.
4. Straight line on the Horner plot gives $m$ and $p^*$.
5. A storage + skin analytical model is fitted to the whole build-up as a cross-check, and stands in when the shut-in is too short for radial flow.
""")
    st.latex(r"k = \frac{162.6\,q B \mu}{m h}")
    st.latex(r"s = 1.151\left[\frac{p_{1hr}-p_{wf}}{m} - \log\frac{k}{\phi \mu c_t r_w^2} + 3.23\right]")
    st.markdown("$q$ is the flow-meter oil rate on the last full day before the shut-in; $t_p = 24\\,N_p/q$. "
                "The window can be changed by hand on the Diagnostic plots page.")
with right:
    st.markdown("<div class='card-title'><h4>Check on synthetic build-ups</h4><p>known k and skin, 0.3 psi gauge noise</p></div>",
                unsafe_allow_html=True)
    try:
        import sys
        from wellperf import config as C
        sys.path.insert(0, str(C.ROOT / "tests"))
        from test_pta_synthetic import CASES, run_case

        @st.cache_data(show_spinner="Running the synthetic build-ups…")
        def _synthetic_table():
            rows = []
            for k, s, c_st in CASES:
                r = run_case(k, s, c_st)
                rows.append({"true k": k, "recovered k": r.k_md, "k error %": 100 * (r.k_md / k - 1),
                             "true skin": s, "recovered skin": r.skin})
            return pd.DataFrame(rows)
        UI.table(_synthetic_table(), formats={"recovered k": "{:.1f}", "k error %": "{:+.1f}", "recovered skin": "{:.2f}",
                                              "true k": "{:.0f}", "true skin": "{:.1f}"},
                 labels={"true k": "True k, md", "recovered k": "Recovered k", "k error %": "Error %",
                         "true skin": "True skin", "recovered skin": "Recovered skin"})
    except Exception as e:  # the tests folder is optional in a deployment
        st.caption(f"Synthetic check not available here ({e}).")

UI.section("Limits")
st.markdown("""
- Straight-line trends hold for months, not years. New well tests can recalibrate the model (sidebar).
- Days without the downhole gauge use interpolated or last-known pressure and are flagged.
- Short shut-ins give short windows and less certain k and skin; they are flagged.
- PTA assumes single-phase oil, constant properties and a homogeneous reservoir.
""")
