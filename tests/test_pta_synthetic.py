"""The automated PTA must recover known k and skin from analytical (synthetic) build-ups with storage and noise."""
import pandas as pd

from wellperf import pta as P
from wellperf.synthetic import buildup_minutes

PROPS = dict(h=80.0, phi=0.2, mu=1.2, B=1.15, ct=1.3e-5, rw=0.328)
CASES = [  # k [md], skin, C [bbl/psi]
    (110.0, 6.0, 0.01),
    (55.0, -0.6, 0.02),
    (290.0, 1.9, 0.01),
    (42.0, -1.6, 0.05),
    (25.0, 0.5, 0.01),
]


def run_case(k, s, C, q=1000.0, tp_hr=5000.0, shut_hr=72.0, noise=0.3, q_interp=None):
    """Generate a build-up produced at rate q; interpret it with q_interp (defaults to q)."""
    bu, pwf = buildup_minutes(k, s, C, q, tp_hr, shut_hr, PROPS, noise_psi=noise)
    t0 = pd.Timestamp("2025-01-10 08:00")
    pre = pd.DataFrame({"timestamp": pd.date_range(t0 - pd.Timedelta(minutes=30), periods=30, freq="min"),
                        "dh_pressure_psia": pwf})
    post = pd.DataFrame({"timestamp": t0 + pd.to_timedelta(bu.dt_hr, unit="h"), "dh_pressure_psia": bu.p_psia})
    minute = pd.concat([pre, post], ignore_index=True)
    minute["well_name"] = "SYN"
    ev = pd.Series(dict(well_name="SYN", t_shut=t0, t_reopen=t0 + pd.Timedelta(hours=shut_hr), duration_hr=shut_hr))
    props = pd.Series(dict(net_pay_thickness_ft=PROPS["h"], porosity_frac=PROPS["phi"], oil_viscosity_cp=PROPS["mu"],
                           oil_fvf_rb_stb=PROPS["B"], total_compressibility_1_psi=PROPS["ct"],
                           wellbore_radius_ft=PROPS["rw"], estimated_drainage_area_acres=1e6))
    return P.interpret_buildup(minute, ev, q if q_interp is None else q_interp, q * tp_hr / 24.0, props)


def test_recovers_known_parameters():
    for k, s, C in CASES:
        r = run_case(k, s, C)
        assert abs(r.k_md / k - 1) < 0.05, (k, s, r.k_md)
        assert abs(r.skin - s) < 0.35, (k, s, r.skin)


if __name__ == "__main__":
    for k, s, C in CASES:
        r = run_case(k, s, C)
        m_true = 162.6 * 1000 * PROPS["B"] * PROPS["mu"] / (k * PROPS["h"])
        print(f"true k={k:6.1f} s={s:5.2f} m={m_true:6.2f} | est k={r.k_md:6.1f} ({100 * (r.k_md / k - 1):+.1f}%) "
              f"s={r.skin:5.2f} ({r.skin - s:+.2f}) m={r.m_psi_cycle:6.2f} window {r.window_start_hr:.2g}-{r.window_end_hr:.2g} h")
    test_recovers_known_parameters()
    print("synthetic PTA test passed")
