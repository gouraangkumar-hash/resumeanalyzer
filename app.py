"""Web application for Resume & Job Match Evaluator.

Provides a clean, high-contrast editorial interface to upload or paste both a
candidate resume and a target job description (.pdf, .docx, .txt, or plain text),
review live category sub-scores and skill alignment, customize summary and bullet
revisions, inspect local resume formatting health and targeted interview questions,
and export reports in PDF, Markdown, or JSON format.
"""

import hashlib
import html
from pathlib import Path
from typing import Dict, Optional
import streamlit as st

from src.pdf_parser import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    extract_text_from_document,
    get_pdf_page_count,
)
from src.pii import redact_pii
from src.resume_health import analyze_resume_health
from src.analyzer import analyze_resume
from src.schemas import ExtractionResult, ResumeAnalysisResult
from src.ui_helpers import (
    apply_placeholder_values,
    compute_rubric_status,
    escape_streamlit_markdown,
    extract_placeholders,
    format_bullet_with_badges_html,
    generate_json_report,
    generate_markdown_report,
    generate_pdf_report,
    get_category_breakdown,
    highlight_skills_in_text,
    render_svg_gauge_html,
)

# ---------------------------------------------------------------------------
# Page Configuration (Zero Emojis)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Resume & Job Match Evaluator",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Clean Light Editorial CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
/* Base Container & Readable Typography */
.stApp {
    background-color: #f8fafc;
    color: #0f172a;
}
.block-container {
    padding-top: 2.25rem !important;
    padding-bottom: 4rem !important;
    max-width: 1200px !important;
}

/* Editorial Header */
.ed-header {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.75rem 2rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.ed-eyebrow {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #2563eb;
    margin-bottom: 0.4rem;
}
.ed-title {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #0f172a;
    margin: 0 0 0.5rem 0;
    line-height: 1.25;
}
.ed-subtitle {
    font-size: 1.02rem;
    color: #475569;
    line-height: 1.6;
    margin: 0 0 1rem 0;
    max-width: 840px;
}
.ed-note {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #64748b;
    border-radius: 8px;
    padding: 0.65rem 1rem;
    color: #475569;
    font-size: 0.88rem;
    line-height: 1.5;
}

/* Surface Cards */
.ed-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.card-label {
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    margin-bottom: 0.35rem;
}
.card-heading {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 0.6rem 0;
}
.card-body {
    font-size: 0.98rem;
    color: #334155;
    line-height: 1.68;
    margin: 0;
    white-space: pre-line;
}

/* Summary Metric Strip */
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.15rem 1.35rem;
    height: 100%;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.kpi-title {
    color: #64748b;
    font-size: 0.76rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.35rem;
}
.kpi-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.15;
}
.kpi-sub {
    font-size: 0.85rem;
    color: #475569;
    margin-top: 0.35rem;
}

/* SVG Circular Gauge */
.gauge-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.5rem 1.25rem;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.gauge-svg-wrap {
    position: relative;
    width: 168px;
    height: 168px;
    margin: 0 auto 0.75rem auto;
}
.gauge-svg {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
}
.gauge-track {
    fill: none;
    stroke: #e2e8f0;
    stroke-width: 12;
}
.gauge-fill {
    fill: none;
    stroke-width: 12;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.6s ease;
}
.gauge-center-text {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.gauge-score-num {
    font-size: 2.5rem;
    font-weight: 700;
    line-height: 1;
}
.gauge-score-max {
    font-size: 0.85rem;
    color: #64748b;
    font-weight: 500;
    margin-top: 0.25rem;
}
.gauge-tier-pill {
    display: inline-block;
    padding: 0.28rem 0.85rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 0.35rem;
}
.gauge-caption {
    font-size: 0.8rem;
    color: #64748b;
}

/* Scoring Category Bars */
.weight-row {
    margin-bottom: 0.65rem;
}
.weight-label-line {
    display: flex;
    justify-content: space-between;
    font-size: 0.86rem;
    color: #334155;
    margin-bottom: 0.22rem;
}
.weight-bar-bg {
    height: 7px;
    background: #f1f5f9;
    border-radius: 999px;
    overflow: hidden;
}
.weight-bar-fill {
    height: 100%;
    border-radius: 999px;
    background: #2563eb;
    transition: width 0.4s ease;
}

/* Skill & Health Status Tags */
.pill-container {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.7rem;
}
.skill-pill {
    display: inline-flex;
    align-items: center;
    padding: 0.34rem 0.8rem;
    border-radius: 6px;
    font-size: 0.86rem;
    font-weight: 600;
    line-height: 1.25;
}
.skill-pill-matched {
    background: #f0fdf4;
    color: #166534;
    border: 1px solid #bbf7d0;
}
.skill-pill-missing {
    background: #fef2f2;
    color: #991b1b;
    border: 1px solid #fecaca;
}
.skill-pill-amber {
    background: #fffbeb;
    color: #92400e;
    border: 1px solid #fde68a;
}
.skill-pill-neutral {
    background: #f8fafc;
    color: #334155;
    border: 1px solid #cbd5e1;
}

/* Priority & Interview Question Cards */
.priority-card {
    display: flex;
    align-items: flex-start;
    gap: 0.95rem;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #2563eb;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}
.priority-num {
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
    font-weight: 700;
    font-size: 0.85rem;
    min-width: 2rem;
    height: 2rem;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.priority-text {
    color: #1e293b;
    font-size: 0.97rem;
    line-height: 1.58;
    white-space: pre-line;
}

/* Personalized Interview Prep Cards */
.iq-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #0d9488;
    border-radius: 12px;
    padding: 1.25rem 1.45rem;
    margin-bottom: 0.9rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}
.iq-meta-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.7rem;
}
.iq-badge-num {
    background: #f0fdfa;
    color: #0f766e;
    border: 1px solid #99f6e4;
    font-weight: 700;
    font-size: 0.78rem;
    padding: 0.22rem 0.6rem;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.iq-badge-anchor {
    background: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.22rem 0.65rem;
    border-radius: 6px;
}
.iq-badge-focus {
    background: #f8fafc;
    color: #334155;
    border: 1px solid #cbd5e1;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.22rem 0.65rem;
    border-radius: 6px;
}
.iq-question {
    font-size: 1.03rem;
    font-weight: 600;
    color: #0f172a;
    line-height: 1.62;
    margin: 0 0 0.75rem 0;
    white-space: pre-line;
}
.iq-prep-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0.75rem 0.95rem;
    font-size: 0.92rem;
    color: #334155;
    line-height: 1.6;
    white-space: pre-line;
}

/* Summary & Bullet Revision Cards */
.summary-draft-box {
    background: #f8fafc;
    border: 1px solid #bfdbfe;
    border-left: 4px solid #2563eb;
    border-radius: 10px;
    padding: 1.1rem 1.35rem;
    color: #0f172a;
    font-size: 0.98rem;
    line-height: 1.68;
}
.bullet-box-orig {
    background: #fffafa;
    border: 1px solid #fecaca;
    border-left: 3px solid #dc2626;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: #1e293b;
    font-size: 0.96rem;
    line-height: 1.62;
    height: 100%;
}
.bullet-box-new {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-left: 3px solid #16a34a;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    color: #0f172a;
    font-size: 0.96rem;
    line-height: 1.62;
    height: 100%;
}
.bullet-tag {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.4rem;
}
.placeholder-badge {
    background: #fef3c7;
    color: #92400e;
    border: 1px dashed #d97706;
    padding: 0.08rem 0.42rem;
    border-radius: 4px;
    font-weight: 700;
    font-family: monospace;
}
.placeholder-filled {
    background: #dcfce7;
    color: #166534;
    border: 1px solid #16a34a;
}

/* Highlighted Document Reader */
.resume-viewer {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    padding: 1.35rem 1.5rem;
    font-size: 0.95rem;
    line-height: 1.72;
    color: #1e293b;
    max-height: 460px;
    overflow-y: auto;
}
mark.kw-highlight {
    background: #dcfce7;
    color: #14532d;
    border-bottom: 2px solid #16a34a;
    padding: 0.06rem 0.32rem;
    border-radius: 3px;
    font-weight: 600;
}

/* Loaded File Status Strip */
.status-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    align-items: center;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 0.55rem 0.85rem;
    font-size: 0.85rem;
    color: #166534;
    margin-top: 0.5rem;
    margin-bottom: 0.4rem;
}

