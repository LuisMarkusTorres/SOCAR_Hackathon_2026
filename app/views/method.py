"""Method & validation: what the models are, how they were tested, and how they compare with alternatives."""
import pandas as pd
import streamlit as st

from wellperf import plots as PLT
from wellperf import ui as UI
from wellperf import vfm as V

ws = UI.ws()
UI.header("Method & validation", "How the flow meter and the build-up analysis work, and the evidence that they do")

# ---------------------------------------------------------------- VFM
UI.section("Virtual flow meter", "A physics-structured model, calibrated per well on the production well tests")
left, right = st.columns([1.1, 1], gap="large")
with left:
    st.markdown(r"""
The wells produce undersaturated oil (flowing bottom-hole pressure far above the bubble point), so only liquid flows in
the reservoir and the inflow is linear. Per well $w$, with $t$ in days:

$$q_L = J_w\,\big(\bar p_{r,w}(t) - p_{wf}\big), \qquad \bar p_{r,w}(t) = p_{0,w} + p_{1,w}\,t$$

$$WC_w(t) = c_w + d_w\,t, \qquad GOR_w \approx R_s(p_b)$$

$$q_o = q_L\,(1 - WC),\qquad q_w = q_L\,WC,\qquad q_g = q_o\,GOR/1000$$

$$\text{daily volume} = \text{rate} \times \text{hours on stream}/24$$

$J$ (productivity index) is ridge-regularised toward a pooled, field-wide value, so wells whose tests barely moved in
pressure still get a physically sensible $J$. The only sensor the daily rate needs is the downhole gauge; shut-ins come
from the gas-lift and choke records.
""")
with right:
    st.markdown("**Per-well parameters**")
    par = pd.DataFrame([vars(p) for p in ws.model.params.values()])
    par = par[["well_name", "n_tests", "J", "J_source", "wc_c", "wc_d", "gor", "rs_pb"]]
    UI.table(par, key_col="well_name", max_height=330,
             labels={"well_name": "Well", "n_tests": "Tests", "J": "J, STB/d/psi", "J_source": "J from",
                     "wc_c": "WC, %", "wc_d": "WC trend, %/d", "gor": "GOR", "rs_pb": "Rs(pb)"},
             formats={"J": "{:.2f}", "wc_c": "{:.1f}", "wc_d": "{:+.3f}", "gor": "{:,.0f}", "rs_pb": "{:,.0f}"})

UI.section("Validation against the well tests",
           "Never graded on data it was trained on. Baseline: carry the last well test forward.")
sf, sl = V.score(ws.backtest_forward).round(2), V.score(ws.backtest_loto).round(2)
sf.insert(1, "scheme", "forward-chaining"); sl.insert(1, "scheme", "leave-one-test-out")
val = pd.concat([sf, sl], ignore_index=True)
cols = ["model", "scheme", "n_tests", "oil MAPE %", "water MAPE %", "gas MAPE %", "oil bias %", "water bias %", "gas bias %"]
UI.table(val[cols], key_col="model", formats={c: "{:.1f}" for c in cols[3:]},
         labels={"model": "Model", "scheme": "Scheme", "n_tests": "Tests"})
UI.howto("<b>Forward-chaining</b>: each test is predicted from tests completed before it, as in deployment. "
         "<b>Leave-one-test-out</b>: one test is hidden and predicted from all the others, the situation of the days "
         "between tests. MAPE = mean absolute error in %; bias = mean signed error in %. The 90% prediction bands in "
         "the app are the 5th and 95th percentiles of the forward-chaining errors.")
c = st.columns(3)
for col, ph in zip(c, V.PHASES):
    col.plotly_chart(PLT.parity_plot(ws.backtest_forward, ph), width="stretch")
UI.howto("Measured well test against the blind, forward-chaining prediction. Points on the dotted line are perfect.")

if ws.candidates is not None and len(ws.candidates):
    UI.section("Why this model and not another",
               "Candidates scored with the same forward-chaining backtest, on the same tests. Lower is better.")
    cand = ws.candidates.copy()
    UI.table(cand, key_col="model", formats={c: "{:.1f}" for c in cand.columns if "MAPE" in c},
             labels={"model": "Model", "n_tests": "Tests"})
    UI.howto("<b>Choke-flow ridge</b> is the Gilbert-type model (choke size, wellhead pressure, downhole minus "
             "wellhead pressure, gas-lift rate, temperature) pooled across wells with a ridge penalty. "
             "<b>Gradient-boosted trees</b> use every sensor feature plus the well identity and time. With under ten "
             "tests per well, the model that already knows the shape of inflow needs the least data and extrapolates "
             "reservoir-pressure decline instead of flattening, which trees cannot do.")
else:
    UI.note("The model comparison table is produced at training time (scripts/run_pipeline.py); this model file "
            "predates it.", "info")

if ws.test_eval is not None and len(ws.test_eval):
    UI.section("Score on the uploaded well tests", "The model as trained, unchanged, against tests it had never seen")
    se = V.score(ws.test_eval).round(2)
    UI.table(se, key_col="model", formats={c: "{:.1f}" for c in se.columns if "%" in c or "MAE" in c})
    c = st.columns(3)
    for col, ph in zip(c, V.PHASES):
        col.plotly_chart(PLT.parity_plot(ws.test_eval, ph), width="stretch")

# ---------------------------------------------------------------- PTA
UI.section("Build-up analysis", "Horner method with an automatic radial-flow window from the Bourdet derivative")
left, right = st.columns([1.1, 1], gap="large")
with left:
    st.markdown(r"""
1. **Shut-ins** are found where gas-lift injection stops or the choke closes for at least an hour.
2. The build-up is resampled in log time and the **Bourdet derivative** is computed on Agarwal equivalent time.
3. The **radial-flow window** is the flattest stretch of the derivative after wellbore storage (at least half a
   log cycle). It can be overridden by hand on the Build-up tests page.
4. A straight line on the **Horner plot** gives the slope $m$ and $p^*$; then, in field units,

$$k = \frac{162.6\,q\,B\,\mu}{m\,h}, \qquad s = 1.151\left[\frac{p_{1hr} - p_{wf}}{m} - \log_{10}\frac{k}{\phi\,\mu\,c_t\,r_w^2} + 3.23\right], \qquad \Delta p_{skin} = 0.87\,m\,s$$

$q$ is the flow meter's oil rate on the last full day before the shut-in, $t_p = 24\,N_p/q$. Every result carries
the fit $R^2$, a derivative cross-check of $m$, the radius of investigation and plain-language flags.
""")
with right:
    st.markdown("**Verification on synthetic build-ups with known answers**")
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
                                              "true k": "{:.0f}", "true skin": "{:.1f}"})
        UI.howto("Analytical wellbore-storage + skin solution (Laplace space, Stehfest inversion) with 0.3 psi gauge "
                 "noise, run through the same automatic pipeline. Permeability within a few percent, skin within 0.2.")
    except Exception as e:  # the tests folder is optional in a deployment
        st.caption(f"Synthetic verification not available here ({e}).")

UI.section("Limits", None)
st.markdown("""
- Reservoir pressure and water cut are straight lines in time: accurate over months, not years. Each new well test can
  recalibrate the model (sidebar, when tests are uploaded with new data).
- The daily rate relies on the downhole gauge. Days without it use interpolated or last-known pressure and are flagged.
- Short shut-ins give short radial-flow windows; they are flagged and less certain.
- PTA assumes single-phase oil, constant properties and a homogeneous reservoir, as the brief specifies.
- p\\* is reported at gauge depth and, with the live-oil gradient estimated from the tests' oil gravity, at datum depth.
""")
