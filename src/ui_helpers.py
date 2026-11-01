"""UI helper utilities, clean HTML/SVG renderers, and report exporters (.md, .pdf, .json)."""

import html
import io
import json
import re
from typing import Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.pii import ALL_REDACTION_MARKERS
from src.schemas import (
    ExtractionResult,
    ResumeAnalysisResult,
    skill_is_matched,
)

_PLACEHOLDER_TOKEN_RE = re.compile(r"\[[^\]]+\]")
_PLACEHOLDER_CONTEXT_RE = re.compile(r"(\$)?(\[[^\]]+\])([%+])?")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _is_redaction_marker(token: str) -> bool:
    return token in ALL_REDACTION_MARKERS or token.upper().endswith("REDACTED]")


# ---------------------------------------------------------------------------
# Text & Placeholder Utilities
# ---------------------------------------------------------------------------


def extract_placeholders(bullet_text: str) -> List[str]:
    """Extracts unique bracketed placeholders like [X], [N], [Metric] in order of appearance."""
    if not bullet_text:
        return []
    matches = _PLACEHOLDER_TOKEN_RE.findall(bullet_text)
    seen = set()
    ordered = []
    for m in matches:
        if not _is_redaction_marker(m) and m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def apply_placeholder_values(bullet_text: str, replacements: Dict[str, str]) -> str:
    """Replaces bracketed placeholders in a single pass while avoiding duplicate % / + / $ symbols."""
    if not bullet_text or not replacements:
        return bullet_text

    def _sub(match: re.Match) -> str:
        leading_sym = match.group(1) or ""
        raw_token = match.group(2)
        trailing_sym = match.group(3) or ""

        if _is_redaction_marker(raw_token):
            return match.group(0)

        user_val = replacements.get(raw_token, "").strip()
        if not user_val:
            return match.group(0)

        prefix = "" if (leading_sym and user_val.startswith(leading_sym)) else leading_sym
        suffix = "" if (trailing_sym and user_val.endswith(trailing_sym)) else trailing_sym
        return f"{prefix}{user_val}{suffix}"

    return _PLACEHOLDER_CONTEXT_RE.sub(_sub, bullet_text)


def format_bullet_with_badges_html(
    bullet_text: str, replacements: Optional[Dict[str, str]] = None
) -> str:
    """Formats text as safe HTML, highlighting unfilled placeholders or filled values."""
    if not bullet_text:
        return ""

    replacements = replacements or {}
    parts: List[str] = []
    last_idx = 0

    for match in _PLACEHOLDER_CONTEXT_RE.finditer(bullet_text):
        parts.append(html.escape(bullet_text[last_idx : match.start()]))

        leading_sym = match.group(1) or ""
        raw_token = match.group(2)
        trailing_sym = match.group(3) or ""

        if _is_redaction_marker(raw_token):
            parts.append(html.escape(match.group(0)))
            last_idx = match.end()
            continue

        user_val = replacements.get(raw_token, "").strip()

        if user_val:
            prefix = "" if (leading_sym and user_val.startswith(leading_sym)) else leading_sym
            suffix = "" if (trailing_sym and user_val.endswith(trailing_sym)) else trailing_sym
            parts.append(
                f"{html.escape(prefix)}"
                f'<span class="placeholder-badge placeholder-filled" '
                f'title="Filled value for {html.escape(raw_token)}">{html.escape(user_val)}</span>'
                f"{html.escape(suffix)}"
            )
        else:
            parts.append(
                f"{html.escape(leading_sym)}"
                f'<span class="placeholder-badge" '
                f'title="Enter your actual number above">{html.escape(raw_token)}</span>'
                f"{html.escape(trailing_sym)}"
            )

        last_idx = match.end()

    parts.append(html.escape(bullet_text[last_idx:]))
    return "".join(parts)


def _build_skill_pattern(skill: str) -> str:
    """Builds a boundary-safe regex pattern for technical skill names (including C++, C#, .NET)."""
    escaped = re.escape(skill)
    left_guard = (
        r"(?<![A-Za-z0-9_+#.])"
        if (skill[0].isalnum() or skill[0] == "_")
        else r"(?<![A-Za-z0-9_])"
    )
    right_guard = r"(?![A-Za-z0-9_+#])"
    return f"{left_guard}{escaped}{right_guard}"


