"""Unit tests for Pydantic output schemas (Person 1 deliverable)."""

import pytest
from pydantic import ValidationError
from src.schemas import (
    ExtractionResult,
    SectionFeedback,
    BulletImprovement,
    InterviewQuestion,
    ResumeAnalysisResult,
)


def test_extraction_result_defaults():
    """Verify ExtractionResult has safe default values for absent sections."""
    result = ExtractionResult()
    assert result.resume_skills == []
    assert result.summary_section == "Not present"
    assert result.experience_section == "Not present"
    assert result.jd_required_skills == []


def test_section_feedback_creation():
    """Verify SectionFeedback holds feedback strings across all sections."""
    feedback = SectionFeedback(
        summary="Strong summary highlighting experience.",
        skills="Missing Docker and Kubernetes from JD.",
        projects="Projects demonstrate Python well.",
        experience="Experience lacks quantitative metrics.",
        education="B.S. in CS matches degree requirement.",
    )
    assert feedback.summary.startswith("Strong")
    assert "Docker" in feedback.skills


def test_bullet_improvement_creation():
    """Verify BulletImprovement schema fields."""
    bullet = BulletImprovement(
        original_bullet="Worked on python backend.",
        suggested_bullet="Architected REST APIs using Python, serving [N] requests/day.",
        rationale="Adds concrete technical details and placeholder for scale.",
    )
    assert "[N]" in bullet.suggested_bullet
    assert bullet.original_bullet == "Worked on python backend."


def test_resume_analysis_result_valid():
    """Verify a full valid ResumeAnalysisResult instance."""
    result = ResumeAnalysisResult(
        match_score=85,
        score_explanation="Matches 4 of 5 required skills, relevant projects present.",
        matched_skills=["Python", "Streamlit", "SQL"],
        missing_skills=["Docker"],
        section_feedback=SectionFeedback(
            summary="Clear summary.",
            skills="Good match on core skills.",
            projects="Directly applicable.",
            experience="Good progression.",
            education="Relevant B.S. degree.",
        ),
        weaknesses=["No containerization experience mentioned."],
        improved_bullets=[
            BulletImprovement(
                original_bullet="Built website.",
                suggested_bullet="Engineered interactive web portal in Streamlit, reducing turnaround by [X]%.",
                rationale="Quantifies impact and aligns with UI role.",
            )
        ],
        priority_fixes=[
            "Add Docker or containerization exposure.",
            "Add quantitative metrics to experience bullets using [Metric] placeholders.",
            "Tailor project titles to match JD keywords.",
        ],
    )
    assert result.match_score == 85
    assert len(result.priority_fixes) == 3


def test_resume_analysis_result_score_bounds():
    """Verify match_score must be between 0 and 100."""
    feedback = SectionFeedback(
        summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
    )

    # Test score > 100
    with pytest.raises(ValidationError):
        ResumeAnalysisResult(
            match_score=105,
            score_explanation="Invalid score",
            section_feedback=feedback,
        )

    # Test score < 0
    with pytest.raises(ValidationError):
        ResumeAnalysisResult(
            match_score=-5,
            score_explanation="Invalid score",
            section_feedback=feedback,
        )


def test_priority_fixes_empty_default():
    """Verify validator generates sensible defaults if priority_fixes is empty."""
    feedback = SectionFeedback(
        summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
    )
    result = ResumeAnalysisResult(
        match_score=70,
        score_explanation="Average match",
        section_feedback=feedback,
        priority_fixes=["   ", ""],
    )
    assert len(result.priority_fixes) >= 1
    assert all(fix.strip() for fix in result.priority_fixes)


def test_subscores_summary_and_interview_questions_validation():
    """Verify category sub-score bounds, summary trimming, and structured/string interview question cleanup."""
    feedback = SectionFeedback(
        summary="ok", skills="ok", projects="ok", experience="ok", education="ok"
    )
    res = ResumeAnalysisResult(
        match_score=83,
        required_skills_score=42,
        experience_alignment_score=24,
        preferred_and_education_score=8,
        clarity_and_impact_score=9,
        score_explanation="Strong alignment.",
        section_feedback=feedback,
        suggested_summary="  Backend engineer skilled in Python and FastAPI with [N] years of experience.  ",
        interview_questions=[
            InterviewQuestion(
                resume_anchor="  **OrderStream API project (Flask, MySQL)**  ",
                jd_focus="  PostgreSQL Migration & Docker  ",
                question="1. **In your OrderStream API project, how would you migrate your MySQL schema to PostgreSQL?**",
                preparation_tip="  Walk through **OrderStream's** current schema and indexing choices honestly.  ",
            ),
            "  Q2: How would you design container orchestration in Kubernetes?  ",
            "",
            "   ",
        ],
        priority_fixes=["Add container orchestration project details."],
    )
    assert res.required_skills_score == 42
    assert res.suggested_summary.startswith("Backend engineer")
    assert len(res.interview_questions) == 2
    assert res.interview_questions[0].resume_anchor == "OrderStream API project (Flask, MySQL)"
    assert res.interview_questions[0].question == (
        "In your OrderStream API project, how would you migrate your MySQL schema to PostgreSQL?"
    )
    assert "**" not in res.interview_questions[0].preparation_tip
    assert res.interview_questions[1].question == (
        "How would you design container orchestration in Kubernetes?"
    )

    with pytest.raises(ValidationError):
        ResumeAnalysisResult(
            match_score=80,
            required_skills_score=55,  # exceeds max 50
            score_explanation="Invalid subscore",
            section_feedback=feedback,
        )
