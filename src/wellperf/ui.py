"""Shared helpers for the Streamlit pages: session state, layout pieces, formatting and the rule-based interpretation."""
from __future__ import annotations

import html as _html

import pandas as pd
import streamlit as st

CSS = """
.block-container {padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1440px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.page-head {margin: 0 0 1.1rem 0; border-bottom: 1px solid #e1e0d9; padding-bottom: 0.7rem;}
.page-head h2 {font-size: 1.55rem; font-weight: 600; margin: 0; padding: 0;}
.page-head p {color: #6b6a65; margin: 0.25rem 0 0 0; font-size: 0.92rem;}
.section {font-size: 1.05rem; font-weight: 600; margin: 1.6rem 0 0.4rem 0;}
.section-sub {color: #6b6a65; font-size: 0.86rem; margin: -0.3rem 0 0.6rem 0;}
.howto {color: #5f5e59; font-size: 0.84rem; line-height: 1.45; margin: -0.4rem 0.4rem 1rem 0.4rem;}
.howto b {color: #3a3936; font-weight: 600;}
.note {padding: 0.55rem 0.85rem; margin: 0.25rem 0; border-radius: 4px; font-size: 0.9rem; line-height: 1.45;
       border: 1px solid #e1e0d9; border-left-width: 3px; background: #ffffff;}
.note-warn {border-left-color: #d98f00; background: #fffaf0;}
.note-good {border-left-color: #1baf7a;}
.note-info {border-left-color: #2a78d6;}
.brand {font-weight: 650; font-size: 1.08rem; letter-spacing: -0.01em; margin-top: -0.6rem;}
.brand-sub {color: #6b6a65; font-size: 0.82rem; margin-bottom: 0.4rem;}
.side-label {text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.7rem; color: #898781;
             font-weight: 600; margin: 1.1rem 0 0.2rem 0;}
.facts {font-size: 0.84rem; color: #52514e; line-height: 1.6;}
.facts span {color: #898781;}
.tbl-wrap {overflow: auto; border: 1px solid #e1e0d9; border-radius: 6px; background: #ffffff; margin: 0.2rem 0 0.8rem 0;}
.tbl {width: 100%; border-collapse: collapse; font-size: 0.86rem; font-variant-numeric: tabular-nums; margin: 0;}
.tbl th {text-align: left; font-weight: 600; color: #6b6a65; font-size: 0.72rem; text-transform: uppercase;
         letter-spacing: 0.045em; padding: 0.55rem 0.8rem; border-bottom: 1px solid #e1e0d9; background: #f7f6f2;
         position: sticky; top: 0; white-space: nowrap;}
.tbl td {padding: 0.5rem 0.8rem; border-bottom: 1px solid #efeee9; color: #1f1e1c; vertical-align: top;}
.tbl tr:last-child td {border-bottom: none;}
.tbl tr:hover td {background: #faf9f6;}
.tbl .num {text-align: right; white-space: nowrap;}
.tbl .nowrap {white-space: nowrap;}
.tbl .muted {color: #a3a29c;}
.tbl td.key {font-weight: 600;}
div[data-testid="stMetricValue"] {font-size: 1.5rem;}
div[data-testid="stMetricLabel"] p {color: #52514e;}
"""


def apply_css() -> None:
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- state
def ws():
    return st.session_state["_ws"]


def well() -> str:
    return st.session_state["well"]


def set_well(w: str) -> None:
    """Only call from a widget callback (the sidebar selectbox owns this key)."""
    st.session_state["well"] = w


# ----------------------------------------------------------------------------- layout pieces
def header(title: str, subtitle: str | None = None) -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f"<div class='page-head'><h2>{title}</h2>{sub}</div>", unsafe_allow_html=True)


def section(title: str, sub: str | None = None) -> None:
    st.markdown(f"<div class='section'>{title}</div>", unsafe_allow_html=True)
    if sub:
        st.markdown(f"<div class='section-sub'>{sub}</div>", unsafe_allow_html=True)


def howto(html: str) -> None:
    st.markdown(f"<div class='howto'>{html}</div>", unsafe_allow_html=True)


def note(html: str, kind: str = "info") -> None:
    st.markdown(f"<div class='note note-{kind}'>{html}</div>", unsafe_allow_html=True)


def table(df: pd.DataFrame, labels: dict | None = None, formats: dict | None = None, max_height: int | None = None,
          key_col: str | None = None, date_fmt: str = "%d %b %Y, %H:%M", nowrap: tuple = ()) -> None:
    """Render a read-only table as styled HTML: right-aligned numbers, readable dates, a dash for missing values.

    formats maps column -> format string ("{:,.1f}") or callable. key_col is shown in bold (usually the well name)
    and kept on one line when its values are short. nowrap lists further columns kept on one line.
    """
    labels, formats = labels or {}, formats or {}
    cols = list(df.columns)
    num = {c: pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c]) for c in cols}
    keep = set(nowrap)
    if key_col in df.columns and df[key_col].astype(str).str.len().max() <= 12:
        keep.add(key_col)

    def cell(c, v):
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return "<td class='muted{}'>–</td>".format(" num" if num[c] else "")
        f = formats.get(c)
        if callable(f):
            s = f(v)
        elif f:
            s = f.format(v)
        elif isinstance(v, pd.Timestamp):
            s = v.strftime(date_fmt)
        elif num[c] and isinstance(v, float):
            s = f"{v:,.2f}"
        elif num[c]:
            s = f"{v:,}"
        else:
            s = str(v)
        cls = "num" if num[c] else ("nowrap" if isinstance(v, pd.Timestamp) or c in keep else "")
        if c == key_col:
            cls += " key"
        return f"<td class='{cls.strip()}'>{_html.escape(s)}</td>"

    head = "".join(f"<th class='{'num' if num[c] else ''}'>{_html.escape(labels.get(c, c))}</th>" for c in cols)
    body = "".join("<tr>" + "".join(cell(c, v) for c, v in zip(cols, row)) + "</tr>"
                   for row in df.itertuples(index=False, name=None))
    style = f" style='max-height:{max_height}px'" if max_height else ""
    st.markdown(f"<div class='tbl-wrap'{style}><table class='tbl'><thead><tr>{head}</tr></thead>"
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)


def rnd(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Round float columns only (timestamps and text untouched)."""
    return df.apply(lambda s: s.round(n) if pd.api.types.is_float_dtype(s) else s)


def event_well(key: str) -> str:
    return key.split(" ")[0]


def event_label(key: str, ws_) -> str:
    r = ws_.pta_objs[key]
    return f"{r.well_name} · {r.t_shut:%d %b %H:%M} · {r.duration_hr:.0f} h"


# ----------------------------------------------------------------------------- interpretation
from .interpret import interpret  # noqa: E402,F401  (re-exported for the pages)
