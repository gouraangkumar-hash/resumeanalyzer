"""Unit tests for the two-stage LLM analyzer and prompt chain (Person 1 deliverable)."""

import os
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.runnables import RunnableLambda

from src.schemas import (
    ExtractionResult,
    SectionFeedback,
    BulletImprovement,
    ResumeAnalysisResult,
)
from src.analyzer import (
    get_api_key,
    analyze_resume,
    create_gemini_llm,
    reconcile_evaluation_scores,
)


def test_get_api_key_explicit():
    """Verify explicit key takes precedence."""
    assert get_api_key("my-test-key-123") == "my-test-key-123"


def test_get_api_key_missing(monkeypatch):
    """Verify ValueError is raised when no API key is available."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Google Gemini API key not found"):
        get_api_key(None)


def test_get_api_key_placeholder(monkeypatch):
    """Verify placeholder key from .env.example is rejected."""
    monkeypatch.setenv("GOOGLE_API_KEY", "your_gemini_api_key_here")
    with pytest.raises(ValueError, match="Google Gemini API key not found"):
        get_api_key(None)


def test_analyze_resume_empty_inputs():
    """Verify empty inputs raise descriptive ValueError."""
    with pytest.raises(ValueError, match="Resume text is empty"):
        analyze_resume("", "Some JD text", api_key="dummy-key")

    with pytest.raises(ValueError, match="Job description is empty"):
        analyze_resume("Some resume text", "", api_key="dummy-key")


@patch("src.analyzer.create_gemini_llm")
def test_analyze_resume_mocked_chain(mock_create_llm):
    """Verify two-stage chaining passes Stage 1 output into Stage 2."""
    mock_llm = MagicMock()
    mock_create_llm.return_value = mock_llm

    # Create sample Stage 1 mock output
    mock_stage1_output = ExtractionResult(
        resume_skills=["Python", "FastAPI"],
        summary_section="Software engineer with 3 years experience.",
        skills_section="Python, FastAPI, Docker",
        projects_section="Built internal developer tools.",
        experience_section="Backend engineer at Tech Corp.",
        education_section="B.S. in Computer Science.",
        sample_resume_bullets=["Developed APIs for internal users."],
        jd_required_skills=["Python", "FastAPI", "SQL"],
        jd_preferred_skills=["Kubernetes"],
        jd_core_responsibilities=["Maintain scalable backend services."],
    )

    # Create sample Stage 2 mock output
    mock_stage2_output = ResumeAnalysisResult(
        match_score=80,
        score_explanation="Matches Python and FastAPI; missing SQL.",
        matched_skills=["Python", "FastAPI"],
        missing_skills=["SQL"],
        section_feedback=SectionFeedback(
            summary="Clear and concise.",
            skills="Aligns well with core backend stack.",
            projects="Good technical relevance.",
            experience="Good scope of work.",
            education="Matches degree requirements.",
        ),
        weaknesses=["No relational database experience listed."],
        improved_bullets=[
            BulletImprovement(
                original_bullet="Developed APIs for internal users.",
                suggested_bullet="Engineered REST APIs with FastAPI, serving [N] requests/day.",
                rationale="Adds framework context and placeholders for throughput.",
            )
        ],
        priority_fixes=[
            "Add SQL or database project experience.",
            "Quantify API scale using [Metric] placeholders.",
            "Align summary keywords with backend requirements.",
        ],
    )

    # Setup with_structured_output to return Runnables
    def mock_structured_output(schema):
        if schema == ExtractionResult:
            return RunnableLambda(lambda x: mock_stage1_output)
        return RunnableLambda(lambda x: mock_stage2_output)

    mock_llm.with_structured_output.side_effect = mock_structured_output

    # Run analyzer with dummy input and stage1 callback
    captured_stage1 = []
    result = analyze_resume(
        resume_text="Jane Doe\nPython Developer with FastAPI experience.",
        jd_text="Looking for a Python Developer proficient in FastAPI and SQL.",
        api_key="mock-api-key",
        on_stage1_complete=lambda ext: captured_stage1.append(ext),
    )

    assert result.match_score == 80
    assert "Python" in result.matched_skills
    assert "SQL" in result.missing_skills
    assert len(result.priority_fixes) == 3
    assert "[N]" in result.improved_bullets[0].suggested_bullet
    assert len(captured_stage1) == 1
    assert captured_stage1[0].resume_skills == ["Python", "FastAPI"]


@patch("src.analyzer.create_gemini_llm")
def test_analyze_resume_fallback_to_secondary_model(mock_create_llm):
    """Verify that analyzer falls back to gemini-3.8-flash when primary model fails."""
    # Primary model (gemini-3.5-flash-lite) fails
    primary_llm = MagicMock()
    primary_structured = MagicMock()
    primary_structured.side_effect = RuntimeError("ResourceExhausted: Quota exceeded for gemini-3.5-flash-lite")
    primary_llm.with_structured_output.return_value = primary_structured

    # Fallback model (gemini-3.8-flash) succeeds
    fallback_llm = MagicMock()
    mock_stage1_output = ExtractionResult(resume_skills=["Python"])
    mock_stage2_output = ResumeAnalysisResult(
        match_score=90,
        score_explanation="Analyzed using fallback model.",
        section_feedback=SectionFeedback(
            summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
        ),
        priority_fixes=["Review fallback output"],
    )

    def mock_fallback_structured(schema):
        if schema == ExtractionResult:
            return RunnableLambda(lambda x: mock_stage1_output)
        return RunnableLambda(lambda x: mock_stage2_output)

    fallback_llm.with_structured_output.side_effect = mock_fallback_structured

    # Dispatch based on model_name
    def create_mock_llm(api_key=None, model_name=None, temperature=0.1):
        if model_name == "gemini-3.5-flash-lite":
            return primary_llm
        return fallback_llm

    mock_create_llm.side_effect = create_mock_llm

    result = analyze_resume(
        resume_text="John Doe\nPython Engineer",
        jd_text="Senior Python Engineer needed.",
        api_key="mock-api-key",
        model_name="gemini-3.5-flash-lite",
        fallback_model_name="gemini-3.8-flash",
    )

    assert result.match_score == 90
    assert result.score_explanation == "Analyzed using fallback model."


@patch("src.analyzer.create_gemini_llm")
def test_analyze_resume_with_resume_and_jd_pdfs(mock_create_llm):
    """Verify analyze_resume accepts PDF streams/bytes for both Resume and Job Description."""
    import io
    from reportlab.pdfgen import canvas

    def _make_pdf(lines: list[str]) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 750
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.save()
        return buf.getvalue()

    resume_pdf_bytes = _make_pdf(
        [
            "Alex Rivera - Backend Software Engineer",
            "Experienced in Python, FastAPI, PostgreSQL, Docker, and Pytest.",
        ]
    )
    jd_pdf_bytes = _make_pdf(
        [
            "Senior Backend Engineer Job Description",
            "Must have strong Python, FastAPI, PostgreSQL, and REST API skills.",
        ]
    )

    mock_llm = MagicMock()
    mock_create_llm.return_value = mock_llm

    captured_inputs = {}

    def mock_structured_output(schema):
        if schema == ExtractionResult:
            def _stage1_fn(prompt_val):
                captured_inputs["stage1_prompt"] = str(prompt_val)
                return ExtractionResult(
                    resume_skills=["Python", "FastAPI", "PostgreSQL"],
                    jd_required_skills=["Python", "FastAPI", "PostgreSQL"],
                )
            return RunnableLambda(_stage1_fn)
        return RunnableLambda(
            lambda _: ResumeAnalysisResult(
                match_score=88,
                score_explanation="Strong match across PDF inputs.",
                matched_skills=["Python", "FastAPI", "PostgreSQL"],
                missing_skills=[],
                section_feedback=SectionFeedback(
                    summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
                ),
                priority_fixes=["Add metrics to bullets"],
            )
        )

    mock_llm.with_structured_output.side_effect = mock_structured_output

    result = analyze_resume(
        resume_pdf=resume_pdf_bytes,
        jd_pdf=io.BytesIO(jd_pdf_bytes),
        api_key="mock-api-key",
    )

    assert result.match_score == 88
    assert "Alex Rivera" in captured_inputs["stage1_prompt"]
    assert "Senior Backend Engineer Job Description" in captured_inputs["stage1_prompt"]


@patch("src.analyzer.create_gemini_llm")
def test_analyze_resume_handles_none_structured_output(mock_create_llm):
    """Verify None returned from structured output raises RuntimeError cleanly instead of AttributeError."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = RunnableLambda(lambda _: None)
    mock_create_llm.return_value = mock_llm

    with pytest.raises(RuntimeError, match="empty response"):
        analyze_resume(
            resume_text="Jane Doe - Python Engineer",
            jd_text="Backend Python Engineer needed.",
            api_key="mock-api-key",
            model_name="gemini-3.5-flash-lite",
            fallback_model_name="gemini-3.5-flash-lite",
        )


