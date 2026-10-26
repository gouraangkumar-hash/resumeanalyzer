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

    # Run analyzer with dummy input
    result = analyze_resume(
        resume_text="Jane Doe\nPython Developer with FastAPI experience.",
        jd_text="Looking for a Python Developer proficient in FastAPI and SQL.",
        api_key="mock-api-key",
    )

    assert result.match_score == 80
    assert "Python" in result.matched_skills
    assert "SQL" in result.missing_skills
    assert len(result.priority_fixes) == 3
    assert "[N]" in result.improved_bullets[0].suggested_bullet


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
