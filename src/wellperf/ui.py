"""Shared helpers for the Streamlit pages: session state, layout pieces, formatting and the rule-based interpretation."""
from __future__ import annotations

import html as _html

import pandas as pd
import streamlit as st

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --bg: #0b0f1a; --card: #111827; --card2: #0f1628; --line: rgba(255,255,255,0.08); --line2: rgba(255,255,255,0.14);
  --ink: #e6eaf2; --ink2: #b7c0d1; --muted: #8a94a8; --dim: #5f6b82;
  --blue: #3b82f6; --blue2: #60a5fa; --oil: #f59e0b; --gas: #2dd4bf; --water: #818cf8;
  --warn: #f59e0b; --good: #34d399; --info: #60a5fa;
}
html, body, .stApp, .stMarkdown, button, input, select, textarea, p, h1, h2, h3, h4, label, li, td, th, small, b,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] div,
[data-testid="stSidebar"] span:not([data-testid="stIconMaterial"]),
.block-container span:not([data-testid="stIconMaterial"]) {
  font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;}
[data-testid="stIconMaterial"], .material-symbols-rounded, span[class*="material"] {
  font-family: "Material Symbols Rounded" !important;}
code, pre, .stCode * {font-family: ui-monospace, "JetBrains Mono", Consolas, monospace !important;}
.stApp {background: radial-gradient(1100px 600px at 85% -10%, rgba(59,130,246,0.10), transparent 60%), var(--bg);}
.block-container {padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1480px;}
h1, h2, h3 {letter-spacing: -0.015em; color: var(--ink);}

/* ---------- motion: one gentle rise per render, hover lift on cards ---------- */
@keyframes rise {from {opacity: 0; transform: translateY(8px);} to {opacity: 1; transform: none;}}
.block-container [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"],
.block-container [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"],
.block-container [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {
  animation: rise .45s cubic-bezier(.2,.7,.2,1) both;}
@media (prefers-reduced-motion: reduce) {* {animation: none !important; transition: none !important;}}

/* ---------- cards ---------- */
[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {gap: 0.6rem;}
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--card); border: 1px solid var(--line) !important; border-radius: 16px !important;
  box-shadow: 0 1px 0 rgba(255,255,255,0.03) inset, 0 10px 30px rgba(0,0,0,0.25);
  transition: border-color .25s ease, transform .25s ease, box-shadow .25s ease;}
[data-testid="stVerticalBlockBorderWrapper"]:hover {border-color: var(--line2) !important;}
[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--line) !important; border-radius: 16px !important;
  padding: 14px 16px !important; transition: border-color .25s ease, transform .25s ease;}
[data-testid="stMetric"]:hover {border-color: var(--line2) !important; transform: translateY(-1px);}
div[data-testid="stMetricLabel"] p {color: var(--muted); font-size: 0.82rem; font-weight: 500;}
div[data-testid="stMetricValue"] {font-size: 1.6rem; font-weight: 600; letter-spacing: -0.02em; color: var(--ink);}
div[data-testid="stMetricDelta"] {font-size: 0.8rem;}

/* ---------- KPI grid (custom) ---------- */
.kpi-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 0.2rem 0 0.4rem 0;}
.kpi {background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 16px 18px 14px 18px;
      animation: rise .5s cubic-bezier(.2,.7,.2,1) both; transition: border-color .25s ease, transform .25s ease;}
.kpi:nth-child(2) {animation-delay: .05s} .kpi:nth-child(3) {animation-delay: .1s} .kpi:nth-child(4) {animation-delay: .15s}
.kpi:hover {border-color: var(--line2); transform: translateY(-2px);}
.kpi .l {color: var(--muted); font-size: 0.82rem; font-weight: 500; margin-bottom: 8px;}
.kpi .v {font-size: 1.85rem; font-weight: 600; letter-spacing: -0.03em; line-height: 1.05; color: var(--ink);}
.kpi .v.oil {color: var(--oil);} .kpi .v.gas {color: var(--gas);} .kpi .v.water {color: var(--water);} .kpi .v.blue {color: var(--blue2);}
.kpi .u {font-size: 0.8rem; font-weight: 500; color: var(--ink2); margin-left: 6px; letter-spacing: 0;}
.kpi .s {color: var(--muted); font-size: 0.78rem; margin-top: 9px;}
.kpi .s b {font-weight: 600; color: var(--ink2);}

