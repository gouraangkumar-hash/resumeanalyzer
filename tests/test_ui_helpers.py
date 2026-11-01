"""Unit tests for UI helper functions, keyword highlighting, placeholder editing, report generation, and emoji-free copy."""

import io
import json
import re
from pathlib import Path
from pypdf import PdfReader

from src.resume_health import analyze_resume_health
from src.schemas import (
    BulletImprovement,
    ExtractionResult,
    InterviewQuestion,
    ResumeAnalysisResult,
    SectionFeedback,
)
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

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def _build_fixture(score: int, matched: list[str], missing: list[str], req_skills: list[str]):
    extraction = ExtractionResult(
        resume_skills=matched,
        jd_required_skills=req_skills,
        jd_preferred_skills=["Kubernetes"],
        jd_core_responsibilities=["Maintain backend services"],
    )
    analysis = ResumeAnalysisResult(
        match_score=score,
        score_explanation="Test evaluation summary.",
        matched_skills=matched,
        missing_skills=missing,
        section_feedback=SectionFeedback(
            summary="Clear summary.",
            skills="Good skill alignment.",
            projects="Relevant project.",
            experience="Add metrics to bullets.",
            education="Matches degree.",
        ),
        weaknesses=["Missing container orchestration."],
        improved_bullets=[
            BulletImprovement(
                original_bullet="Built backend APIs.",
                suggested_bullet="Built [N]+ REST APIs reducing latency by [X]%.",
                rationale="Adds concrete scale placeholders.",
            )
        ],
        priority_fixes=["Add metrics to experience bullets."],
    )
    return extraction, analysis


def test_extract_and_apply_placeholders():
    """Verify bracketed placeholders are extracted in order and replaced cleanly."""
    bullet = "Delivered [N]+ endpoints in FastAPI, reducing latency by [X]% across [N]+ services."
    placeholders = extract_placeholders(bullet)
    assert placeholders == ["[N]", "[X]"]

    updated = apply_placeholder_values(bullet, {"[N]": "15", "[X]": "40"})
    assert updated == "Delivered 15+ endpoints in FastAPI, reducing latency by 40% across 15+ services."

    # Verify typing duplicate symbols like '40%' or '15+' or '$50K' does not produce '40%%', '15++', or '$$50K'
    deduped = apply_placeholder_values(
        "Saved $[Amount] and cut latency by [X]% across [N]+ services.",
        {"[Amount]": "$50K", "[X]": "40%", "[N]": "15+"},
    )
    assert deduped == "Saved $50K and cut latency by 40% across 15+ services."

    # Verify redaction markers are ignored by placeholder extraction
    with_redacted = "Contact [EMAIL REDACTED] after delivering [N]+ services."
    assert extract_placeholders(with_redacted) == ["[N]"]
    assert apply_placeholder_values(with_redacted, {"[N]": "10"}) == "Contact [EMAIL REDACTED] after delivering 10+ services."


def test_format_bullet_with_badges_html():
    """Verify unfilled and filled placeholders render with distinct CSS badge classes."""
    bullet = "Reduced latency by [X]% for [N] users."
    html_out = format_bullet_with_badges_html(bullet, {"[X]": "35"})
    assert "placeholder-filled" in html_out
    assert "35" in html_out
    assert "[N]" in html_out


def test_highlight_skills_in_text_escapes_html_and_marks_skills():
    """Verify matched skills are wrapped in <mark> tags, entities are preserved, and C does not match C++/C#."""
    text = "R&D in C++, C#, Python, FastAPI, and <script>alert(1)</script>."
    highlighted, count = highlight_skills_in_text(text, ["C", "AMP", "Python", "FastAPI"])
    assert count == 2
    assert "R&amp;D" in highlighted
    assert "C++" in highlighted
    assert "C#" in highlighted
    assert '<mark class="kw-highlight">Python</mark>' in highlighted
    assert '<mark class="kw-highlight">FastAPI</mark>' in highlighted
    assert "&lt;script&gt;" in highlighted


def test_compute_rubric_status_and_hard_cap():
    """Verify status metadata accurately detects strong match vs score-capped scenarios."""
    strong_ext, strong_res = _build_fixture(
        score=84,
        matched=["Python", "FastAPI", "PostgreSQL"],
        missing=["Kubernetes"],
        req_skills=["Python", "FastAPI", "PostgreSQL"],
    )
    strong_meta = compute_rubric_status(strong_res, strong_ext)
    assert strong_meta["tier_label"] == "Strong Match"
    assert strong_meta["hard_cap_triggered"] is False

    capped_ext, capped_res = _build_fixture(
        score=42,
        matched=["Python"],
        missing=["Spark", "Airflow", "PostgreSQL", "Docker"],
        req_skills=["Python", "Spark", "Airflow", "PostgreSQL", "Docker"],
    )
    capped_meta = compute_rubric_status(capped_res, capped_ext)
    assert capped_meta["tier_label"] == "Low Match"
    assert capped_meta["hard_cap_triggered"] is True

    # Empty required skills list must not falsely trigger hard cap from preferred skills alone
    no_req_ext, no_req_res = _build_fixture(
        score=48,
        matched=["Python"],
        missing=["Terraform", "Helm", "Istio"],
        req_skills=[],
    )
    no_req_meta = compute_rubric_status(no_req_res, no_req_ext)
    assert no_req_meta["hard_cap_triggered"] is False


def test_escape_streamlit_markdown_escapes_currency_dollars():
    """Verify currency dollar signs are escaped so KaTeX math is not triggered."""
    escaped = escape_streamlit_markdown("Saved $10,000 to $25,000 and [$Amount].")
    assert r"\$10,000" in escaped
    assert r"\$25,000" in escaped
    assert r"[\$Amount]" in escaped


