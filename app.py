"""
app.py  —  SFU Course Predictor
Run with: streamlit run app.py
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st

st.set_page_config(
    page_title="SFU Course Predictor",
    page_icon="🎓",
    layout="centered",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background: #0e0e0e;
    color: #f0f0f0;
}

/* ── header ── */
.header {
    padding: 2.5rem 0 1.5rem;
    border-bottom: 1px solid #2a2a2a;
    margin-bottom: 2rem;
}
.header-eyebrow {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #cc0000;
    margin-bottom: 0.5rem;
}
.header-title {
    font-size: 2rem;
    font-weight: 600;
    color: #f0f0f0;
    margin: 0;
    line-height: 1.1;
}
.header-sub {
    font-size: 0.85rem;
    color: #666;
    margin-top: 0.4rem;
    font-weight: 300;
}

/* ── result card ── */
.rcard {
    background: #161616;
    border: 1px solid #2a2a2a;
    border-top: 3px solid #cc0000;
    border-radius: 4px;
    padding: 1.6rem 1.8rem;
    margin: 1.2rem 0;
}
.rcard-course {
    font-family: 'DM Mono', monospace;
    font-size: 1.3rem;
    font-weight: 500;
    color: #f0f0f0;
    letter-spacing: -0.3px;
}
.rcard-semester {
    font-size: 0.8rem;
    color: #666;
    margin-top: 0.15rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}
.prob-block {
    margin: 1.4rem 0 0.4rem;
}
.prob-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #555;
    margin-bottom: 0.5rem;
}
.prob-num {
    font-family: 'DM Mono', monospace;
    font-size: 3rem;
    font-weight: 500;
    line-height: 1;
    margin-bottom: 0.6rem;
}
.prob-num.high   { color: #22c55e; }
.prob-num.medium { color: #f59e0b; }
.prob-num.low    { color: #cc0000; }
.prob-bar-track {
    height: 3px;
    background: #2a2a2a;
    border-radius: 2px;
    margin-bottom: 1.4rem;
}
.prob-bar-fill {
    height: 3px;
    border-radius: 2px;
    transition: width 0.3s ease;
}
.fill-high   { background: #22c55e; }
.fill-medium { background: #f59e0b; }
.fill-low    { background: #cc0000; }
.divider { border-top: 1px solid #2a2a2a; margin: 1.2rem 0; }
.stats-row {
    display: flex;
    gap: 2.5rem;
    margin-top: 1rem;
}
.stat-item {}
.stat-val {
    font-family: 'DM Mono', monospace;
    font-size: 1.7rem;
    font-weight: 500;
    color: #f0f0f0;
    line-height: 1;
}
.stat-lbl {
    font-size: 0.7rem;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-top: 0.2rem;
}
.fill-row {
    margin-top: 1.2rem;
}
.fill-row-label {
    font-size: 0.7rem;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 0.4rem;
}
.fill-track {
    height: 5px;
    background: #2a2a2a;
    border-radius: 3px;
}
.fill-inner {
    height: 5px;
    border-radius: 3px;
    background: #cc0000;
}
.badge {
    display: inline-block;
    font-family: 'DM Mono', monospace;
    font-size: 0.7rem;
    padding: 0.25rem 0.6rem;
    border-radius: 3px;
    margin-top: 0.8rem;
    margin-right: 0.4rem;
}
.badge-warn {
    background: #1a1200;
    color: #f59e0b;
    border: 1px solid #3a2a00;
}
.badge-cold {
    background: #0a0a1a;
    color: #818cf8;
    border: 1px solid #1e1b4b;
}
.disclaimer {
    font-size: 0.68rem;
    color: #444;
    margin-top: 1rem;
    font-style: italic;
}

/* ── about ── */
.about-body {
    font-size: 0.9rem;
    color: #aaa;
    line-height: 1.7;
}
.metric-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: #2a2a2a;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    overflow: hidden;
    margin: 1.2rem 0;
}
.metric-cell {
    background: #161616;
    padding: 1.2rem 1.4rem;
}
.metric-cell-val {
    font-family: 'DM Mono', monospace;
    font-size: 1.6rem;
    font-weight: 500;
    color: #cc0000;
    line-height: 1;
}
.metric-cell-lbl {
    font-size: 0.72rem;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-top: 0.3rem;
}
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    margin: 1rem 0;
}
.data-table td {
    padding: 0.5rem 0;
    border-bottom: 1px solid #1e1e1e;
    color: #aaa;
}
.data-table td:first-child {
    color: #555;
    font-family: 'DM Mono', monospace;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    width: 40%;
}

/* ── hide chrome ── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
.stDeployButton { display: none; }

/* ── streamlit overrides ── */
.stChatInput textarea {
    background: #161616 !important;
    border: 1px solid #2a2a2a !important;
    color: #f0f0f0 !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stButton > button {
    background: #cc0000 !important;
    color: white !important;
    border: none !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    border-radius: 4px !important;
}
.stButton > button:hover {
    background: #aa0000 !important;
}
.stSelectbox label, .stSelectbox > div {
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stTab"] {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
    letter-spacing: 1px !important;
}
</style>
""", unsafe_allow_html=True)