/* ---------- page pieces ---------- */
.page-head {margin: 0 0 1.1rem 0; display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap;}
.page-head h2 {font-size: 1.6rem; font-weight: 600; margin: 0; padding: 0; color: var(--ink);}
.page-head p {color: var(--muted); margin: 0.3rem 0 0 0; font-size: 0.92rem;}
.section {font-size: 1.02rem; font-weight: 600; margin: 1.5rem 0 0.45rem 0; color: var(--ink);}
.section-sub {color: var(--muted); font-size: 0.85rem; margin: -0.3rem 0 0.6rem 0;}
.howto {color: var(--muted); font-size: 0.83rem; line-height: 1.5; margin: -0.3rem 0.3rem 1rem 0.3rem;}
.howto b {color: var(--ink2); font-weight: 600;}
.note {padding: 0.6rem 0.9rem; margin: 0.3rem 0; border-radius: 12px; font-size: 0.9rem; line-height: 1.5;
       border: 1px solid var(--line); border-left-width: 3px; background: var(--card2); color: var(--ink2);}
.note b {color: var(--ink);}
.note-warn {border-left-color: var(--warn);} .note-good {border-left-color: var(--good);} .note-info {border-left-color: var(--info);}
.side-label {text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.68rem; color: var(--dim);
             font-weight: 600; margin: 1.1rem 0 0.25rem 0;}
.facts {font-size: 0.83rem; color: var(--ink2); line-height: 1.65;}
.facts span {color: var(--muted);}

/* ---------- attention list ---------- */
.attn {display: flex; flex-direction: column; gap: 6px;}
.attn .row {display: flex; align-items: flex-start; gap: 12px; padding: 11px 12px; border-radius: 12px;
            border: 1px solid transparent; transition: background .2s ease, border-color .2s ease;}
.attn .row:hover {background: rgba(255,255,255,0.03); border-color: var(--line);}
.attn .ic {width: 22px; height: 22px; border-radius: 7px; display: grid; place-items: center; font-size: 12px; flex: none; margin-top: 1px;}
.attn .ic.warn {background: rgba(245,158,11,0.15); color: var(--warn);} .attn .ic.info {background: rgba(96,165,250,0.15); color: var(--info);}
.attn .ic.good {background: rgba(52,211,153,0.15); color: var(--good);}
.attn .t {font-size: 0.92rem; font-weight: 600; color: var(--ink);}
.attn .d {font-size: 0.82rem; color: var(--muted); margin-top: 2px;}
.attn .arrow {margin-left: auto; color: var(--dim); font-size: 1rem; align-self: center;}

/* ---------- mini stat grid (reservoir card) ---------- */
.mini {display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; margin-top: 6px;}
.mini .l {font-size: 0.78rem; color: var(--muted);} .mini .v {font-size: 1.35rem; font-weight: 600; letter-spacing: -0.02em; color: var(--ink);}
.mini .v small {font-size: 0.75rem; font-weight: 500; color: var(--ink2); margin-left: 4px;} .mini .s {font-size: 0.74rem; color: var(--dim);}
.card-title {display: flex; justify-content: space-between; align-items: baseline;}
.card-title h4 {margin: 0; font-size: 1rem; font-weight: 600; color: var(--ink);}
.card-title p {margin: 0; font-size: 0.8rem; color: var(--muted);}

/* ---------- tables ---------- */
.tbl-wrap {overflow: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--card2); margin: 0.2rem 0 0.8rem 0;}
.tbl {width: 100%; border-collapse: collapse; font-size: 0.86rem; font-variant-numeric: tabular-nums; margin: 0;}
.tbl th {text-align: left; font-weight: 600; color: var(--muted); font-size: 0.7rem; text-transform: uppercase;
         letter-spacing: 0.06em; padding: 0.6rem 0.8rem; border-bottom: 1px solid var(--line); background: var(--card);
         position: sticky; top: 0; white-space: nowrap;}