@patch("src.analyzer.create_gemini_llm")
def test_analyze_resume_redacts_pii_before_llm_invocation(mock_create_llm):
    """Verify emails, phones, and profile URLs are masked locally before reaching the model."""
    mock_llm = MagicMock()
    mock_create_llm.return_value = mock_llm
    captured = {}

    def mock_structured_output(schema):
        if schema == ExtractionResult:
            def _capture_stage1(prompt_val):
                captured["prompt_str"] = str(prompt_val)
                return ExtractionResult(resume_skills=["Python"], jd_required_skills=["Python"])
            return RunnableLambda(_capture_stage1)
        return RunnableLambda(
            lambda _: ResumeAnalysisResult(
                match_score=85,
                score_explanation="Strong alignment.",
                matched_skills=["Python"],
                missing_skills=[],
                section_feedback=SectionFeedback(
                    summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
                ),
                priority_fixes=["Add metrics"],
            )
        )

    mock_llm.with_structured_output.side_effect = mock_structured_output

    analyze_resume(
        resume_text="Alex Rivera | alex.secret@gmail.com | (415) 555-9876 | linkedin.com/in/alexrivera\nPython Engineer",
        jd_text="Send applications to jobs@company.com for Python Engineer role.",
        api_key="mock-api-key",
    )

    sent_prompt = captured["prompt_str"]
    assert "alex.secret@gmail.com" not in sent_prompt
    assert "555-9876" not in sent_prompt
    assert "linkedin.com/in/alexrivera" not in sent_prompt
    assert "jobs@company.com" not in sent_prompt
    assert "[EMAIL REDACTED]" in sent_prompt
    assert "[PHONE REDACTED]" in sent_prompt
    assert "[LINK REDACTED]" in sent_prompt


