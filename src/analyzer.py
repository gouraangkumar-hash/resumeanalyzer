"""Resume analysis service using LangChain and Google Gemini API.

Orchestrates a two-stage pipeline:
1. Stage 1: Fact and requirement extraction (ExtractionResult)
2. Stage 2: Rubric-based comparative evaluation and coaching (ResumeAnalysisResult)
Supports plain text, PDF, DOCX, and TXT inputs for Resume and Job Description.
"""

import os
from pathlib import Path
from typing import BinaryIO, Callable, Optional, Union
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from src.pdf_parser import extract_text_from_document, extract_text_from_pdf
from src.pii import redact_pii
from src.schemas import ExtractionResult, ResumeAnalysisResult, skill_is_matched
from src.prompts import STAGE1_PROMPT, STAGE2_PROMPT

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Loads environment variables from .env in project root with fallback."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=True)
    else:
        load_dotenv(override=True)


# Initial environment load
load_env()

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
MAX_JD_CHARS = 15000
MAX_RESUME_CHARS = 30000


def get_api_key(api_key: Optional[str] = None) -> str:
    """Retrieves and validates the Google Gemini API key."""
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key or not key.strip() or key.strip() == "your_gemini_api_key_here":
        raise ValueError(
            "Google Gemini API key not found. Please set GOOGLE_API_KEY in your .env file "
            "in the project root."
        )
    return key.strip()


def create_gemini_llm(
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.1,
) -> ChatGoogleGenerativeAI:
    """Initializes the Gemini chat model with the required configuration."""
    key = get_api_key(api_key)
    model = model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=key,
        temperature=temperature,
    )


def reconcile_evaluation_scores(
    evaluation_result: ResumeAnalysisResult,
    extracted_facts: ExtractionResult,
) -> ResumeAnalysisResult:
    """Deterministically reconciles match_score from sub-scores and enforces the <50% required-skills cap."""
    subscores = (
        evaluation_result.required_skills_score,
        evaluation_result.experience_alignment_score,
        evaluation_result.preferred_and_education_score,
        evaluation_result.clarity_and_impact_score,
    )
    if all(score is not None for score in subscores):
        raw_total = sum(int(s) for s in subscores if s is not None)
        evaluation_result.match_score = max(0, min(100, raw_total))

    req_skills = [s.strip() for s in extracted_facts.jd_required_skills if s and s.strip()]
    if req_skills:
        matched_req = sum(
            1 for r in req_skills if skill_is_matched(r, evaluation_result.matched_skills)
        )
        if (matched_req / len(req_skills)) < 0.5:
            evaluation_result.match_score = min(evaluation_result.match_score, 50)

    return evaluation_result


def _run_two_stage_pipeline(
    llm: ChatGoogleGenerativeAI,
    cleaned_resume: str,
    cleaned_jd: str,
    on_stage1_complete: Optional[Callable[[ExtractionResult], None]] = None,
) -> ResumeAnalysisResult:
    """Executes Stage 1 extraction followed by Stage 2 evaluation."""
    stage1_structured_llm = llm.with_structured_output(ExtractionResult)
    stage1_chain = STAGE1_PROMPT | stage1_structured_llm

    extracted_facts = stage1_chain.invoke(
        {"resume_text": cleaned_resume, "jd_text": cleaned_jd}
    )
    if extracted_facts is None:
        raise RuntimeError(
            "Document requirement extraction returned an empty response from the model."
        )
    if isinstance(extracted_facts, dict):
        extracted_facts = ExtractionResult.model_validate(extracted_facts)

    if on_stage1_complete is not None:
        on_stage1_complete(extracted_facts)

    stage2_structured_llm = llm.with_structured_output(ResumeAnalysisResult)
    stage2_chain = STAGE2_PROMPT | stage2_structured_llm

    evaluation_result = stage2_chain.invoke(
        {
            "extracted_data_json": extracted_facts.model_dump_json(indent=2),
            "resume_text": cleaned_resume,
            "jd_text": cleaned_jd,
        }
    )
    if evaluation_result is None:
        raise RuntimeError(
            "Resume evaluation returned an empty response from the model."
        )
    if isinstance(evaluation_result, dict):
        evaluation_result = ResumeAnalysisResult.model_validate(evaluation_result)

    return reconcile_evaluation_scores(evaluation_result, extracted_facts)