import controller
import gemini as gm
from context import get_all_context


@st.cache_resource
def _get_gemini():
    return gm.get_client()


@st.cache_data
def _get_context() -> dict:
    return get_all_context()


@st.cache_data
def _get_eval_results() -> dict:
    path = Path(__file__).parent / "models" / "eval_results.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


# ── result renderer ───────────────────────────────────────────────────────────
def render_result(result: dict):
    if result["status"] == "error":
        st.error(result["error"])
        return

    dept       = result["dept"]
    course_num = result["course_num"]
    semester   = result["semester"].capitalize()
    year       = result["year"]
    prob       = result["offered_prob"]
    capacity   = result["capacity"]
    enrollment = result["enrollment"]
    fill_rate  = (enrollment / capacity) if capacity > 0 else 0

    # ── course title header (simple inline styles — reliable in all ST versions)
    prob_color = "#22c55e" if prob >= 0.70 else ("#f59e0b" if prob >= 0.30 else "#cc0000")
    st.markdown(
        f'<div style="border-left:3px solid {prob_color};padding:0.6rem 1rem;'
        f'margin-bottom:0.8rem;background:#161616;border-radius:0 4px 4px 0;">'
        f'<span style="font-family:DM Mono,monospace;font-size:1.1rem;'
        f'font-weight:500;color:#f0f0f0;">{dept} {course_num}</span>'
        f'&nbsp;&nbsp;<span style="font-size:0.78rem;color:#666;'
        f'text-transform:uppercase;letter-spacing:1.5px;">{semester} {year}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── probability
    st.markdown(
        f'<div style="font-family:DM Mono,monospace;font-size:0.65rem;'
        f'letter-spacing:2px;text-transform:uppercase;color:#555;'
        f'margin-bottom:0.3rem;">Offered probability</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="font-family:DM Mono,monospace;font-size:2.4rem;'
        f'font-weight:500;color:{prob_color};line-height:1;'
        f'margin-bottom:0.5rem;">{prob * 100:.1f}%</div>',
        unsafe_allow_html=True,
    )
    st.progress(prob)

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    # ── enrollment / capacity / fill
    c1, c2, c3 = st.columns(3)
    c1.metric("Expected enrolled", f"{enrollment:,}")
    c2.metric("Expected capacity", f"{capacity:,}")
    c3.metric("Est. fill rate",    f"{fill_rate * 100:.0f}%")

    st.markdown(
        '<div style="font-family:DM Mono,monospace;font-size:0.65rem;'
        'letter-spacing:2px;text-transform:uppercase;color:#555;'
        'margin:0.8rem 0 0.3rem;">Fill rate</div>',
        unsafe_allow_html=True,
    )
    st.progress(min(fill_rate, 1.0))

    # ── flags
    if result["is_cold_start"]:
        st.info("◈ Cold start — no historical data. Predictions use static features only.")
    if result["is_unlikely"]:
        st.warning(f"⚠ Only {prob * 100:.0f}% chance of running. Seat estimates may be unreliable.")

    ev        = _get_eval_results()
    test_term = ev.get("test_term", "latest term").title()
    st.caption(f"Evaluated on {test_term} · Estimates only")


# ── Gemini prompt builders ────────────────────────────────────────────────────


# ── page header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="header">
    <div class="header-eyebrow">SFU · ML Project</div>
    <div class="header-title">Course Predictor</div>
    <div class="header-sub">Will this course run? How full will it be?</div>
</div>
""", unsafe_allow_html=True)

ctx    = _get_context()
gemini = _get_gemini()
ev     = _get_eval_results()

tab_chat, tab_manual, tab_about = st.tabs(["CHAT", "MANUAL", "ABOUT"])


# ════════════════════════════════════════════════════════════════════════════
# CHAT TAB
# ════════════════════════════════════════════════════════════════════════════
with tab_chat:
    if gemini is None:
        st.error("Gemini API key not found. Add GEMINI_API_KEY to .env")
    else:
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # clear button
        if st.session_state.messages:
            if st.button("Clear chat", key="clear"):
                st.session_state.messages = []
                st.rerun()

        # render history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if msg.get("result"):
                    render_result(msg["result"])
                st.markdown(msg["content"])

        # hint on empty
        if not st.session_state.messages:
            st.markdown(
                '<div style="color:#444;font-size:0.85rem;margin:1rem 0 0.5rem;">'
                'Try asking: <em>"Will CMPT 225 run in Fall 2027?"</em> or '
                '<em>"How full is MATH 151 in Spring 2028?"</em></div>',
                unsafe_allow_html=True
            )

        user_input = st.chat_input("Ask about any SFU course...")

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input, "result": None})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.spinner(""):
                extracted = gm.extract_params(gemini, ctx, user_input)

            if "error" in extracted:
                reply = extracted["error"]
                st.session_state.messages.append({"role": "assistant", "content": reply, "result": None})
                with st.chat_message("assistant"):
                    st.markdown(reply)
            else:
                result = controller.predict(
                    extracted["dept"],
                    extracted["course_num"],
                    extracted["semester"],
                    int(extracted["year"]),
                )
                reply = gm.format_response(gemini, result, user_input)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": reply,
                    "result": result if result["status"] == "ok" else None,
                })
                with st.chat_message("assistant"):
                    render_result(result)
                    st.markdown(reply)


# ════════════════════════════════════════════════════════════════════════════
# MANUAL TAB
# ════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)

    depts         = sorted(ctx["depts"])
    selected_dept = st.selectbox("Department", depts, key="m_dept")

    dept_courses  = [c for c in ctx["course_pairs"] if c["dept"] == selected_dept]
    course_labels = [
        f"{c['course_num']}  —  {c['title']}" if c["title"] else c["course_num"]
        for c in dept_courses
    ]
    sel_label     = st.selectbox("Course", course_labels, key="m_course")
    sel_num       = dept_courses[course_labels.index(sel_label)]["course_num"]

    c1, c2 = st.columns(2)
    with c1:
        sel_semester = st.selectbox("Semester", ctx["semesters"], key="m_sem")
    with c2:
        yr_min = ctx["year_range"]["min"]
        yr_max = ctx["year_range"]["max"]
        sel_year = st.selectbox("Year", list(range(yr_min, yr_max + 1)), key="m_yr")

    st.markdown('<div style="height:0.3rem"></div>', unsafe_allow_html=True)

    if st.button("Run prediction", type="primary", use_container_width=True):
        with st.spinner(""):
            res = controller.predict(selected_dept, sel_num, sel_semester, sel_year)
        render_result(res)


# ════════════════════════════════════════════════════════════════════════════
# ABOUT TAB
# ════════════════════════════════════════════════════════════════════════════
with tab_about:
    st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)

    st.markdown("""
<div class="about-body">
A machine learning system that predicts future SFU course offerings using
historical enrollment data. Given any course, semester, and year,
it returns offering probability, expected seat capacity, and expected enrollment.
</div>
""", unsafe_allow_html=True)

    st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)

    # ── metric grid (dynamic from eval_results.json) ──────────────────────
    auc            = ev.get("offered",    {}).get("auc",              "—")
    fully_correct  = ev.get("system",     {}).get("fully_correct_pct","—")
    cap_mae        = ev.get("capacity",   {}).get("mae",              "—")
    enr_mae        = ev.get("enrollment", {}).get("mae",              "—")
    test_term      = ev.get("test_term",  "latest term").title()

    auc_str = f"{auc:.3f}"          if isinstance(auc,           float) else str(auc)
    fc_str  = f"{fully_correct:.0f}%" if isinstance(fully_correct, float) else str(fully_correct)
    cap_str = f"{cap_mae:.1f}"      if isinstance(cap_mae,        float) else str(cap_mae)
    enr_str = f"{enr_mae:.1f}"      if isinstance(enr_mae,        float) else str(enr_mae)

    st.markdown(f"""
<div class="metric-grid">
    <div class="metric-cell">
        <div class="metric-cell-val">{auc_str}</div>
        <div class="metric-cell-lbl">Offered AUC ({test_term})</div>
    </div>
    <div class="metric-cell">
        <div class="metric-cell-val">{fc_str}</div>
        <div class="metric-cell-lbl">Fully correct (3/3)</div>
    </div>
    <div class="metric-cell">
        <div class="metric-cell-val">{cap_str}</div>
        <div class="metric-cell-lbl">Capacity MAE (seats)</div>
    </div>
    <div class="metric-cell">
        <div class="metric-cell-val">{enr_str}</div>
        <div class="metric-cell-lbl">Enrollment MAE (students)</div>
    </div>
</div>
""", unsafe_allow_html=True)

    # ── system score bar chart ────────────────────────────────────────────
    sys_scores = ev.get("system", {})
    s3 = sys_scores.get("fully_correct_pct", 0)
    s2 = sys_scores.get("one_wrong_pct",     0)
    s1 = sys_scores.get("two_wrong_pct",     0)
    s0 = sys_scores.get("all_wrong_pct",     0)

    def _bar(pct, color, label):
        w = max(pct, 1)
        return (
            f'<div style="margin-bottom:0.6rem;">'
            f'<div style="font-family:DM Mono,monospace;font-size:0.65rem;'
            f'letter-spacing:1.5px;text-transform:uppercase;color:#555;'
            f'margin-bottom:0.25rem;">{label}</div>'
            f'<div style="display:flex;align-items:center;gap:0.6rem;">'
            f'<div style="flex:1;height:6px;background:#1e1e1e;border-radius:3px;">'
            f'<div style="width:{w}%;height:6px;background:{color};border-radius:3px;"></div>'
            f'</div>'
            f'<span style="font-family:DM Mono,monospace;font-size:0.75rem;'
            f'color:#aaa;min-width:3rem;text-align:right;">{pct:.1f}%</span>'
            f'</div></div>'
        )

    st.markdown(
        '<div style="margin:1rem 0 0.3rem;font-family:DM Mono,monospace;'
        'font-size:0.65rem;letter-spacing:2px;text-transform:uppercase;'
        'color:#555;">System accuracy — all 3 predictions simultaneously</div>',
        unsafe_allow_html=True
    )
    st.markdown(
        _bar(s3, "#22c55e", "3/3 — Fully correct") +
        _bar(s2, "#aec7e8", "2/3 — One wrong") +
        _bar(s1, "#f59e0b", "1/3 — Two wrong") +
        _bar(s0, "#cc0000", "0/3 — All wrong"),
        unsafe_allow_html=True
    )

    one_wrong_pct = s2
    all_wrong_pct = s0
    st.markdown(
        f'<div class="disclaimer" style="margin-top:0.3rem">'
        f'Evaluated on {test_term}. '
        f'"Fully correct" = all three predictions within ±10 seats/students or ±20%. '
        f'Only {all_wrong_pct:.0f}% of courses were completely wrong across all three predictions.'
        f'</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.markdown(f"""
<table class="data-table">
    <tr><td>Source</td><td>SFU Coursys API</td></tr>
    <tr><td>Evaluation term</td><td>{test_term}</td></tr>
    <tr><td>Offered model</td><td>Gradient Boosting</td></tr>
    <tr><td>Capacity model</td><td>Random Forest</td></tr>
    <tr><td>Enrollment model</td><td>Random Forest</td></tr>
</table>
""", unsafe_allow_html=True)

    st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)
    st.link_button(
        "View on GitHub →",
        "https://github.com/chaitanya-maddala/SFU_offering_predictor",
    )