def highlight_skills_in_text(
    text: str,
    matched_skills: List[str],
    extra_resume_skills: Optional[List[str]] = None,
) -> Tuple[str, int]:
    """Safely highlights matched job description skills on raw text before HTML-escaping slices."""
    if not text:
        return "", 0

    clean_matched = sorted(
        {s.strip() for s in matched_skills if s and s.strip()},
        key=len,
        reverse=True,
    )
    if not clean_matched:
        return html.escape(text).replace("\n", "<br>"), 0

    pattern = re.compile(
        "|".join(_build_skill_pattern(s) for s in clean_matched),
        re.IGNORECASE,
    )

    parts: List[str] = []
    last_idx = 0
    count = 0

    for match in pattern.finditer(text):
        parts.append(html.escape(text[last_idx : match.start()]))
        parts.append(f'<mark class="kw-highlight">{html.escape(match.group(0))}</mark>')
        count += 1
        last_idx = match.end()

    parts.append(html.escape(text[last_idx:]))
    return "".join(parts).replace("\n", "<br>"), count


def get_category_breakdown(result: ResumeAnalysisResult) -> List[Dict[str, object]]:
    """Returns category sub-score display metadata (earned points when available, rubric weights otherwise)."""
    specs = [
        (
            "Required Skills & Core Qualifications",
            result.required_skills_score,
            50,
            "#2563eb",
        ),
        (
            "Relevant Experience & Project Fit",
            result.experience_alignment_score,
            30,
            "#0d9488",
        ),
        (
            "Preferred Qualifications & Education",
            result.preferred_and_education_score,
            10,
            "#6366f1",
        ),
        (
            "Clarity, Structure & Impact",
            result.clarity_and_impact_score,
            10,
            "#64748b",
        ),
    ]
    rows: List[Dict[str, object]] = []
    for label, earned, max_pts, color in specs:
        if earned is not None:
            clamped_earned = max(0, min(max_pts, int(earned)))
            bar_pct = round((clamped_earned / max_pts) * 100) if max_pts > 0 else 0
            display = f"{clamped_earned} / {max_pts} pts"
        else:
            clamped_earned = None
            bar_pct = max_pts
            display = f"{max_pts} pts"
        rows.append(
            {
                "label": label,
                "earned": clamped_earned,
                "max_points": max_pts,
                "bar_pct": bar_pct,
                "display": display,
                "color": color,
            }
        )
    return rows


def compute_rubric_status(
    result: ResumeAnalysisResult,
    extraction: Optional[ExtractionResult] = None,
) -> dict:
    """Computes skill coverage ratio, sub-score status, and whether the <50% required skills cap applies."""
    matched_count = len(result.matched_skills)
    missing_count = len(result.missing_skills)
    total_evaluated = matched_count + missing_count
    skill_coverage_pct = (
        round((matched_count / total_evaluated) * 100) if total_evaluated > 0 else 0
    )

    subscores = (
        result.required_skills_score,
        result.experience_alignment_score,
        result.preferred_and_education_score,
        result.clarity_and_impact_score,
    )
    has_live_subscores = all(s is not None for s in subscores)
    raw_subscore_sum = (
        sum(int(s) for s in subscores if s is not None) if has_live_subscores else None
    )

    hard_cap_triggered = False
    if extraction is not None:
        req_skills = [s.strip() for s in extraction.jd_required_skills if s and s.strip()]
        if req_skills:
            matched_req = sum(
                1 for r in req_skills if skill_is_matched(r, result.matched_skills)
            )
            if (matched_req / len(req_skills)) < 0.5 and result.match_score <= 50:
                hard_cap_triggered = True
    elif total_evaluated > 0 and skill_coverage_pct < 50 and result.match_score <= 50:
        hard_cap_triggered = True

    if result.match_score >= 75:
        tier_label = "Strong Match"
        tier_color = "#15803d"
        tier_bg = "#dcfce7"
    elif result.match_score >= 50:
        tier_label = "Moderate Match"
        tier_color = "#b45309"
        tier_bg = "#fef3c7"
    else:
        tier_label = "Low Match"
        tier_color = "#b91c1c"
        tier_bg = "#fee2e2"

    return {
        "matched_count": matched_count,
        "missing_count": missing_count,
        "total_evaluated": total_evaluated,
        "skill_coverage_pct": skill_coverage_pct,
        "hard_cap_triggered": hard_cap_triggered,
        "has_live_subscores": has_live_subscores,
        "raw_subscore_sum": raw_subscore_sum,
        "tier_label": tier_label,
        "tier_color": tier_color,
        "tier_bg": tier_bg,
    }


