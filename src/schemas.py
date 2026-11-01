"""Pydantic data schemas for AI Resume Analyzer.

Stage 1 schema: ExtractionResult
Stage 2 schemas: SectionFeedback, BulletImprovement, ResumeAnalysisResult
"""

from typing import Any, List, Optional
import re
from pydantic import BaseModel, Field, field_validator


def _normalize_skill_phrase(text: str) -> str:
    """Lowercases whitespace-normalized skill text and normalizes simple plural endings."""
    cleaned = re.sub(r"\s+", " ", text.lower().strip())
    # Normalize trailing plural 's' on words of 4+ letters (e.g. 'apis' -> 'api', 'pipelines' -> 'pipeline')
    return re.sub(r"\b([a-z]{3,})s\b", r"\1", cleaned)


def skill_is_matched(req_skill: str, matched_skills: List[str]) -> bool:
    """Checks whether a required JD skill is satisfied by any skill in matched_skills."""
    req = req_skill.lower().strip()
    if not req:
        return False
    req_norm = _normalize_skill_phrase(req)

    for raw_match in matched_skills:
        if not raw_match or not raw_match.strip():
            continue
        m = raw_match.lower().strip()
        if req == m:
            return True
        if len(req) >= 3 and len(m) >= 3 and (req in m or m in req):
            return True
        m_norm = _normalize_skill_phrase(m)
        if req_norm and m_norm:
            if req_norm == m_norm:
                return True
            if len(req_norm) >= 3 and len(m_norm) >= 3 and (
                req_norm in m_norm or m_norm in req_norm
            ):
                return True
    return False


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
        description="Detailed factual projects from the resume, preserving exact project names, tech stacks used per project, and stated outcomes.",
    )
    experience_section: str = Field(
        default="Not present",
        description="Detailed factual work experience from the resume, preserving exact role titles, domains, tools used, and stated responsibilities/outcomes.",
    )
    education_section: str = Field(
        default="Not present",
        description="Degrees, universities, and certifications from the resume.",
    )
    sample_resume_bullets: List[str] = Field(
        default_factory=list,
        description="Verbatim bullet points from the resume that could be improved.",
    )
    jd_role_title: str = Field(
        default="Target Role",
        description="Exact job title and team or domain focus stated in the job description.",
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


def _clean_plain_field(text: str, strip_leading_num: bool = False) -> str:
    """Removes stray markdown bold/italic asterisks and optional leading numbering."""
    cleaned = (text or "").replace("**", "").strip()
    if strip_leading_num:
        cleaned = re.sub(
            r"^(?:question\s*\d+\s*[:.)\-]|q\d+\s*[:.)\-]|\d+\s*[.)\-])\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
    return cleaned


class InterviewQuestion(BaseModel):
    """A personalized interview question anchored in a specific resume detail and linked to a JD requirement."""

    resume_anchor: str = Field(
        default="Resume Experience",
        description="Exact project name, role title, or specific bullet claim from the candidate's resume that anchors this question.",
    )
    jd_focus: str = Field(
        default="Role Alignment",
        description="Specific job description requirement, missing skill, or responsibility being probed.",
    )
    question: str = Field(
        description="Personalized interviewer question explicitly referencing the candidate's stated work (resume_anchor) in relation to jd_focus.",
    )
    preparation_tip: str = Field(
        default="",
        description="Plain-English coaching on how to answer honestly using stated resume work and transferable skills without claiming unverified experience.",
    )

    @field_validator("resume_anchor", "jd_focus", "preparation_tip")
    @classmethod
    def clean_metadata_fields(cls, v: str) -> str:
        return _clean_plain_field(v, strip_leading_num=False)

    @field_validator("question")
    @classmethod
    def clean_question_text(cls, v: str) -> str:
        return _clean_plain_field(v, strip_leading_num=True)


class ResumeAnalysisResult(BaseModel):
    """Final evaluation and coaching output generated in Stage 2."""

    match_score: int = Field(
        ge=0,
        le=100,
        description="Overall match score from 0 to 100 based on the rubric.",
    )
    required_skills_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=50,
        description="Earned points out of 50 for required skills and core qualifications.",
    )
    experience_alignment_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=30,
        description="Earned points out of 30 for relevant experience and project alignment.",
    )
    preferred_and_education_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=10,
        description="Earned points out of 10 for preferred skills and education fit.",
    )
    clarity_and_impact_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=10,
        description="Earned points out of 10 for resume structure, completeness, and impact clarity.",
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
    suggested_summary: str = Field(
        default="",
        description="Tailored 2 to 3 sentence professional summary grounded strictly in stated resume facts, using [placeholder] tokens if needed.",
    )
    interview_questions: List[InterviewQuestion] = Field(
        default_factory=list,
        description="3 to 5 personalized interview questions anchored in specific projects, roles, or bullets from the candidate's resume and mapped to target JD requirements.",
    )
    priority_fixes: List[str] = Field(
        default_factory=list,
        description="Top three actionable fixes for the candidate to address first.",
    )

    @field_validator("suggested_summary")
    @classmethod
    def validate_suggested_summary(cls, v: str) -> str:
        """Trim surrounding whitespace on suggested_summary."""
        return (v or "").strip()

    @field_validator("interview_questions", mode="before")
    @classmethod
    def validate_interview_questions(cls, v: Any) -> List[Any]:
        """Coerces string or dict items into clean InterviewQuestion entries and drops blanks."""
        if not v:
            return []
        cleaned: List[Any] = []
        for item in v:
            if isinstance(item, InterviewQuestion):
                if item.question and item.question.strip():
                    cleaned.append(item)
            elif isinstance(item, str):
                q_str = _clean_plain_field(item, strip_leading_num=True)
                if q_str:
                    cleaned.append({"question": q_str})
            elif isinstance(item, dict):
                q_val = _clean_plain_field(str(item.get("question", "")), strip_leading_num=True)
                if q_val:
                    normalized = dict(item)
                    normalized["question"] = q_val
                    cleaned.append(normalized)
        return cleaned[:6]

    @field_validator("priority_fixes")
    @classmethod
    def validate_priority_fixes(cls, v: List[str]) -> List[str]:
        """Ensure priority fixes are non-empty and free of blank strings."""
        cleaned = [item.strip() for item in v if item and item.strip()]
        if not cleaned:
            return [
                "Address missing required qualifications from the job description.",
                "Add measurable outcomes to experience bullet points.",
                "Align project descriptions with core role responsibilities.",
            ]
        return cleaned
