"""Resume analysis service using LangChain and Google Gemini API.

Orchestrates a two-stage prompt chain:
1. Stage 1: Fact and requirement extraction (ExtractionResult)
2. Stage 2: Rubric-based comparative evaluation and coaching (ResumeAnalysisResult)
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from src.schemas import ExtractionResult, ResumeAnalysisResult
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


def _run_two_stage_pipeline(
    llm: ChatGoogleGenerativeAI, cleaned_resume: str, cleaned_jd: str
) -> ResumeAnalysisResult:
    """Executes Stage 1 extraction followed by Stage 2 evaluation."""
    # Build Stage 1 chain: Extraction
    stage1_structured_llm = llm.with_structured_output(ExtractionResult)
    stage1_chain = STAGE1_PROMPT | stage1_structured_llm

    # Run Stage 1
    extracted_facts: ExtractionResult = stage1_chain.invoke(
        {"resume_text": cleaned_resume, "jd_text": cleaned_jd}
    )

    # Build Stage 2 chain: Evaluation
    stage2_structured_llm = llm.with_structured_output(ResumeAnalysisResult)
    stage2_chain = STAGE2_PROMPT | stage2_structured_llm

    # Run Stage 2 with the serialized extracted facts
    evaluation_result: ResumeAnalysisResult = stage2_chain.invoke(
        {"extracted_data_json": extracted_facts.model_dump_json(indent=2)}
    )

    return evaluation_result


def _handle_llm_exception(exc: Exception) -> None:
    """Translates common API errors into user-friendly exceptions."""
    err_msg = str(exc)
    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
        raise RuntimeError(
            "Gemini API rate limit or quota exceeded. Please wait a minute before trying again."
        ) from exc
    if "401" in err_msg or "403" in err_msg or "API_KEY_INVALID" in err_msg:
        raise RuntimeError(
            "Invalid Gemini API key. Please check your credentials in .env or the UI."
        ) from exc
    raise RuntimeError(f"Resume analysis failed: {exc}") from exc


def analyze_resume(
    resume_text: str,
    jd_text: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    fallback_model_name: Optional[str] = None,
) -> ResumeAnalysisResult:
    """Executes the two-stage resume analysis pipeline with automatic fallback.

    Args:
        resume_text: Cleaned text extracted from the candidate's resume.
        jd_text: Target job description text.
        api_key: Optional Gemini API key override (e.g. from Streamlit UI).
        model_name: Primary Gemini model name (defaults to gemini-3.5-flash-lite).
        fallback_model_name: Fallback model if primary encounters an error (defaults to gemini-3.8-flash).

    Returns:
        Validated ResumeAnalysisResult containing match score, skills gap,
        section feedback, bullet improvements, and priority fixes.

    Raises:
        ValueError: If input text is empty or invalid.
        RuntimeError: If LLM call or chain execution fails across both models.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError("Resume text is empty. Please provide a valid resume.")

    if not jd_text or not jd_text.strip():
        raise ValueError("Job description is empty. Please paste the job description text.")

    cleaned_resume = resume_text.strip()[:MAX_RESUME_CHARS]
    cleaned_jd = jd_text.strip()[:MAX_JD_CHARS]

    primary_model = model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    fallback_model = fallback_model_name or os.getenv("GEMINI_FALLBACK_MODEL", FALLBACK_MODEL)

    # Attempt primary model execution
    try:
        llm = create_gemini_llm(api_key=api_key, model_name=primary_model, temperature=0.1)
        return _run_two_stage_pipeline(llm, cleaned_resume, cleaned_jd)
    except Exception as primary_exc:
        # If a distinct fallback model is specified, attempt recovery
        if fallback_model and fallback_model != primary_model:
            try:
                fallback_llm = create_gemini_llm(
                    api_key=api_key, model_name=fallback_model, temperature=0.1
                )
                return _run_two_stage_pipeline(fallback_llm, cleaned_resume, cleaned_jd)
            except Exception as fallback_exc:
                _handle_llm_exception(fallback_exc)

        _handle_llm_exception(primary_exc)