def render_svg_gauge_html(
    score: int, tier_label: str, tier_color: str, tier_bg: str
) -> str:
    """Renders a clean editorial SVG circular score indicator."""
    clamped = max(0, min(100, int(score)))
    radius = 66
    circumference = 2 * 3.14159265 * radius
    dash_offset = circumference * (1.0 - clamped / 100.0)

    return f"""
    <div class="gauge-card">
        <div class="gauge-svg-wrap">
            <svg viewBox="0 0 176 176" class="gauge-svg" role="img" aria-label="Match Score {clamped} out of 100">
                <circle class="gauge-track" cx="88" cy="88" r="{radius}" />
                <circle
                    class="gauge-fill"
                    cx="88"
                    cy="88"
                    r="{radius}"
                    stroke="{tier_color}"
                    stroke-dasharray="{circumference:.2f}"
                    stroke-dashoffset="{dash_offset:.2f}"
                />
            </svg>
            <div class="gauge-center-text">
                <span class="gauge-score-num" style="color: {tier_color};">{clamped}</span>
                <span class="gauge-score-max">out of 100</span>
            </div>
        </div>
        <div class="gauge-tier-pill" style="background: {tier_bg}; color: {tier_color};">
            {html.escape(tier_label)}
        </div>
        <div class="gauge-caption">Estimated Role Fit</div>
    </div>
    """


def escape_streamlit_markdown(md_text: str) -> str:
    """Escapes literal dollar signs so Streamlit st.markdown does not render currency as KaTeX math."""
    if not md_text:
        return ""
    return re.sub(r"(?<!\\)\$", r"\\$", md_text)


# ---------------------------------------------------------------------------
# Report Exporters (.md, .json, .pdf)
# ---------------------------------------------------------------------------