def test_reconcile_evaluation_scores_sum_and_hard_cap():
    """Verify deterministic sub-score summation and <50% required-skills hard cap enforcement."""
    fb = SectionFeedback(
        summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
    )

    # Case 1: >=50% required skills matched (including plural 'REST APIs' matching 'REST API design')
    ext_strong = ExtractionResult(
        jd_required_skills=["Python", "REST API design", "Docker"],
    )
    eval_strong = ResumeAnalysisResult(
        match_score=70,  # out-of-sync LLM total; should reconcile to 40+25+8+9 = 82
        required_skills_score=40,
        experience_alignment_score=25,
        preferred_and_education_score=8,
        clarity_and_impact_score=9,
        score_explanation="Good match.",
        matched_skills=["Python", "REST APIs"],
        missing_skills=["Docker"],
        section_feedback=fb,
        priority_fixes=["Add Docker"],
    )
    reconciled_strong = reconcile_evaluation_scores(eval_strong, ext_strong)
    assert reconciled_strong.match_score == 82

    # Case 2: <50% required skills matched -> must clamp match_score to <= 50 even if subscores sum to 62
    ext_weak = ExtractionResult(
        jd_required_skills=["Python", "Spark", "Airflow", "Snowflake", "Kafka"],
    )
    eval_weak = ResumeAnalysisResult(
        match_score=65,
        required_skills_score=20,
        experience_alignment_score=25,
        preferred_and_education_score=8,
        clarity_and_impact_score=9,
        score_explanation="Missing core data engineering stack.",
        matched_skills=["Python"],
        missing_skills=["Spark", "Airflow", "Snowflake", "Kafka"],
        section_feedback=fb,
        priority_fixes=["Gain Spark and Airflow exposure"],
    )
    reconciled_weak = reconcile_evaluation_scores(eval_weak, ext_weak)
    assert reconciled_weak.match_score == 50
    assert reconciled_weak.required_skills_score == 20


