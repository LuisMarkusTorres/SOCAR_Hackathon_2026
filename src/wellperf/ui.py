"""Shared helpers for the Streamlit pages: session state, layout pieces, formatting and the rule-based interpretation.

Design system (see .streamlit/config.toml for the theme tokens): near-black neutral surfaces, 1 px borders, 10 px
radius, Geist for text and Geist Mono for numbers, one accent. Motion is limited to colour transitions and the button
press; nothing animates on page load.
"""
from __future__ import annotations

import html as _html

import pandas as pd
import streamlit as st

CSS = """
:root {
  --bg: #0b0c0e; --card: #121416; --pop: #17181b; --muted: #1e1f22; --accent: #222427;
  --line: rgba(255,255,255,0.09); --line2: rgba(255,255,255,0.16);
  --fg: #f1f2f3; --fg2: #c9ccd1; --mf: #9b9fa5; --dim: #6f7378;
  --oil: #f59740; --gas: #5ecad6; --water: #6095fa; --blue: #6095fa;
  --ok: #47b777; --warn: #eba941; --bad: #f14d4c;
  --r: 10px; --r-sm: 8px; --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
}
[data-testid="stIconMaterial"], .material-symbols-rounded, span[class*="material"] {
  font-family: "Material Symbols Rounded" !important;}
.stApp {background: var(--bg);}
.block-container {padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1280px;}
h1, h2, h3 {letter-spacing: -0.02em; color: var(--fg);}
p, li {line-height: 1.55;}
.tnum, .num {font-variant-numeric: tabular-nums;}
@media (prefers-reduced-motion: reduce) {* {animation: none !important; transition: none !important;}}

/* ---------- surfaces: flat cards, one border, no shadow ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--card); border: 1px solid var(--line) !important; border-radius: var(--r) !important;
  box-shadow: none !important;}
[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {gap: 0.6rem;}
[data-testid="stMetric"] {background: var(--card); border: 1px solid var(--line) !important;
  border-radius: var(--r) !important; padding: 14px 16px !important;}
div[data-testid="stMetricLabel"] p {color: var(--mf); font-size: 0.75rem; font-weight: 500;}
div[data-testid="stMetricValue"] {font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; color: var(--fg);
  font-variant-numeric: tabular-nums;}
div[data-testid="stMetricDelta"] {font-size: 0.8rem;}
[data-testid="stExpander"] {border-radius: var(--r); background: var(--card);}
[data-testid="stExpander"] details {border-color: var(--line) !important;}
[data-testid="stExpander"] summary {font-size: 0.875rem; font-weight: 500;}

/* ---------- KPI grid ---------- */
.kpi-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 0.2rem 0 0.4rem 0;}
.kpi {background: var(--card); border: 1px solid var(--line); border-radius: var(--r); padding: 14px 16px;
      transition: border-color 150ms ease;}
.kpi:hover {border-color: var(--line2);}
.kpi .l {color: var(--fg2); font-size: 0.75rem; font-weight: 500;}
.kpi .l.oil {color: var(--oil);} .kpi .l.gas {color: var(--gas);} .kpi .l.water {color: var(--water);}
.kpi .l.blue {color: var(--blue);} .kpi .l.bad {color: var(--bad);} .kpi .l.ok {color: var(--ok);} .kpi .l.warn {color: var(--warn);}
.kpi .v {margin-top: 8px; font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; line-height: 1.15; color: var(--fg);
         font-variant-numeric: tabular-nums;}
.kpi .u {font-size: 0.8rem; font-weight: 500; color: var(--mf); margin-left: 5px; letter-spacing: 0;}
.kpi .s {color: var(--mf); font-size: 0.8rem; margin-top: 6px; font-variant-numeric: tabular-nums;}
.kpi .s b {font-weight: 500; color: var(--fg2);}

/* ---------- page pieces ---------- */
.page-head {margin: 0 0 1.1rem 0;}
.page-head h2 {font-size: 1.5rem; font-weight: 600; margin: 0; padding: 0; line-height: 1.2; color: var(--fg);}
.page-head p {color: var(--mf); margin: 0.35rem 0 0 0; font-size: 0.875rem; max-width: 72ch;}
.section {font-size: 0.9375rem; font-weight: 600; margin: 1.5rem 0 0.35rem 0; color: var(--fg);}
.section-sub {color: var(--mf); font-size: 0.8125rem; margin: -0.2rem 0 0.6rem 0; max-width: 80ch;}
.howto {color: var(--mf); font-size: 0.8125rem; line-height: 1.5; margin: -0.2rem 0.2rem 1rem 0.2rem; max-width: 100ch;}
.howto b {color: var(--fg2); font-weight: 500;}
.note {display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin: 0.3rem 0; border-radius: var(--r-sm);
       font-size: 0.875rem; line-height: 1.5; border: 1px solid var(--line); background: var(--card); color: var(--fg2);}
.note svg {width: 16px; height: 16px; flex: none; margin-top: 2px;}
.note b {color: var(--fg); font-weight: 500;}
.note-warn {border-color: rgba(235,169,65,0.4); background: rgba(235,169,65,0.08);} .note-warn svg {color: var(--warn);}
.note-good {border-color: rgba(71,183,119,0.35); background: rgba(71,183,119,0.07);} .note-good svg {color: var(--ok);}
.note-info svg {color: var(--mf);}
.side-label {font-size: 0.75rem; color: var(--mf); font-weight: 500; margin: 1rem 0 0.3rem 0;}
.facts {font-size: 0.8125rem; color: var(--fg2); line-height: 1.6; font-variant-numeric: tabular-nums;}
.facts span {color: var(--mf);}
.empty {border: 1px dashed var(--line2); border-radius: 14px; padding: 48px 24px; text-align: center; margin: 1rem 0;}
.empty .ic {width: 40px; height: 40px; border-radius: 10px; background: var(--muted); display: inline-grid; place-items: center;
            color: var(--mf); margin-bottom: 12px;}
.empty .t {font-size: 0.9375rem; font-weight: 500; color: var(--fg);}
.empty .d {font-size: 0.875rem; color: var(--mf); margin: 4px auto 0 auto; max-width: 48ch;}

/* ---------- attention list ---------- */
.attn {display: flex; flex-direction: column;}
.attn .row {display: flex; align-items: flex-start; gap: 12px; padding: 10px 8px; border-bottom: 1px solid var(--line);
            border-radius: 6px; transition: background-color 150ms ease;}
.attn .row:last-child {border-bottom: none;}
.attn .row:hover {background: rgba(255,255,255,0.03);}
.attn .dot {width: 8px; height: 8px; border-radius: 50%; flex: none; margin-top: 7px; background: var(--mf);}
.attn .dot.warn {background: var(--warn);} .attn .dot.good {background: var(--ok);} .attn .dot.info {background: var(--blue);}
.attn .t {font-size: 0.875rem; font-weight: 500; color: var(--fg);}
.attn .d {font-size: 0.8125rem; color: var(--mf); margin-top: 1px;}

/* ---------- mini stat grid ---------- */
.mini {display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; margin-top: 4px;}
.mini .l {font-size: 0.75rem; color: var(--fg2); font-weight: 500;}
.mini .l.oil {color: var(--oil);} .mini .l.gas {color: var(--gas);} .mini .l.water {color: var(--water);}
.mini .l.blue {color: var(--blue);} .mini .l.bad {color: var(--bad);} .mini .l.ok {color: var(--ok);}
.mini .v {font-size: 1.25rem; font-weight: 600; letter-spacing: -0.02em; color: var(--fg); font-variant-numeric: tabular-nums; margin-top: 2px;}
.mini .v small {font-size: 0.75rem; font-weight: 500; color: var(--mf); margin-left: 4px;} .mini .s {font-size: 0.75rem; color: var(--dim);}
.card-title {display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;}
.card-title h4 {margin: 0; font-size: 0.9375rem; font-weight: 600; color: var(--fg);}
.card-title p {margin: 0; font-size: 0.8125rem; color: var(--mf);}

/* ---------- tables ---------- */
.tbl-wrap {overflow: auto; border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--card); margin: 0.2rem 0 0.8rem 0;}
.tbl {width: 100%; border-collapse: collapse; font-size: 0.8125rem; margin: 0;}
.tbl th {text-align: left; font-weight: 500; color: var(--mf); font-size: 0.75rem; padding: 0.55rem 0.75rem;
         border-bottom: 1px solid var(--line); background: var(--card); position: sticky; top: 0; white-space: nowrap;}
.tbl td {padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--line); color: var(--fg2); vertical-align: top;}
.tbl tr:last-child td {border-bottom: none;}
.tbl tr:hover td {background: rgba(255,255,255,0.025);}
.tbl .num {text-align: right; white-space: nowrap; font-family: var(--mono); font-size: 0.78rem; font-variant-numeric: tabular-nums;}
.tbl th.num {font-family: inherit; font-size: 0.75rem;}
.tbl .nowrap {white-space: nowrap;}
.tbl .muted {color: var(--dim);}
.tbl td.key {font-weight: 500; color: var(--fg);}

/* ---------- sidebar ---------- */
[data-testid="stSidebarNav"] a {border-radius: var(--r-sm); margin: 1px 0; transition: background-color 150ms ease, color 150ms ease;}
[data-testid="stSidebarNav"] a span {font-size: 0.875rem; font-weight: 500; color: var(--fg2);}
[data-testid="stSidebarNav"] a [data-testid="stIconMaterial"] {color: var(--mf); font-size: 1.1rem;}
[data-testid="stSidebarNav"] a:hover {background: rgba(255,255,255,0.04);}
[data-testid="stSidebarNav"] a[aria-current="page"] {background: var(--accent);}
[data-testid="stSidebarNav"] a[aria-current="page"] span {color: var(--fg);}
[data-testid="stSidebarNav"] a[aria-current="page"] [data-testid="stIconMaterial"] {color: var(--fg);}
[data-testid="stLogo"] {height: 28px; max-width: 170px; margin: 2px 0 4px 2px;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a {padding: 5px 10px; border-radius: var(--r-sm); margin: 0;
  transition: background-color 150ms ease, color 150ms ease;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a span {font-size: 0.875rem; font-weight: 500; color: var(--fg2);}
[data-testid="stSidebar"] [data-testid="stPageLink"] a [data-testid="stIconMaterial"] {color: var(--mf); font-size: 1.1rem;}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {background: rgba(255,255,255,0.04);}
[data-testid="stSidebar"] [data-testid="stExpander"] {background: transparent;}
[data-testid="stSidebar"] [data-testid="stExpander"] details {border: none !important; background: transparent;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {padding: 5px 10px; border-radius: var(--r-sm); border-bottom: none !important;
  transition: background-color 150ms ease;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {background: rgba(255,255,255,0.04);}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {font-size: 0.875rem; font-weight: 500; color: var(--fg2);}
[data-testid="stSidebar"] [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {color: var(--mf); font-size: 1.1rem;}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {padding: 0 0 2px 22px;}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] [data-testid="stVerticalBlock"] {gap: 0;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {margin: 0;}
[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploader"] section {
  border: 1px dashed var(--line2) !important; border-radius: var(--r) !important; background: transparent !important;}
[data-testid="stFileUploaderDropzone"] small, [data-testid="stFileUploader"] section small {color: var(--mf);}

/* ---------- widgets: colour transitions only, press feedback on buttons ---------- */
.stButton > button, .stDownloadButton > button, [data-testid="stPageLink"] a {
  transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, transform 160ms var(--ease-out);}
.stButton > button:active, .stDownloadButton > button:active {transform: scale(0.97);}
[data-testid="stPageLink"] a {font-size: 0.875rem; font-weight: 500;}
[data-testid="stPills"] button, [data-testid="stSegmentedControl"] button {transition: background-color 150ms ease, color 150ms ease;}
.stCaption, [data-testid="stCaptionContainer"] p {color: var(--mf) !important;}
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
_MARK = ('<rect x="0" y="0" width="28" height="28" rx="7" fill="#f1f2f3"/>'
         '<path d="M6 20h4.5v-5.5H15V9h4.5v7H22" fill="none" stroke="#0b0c0e" stroke-width="2.2" '
         'stroke-linejoin="round" stroke-linecap="round"/>')
# "VFMonitor" set in Geist 600, outlined to a path so the logo does not depend on the font being installed
_WORDMARK = "M5.24 -0.00L0.36 -13.49L2.96 -13.49L6.75 -2.75L10.51 -13.49L13.11 -13.49L8.21 -0.00L5.24 -0.00ZM14.52 -0.00L14.52 -13.49L23.54 -13.49L23.54 -11.34L15.64 -11.34L16.99 -12.73L16.99 -6.54L15.64 -7.66L23.20 -7.66L23.20 -5.53L15.64 -5.53L16.99 -6.65L16.99 -0.00L14.52 -0.00ZM25.61 -0.00L25.61 -13.49L28.94 -13.49L32.66 -3.04L36.39 -13.49L39.71 -13.49L39.71 -0.00L37.24 -0.00L37.24 -9.31L33.84 -0.02L31.49 -0.02L28.08 -9.31L28.08 -0.00L25.61 -0.00ZM46.78 0.23Q45.28 0.23 44.15 -0.43Q43.02 -1.08 42.40 -2.28Q41.79 -3.48 41.79 -5.07Q41.79 -6.69 42.40 -7.88Q43.02 -9.06 44.15 -9.72Q45.28 -10.37 46.78 -10.37Q48.28 -10.37 49.40 -9.72Q50.53 -9.06 51.14 -7.88Q51.76 -6.69 51.76 -5.07Q51.76 -3.48 51.14 -2.28Q50.53 -1.08 49.40 -0.43Q48.28 0.23 46.78 0.23ZM46.78 -1.75Q47.96 -1.75 48.60 -2.62Q49.23 -3.50 49.23 -5.07Q49.23 -6.63 48.60 -7.51Q47.96 -8.40 46.78 -8.40Q45.60 -8.40 44.96 -7.51Q44.31 -6.63 44.31 -5.07Q44.31 -3.50 44.96 -2.62Q45.60 -1.75 46.78 -1.75ZM53.64 -0.00L53.64 -10.15L55.84 -10.15L55.94 -7.30L55.65 -7.41Q55.81 -8.47 56.28 -9.12Q56.76 -9.77 57.44 -10.07Q58.12 -10.37 58.94 -10.37Q60.06 -10.37 60.83 -9.88Q61.60 -9.39 62.00 -8.52Q62.40 -7.66 62.40 -6.52L62.40 -0.00L59.97 -0.00L59.97 -5.74Q59.97 -6.59 59.79 -7.18Q59.62 -7.77 59.24 -8.08Q58.85 -8.40 58.20 -8.40Q57.23 -8.40 56.65 -7.71Q56.07 -7.03 56.07 -5.74L56.07 -0.00L53.64 -0.00ZM64.94 -0.00L64.94 -10.15L67.38 -10.15L67.38 -0.00L64.94 -0.00ZM64.91 -11.50L64.91 -13.66L67.44 -13.66L67.44 -11.50L64.91 -11.50ZM73.50 -0.00Q71.98 -0.00 71.26 -0.70Q70.55 -1.41 70.55 -2.91L70.55 -12.52L72.98 -12.52L72.98 -3.14Q72.98 -2.43 73.29 -2.16Q73.59 -1.88 74.24 -1.88L75.66 -1.88L75.66 -0.00L73.50 -0.00ZM68.96 -8.27L68.96 -10.15L75.66 -10.15L75.66 -8.27L68.96 -8.27ZM81.69 0.23Q80.18 0.23 79.05 -0.43Q77.92 -1.08 77.31 -2.28Q76.69 -3.48 76.69 -5.07Q76.69 -6.69 77.31 -7.88Q77.92 -9.06 79.05 -9.72Q80.18 -10.37 81.69 -10.37Q83.18 -10.37 84.31 -9.72Q85.43 -9.06 86.05 -7.88Q86.66 -6.69 86.66 -5.07Q86.66 -3.48 86.05 -2.28Q85.43 -1.08 84.31 -0.43Q83.18 0.23 81.69 0.23ZM81.69 -1.75Q82.86 -1.75 83.50 -2.62Q84.13 -3.50 84.13 -5.07Q84.13 -6.63 83.50 -7.51Q82.86 -8.40 81.69 -8.40Q80.51 -8.40 79.86 -7.51Q79.22 -6.63 79.22 -5.07Q79.22 -3.50 79.86 -2.62Q80.51 -1.75 81.69 -1.75ZM88.54 -0.00L88.54 -10.15L90.82 -10.15L90.92 -7.33L90.71 -7.37Q90.94 -8.84 91.57 -9.49Q92.21 -10.15 93.31 -10.15L94.24 -10.15L94.24 -8.06L93.29 -8.06Q92.52 -8.06 92.00 -7.83Q91.49 -7.60 91.23 -7.12Q90.97 -6.63 90.97 -5.85L90.97 -0.00L88.54 -0.00Z"
LOGO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="140" height="28" viewBox="0 0 140 28">' + _MARK +
            f'<g transform="translate(36 20.5)"><path d="{_WORDMARK}" fill="#f1f2f3"/></g></svg>')
ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">' + _MARK + '</svg>'

_ICONS = {
    "warn": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
            '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    "good": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
    "info": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/>'
            '<line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    "upload": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
              'stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
              '<polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
}


# ----------------------------------------------------------------------------- layout pieces
def header(title: str, subtitle: str | None = None) -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f"<div class='page-head'><h2>{title}</h2>{sub}</div>", unsafe_allow_html=True)


def kpis(cards: list[dict], min_width: int = 190) -> None:
    """A row of KPI cards. Each card: label, value, unit (opt), sub (opt, html), tone (opt: oil|gas|water|blue|bad|ok|warn, colours the label).
    min_width is the narrowest card in px; the row wraps below it."""
    html = ""
    for c in cards:
        tone = f" {c['tone']}" if c.get("tone") else ""
        unit = f"<span class='u'>{c['unit']}</span>" if c.get("unit") else ""
        sub = f"<div class='s'>{c['sub']}</div>" if c.get("sub") else ""
        html += f"<div class='kpi'><div class='l{tone}'>{c['label']}</div><div class='v'>{c['value']}{unit}</div>{sub}</div>"
    st.markdown(f"<div class='kpi-grid' style='grid-template-columns: repeat(auto-fit, minmax({min_width}px, 1fr))'>"
                f"{html}</div>", unsafe_allow_html=True)


def attention(items: list[tuple[str, str, str]]) -> None:
    """items: (kind, title, detail) with kind in warn|info|good."""
    rows = "".join(f"<div class='row'><div class='dot {k}'></div><div><div class='t'>{t}</div>"
                   f"<div class='d'>{d}</div></div></div>" for k, t, d in items)
    st.markdown(f"<div class='attn'>{rows}</div>", unsafe_allow_html=True)


def card_title(title: str, sub: str | None = None) -> None:
    st.markdown(f"<div class='card-title'><h4>{title}</h4>{f'<p>{sub}</p>' if sub else ''}</div>", unsafe_allow_html=True)


def mini_stats(items: list[tuple]) -> None:
    """items: (label, value, unit, small note[, tone]); tone colours the label like kpis()."""
    html = "".join(f"<div><div class='l {it[4] if len(it) > 4 else ''}'>{it[0]}</div><div class='v'>{it[1]}<small>{it[2]}</small>"
                   f"</div><div class='s'>{it[3]}</div></div>" for it in items)
    st.markdown(f"<div class='mini'>{html}</div>", unsafe_allow_html=True)


def section(title: str, sub: str | None = None) -> None:
    st.markdown(f"<div class='section'>{title}</div>", unsafe_allow_html=True)
    if sub:
        st.markdown(f"<div class='section-sub'>{sub}</div>", unsafe_allow_html=True)


def howto(html: str) -> None:
    st.markdown(f"<div class='howto'>{html}</div>", unsafe_allow_html=True)


def note(html: str, kind: str = "info") -> None:
    st.markdown(f"<div class='note note-{kind}'>{_ICONS.get(kind, _ICONS['info'])}<div>{html}</div></div>",
                unsafe_allow_html=True)


def empty_state(title: str, detail: str) -> None:
    st.markdown(f"<div class='empty'><div class='ic'>{_ICONS['upload']}</div><div class='t'>{title}</div>"
                f"<div class='d'>{detail}</div></div>", unsafe_allow_html=True)


def table(df: pd.DataFrame, labels: dict | None = None, formats: dict | None = None, max_height: int | None = None,
          key_col: str | None = None, date_fmt: str = "%d %b %Y, %H:%M", nowrap: tuple = ()) -> None:
    """Render a read-only table as styled HTML: right-aligned tabular numbers, readable dates, a dash for missing values.

    formats maps column -> format string ("{:,.1f}") or callable. key_col is shown in medium weight (usually the well
    name) and kept on one line when its values are short. nowrap lists further columns kept on one line.
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