def generate_markdown_report(
    result: ResumeAnalysisResult,
    extraction: Optional[ExtractionResult] = None,
    custom_bullets: Optional[Dict[int, str]] = None,
    custom_summary: Optional[str] = None,
    health_report: Optional[Dict[str, object]] = None,
    interview_notes: Optional[Dict[int, str]] = None,
) -> str:
    """Generates a clean, plain-English downloadable Markdown review report."""
    custom_bullets = custom_bullets or {}
    interview_notes = interview_notes or {}
    meta = compute_rubric_status(result, extraction)
    breakdown = get_category_breakdown(result)
    resolved_summary = (
        custom_summary.strip()
        if custom_summary and custom_summary.strip()
        else result.suggested_summary.strip()
    )

    lines = [
        "# Resume & Job Match Report",
        "",
        "> **Note:** Match scores and recommendations are automated self-review estimates. They do not represent company ATS software or hiring decisions.",
        "",
        f"## Overall Match Score: **{result.match_score} / 100** ({meta['tier_label']})",
        "",
        f"**Summary:** {result.score_explanation}",
        "",
    ]

    if meta["has_live_subscores"]:
        lines.append("### Category Score Breakdown")
        for row in breakdown:
            lines.append(f"- **{row['label']}:** {row['display']}")
        if meta["hard_cap_triggered"]:
            lines.append(
                "- **Score Cap Note:** Overall score is capped at 50 / 100 because fewer than half of the required job skills appear in the resume."
            )
        lines.append("")

    lines.extend(["---", "", "## Priority Improvements"])
    for idx, fix in enumerate(result.priority_fixes, start=1):
        lines.append(f"{idx}. {fix}")

    if resolved_summary:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Tailored Professional Summary Draft",
                "",
                resolved_summary,
            ]
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Skills Comparison",
            "",
            f"### Matched Skills ({len(result.matched_skills)})",
            ", ".join(result.matched_skills) if result.matched_skills else "None identified",
            "",
            f"### Missing Skills ({len(result.missing_skills)})",
            ", ".join(result.missing_skills) if result.missing_skills else "None identified",
            "",
            "---",
            "",
            "## Suggested Bullet Revisions",
            "",
        ]
    )

    if result.improved_bullets:
        for idx, b in enumerate(result.improved_bullets, start=1):
            final_rewrite = custom_bullets.get(idx, b.suggested_bullet)
            lines.extend(
                [
                    f"### Bullet {idx}",
                    f"- **Current:** {b.original_bullet}",
                    f"- **Suggested:** {final_rewrite}",
                    f"- **Why this works:** {b.rationale}",
                    "",
                ]
            )
    else:
        lines.append("No bullet revisions generated.\n")

    lines.extend(
        [
            "---",
            "",
            "## Section-by-Section Feedback",
            f"- **Summary:** {result.section_feedback.summary}",
            f"- **Skills:** {result.section_feedback.skills}",
            f"- **Projects:** {result.section_feedback.projects}",
            f"- **Experience:** {result.section_feedback.experience}",
            f"- **Education:** {result.section_feedback.education}",
            "",
            "---",
            "",
            "## Areas to Strengthen",
        ]
    )
    if result.weaknesses:
        for w in result.weaknesses:
            lines.append(f"- {w}")
    else:
        lines.append("No major gaps identified.")

    if health_report:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Resume Formatting & Writing Health",
                f"- **Length & Word Count:** {health_report.get('word_count', 0)} words ({health_report.get('length_status', 'N/A')}) — {health_report.get('length_note', '')}",
                f"- **Quantified Bullets:** {health_report.get('quantification_pct', 0)}% ({health_report.get('quantified_bullets', 0)} of {health_report.get('total_bullets', 0)} bullets) — {health_report.get('quant_note', '')}",
                f"- **Action Verb Phrasing:** {health_report.get('phrasing_status', 'N/A')} — {health_report.get('phrasing_note', '')}",
                f"- **Sections Detected:** {', '.join(health_report.get('sections_present', [])) or 'None'}",
            ]
        )

    if result.interview_questions:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Targeted Interview Preparation",
                "",
            ]
        )
        for idx, iq in enumerate(result.interview_questions, start=1):
            lines.append(f"### Question {idx}: {iq.question}")
            if iq.resume_anchor:
                lines.append(f"- **From Your Resume:** {iq.resume_anchor}")
            if iq.jd_focus:
                lines.append(f"- **Target Requirement:** {iq.jd_focus}")
            if iq.preparation_tip:
                lines.append(f"- **How to Prepare:** {iq.preparation_tip}")
            user_note = (interview_notes.get(idx) or "").strip()
            if user_note:
                lines.append(f"- **Your Practice Notes:** {user_note}")
            lines.append("")

    if extraction is not None:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Parsed Document Summary",
                f"- **Resume Skills Identified ({len(extraction.resume_skills)}):** {', '.join(extraction.resume_skills)}",
                f"- **Required Job Skills ({len(extraction.jd_required_skills)}):** {', '.join(extraction.jd_required_skills)}",
                f"- **Preferred Job Skills ({len(extraction.jd_preferred_skills)}):** {', '.join(extraction.jd_preferred_skills)}",
            ]
        )

    return "\n".join(lines)


def generate_json_report(
    result: ResumeAnalysisResult,
    extraction: Optional[ExtractionResult] = None,
    custom_bullets: Optional[Dict[int, str]] = None,
    custom_summary: Optional[str] = None,
    health_report: Optional[Dict[str, object]] = None,
    interview_notes: Optional[Dict[int, str]] = None,
) -> str:
    """Generates a downloadable JSON bundle containing parsed details, health checks, and evaluation outputs."""
    payload = {
        "note": "Automated self-review estimate only; not an ATS score or hiring decision.",
        "parsed_requirements": extraction.model_dump() if extraction else None,
        "evaluation": result.model_dump(),
        "customized_summary": (
            custom_summary.strip()
            if custom_summary and custom_summary.strip()
            else result.suggested_summary
        ),
        "customized_bullets": custom_bullets or {},
        "interview_practice_notes": {
            k: v.strip() for k, v in (interview_notes or {}).items() if v and v.strip()
        },
        "resume_health": health_report,
    }
    return json.dumps(payload, indent=2)