def _handle_llm_exception(exc: Exception) -> None:
    """Translates common API errors into user-friendly exceptions."""
    err_msg = str(exc)
    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
        raise RuntimeError(
            "Service rate limit or quota exceeded. Please wait a minute before trying again."
        ) from exc
    if "401" in err_msg or "403" in err_msg or "API_KEY_INVALID" in err_msg:
        raise RuntimeError(
            "Invalid API key configured. Please check your credentials in .env."
        ) from exc
    raise RuntimeError(f"Resume evaluation failed: {exc}") from exc


def analyze_resume(
    resume_text: Optional[Union[str, bytes, BinaryIO]] = None,
    jd_text: Optional[Union[str, bytes, BinaryIO]] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    fallback_model_name: Optional[str] = None,
    on_stage1_complete: Optional[Callable[[ExtractionResult], None]] = None,
    resume_pdf: Optional[Union[BinaryIO, bytes, str, Path]] = None,
    jd_pdf: Optional[Union[BinaryIO, bytes, str, Path]] = None,
    redact_pii_enabled: bool = True,
    resume_file: Optional[Union[BinaryIO, bytes, str, Path]] = None,
    resume_filename: str = "",
    jd_file: Optional[Union[BinaryIO, bytes, str, Path]] = None,
    jd_filename: str = "",
) -> ResumeAnalysisResult:
    """Executes the resume against job description evaluation with text, PDF, DOCX, or TXT inputs."""
    # Resolve Resume input
    if resume_file is not None:
        resolved_resume = extract_text_from_document(
            resume_file, filename=resume_filename, document_name="Resume"
        )
    elif resume_pdf is not None:
        resolved_resume = extract_text_from_pdf(resume_pdf, document_name="Resume PDF")
    elif isinstance(resume_text, bytes) or hasattr(resume_text, "read"):
        resolved_resume = extract_text_from_document(
            resume_text, filename=resume_filename, document_name="Resume"
        )
    else:
        resolved_resume = resume_text or ""

    # Resolve Job Description input
    if jd_file is not None:
        resolved_jd = extract_text_from_document(
            jd_file, filename=jd_filename, document_name="Job Description"
        )
    elif jd_pdf is not None:
        resolved_jd = extract_text_from_pdf(jd_pdf, document_name="Job Description PDF")
    elif isinstance(jd_text, bytes) or hasattr(jd_text, "read"):
        resolved_jd = extract_text_from_document(
            jd_text, filename=jd_filename, document_name="Job Description"
        )
    else:
        resolved_jd = jd_text or ""

    if not resolved_resume or not resolved_resume.strip():
        raise ValueError(
            "Resume text is empty. Please provide a valid resume file (.pdf, .docx, .txt) or text."
        )

    if not resolved_jd or not resolved_jd.strip():
        raise ValueError(
            "Job description is empty. Please provide a valid job description file (.pdf, .docx, .txt) or text."
        )

    if redact_pii_enabled:
        resolved_resume, _ = redact_pii(resolved_resume)
        resolved_jd, _ = redact_pii(resolved_jd)

    cleaned_resume = resolved_resume.strip()[:MAX_RESUME_CHARS]
    cleaned_jd = resolved_jd.strip()[:MAX_JD_CHARS]

    primary_model = model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    fallback_model = fallback_model_name or os.getenv("GEMINI_FALLBACK_MODEL", FALLBACK_MODEL)

    try:
        llm = create_gemini_llm(api_key=api_key, model_name=primary_model, temperature=0.1)
        return _run_two_stage_pipeline(
            llm, cleaned_resume, cleaned_jd, on_stage1_complete=on_stage1_complete
        )
    except Exception as primary_exc:
        if fallback_model and fallback_model != primary_model:
            try:
                fallback_llm = create_gemini_llm(
                    api_key=api_key, model_name=fallback_model, temperature=0.1
                )
                return _run_two_stage_pipeline(
                    fallback_llm,
                    cleaned_resume,
                    cleaned_jd,
                    on_stage1_complete=on_stage1_complete,
                )
            except Exception as fallback_exc:
                _handle_llm_exception(fallback_exc)

        _handle_llm_exception(primary_exc)