def test_render_svg_gauge_and_reports():
    """Verify SVG gauge HTML and Markdown/JSON export generators produce clean emoji-free outputs."""
    ext, res = _build_fixture(
        score=84,
        matched=["Python", "FastAPI"],
        missing=["Kubernetes"],
        req_skills=["Python", "FastAPI"],
    )
    meta = compute_rubric_status(res, ext)
    svg_html = render_svg_gauge_html(84, meta["tier_label"], meta["tier_color"], meta["tier_bg"])
    assert "<svg" in svg_html
    assert "84" in svg_html
    assert not EMOJI_PATTERN.search(svg_html)

    md = generate_markdown_report(res, ext, {1: "Custom bullet 1"})
    assert "84 / 100" in md
    assert "Custom bullet 1" in md
    assert not EMOJI_PATTERN.search(md)

    json_str = generate_json_report(res, ext, {1: "Custom bullet 1"})
    parsed = json.loads(json_str)
    assert parsed["evaluation"]["match_score"] == 84
    assert parsed["parsed_requirements"]["resume_skills"][0] == "Python"
    assert not EMOJI_PATTERN.search(json_str)


def test_category_breakdown_and_pdf_report_export():
    """Verify live category breakdown and ReportLab PDF export handle XML entities safely."""
    ext, res = _build_fixture(
        score=83,
        matched=["Python", "FastAPI", "C++"],
        missing=["Kubernetes"],
        req_skills=["Python", "FastAPI"],
    )
    res.required_skills_score = 42
    res.experience_alignment_score = 24
    res.preferred_and_education_score = 8
    res.clarity_and_impact_score = 9
    res.score_explanation = "Strong R&D fit in C++ <vector> & Python; saved ₹50,000."
    res.suggested_summary = "Backend Engineer with [N] years of Python & FastAPI experience."
    res.interview_questions = [
        InterviewQuestion(
            resume_anchor="OrderStream Billing Service (FastAPI & C++)",
            jd_focus="Missing Skill: Kubernetes Orchestration",
            question="In your OrderStream Billing Service, how would you containerize & orchestrate <FastAPI> endpoints in Kubernetes?",
            preparation_tip="Walk through OrderStream's deployment architecture first, then map health checks to Kubernetes probes.",
        )
    ]

    breakdown = get_category_breakdown(res)
    assert breakdown[0]["display"] == "42 / 50 pts"
    assert breakdown[0]["bar_pct"] == 84

    health = analyze_resume_health(
        "Summary\nBackend engineer\nExperience\n- Built 10+ APIs cutting latency by 30%.",
        page_count=1,
        extraction=ext,
    )

    pdf_bytes = generate_pdf_report(
        result=res,
        extraction=ext,
        custom_bullets={1: "Built 12+ REST APIs reducing latency by 35% & saving $10K."},
        custom_summary="Backend Engineer with 4 years of Python & FastAPI experience.",
        health_report=health,
        interview_notes={1: "Discuss readiness/liveness probes & zero-downtime rollouts."},
    )
    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    pdf_text = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "83 / 100" in pdf_text
    assert "42 / 50 pts" in pdf_text
    assert "4 years of Python" in pdf_text
    assert "OrderStream Billing Service" in pdf_text
    assert "zero-downtime rollouts" in pdf_text
    assert not EMOJI_PATTERN.search(pdf_text)

    md = generate_markdown_report(
        res,
        ext,
        custom_bullets={1: "Built 12+ REST APIs."},
        custom_summary="Backend Engineer with 4 years of Python & FastAPI experience.",
        health_report=health,
        interview_notes={1: "Discuss readiness/liveness probes & zero-downtime rollouts."},
    )
    assert "42 / 50 pts" in md
    assert "Tailored Professional Summary Draft" in md
    assert "Targeted Interview Preparation" in md
    assert "From Your Resume:** OrderStream Billing Service" in md
    assert "Your Practice Notes:** Discuss readiness/liveness probes" in md
    assert not EMOJI_PATTERN.search(md)

    json_out = json.loads(
        generate_json_report(
            res,
            ext,
            interview_notes={1: "Discuss readiness/liveness probes."},
        )
    )
    assert json_out["evaluation"]["interview_questions"][0]["resume_anchor"].startswith("OrderStream")
    assert json_out["interview_practice_notes"]["1"] == "Discuss readiness/liveness probes."


def test_frontend_files_contain_no_emojis_ai_jargon_or_samples():
    """Ensure app.py, src/ui_helpers.py, and src/resume_health.py contain zero emojis, no AI jargon, and no sample presets."""
    root = Path(__file__).resolve().parent.parent
    checked_files = [
        ("app.py", (root / "app.py").read_text(encoding="utf-8")),
        ("src/ui_helpers.py", (root / "src" / "ui_helpers.py").read_text(encoding="utf-8")),
        ("src/resume_health.py", (root / "src" / "resume_health.py").read_text(encoding="utf-8")),
    ]

    banned_jargon = [
        "LangChain",
        "Google Gemini",
        "Prompt Chain",
        "Pydantic",
        "Heuristic AI",
        "Anti-Fabrication",
        "Grounded AI",
        "X-Ray",
    ]

    for rel_name, code in checked_files:
        assert not EMOJI_PATTERN.search(code), f"Found emoji in {rel_name}"
        assert "DEMO_PRESETS" not in code, f"Found DEMO_PRESETS in {rel_name}"
        for phrase in banned_jargon:
            assert phrase.lower() not in code.lower(), f"Found jargon '{phrase}' in {rel_name}"