.tbl td {padding: 0.55rem 0.8rem; border-bottom: 1px solid var(--line); color: var(--ink2); vertical-align: top;}
.tbl tr:last-child td {border-bottom: none;}
.tbl tr:hover td {background: rgba(255,255,255,0.03);}
.tbl .num {text-align: right; white-space: nowrap;}
.tbl .nowrap {white-space: nowrap;}
.tbl .muted {color: var(--dim);}
.tbl td.key {font-weight: 600; color: var(--ink);}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {border-right: 1px solid var(--line);}
[data-testid="stSidebarNav"] a {border-radius: 10px; margin: 2px 0; transition: background .2s ease;}
[data-testid="stSidebarNav"] a span {font-size: 0.92rem; font-weight: 500;}
[data-testid="stSidebarNav"] a[aria-current="page"] {background: rgba(59,130,246,0.16); box-shadow: inset 3px 0 0 var(--blue);}
[data-testid="stSidebarNav"] a[aria-current="page"] span {color: var(--ink); font-weight: 600;}
[data-testid="stLogo"] {height: 36px; max-width: 190px;}

/* ---------- widgets ---------- */
.stButton > button, .stDownloadButton > button {border-radius: 10px; transition: transform .15s ease, box-shadow .2s ease;}
.stButton > button:hover, .stDownloadButton > button:hover {transform: translateY(-1px);}
[data-testid="stExpander"] {border-radius: 14px;}
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


# ----------------------------------------------------------------------------- brand
APP_NAME = "VFMonitor"
_MARK = ('<rect x="0" y="0" width="32" height="32" rx="9" fill="#2563eb"/>'
         '<path d="M7 23h5v-6h5v-6h5v8h3" fill="none" stroke="#fff" stroke-width="2.4" '
         'stroke-linejoin="round" stroke-linecap="round"/>')
LOGO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="176" height="32" viewBox="0 0 176 32">' + _MARK +
            '<text x="41" y="22.5" font-family="Inter, system-ui, -apple-system, Segoe UI, sans-serif" font-size="19" '
            'font-weight="700" letter-spacing="-0.5" fill="#e6eaf2">VF<tspan fill="#60a5fa">Monitor</tspan></text></svg>')
ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">' + _MARK + '</svg>'


# ----------------------------------------------------------------------------- layout pieces
def header(title: str, subtitle: str | None = None) -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f"<div class='page-head'><div><h2>{title}</h2>{sub}</div></div>", unsafe_allow_html=True)


def kpis(cards: list[dict]) -> None:
    """A row of KPI cards. Each card: label, value, unit (opt), sub (opt, html), tone (oil|gas|water|blue, opt)."""
    html = ""
    for c in cards:
        tone = f" {c['tone']}" if c.get("tone") else ""
        unit = f"<span class='u'>{c['unit']}</span>" if c.get("unit") else ""
        sub = f"<div class='s'>{c['sub']}</div>" if c.get("sub") else ""
        html += f"<div class='kpi'><div class='l'>{c['label']}</div><div class='v{tone}'>{c['value']}{unit}</div>{sub}</div>"
    st.markdown(f"<div class='kpi-grid'>{html}</div>", unsafe_allow_html=True)


def attention(items: list[tuple[str, str, str]]) -> None:
    """items: (kind, title, detail) with kind in warn|info|good."""
    glyph = {"warn": "!", "info": "i", "good": "✓"}
    rows = "".join(f"<div class='row'><div class='ic {k}'>{glyph.get(k, 'i')}</div><div><div class='t'>{t}</div>"
                   f"<div class='d'>{d}</div></div><div class='arrow'>›</div></div>" for k, t, d in items)
    st.markdown(f"<div class='attn'>{rows}</div>", unsafe_allow_html=True)


def card_title(title: str, sub: str | None = None) -> None:
    st.markdown(f"<div class='card-title'><h4>{title}</h4>{f'<p>{sub}</p>' if sub else ''}</div>", unsafe_allow_html=True)


def mini_stats(items: list[tuple[str, str, str, str]]) -> None:
    """items: (label, value, unit, small note)."""
    html = "".join(f"<div><div class='l'>{l}</div><div class='v'>{v}<small>{u}</small></div><div class='s'>{n}</div></div>"
                   for l, v, u, n in items)
    st.markdown(f"<div class='mini'>{html}</div>", unsafe_allow_html=True)


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