def _pdf_safe_text(text: str) -> str:
    """Normalizes text to WinAnsi-compatible characters and escapes XML entities for ReportLab Paragraph."""
    if not text:
        return ""
    cleaned = _CONTROL_CHARS_RE.sub("", str(text))
    cleaned = (
        cleaned.replace("\u2011", "-")
        .replace("\u2212", "-")
        .replace("\u00a0", " ")
        .replace("₹", "INR ")
    )
    cleaned = cleaned.encode("cp1252", errors="replace").decode("cp1252")
    escaped = html.escape(cleaned, quote=False)
    return escaped.replace("\n", "<br/>")


def _draw_pdf_footer(canvas_obj, doc) -> None:
    """Draws a subtle editorial footer with page numbering on every page."""
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 8.5)
    canvas_obj.setFillColor(colors.HexColor("#64748b"))
    canvas_obj.drawString(
        doc.leftMargin,
        0.48 * inch,
        "Resume & Job Match Report — Automated Self-Review Estimate",
    )
    canvas_obj.drawRightString(
        LETTER[0] - doc.rightMargin,
        0.48 * inch,
        f"Page {doc.page}",
    )
    canvas_obj.restoreState()


def generate_pdf_report(
    result: ResumeAnalysisResult,
    extraction: Optional[ExtractionResult] = None,
    custom_bullets: Optional[Dict[int, str]] = None,
    custom_summary: Optional[str] = None,
    health_report: Optional[Dict[str, object]] = None,
    interview_notes: Optional[Dict[int, str]] = None,
) -> bytes:
    """Generates a clean, print-ready editorial PDF report using ReportLab."""
    custom_bullets = custom_bullets or {}
    interview_notes = interview_notes or {}
    meta = compute_rubric_status(result, extraction)
    breakdown = get_category_breakdown(result)
    resolved_summary = (
        custom_summary.strip()
        if custom_summary and custom_summary.strip()
        else result.suggested_summary.strip()
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.75 * inch,
        title="Resume & Job Match Report",
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EdTitle",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )
    eyebrow_style = ParagraphStyle(
        "EdEyebrow",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#2563eb"),
        spaceAfter=2,
    )
    section_h2_style = ParagraphStyle(
        "EdH2",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )
    section_h3_style = ParagraphStyle(
        "EdH3",
        parent=base_styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "EdBody",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9.8,
        leading=14.2,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5,
    )
    note_style = ParagraphStyle(
        "EdNote",
        parent=body_style,
        fontSize=8.8,
        leading=12.5,
        textColor=colors.HexColor("#475569"),
    )
    score_big_style = ParagraphStyle(
        "EdScoreBig",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor(meta["tier_color"]),
        alignment=1,
    )
    score_sub_style = ParagraphStyle(
        "EdScoreSub",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#334155"),
        alignment=1,
    )

    story: List[object] = []
    avail_width = LETTER[0] - doc.leftMargin - doc.rightMargin

    # 1. Header & Disclaimer
    story.append(Paragraph("CAREER &amp; APPLICATION REVIEW", eyebrow_style))
    story.append(Paragraph("Resume &amp; Job Match Report", title_style))

    disclaimer_table = Table(
        [
            [
                Paragraph(
                    "<b>Note:</b> Match scores and recommendations are automated self-review estimates. "
                    "They do not simulate company ATS software and do not represent hiring decisions.",
                    note_style,
                )
            ]
        ],
        colWidths=[avail_width],
    )
    disclaimer_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#64748b")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(disclaimer_table)
    story.append(Spacer(1, 12))

    # 2. Score Summary Card
    score_left = [
        Paragraph(f"{result.match_score} / 100", score_big_style),
        Spacer(1, 3),
        Paragraph(_pdf_safe_text(meta["tier_label"]), score_sub_style),
        Paragraph(
            f"Skill Coverage: {meta['skill_coverage_pct']}% ({meta['matched_count']} matched)",
            note_style,
        ),
    ]
    score_right: List[object] = [
        Paragraph("<b>Assessment Summary</b>", section_h3_style),
        Paragraph(_pdf_safe_text(result.score_explanation), body_style),
    ]
    if meta["hard_cap_triggered"]:
        score_right.append(
            Paragraph(
                "<b>Score Cap Applied:</b> Overall score is capped at 50 / 100 because fewer than half of the required job skills appear in the resume.",
                ParagraphStyle(
                    "CapWarn",
                    parent=note_style,
                    textColor=colors.HexColor("#991b1b"),
                ),
            )
        )

    summary_table = Table(
        [[score_left, score_right]],
        colWidths=[1.95 * inch, avail_width - 1.95 * inch],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
                ("LINEAFTER", (0, 0), (0, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # 3. Category Breakdown Table
    cat_header = "Earned / Max" if meta["has_live_subscores"] else "Rubric Weight"
    cat_rows = [
        [
            Paragraph("<b>Scoring Category</b>", body_style),
            Paragraph(f"<b>{cat_header}</b>", body_style),
        ]
    ]
    for row in breakdown:
        cat_rows.append(
            [
                Paragraph(_pdf_safe_text(str(row["label"])), body_style),
                Paragraph(f"<b>{_pdf_safe_text(str(row['display']))}</b>", body_style),
            ]
        )

    cat_table = Table(cat_rows, colWidths=[avail_width - 1.5 * inch, 1.5 * inch])
    cat_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(cat_table)

    # 4. Priority Improvements
    story.append(Paragraph("Top Priority Improvements", section_h2_style))
    for idx, fix in enumerate(result.priority_fixes, start=1):
        story.append(Paragraph(f"<b>{idx}.</b> {_pdf_safe_text(fix)}", body_style))

    # 5. Tailored Summary Draft
    if resolved_summary:
        story.append(Paragraph("Tailored Professional Summary Draft", section_h2_style))
        sum_box = Table(
            [[Paragraph(_pdf_safe_text(resolved_summary), body_style)]],
            colWidths=[avail_width],
        )
        sum_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.5, colors.HexColor("#2563eb")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(sum_box)

    # 6. Skills Comparison
    story.append(Paragraph("Skills Comparison", section_h2_style))
    matched_str = (
        ", ".join(result.matched_skills) if result.matched_skills else "None identified"
    )
    missing_str = (
        ", ".join(result.missing_skills) if result.missing_skills else "None identified"
    )
    skills_table = Table(
        [
            [
                Paragraph(
                    f"<b>Matched Skills ({len(result.matched_skills)})</b><br/>{_pdf_safe_text(matched_str)}",
                    body_style,
                ),
                Paragraph(
                    f"<b>Missing Skills ({len(result.missing_skills)})</b><br/>{_pdf_safe_text(missing_str)}",
                    body_style,
                ),
            ]
        ],
        colWidths=[avail_width / 2.0, avail_width / 2.0],
    )
    skills_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0fdf4")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fef2f2")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(skills_table)

    # 7. Suggested Bullet Revisions
    story.append(Paragraph("Suggested Bullet Revisions", section_h2_style))
    if result.improved_bullets:
        for idx, b in enumerate(result.improved_bullets, start=1):
            final_rewrite = custom_bullets.get(idx, b.suggested_bullet)
            story.append(Paragraph(f"Bullet Revision {idx}", section_h3_style))
            story.append(
                Paragraph(f"<b>Current:</b> {_pdf_safe_text(b.original_bullet)}", body_style)
            )
            story.append(
                Paragraph(f"<b>Suggested:</b> {_pdf_safe_text(final_rewrite)}", body_style)
            )
            story.append(
                Paragraph(f"<b>Why this works:</b> {_pdf_safe_text(b.rationale)}", note_style)
            )
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No bullet revisions generated.", body_style))

    # 8. Section-by-Section Feedback & Areas to Strengthen
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=6, spaceAfter=4)
    )
    story.append(Paragraph("Section-by-Section Feedback", section_h2_style))
    for sec_label, sec_text in [
        ("Summary", result.section_feedback.summary),
        ("Skills", result.section_feedback.skills),
        ("Experience", result.section_feedback.experience),
        ("Projects", result.section_feedback.projects),
        ("Education", result.section_feedback.education),
    ]:
        story.append(
            Paragraph(f"<b>{sec_label}:</b> {_pdf_safe_text(sec_text)}", body_style)
        )

    story.append(Paragraph("Areas to Strengthen", section_h2_style))
    if result.weaknesses:
        for w in result.weaknesses:
            story.append(Paragraph(f"- {_pdf_safe_text(w)}", body_style))
    else:
        story.append(Paragraph("No major gaps identified.", body_style))

    # 9. Resume Formatting & Writing Health
    if health_report:
        story.append(Paragraph("Resume Formatting &amp; Writing Health", section_h2_style))
        story.append(
            Paragraph(
                f"<b>Length &amp; Word Count:</b> {_pdf_safe_text(str(health_report.get('word_count', 0)))} words "
                f"({_pdf_safe_text(str(health_report.get('length_status', '')))}) — "
                f"{_pdf_safe_text(str(health_report.get('length_note', '')))}",
                body_style,
            )
        )
        story.append(
            Paragraph(
                f"<b>Quantified Bullets:</b> {_pdf_safe_text(str(health_report.get('quantification_pct', 0)))}% "
                f"({_pdf_safe_text(str(health_report.get('quantified_bullets', 0)))} of "
                f"{_pdf_safe_text(str(health_report.get('total_bullets', 0)))} bullets) — "
                f"{_pdf_safe_text(str(health_report.get('quant_note', '')))}",
                body_style,
            )
        )
        story.append(
            Paragraph(
                f"<b>Action Verb Phrasing:</b> {_pdf_safe_text(str(health_report.get('phrasing_status', '')))} — "
                f"{_pdf_safe_text(str(health_report.get('phrasing_note', '')))}",
                body_style,
            )
        )
        present_secs = ", ".join(health_report.get("sections_present", [])) or "None"  # type: ignore[arg-type]
        story.append(
            Paragraph(
                f"<b>Sections Detected:</b> {_pdf_safe_text(present_secs)}",
                body_style,
            )
        )

    # 10. Targeted Interview Preparation
    if result.interview_questions:
        story.append(Paragraph("Targeted Interview Preparation", section_h2_style))
        for idx, iq in enumerate(result.interview_questions, start=1):
            story.append(
                Paragraph(f"Question {idx}: {_pdf_safe_text(iq.question)}", section_h3_style)
            )
            meta_parts = []
            if iq.resume_anchor:
                meta_parts.append(f"<b>From Resume:</b> {_pdf_safe_text(iq.resume_anchor)}")
            if iq.jd_focus:
                meta_parts.append(f"<b>Target Area:</b> {_pdf_safe_text(iq.jd_focus)}")
            if meta_parts:
                story.append(Paragraph(" &nbsp;|&nbsp; ".join(meta_parts), note_style))
            if iq.preparation_tip:
                story.append(
                    Paragraph(
                        f"<b>How to Prepare:</b> {_pdf_safe_text(iq.preparation_tip)}",
                        body_style,
                    )
                )
            user_note = (interview_notes.get(idx) or "").strip()
            if user_note:
                story.append(
                    Paragraph(
                        f"<b>Your Practice Notes:</b> {_pdf_safe_text(user_note)}",
                        body_style,
                    )
                )
            story.append(Spacer(1, 5))

    # 11. Parsed Document Summary
    if extraction is not None:
        story.append(Paragraph("Parsed Document Summary", section_h2_style))
        story.append(
            Paragraph(
                f"<b>Resume Skills Identified ({len(extraction.resume_skills)}):</b> "
                f"{_pdf_safe_text(', '.join(extraction.resume_skills) or 'None')}",
                body_style,
            )
        )
        story.append(
            Paragraph(
                f"<b>Required Job Skills ({len(extraction.jd_required_skills)}):</b> "
                f"{_pdf_safe_text(', '.join(extraction.jd_required_skills) or 'None')}",
                body_style,
            )
        )
        story.append(
            Paragraph(
                f"<b>Preferred Job Skills ({len(extraction.jd_preferred_skills)}):</b> "
                f"{_pdf_safe_text(', '.join(extraction.jd_preferred_skills) or 'None')}",
                body_style,
            )
        )

    doc.build(story, onFirstPage=_draw_pdf_footer, onLaterPages=_draw_pdf_footer)
    return buffer.getvalue()