/* Tab Label Readability */
button[data-baseweb="tab"] p {
    font-size: 0.92rem !important;
    font-weight: 600 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
defaults = {
    "active_resume_text": "",
    "active_resume_source": "",
    "resume_page_count": None,
    "resume_pii_count": 0,
    "resume_error": None,
    "active_jd_text": "",
    "active_jd_source": "",
    "jd_pii_count": 0,
    "jd_error": None,
    "custom_bullets": {},
    "custom_summary": "",
    "interview_notes": {},
    "evaluated_resume_text": "",
    "evaluated_resume_pages": None,
    "analysis_run_id": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _compute_upload_signature(uploaded_file) -> str:
    """Computes a content-based SHA-256 signature for an uploaded file."""
    raw_bytes = uploaded_file.getvalue()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    return f"{uploaded_file.name}:{len(raw_bytes)}:{digest}"


def _sync_resume_paste() -> None:
    raw_txt = st.session_state.get("_resume_paste_widget", "")
    scrubbed_txt, pii_stats = redact_pii(raw_txt)
    st.session_state["_resume_paste_widget"] = scrubbed_txt
    st.session_state["active_resume_text"] = scrubbed_txt
    st.session_state["active_resume_source"] = (
        "Pasted Resume Text" if scrubbed_txt.strip() else ""
    )
    st.session_state["resume_page_count"] = None
    st.session_state["resume_pii_count"] = pii_stats["total"]
    st.session_state["resume_error"] = None
    st.session_state.pop("_last_resume_sig", None)


def _sync_jd_paste() -> None:
    raw_txt = st.session_state.get("_jd_paste_widget", "")
    scrubbed_txt, pii_stats = redact_pii(raw_txt)
    st.session_state["_jd_paste_widget"] = scrubbed_txt
    st.session_state["active_jd_text"] = scrubbed_txt
    st.session_state["active_jd_source"] = (
        "Pasted Job Description Text" if scrubbed_txt.strip() else ""
    )
    st.session_state["jd_pii_count"] = pii_stats["total"]
    st.session_state["jd_error"] = None
    st.session_state.pop("_last_jd_sig", None)


def _clear_old_placeholder_widget_keys() -> None:
    """Removes placeholder and interview note widget state keys from prior evaluation runs."""
    stale_keys = [
        k
        for k in st.session_state.keys()
        if k.startswith("run_")
        and ("_bullet_" in k or "_summary_" in k or "_iq_note_" in k)
    ]
    for k in stale_keys:
        st.session_state.pop(k, None)


def _tone_pill_class(tone: str) -> str:
    if tone == "good":
        return "skill-pill-matched"
    if tone == "fair":
        return "skill-pill-amber"
    return "skill-pill-missing"


# ---------------------------------------------------------------------------
# Editorial Header
# ---------------------------------------------------------------------------
st.markdown(
    """
<div class="ed-header">
    <div class="ed-eyebrow">Career &amp; Application Review</div>
    <h1 class="ed-title">Resume &amp; Job Match Evaluator</h1>
    <p class="ed-subtitle">
        Upload or paste a resume and a target job description (.pdf, .docx, .txt, or text) to measure
        category alignment, identify missing qualifications, draft stronger summary and bullet statements,
        check formatting health, and prepare for role-specific interview questions.
    </p>
    <div class="ed-note">
        <strong>Note:</strong> Match scores and feedback are automated estimates intended for self-review.
        Personal contact details (emails, phone numbers, profile links, and ID numbers) are masked locally before evaluation.
        This tool does not simulate proprietary company ATS software and does not predict hiring decisions.
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Symmetrical Input Section: Candidate Resume & Job Description
# ---------------------------------------------------------------------------
col_resume, col_jd = st.columns(2, gap="large")

# ---- Left Column: Candidate Resume ----
with col_resume:
    st.markdown('<div class="card-label">Step 1 - Candidate Document</div>', unsafe_allow_html=True)
    st.subheader("Candidate Resume")

    resume_mode = st.radio(
        "Resume input method",
        options=["Upload File", "Paste Text"],
        horizontal=True,
        key="resume_input_mode",
        label_visibility="collapsed",
    )

    uploaded_resume_file = None
    if resume_mode == "Upload File":
        uploaded_resume_file = st.file_uploader(
            "Select a Resume file (.pdf, .docx, or .txt)",
            type=list(SUPPORTED_UPLOAD_EXTENSIONS),
            key="resume_file_uploader",
            help="Supports text-selectable PDFs (up to 10 pages), Word (.docx), and plain text (.txt) files.",
        )
        if uploaded_resume_file is not None:
            sig = _compute_upload_signature(uploaded_resume_file)
            if st.session_state.get("_last_resume_sig") != sig:
                st.session_state["_last_resume_sig"] = sig
                try:
                    raw_bytes = uploaded_resume_file.getvalue()
                    raw_res = extract_text_from_document(
                        raw_bytes,
                        filename=uploaded_resume_file.name,
                        document_name="Resume",
                    )
                    parsed_res, res_pii = redact_pii(raw_res)
                    is_pdf = Path(uploaded_resume_file.name).suffix.lower() == ".pdf"
                    st.session_state["active_resume_text"] = parsed_res
                    st.session_state["active_resume_source"] = (
                        f"{uploaded_resume_file.name} ({uploaded_resume_file.size / 1024:.1f} KB)"
                    )
                    st.session_state["resume_page_count"] = (
                        get_pdf_page_count(raw_bytes) if is_pdf else None
                    )
                    st.session_state["resume_pii_count"] = res_pii["total"]
                    st.session_state["resume_error"] = None
                except ValueError as ve:
                    st.session_state["active_resume_text"] = ""
                    st.session_state["active_resume_source"] = ""
                    st.session_state["resume_page_count"] = None
                    st.session_state["resume_pii_count"] = 0
                    st.session_state["resume_error"] = str(ve)
                except Exception as exc:
                    st.session_state["active_resume_text"] = ""
                    st.session_state["active_resume_source"] = ""
                    st.session_state["resume_page_count"] = None
                    st.session_state["resume_pii_count"] = 0
                    st.session_state["resume_error"] = f"Could not read Resume file: {exc}"
        elif st.session_state.get("_last_resume_sig") is not None:
            st.session_state.pop("_last_resume_sig", None)
            st.session_state["active_resume_text"] = ""
            st.session_state["active_resume_source"] = ""
            st.session_state["resume_page_count"] = None
            st.session_state["resume_pii_count"] = 0
            st.session_state["resume_error"] = None
    else:
        st.text_area(
            "Paste resume text:",
            value=st.session_state["active_resume_text"],
            height=210,
            key="_resume_paste_widget",
            on_change=_sync_resume_paste,
            placeholder="Paste the candidate's full resume text (summary, skills, experience, projects, education)...",
        )

    if st.session_state.get("resume_error"):
        st.error(st.session_state["resume_error"])

    active_res_txt = st.session_state.get("active_resume_text", "")
    active_res_src = st.session_state.get("active_resume_source", "")
    res_pii_count = st.session_state.get("resume_pii_count", 0)
    if active_res_txt.strip():
        res_words = len(active_res_txt.split())
        res_chars = len(active_res_txt)
        res_privacy_label = (
            f"{res_pii_count} personal contact item{'s' if res_pii_count != 1 else ''} masked"
            if res_pii_count > 0
            else "Privacy filter active"
        )
        st.markdown(
            f"""
            <div class="status-strip">
                <span><strong>Ready:</strong> {html.escape(active_res_src or 'Resume Text')}</span>
                <span>|</span>
                <span>{res_words:,} words</span>
                <span>|</span>
                <span>{res_chars:,} characters</span>
                <span>|</span>
                <span>{res_privacy_label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if resume_mode == "Upload File":
            with st.expander("Preview extracted resume text"):
                st.text_area(
                    "Extracted Resume Preview",
                    value=active_res_txt,
                    height=160,
                    disabled=True,
                    label_visibility="collapsed",
                )
    elif resume_mode == "Upload File":
        st.caption("Upload a .pdf, .docx, or .txt resume file, or switch to Paste Text.")

# ---- Right Column: Job Description ----
with col_jd:
    st.markdown('<div class="card-label">Step 2 - Target Role</div>', unsafe_allow_html=True)
    st.subheader("Job Description")

    jd_mode = st.radio(
        "Job Description input method",
        options=["Upload File", "Paste Text"],
        horizontal=True,
        key="jd_input_mode",
        label_visibility="collapsed",
    )

    uploaded_jd_file = None
    if jd_mode == "Upload File":
        uploaded_jd_file = st.file_uploader(
            "Select a Job Description file (.pdf, .docx, or .txt)",
            type=list(SUPPORTED_UPLOAD_EXTENSIONS),
            key="jd_file_uploader",
            help="Upload a .pdf, .docx, or .txt job posting, or switch to Paste Text to enter requirements directly.",
        )
        if uploaded_jd_file is not None:
            jd_sig = _compute_upload_signature(uploaded_jd_file)
            if st.session_state.get("_last_jd_sig") != jd_sig:
                st.session_state["_last_jd_sig"] = jd_sig
                try:
                    raw_jd = extract_text_from_document(
                        uploaded_jd_file.getvalue(),
                        filename=uploaded_jd_file.name,
                        document_name="Job Description",
                    )
                    parsed_jd, jd_pii = redact_pii(raw_jd)
                    st.session_state["active_jd_text"] = parsed_jd
                    st.session_state["active_jd_source"] = (
                        f"{uploaded_jd_file.name} ({uploaded_jd_file.size / 1024:.1f} KB)"
                    )
                    st.session_state["jd_pii_count"] = jd_pii["total"]
                    st.session_state["jd_error"] = None
                except ValueError as ve:
                    st.session_state["active_jd_text"] = ""
                    st.session_state["active_jd_source"] = ""
                    st.session_state["jd_pii_count"] = 0
                    st.session_state["jd_error"] = str(ve)
                except Exception as exc:
                    st.session_state["active_jd_text"] = ""
                    st.session_state["active_jd_source"] = ""
                    st.session_state["jd_pii_count"] = 0
                    st.session_state["jd_error"] = f"Could not read Job Description file: {exc}"
        elif st.session_state.get("_last_jd_sig") is not None:
            st.session_state.pop("_last_jd_sig", None)
            st.session_state["active_jd_text"] = ""
            st.session_state["active_jd_source"] = ""
            st.session_state["jd_pii_count"] = 0
            st.session_state["jd_error"] = None
    else:
        st.text_area(
            "Paste job description text:",
            value=st.session_state["active_jd_text"],
            height=210,
            key="_jd_paste_widget",
            on_change=_sync_jd_paste,
            placeholder="Paste required skills, preferred qualifications, and core responsibilities...",
        )

    if st.session_state.get("jd_error"):
        st.error(st.session_state["jd_error"])

    active_jd_txt = st.session_state.get("active_jd_text", "")
    active_jd_src = st.session_state.get("active_jd_source", "")
    jd_pii_count = st.session_state.get("jd_pii_count", 0)
    if active_jd_txt.strip():
        jd_words = len(active_jd_txt.split())
        jd_chars = len(active_jd_txt)
        jd_privacy_label = (
            f"{jd_pii_count} contact item{'s' if jd_pii_count != 1 else ''} masked"
            if jd_pii_count > 0
            else "Privacy filter active"
        )
        st.markdown(
            f"""
            <div class="status-strip">
                <span><strong>Ready:</strong> {html.escape(active_jd_src or 'Job Description Text')}</span>
                <span>|</span>
                <span>{jd_words:,} words</span>
                <span>|</span>
                <span>{jd_chars:,} characters</span>
                <span>|</span>
                <span>{jd_privacy_label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if jd_mode == "Upload File":
            with st.expander("Preview extracted job description text"):
                st.text_area(
                    "Extracted Job Description Preview",
                    value=active_jd_txt,
                    height=160,
                    disabled=True,
                    label_visibility="collapsed",
                )
    elif jd_mode == "Upload File":
        st.caption("Upload a .pdf, .docx, or .txt job posting, or switch to Paste Text.")

# ---------------------------------------------------------------------------
# Trigger Evaluation
# ---------------------------------------------------------------------------
st.markdown("<div style='height: 0.65rem'></div>", unsafe_allow_html=True)
evaluate_clicked = st.button(
    "Evaluate Resume Against Job Description",
    type="primary",
    use_container_width=True,
)

if evaluate_clicked:
    resume_ready = st.session_state.get("active_resume_text", "").strip()
    jd_ready = st.session_state.get("active_jd_text", "").strip()

    if not resume_ready and uploaded_resume_file is not None:
        try:
            raw_bytes = uploaded_resume_file.getvalue()
            raw_res = extract_text_from_document(
                raw_bytes, filename=uploaded_resume_file.name, document_name="Resume"
            )
            resume_ready, res_pii = redact_pii(raw_res)
            is_pdf = Path(uploaded_resume_file.name).suffix.lower() == ".pdf"
            st.session_state["active_resume_text"] = resume_ready
            st.session_state["active_resume_source"] = uploaded_resume_file.name
            st.session_state["resume_page_count"] = (
                get_pdf_page_count(raw_bytes) if is_pdf else None
            )
            st.session_state["resume_pii_count"] = res_pii["total"]
        except Exception as exc:
            st.error(str(exc))

    if not jd_ready and uploaded_jd_file is not None:
        try:
            raw_jd = extract_text_from_document(
                uploaded_jd_file.getvalue(),
                filename=uploaded_jd_file.name,
                document_name="Job Description",
            )
            jd_ready, jd_pii = redact_pii(raw_jd)
            st.session_state["active_jd_text"] = jd_ready
            st.session_state["active_jd_source"] = uploaded_jd_file.name
            st.session_state["jd_pii_count"] = jd_pii["total"]
        except Exception as exc:
            st.error(str(exc))

    if not resume_ready:
        st.warning("Please upload a Resume file (.pdf, .docx, .txt) or enter resume text before evaluating.")
    elif not jd_ready:
        st.warning("Please upload a Job Description file (.pdf, .docx, .txt) or enter job description text before evaluating.")
    else:
        with st.status("Reviewing resume and job description...", expanded=True) as status_box:
            st.write("Step 1 of 3: Verified readable text for both documents.")
            st.write("Step 2 of 3: Extracting skills, qualifications, and core responsibilities...")
            stage1_msg_slot = st.empty()
            stage2_msg_slot = st.empty()
            pending_extraction: Dict[str, ExtractionResult] = {}

            def _on_parsed_details(extracted: ExtractionResult) -> None:
                pending_extraction["value"] = extracted
                stage1_msg_slot.write(
                    f"Identified {len(extracted.resume_skills)} skills in the resume and "
                    f"{len(extracted.jd_required_skills)} required skills in the job description."
                )
                stage2_msg_slot.write(
                    "Step 3 of 3: Scoring category alignment, drafting revisions, and preparing interview questions..."
                )

            try:
                new_result: ResumeAnalysisResult = analyze_resume(
                    resume_text=resume_ready,
                    jd_text=jd_ready,
                    on_stage1_complete=_on_parsed_details,
                    redact_pii_enabled=False,  # Already masked locally in resume_ready / jd_ready
                )
                # Commit outputs atomically only after full pipeline success
                _clear_old_placeholder_widget_keys()
                st.session_state["analysis_run_id"] = st.session_state.get("analysis_run_id", 0) + 1
                st.session_state["analysis_result"] = new_result
                if "value" in pending_extraction:
                    st.session_state["extraction_result"] = pending_extraction["value"]
                else:
                    st.session_state.pop("extraction_result", None)
                st.session_state["evaluated_resume_text"] = resume_ready
                st.session_state["evaluated_resume_pages"] = st.session_state.get("resume_page_count")
                st.session_state["custom_bullets"] = {}
                st.session_state["custom_summary"] = new_result.suggested_summary
                st.session_state["interview_notes"] = {}
                status_box.update(
                    label=f"Evaluation complete — Match Score: {new_result.match_score} / 100",
                    state="complete",
                    expanded=False,
                )
            except ValueError as ve:
                status_box.update(label="Validation error", state="error", expanded=True)
                st.error(str(ve))
            except RuntimeError as re_err:
                status_box.update(label="Service error", state="error", expanded=True)
                st.error(str(re_err))
            except Exception as exc:
                status_box.update(label="Unexpected error", state="error", expanded=True)
                st.error(f"An unexpected error occurred: {exc}")

# ---------------------------------------------------------------------------
# Display Results Dashboard
# ---------------------------------------------------------------------------
if "analysis_result" in st.session_state:
    result: ResumeAnalysisResult = st.session_state["analysis_result"]
    extraction: Optional[ExtractionResult] = st.session_state.get("extraction_result")
    run_id: int = st.session_state.get("analysis_run_id", 0)
    eval_resume_txt: str = (
        st.session_state.get("evaluated_resume_text")
        or st.session_state.get("active_resume_text", "")
    )
    eval_resume_pages: Optional[int] = st.session_state.get("evaluated_resume_pages")

    meta = compute_rubric_status(result, extraction)
    breakdown = get_category_breakdown(result)
    health_report = analyze_resume_health(
        eval_resume_txt,
        page_count=eval_resume_pages,
        extraction=extraction,
    )

    st.markdown("---")

    # -----------------------------------------------------------------------
    # 1. Summary Metrics Strip
    # -----------------------------------------------------------------------
    m1, m2, m3, m4 = st.columns(4, gap="medium")

    with m1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Overall Match</div>
                <div class="kpi-value" style="color: {meta['tier_color']};">{result.match_score}<span style="font-size:1rem;color:#64748b;font-weight:500;"> / 100</span></div>
                <div class="kpi-sub">{html.escape(meta['tier_label'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Skill Coverage</div>
                <div class="kpi-value" style="color: #1d4ed8;">{meta['skill_coverage_pct']}%</div>
                <div class="kpi-sub">{meta['matched_count']} matched, {meta['missing_count']} missing</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Quantified Bullets</div>
                <div class="kpi-value">{health_report['quantification_pct']}%</div>
                <div class="kpi-sub">{health_report['quantified_bullets']} of {health_report['total_bullets']} bullets have metrics</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        cap_note = (
            "Score capped at 50 (missing core skills)"
            if meta["hard_cap_triggered"]
            else "Highest-impact edits prioritized"
        )
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Priority Actions</div>
                <div class="kpi-value">{len(result.priority_fixes)}</div>
                <div class="kpi-sub">{html.escape(cap_note)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 0.85rem'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # 2. Score Gauge & Live Category Sub-Scores
    # -----------------------------------------------------------------------
    g_col, exp_col = st.columns([1.0, 2.3], gap="large")

    with g_col:
        st.markdown(
            render_svg_gauge_html(
                score=result.match_score,
                tier_label=meta["tier_label"],
                tier_color=meta["tier_color"],
                tier_bg=meta["tier_bg"],
            ),
            unsafe_allow_html=True,
        )

    with exp_col:
        cap_alert_html = ""
        if meta["hard_cap_triggered"]:
            raw_sum_clause = (
                f" (raw category points totaled {meta['raw_subscore_sum']} / 100)"
                if meta["has_live_subscores"]
                and meta["raw_subscore_sum"] is not None
                and meta["raw_subscore_sum"] > 50
                else ""
            )
            cap_alert_html = (
                '<div style="background:#fef2f2;border:1px solid #fecaca;border-left:3px solid #dc2626;'
                'color:#991b1b;padding:0.65rem 0.95rem;border-radius:8px;font-size:0.9rem;margin-bottom:0.9rem;">'
                '<strong>Score Cap Applied:</strong> Because fewer than half of the required job skills appear in the resume, '
                f'the overall score cannot exceed 50 out of 100{html.escape(raw_sum_clause)}.'
                '</div>'
            )

        bars_heading = (
            "Earned Category Sub-Scores (100 Points Total)"
            if meta["has_live_subscores"]
            else "Scoring Rubric Weights (100 Points Total)"
        )
        bars_html_parts = []
        for row_idx, row in enumerate(breakdown):
            mb_style = "margin-bottom:0;" if row_idx == len(breakdown) - 1 else ""
            bars_html_parts.append(
                f'<div class="weight-row" style="{mb_style}">'
                f'<div class="weight-label-line"><span>{html.escape(str(row["label"]))}</span>'
                f'<strong>{html.escape(str(row["display"]))}</strong></div>'
                f'<div class="weight-bar-bg"><div class="weight-bar-fill" '
                f'style="width: {row["bar_pct"]}%; background: {row["color"]};"></div></div>'
                f'</div>'
            )
        bars_html = "".join(bars_html_parts)

        st.markdown(
            f"""
            <div class="ed-card" style="height: 100%; margin-bottom: 0;">
                <div class="card-label">Evaluation Summary</div>
                <h3 class="card-heading">How This Score Was Calculated</h3>
                {cap_alert_html}
                <p class="card-body" style="margin-bottom: 1.25rem;">{html.escape(result.score_explanation)}</p>
                <div class="card-label" style="margin-bottom: 0.55rem;">{bars_heading}</div>
                {bars_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.1rem'></div>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # 3. Clean Top-Level Navigation Tabs (No Nested Sub-Tabs)
    # -----------------------------------------------------------------------
    (
        tab_skills,
        tab_bullets,
        tab_feedback,
        tab_health,
        tab_interview,
        tab_requirements,
        tab_export,
    ) = st.tabs(
        [
            "Skills & Match",
            "Summary & Bullets",
            "Actions & Feedback",
            "Resume Health",
            "Interview Prep",
            "Parsed Details",
            "Download Report",
        ]
    )

    # =======================================================================
    # TAB 1: Skills Comparison & Highlighted Resume Text
    # =======================================================================
    with tab_skills:
        skill_query = st.text_input(
            "Filter skills",
            placeholder="Filter matched or missing skills by keyword...",
            label_visibility="collapsed",
        ).strip().lower()

        filtered_matched = [
            s for s in result.matched_skills if not skill_query or skill_query in s.lower()
        ]
        filtered_missing = [
            s for s in result.missing_skills if not skill_query or skill_query in s.lower()
        ]

        sk_col1, sk_col2 = st.columns(2, gap="large")

        with sk_col1:
            matched_html = (
                "".join(
                    f'<span class="skill-pill skill-pill-matched">{html.escape(s)}</span>'
                    for s in filtered_matched
                )
                if filtered_matched
                else '<span style="color:#64748b;">No matching skills found.</span>'
            )
            st.markdown(
                f"""
                <div class="ed-card">
                    <div class="card-label" style="color:#166534;">Found in Resume</div>
                    <h4 class="card-heading">Matched Skills ({len(filtered_matched)})</h4>
                    <div class="pill-container">{matched_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with sk_col2:
            missing_html = (
                "".join(
                    f'<span class="skill-pill skill-pill-missing">{html.escape(s)}</span>'
                    for s in filtered_missing
                )
                if filtered_missing
                else '<span style="color:#64748b;">No missing skills identified.</span>'
            )
            st.markdown(
                f"""
                <div class="ed-card">
                    <div class="card-label" style="color:#991b1b;">Not Found in Resume</div>
                    <h4 class="card-heading">Missing Skills ({len(filtered_missing)})</h4>
                    <div class="pill-container">{missing_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if eval_resume_txt:
            highlighted_html, hit_count = highlight_skills_in_text(
                eval_resume_txt, result.matched_skills
            )
            st.markdown(
                f"""
                <div class="ed-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.75rem;">
                        <div>
                            <div class="card-label">Document Keyword View</div>
                            <h4 class="card-heading" style="margin:0;">Resume Text with Matched Skills Highlighted</h4>
                        </div>
                        <span class="skill-pill skill-pill-matched">{hit_count} matches highlighted</span>
                    </div>
                    <div class="resume-viewer">{highlighted_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # =======================================================================
    # TAB 2: Tailored Summary Draft & Bullet Point Revisions
    # =======================================================================
    with tab_bullets:
        if result.suggested_summary:
            st.subheader("Tailored Professional Summary Draft")
            st.caption(
                "Written strictly from facts present on your resume and aligned to this job description."
            )
            sum_placeholders = extract_placeholders(result.suggested_summary)
            sum_replacements: Dict[str, str] = {}
            if sum_placeholders:
                st.caption("Enter your verified figures to fill in any bracketed placeholders:")
                sum_cols = st.columns(min(len(sum_placeholders), 4), gap="small")
                for sp_idx, token in enumerate(sum_placeholders):
                    with sum_cols[sp_idx % len(sum_cols)]:
                        s_val = st.text_input(
                            f"Value for {token}",
                            key=f"run_{run_id}_summary_ph_{sp_idx}_{token}",
                            placeholder=f"Enter value for {token}",
                        )
                        if s_val and s_val.strip():
                            sum_replacements[token] = s_val.strip()

            final_summary_str = apply_placeholder_values(
                result.suggested_summary, sum_replacements
            )
            st.session_state["custom_summary"] = final_summary_str
            formatted_summary_html = format_bullet_with_badges_html(
                result.suggested_summary, sum_replacements
            )
            st.markdown(
                f'<div class="summary-draft-box">{formatted_summary_html}</div>',
                unsafe_allow_html=True,
            )
            st.caption("Copy-ready summary:")
            st.code(final_summary_str, language=None)
            st.markdown("---")

        st.subheader("Bullet Point Revisions")
        st.markdown(
            """
            <div class="ed-card" style="padding: 1.1rem 1.4rem;">
                <p class="card-body"><strong>How to use these revisions:</strong> Each rewrite strengthens action verbs and connects your experience to the job description. Bracketed items such as <code>[X]</code> or <code>[N]</code> mark places where you should enter your own real numbers rather than guessing. Type your numbers into the fields below to update the bullet automatically.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if result.improved_bullets:
            for idx, bullet in enumerate(result.improved_bullets, start=1):
                placeholders = extract_placeholders(bullet.suggested_bullet)
                replacements: Dict[str, str] = {}

                st.markdown(f"#### Bullet Revision {idx}")

                if placeholders:
                    st.caption(
                        "Enter your actual figures below to replace the bracketed placeholders:"
                    )
                    input_cols = st.columns(min(len(placeholders), 4), gap="small")
                    for p_idx, token in enumerate(placeholders):
                        with input_cols[p_idx % len(input_cols)]:
                            user_val = st.text_input(
                                f"Value for {token}",
                                key=f"run_{run_id}_bullet_{idx}_ph_{p_idx}_{token}",
                                placeholder=f"Enter number for {token}",
                            )
                            if user_val and user_val.strip():
                                replacements[token] = user_val.strip()

                final_bullet_str = apply_placeholder_values(bullet.suggested_bullet, replacements)
                st.session_state["custom_bullets"][idx] = final_bullet_str
                formatted_new_html = format_bullet_with_badges_html(
                    bullet.suggested_bullet, replacements
                )

                b_col1, b_col2 = st.columns(2, gap="medium")
                with b_col1:
                    st.markdown(
                        f"""
                        <div class="bullet-box-orig">
                            <div class="bullet-tag" style="color:#991b1b;">Current Resume Bullet</div>
                            <div>{html.escape(bullet.original_bullet)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with b_col2:
                    st.markdown(
                        f"""
                        <div class="bullet-box-new">
                            <div class="bullet-tag" style="color:#166534;">Suggested Revision</div>
                            <div>{formatted_new_html}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown(
                    f"<div style='margin:0.65rem 0 0.35rem 0;font-size:0.92rem;color:#475569;'>"
                    f"<strong>Why this works:</strong> {html.escape(bullet.rationale)}</div>",
                    unsafe_allow_html=True,
                )
                st.caption("Copy-ready text:")
                st.code(final_bullet_str, language=None)
                st.markdown("---")
        else:
            st.info("No bullet revisions were generated for this resume.")

    # =======================================================================
    # TAB 3: Priority Actions & Section-by-Section Feedback (Readable Grid)
    # =======================================================================
    with tab_feedback:
        st.subheader("Top Priority Improvements")
        for idx, fix in enumerate(result.priority_fixes, start=1):
            st.markdown(
                f"""
                <div class="priority-card">
                    <div class="priority-num">{idx}</div>
                    <div class="priority-text">{html.escape(fix)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
        st.subheader("Section-by-Section Feedback")

        sections = [
            ("Summary", result.section_feedback.summary, extraction.summary_section if extraction else None),
            ("Skills", result.section_feedback.skills, extraction.skills_section if extraction else None),
            ("Experience", result.section_feedback.experience, extraction.experience_section if extraction else None),
            ("Projects", result.section_feedback.projects, extraction.projects_section if extraction else None),
            ("Education", result.section_feedback.education, extraction.education_section if extraction else None),
        ]

        for row_start in range(0, len(sections), 2):
            row_items = sections[row_start : row_start + 2]
            grid_cols = st.columns(2, gap="medium")
            for col_obj, (sec_title, sec_fb, raw_sec) in zip(grid_cols, row_items):
                with col_obj:
                    status_badge = ""
                    if raw_sec is not None:
                        present = raw_sec.strip().lower() != "not present"
                        cls = "skill-pill-matched" if present else "skill-pill-missing"
                        lbl = "Included" if present else "Missing on Resume"
                        status_badge = (
                            f'<span class="skill-pill {cls}" style="font-size:0.74rem;padding:0.2rem 0.6rem;">{lbl}</span>'
                        )
                    st.markdown(
                        f"""
                        <div class="ed-card" style="height:100%;">
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.55rem;">
                                <h4 class="card-heading" style="margin:0;">{html.escape(sec_title)}</h4>
                                {status_badge}
                            </div>
                            <p class="card-body">{html.escape(sec_fb)}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        st.subheader("Areas to Strengthen")
        if result.weaknesses:
            for weakness in result.weaknesses:
                st.markdown(
                    f"""
                    <div class="ed-card" style="padding:0.9rem 1.25rem;border-left:3px solid #d97706;margin-bottom:0.6rem;">
                        <p class="card-body">{html.escape(weakness)}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No major weaknesses identified.")

    # =======================================================================
    # TAB 4: Local Resume Formatting & Writing Health Check
    # =======================================================================
    with tab_health:
        st.subheader("Resume Formatting & Writing Health")
        st.caption(
            "Instant document checks measuring length balance, quantified bullet coverage, active phrasing, and standard section structure."
        )

        hc1, hc2, hc3 = st.columns(3, gap="medium")
        pages_num = int(health_report["page_count"])  # type: ignore[arg-type]
        page_label = (
            f"{pages_num} PDF page{'s' if pages_num != 1 else ''}"
            if health_report["is_exact_pages"]
            else f"~{pages_num} estimated page{'s' if pages_num != 1 else ''}"
        )

        with hc1:
            len_cls = _tone_pill_class(str(health_report["length_tone"]))
            st.markdown(
                f"""
                <div class="ed-card" style="height:100%;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                        <span class="card-label" style="margin:0;">Length Balance</span>
                        <span class="skill-pill {len_cls}" style="font-size:0.75rem;padding:0.2rem 0.6rem;">{html.escape(str(health_report['length_status']))}</span>
                    </div>
                    <div class="kpi-value" style="margin-bottom:0.2rem;">{health_report['word_count']:,} <span style="font-size:0.95rem;color:#64748b;font-weight:500;">words</span></div>
                    <div class="kpi-sub" style="margin-bottom:0.6rem;">{html.escape(page_label)}</div>
                    <p class="card-body" style="font-size:0.9rem;">{html.escape(str(health_report['length_note']))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with hc2:
            q_cls = _tone_pill_class(str(health_report["quant_tone"]))
            q_pct = int(health_report["quantification_pct"])  # type: ignore[arg-type]
            st.markdown(
                f"""
                <div class="ed-card" style="height:100%;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                        <span class="card-label" style="margin:0;">Quantified Impact</span>
                        <span class="skill-pill {q_cls}" style="font-size:0.75rem;padding:0.2rem 0.6rem;">{html.escape(str(health_report['quant_status']))}</span>
                    </div>
                    <div class="kpi-value" style="margin-bottom:0.35rem;">{q_pct}%</div>
                    <div class="weight-bar-bg" style="margin-bottom:0.55rem;"><div class="weight-bar-fill" style="width:{min(100, q_pct)}%;background:#0d9488;"></div></div>
                    <p class="card-body" style="font-size:0.9rem;">{html.escape(str(health_report['quant_note']))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with hc3:
            p_cls = _tone_pill_class(str(health_report["phrasing_tone"]))
            weak_cnt = int(health_report["weak_verb_count"])  # type: ignore[arg-type]
            st.markdown(
                f"""
                <div class="ed-card" style="height:100%;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">
                        <span class="card-label" style="margin:0;">Action Verb Phrasing</span>
                        <span class="skill-pill {p_cls}" style="font-size:0.75rem;padding:0.2rem 0.6rem;">{html.escape(str(health_report['phrasing_status']))}</span>
                    </div>
                    <div class="kpi-value" style="margin-bottom:0.2rem;">{weak_cnt} <span style="font-size:0.95rem;color:#64748b;font-weight:500;">passive opening{'s' if weak_cnt != 1 else ''}</span></div>
                    <div class="kpi-sub" style="margin-bottom:0.6rem;">{'First-person pronouns found' if health_report['has_first_person'] else 'Zero first-person pronouns'}</div>
                    <p class="card-body" style="font-size:0.9rem;">{html.escape(str(health_report['phrasing_note']))}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Standard Sections Strip
        sec_pills_html = []
        present_set = set(health_report["sections_present"])  # type: ignore[arg-type]
        for s_name in ["Summary", "Skills", "Experience", "Projects", "Education"]:
            if s_name in present_set:
                sec_pills_html.append(
                    f'<span class="skill-pill skill-pill-matched">{s_name}: Included</span>'
                )
            else:
                sec_pills_html.append(
                    f'<span class="skill-pill skill-pill-amber">{s_name}: Not Detected</span>'
                )

        st.markdown(
            f"""
            <div class="ed-card">
                <div class="card-label">Structure Check</div>
                <h4 class="card-heading" style="margin-bottom:0.3rem;">Standard Resume Sections</h4>
                <div class="pill-container">{"".join(sec_pills_html)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        weak_examples = health_report.get("weak_verb_examples", [])
        if weak_examples:
            flagged_items = "".join(
                f"<li style='margin-bottom:0.4rem;'>{html.escape(str(item))}</li>"
                for item in weak_examples  # type: ignore[union-attr]
            )
            st.markdown(
                f"""
                <div class="ed-card" style="border-left:3px solid #d97706;">
                    <div class="card-label" style="color:#92400e;">Phrasing Lines to Tighten</div>
                    <h4 class="card-heading">Bullets Starting with Passive or Indirect Openings</h4>
                    <p class="card-body" style="margin-bottom:0.5rem;">Replace phrases like <em>Responsible for</em>, <em>Worked on</em>, or <em>Helped with</em> with direct action verbs such as <em>Engineered</em>, <em>Automated</em>, <em>Designed</em>, or <em>Reduced</em>:</p>
                    <ul style="margin:0.35rem 0 0 1.2rem;padding:0;color:#334155;font-size:0.94rem;line-height:1.6;">
                        {flagged_items}
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # =======================================================================
    # TAB 5: Personalized Interview Preparation
    # =======================================================================
    with tab_interview:
        role_heading_suffix = (
            f" for {extraction.jd_role_title}"
            if extraction and extraction.jd_role_title and extraction.jd_role_title != "Target Role"
            else ""
        )
        st.subheader(f"Targeted Interview Preparation{role_heading_suffix}")
        st.markdown(
            """
            <div class="ed-card" style="padding: 1.1rem 1.4rem;">
                <p class="card-body">Each question below connects a <strong>specific project, role, or technical choice from your resume</strong> directly to a requirement or skill gap in the target job description. Use the optional notes field under any question to draft talking points that will be included in your exported report.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if result.interview_questions:
            for q_idx, iq in enumerate(result.interview_questions, start=1):
                anchor_pill = (
                    f'<span class="iq-badge-anchor">From Your Resume: {html.escape(iq.resume_anchor)}</span>'
                    if iq.resume_anchor
                    else ""
                )
                focus_pill = (
                    f'<span class="iq-badge-focus">Target Area: {html.escape(iq.jd_focus)}</span>'
                    if iq.jd_focus
                    else ""
                )
                prep_html = (
                    f'<div class="iq-prep-box"><strong>How to prepare:</strong> {html.escape(iq.preparation_tip)}</div>'
                    if iq.preparation_tip
                    else ""
                )

                st.markdown(
                    f"""
                    <div class="iq-card">
                        <div class="iq-meta-row">
                            <span class="iq-badge-num">Question {q_idx}</span>
                            {anchor_pill}
                            {focus_pill}
                        </div>
                        <div class="iq-question">{html.escape(iq.question)}</div>
                        {prep_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with st.expander(f"Add your practice talking points for Question {q_idx}"):
                    note_val = st.text_area(
                        f"Practice notes for Question {q_idx}",
                        key=f"run_{run_id}_iq_note_{q_idx}",
                        height=95,
                        placeholder="Jot down key metrics, design decisions, or examples from your experience...",
                        label_visibility="collapsed",
                    )
                    st.session_state["interview_notes"][q_idx] = (note_val or "").strip()
        else:
            st.info("Personalized interview questions will appear here after running an evaluation.")

    # =======================================================================
    # TAB 6: Parsed Details (Plain-English Document Breakdown)
    # =======================================================================
    with tab_requirements:
        st.markdown(
            """
            <div class="ed-card" style="padding: 1.1rem 1.4rem;">
                <p class="card-body">Below is a summary of the skills, qualifications, and responsibilities identified directly from your resume and the job description before scoring.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if extraction is not None:
            r_col1, r_col2 = st.columns(2, gap="large")

            with r_col1:
                res_pills = (
                    "".join(
                        f'<span class="skill-pill skill-pill-neutral">{html.escape(s)}</span>'
                        for s in extraction.resume_skills
                    )
                    if extraction.resume_skills
                    else '<span style="color:#64748b;">None listed</span>'
                )
                st.markdown(
                    f"""
                    <div class="ed-card">
                        <div class="card-label">From Candidate Resume</div>
                        <h4 class="card-heading">Skills Listed on Resume ({len(extraction.resume_skills)})</h4>
                        <div class="pill-container">{res_pills}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(
                    """
                    <div class="card-label" style="margin-top:1rem;">Resume Sections Found</div>
                    """,
                    unsafe_allow_html=True,
                )
                for sec_name, sec_val in [
                    ("Summary", extraction.summary_section),
                    ("Experience", extraction.experience_section),
                    ("Projects", extraction.projects_section),
                    ("Education", extraction.education_section),
                ]:
                    st.markdown(
                        f"""
                        <div class="ed-card" style="padding:0.9rem 1.15rem;margin-bottom:0.65rem;">
                            <div style="font-weight:700;font-size:0.88rem;color:#0f172a;margin-bottom:0.25rem;">{sec_name}</div>
                            <div style="font-size:0.92rem;color:#334155;line-height:1.55;white-space:pre-line;">{html.escape(sec_val)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            with r_col2:
                req_pills = (
                    "".join(
                        f'<span class="skill-pill skill-pill-matched">{html.escape(s)}</span>'
                        for s in extraction.jd_required_skills
                    )
                    if extraction.jd_required_skills
                    else '<span style="color:#64748b;">None listed</span>'
                )
                pref_pills = (
                    "".join(
                        f'<span class="skill-pill skill-pill-neutral">{html.escape(s)}</span>'
                        for s in extraction.jd_preferred_skills
                    )
                    if extraction.jd_preferred_skills
                    else '<span style="color:#64748b;">None listed</span>'
                )
                st.markdown(
                    f"""
                    <div class="ed-card">
                        <div class="card-label">From Job Description</div>
                        <h4 class="card-heading">Required Qualifications ({len(extraction.jd_required_skills)})</h4>
                        <div class="pill-container" style="margin-bottom:1.1rem;">{req_pills}</div>
                        <h4 class="card-heading">Preferred Qualifications ({len(extraction.jd_preferred_skills)})</h4>
                        <div class="pill-container">{pref_pills}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if extraction.jd_core_responsibilities:
                    resp_items = "".join(
                        f"<li style='margin-bottom:0.45rem;'>{html.escape(r)}</li>"
                        for r in extraction.jd_core_responsibilities
                    )
                    st.markdown(
                        f"""
                        <div class="ed-card">
                            <div class="card-label">Role Expectations</div>
                            <h4 class="card-heading">Core Responsibilities</h4>
                            <ul style="margin:0.4rem 0 0 1.1rem;padding:0;color:#334155;font-size:0.95rem;line-height:1.6;">
                                {resp_items}
                            </ul>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.info("Parsed document details will appear here after running an evaluation.")

    # =======================================================================
    # TAB 7: Download Report (.pdf, .md, .json)
    # =======================================================================
    with tab_export:
        active_custom_bullets = st.session_state.get("custom_bullets", {})
        active_custom_summary = st.session_state.get("custom_summary", "")
        active_interview_notes = st.session_state.get("interview_notes", {})

        md_report = generate_markdown_report(
            result=result,
            extraction=extraction,
            custom_bullets=active_custom_bullets,
            custom_summary=active_custom_summary,
            health_report=health_report,
            interview_notes=active_interview_notes,
        )
        pdf_report_bytes = generate_pdf_report(
            result=result,
            extraction=extraction,
            custom_bullets=active_custom_bullets,
            custom_summary=active_custom_summary,
            health_report=health_report,
            interview_notes=active_interview_notes,
        )
        json_report = generate_json_report(
            result=result,
            extraction=extraction,
            custom_bullets=active_custom_bullets,
            custom_summary=active_custom_summary,
            health_report=health_report,
            interview_notes=active_interview_notes,
        )

        dl_col1, dl_col2, dl_col3 = st.columns(3, gap="medium")
        with dl_col1:
            st.download_button(
                label="Download PDF Report (.pdf)",
                data=pdf_report_bytes,
                file_name="resume_match_report.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        with dl_col2:
            st.download_button(
                label="Download Markdown Report (.md)",
                data=md_report,
                file_name="resume_match_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with dl_col3:
            st.download_button(
                label="Download Structured Data (.json)",
                data=json_report,
                file_name="resume_match_data.json",
                mime="application/json",
                use_container_width=True,
            )

        with st.expander("Preview Report Content", expanded=True):
            st.markdown(escape_streamlit_markdown(md_report))