@patch("src.analyzer.create_gemini_llm")
def test_analyze_resume_with_docx_and_txt_files(mock_create_llm):
    """Verify analyze_resume accepts .docx and .txt uploads and masks PII before invoking the model."""
    import io
    import zipfile

    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    doc_xml = (
        f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f"<w:document xmlns:w='{w_ns}'><w:body>"
        f"<w:p><w:r><w:t>Sam Taylor | sam@private.org | Senior Python &amp; FastAPI Engineer</w:t></w:r></w:p>"
        f"</w:body></w:document>"
    )
    docx_buf = io.BytesIO()
    with zipfile.ZipFile(docx_buf, "w") as zf:
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))

    jd_txt_bytes = (
        b"Backend Role: Must know Python, FastAPI, PostgreSQL, and automated testing. Contact hr@corp.io."
    )

    captured = {}
    mock_llm = MagicMock()
    mock_create_llm.return_value = mock_llm

    def mock_structured(schema):
        if schema == ExtractionResult:
            def _s1(prompt_val):
                captured["prompt"] = str(prompt_val)
                return ExtractionResult(
                    resume_skills=["Python", "FastAPI"],
                    projects_section="PulseTrack Telemetry Service (FastAPI, Redis)",
                    jd_role_title="Senior Backend Platform Engineer",
                    jd_required_skills=["Python", "FastAPI", "PostgreSQL"],
                )
            return RunnableLambda(_s1)

        def _s2(prompt_val):
            captured["stage2_prompt"] = str(prompt_val)
            return ResumeAnalysisResult(
                match_score=80,
                required_skills_score=36,
                experience_alignment_score=26,
                preferred_and_education_score=9,
                clarity_and_impact_score=9,
                score_explanation="Strong Python/FastAPI alignment.",
                matched_skills=["Python", "FastAPI"],
                missing_skills=["PostgreSQL"],
                section_feedback=SectionFeedback(
                    summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
                ),
                suggested_summary="Backend Engineer experienced in Python and FastAPI.",
                interview_questions=[
                    {
                        "resume_anchor": "PulseTrack Telemetry Service (FastAPI, Redis)",
                        "jd_focus": "PostgreSQL Schema & Indexing",
                        "question": "In your PulseTrack Telemetry Service, how would you persist time-series events in PostgreSQL?",
                        "preparation_tip": "Connect your Redis caching design in PulseTrack to relational indexing trade-offs.",
                    }
                ],
                priority_fixes=["Highlight relational database experience"],
            )

        return RunnableLambda(_s2)

    mock_llm.with_structured_output.side_effect = mock_structured

    res = analyze_resume(
        resume_file=docx_buf.getvalue(),
        resume_filename="sam_resume.docx",
        jd_file=jd_txt_bytes,
        jd_filename="backend_jd.txt",
        api_key="mock-api-key",
    )

    assert res.match_score == 80
    assert "sam@private.org" not in captured["prompt"]
    assert "hr@corp.io" not in captured["prompt"]
    assert "[EMAIL REDACTED]" in captured["prompt"]
    # Verify Stage 2 receives both extracted facts AND scrubbed resume/JD context for personalization
    assert "sam@private.org" not in captured["stage2_prompt"]
    assert "PulseTrack Telemetry Service" in captured["stage2_prompt"]
    assert "Sam Taylor" in captured["stage2_prompt"]
    assert len(res.interview_questions) == 1
    assert "PulseTrack" in res.interview_questions[0].resume_anchor
