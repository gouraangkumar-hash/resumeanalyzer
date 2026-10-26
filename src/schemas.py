"""Pydantic data schemas for AI Resume Analyzer.

Stage 1 schema: ExtractionResult
Stage 2 schemas: SectionFeedback, BulletImprovement, ResumeAnalysisResult
"""

from typing import List
from pydantic import BaseModel, Field, field_validator


class ExtractionResult(BaseModel):
    """Structured facts extracted from the resume and requirements from the JD."""

    resume_skills: List[str] = Field(
        default_factory=list,
        description="Explicit skills, tools, languages, and frameworks stated in the resume.",
    )
    summary_section: str = Field(
        default="Not present",
        description="Factual summary or objective statement from the resume.",
    )
    skills_section: str = Field(
        default="Not present",
        description="Skills section overview from the resume.",
    )
    projects_section: str = Field(
        default="Not present",
        description="Factual projects listed in the resume.",
    )
    experience_section: str = Field(
        default="Not present",
        description="Factual work experience and roles from the resume.",
    )
    education_section: str = Field(
        default="Not present",
        description="Degrees, universities, and certifications from the resume.",
    )
    sample_resume_bullets: List[str] = Field(
        default_factory=list,
        description="Verbatim bullet points from the resume that could be improved.",
    )
    jd_required_skills: List[str] = Field(
        default_factory=list,
        description="Must-have or required skills and qualifications stated in the JD.",
    )
    jd_preferred_skills: List[str] = Field(
        default_factory=list,
        description="Preferred, bonus, or nice-to-have skills stated in the JD.",
    )
    jd_core_responsibilities: List[str] = Field(
        default_factory=list,
        description="Key responsibilities and duties stated in the JD.",
    )


class SectionFeedback(BaseModel):
    """Section-wise feedback across standard resume sections."""

    summary: str = Field(
        description="Feedback on summary or objective statement (note if absent).",
    )
    skills: str = Field(
        description="Feedback on skills organization and JD keyword alignment.",
    )
    projects: str = Field(
        description="Feedback on project relevance, technical depth, and impact.",
    )
    experience: str = Field(
        description="Feedback on work experience description and alignment with responsibilities.",
    )
    education: str = Field(
        description="Feedback on education and certifications alignment.",
    )


class BulletImprovement(BaseModel):
    """A rewritten bullet point demonstrating how to improve clarity and impact."""

    original_bullet: str = Field(
        description="Original verbatim bullet point from the candidate's resume.",
    )
    suggested_bullet: str = Field(
        description="Rewritten bullet point using strong action verbs, JD alignment, and [placeholder] metrics.",
    )
    rationale: str = Field(
        description="Reasoning behind why the rewrite is stronger.",
    )


class ResumeAnalysisResult(BaseModel):
    """Final evaluation and coaching output generated in Stage 2."""

    match_score: int = Field(
        ge=0,
        le=100,
        description="Heuristic match score from 0 to 100 based on the rubric.",
    )
    score_explanation: str = Field(
        description="Explanation of the score breakdown across required skills, experience, and presentation.",
    )
    matched_skills: List[str] = Field(
        default_factory=list,
        description="Skills present in the resume that match the job description.",
    )
    missing_skills: List[str] = Field(
        default_factory=list,
        description="Skills required or preferred by the job description that are missing from the resume.",
    )
    section_feedback: SectionFeedback = Field(
        description="Feedback broken down by standard resume sections.",
    )
    weaknesses: List[str] = Field(
        default_factory=list,
        description="Specific gaps or weaknesses in the resume relative to the JD.",
    )
    improved_bullets: List[BulletImprovement] = Field(
        default_factory=list,
        description="Suggestions for improving existing resume bullet points.",
    )
    priority_fixes: List[str] = Field(
        default_factory=list,
        description="Top three actionable fixes for the candidate to address first.",
    )

    @field_validator("priority_fixes")
    @classmethod
    def validate_priority_fixes(cls, v: List[str]) -> List[str]:
        """Ensure priority fixes are non-empty and reasonably sized."""
        if not v:
            return ["Address missing required skills", "Quantify bullet points with [Metric] placeholders", "Tailor project descriptions to the JD"]
        return v
