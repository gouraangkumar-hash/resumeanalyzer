# AI Resume Analyzer — Phase-by-Phase Implementation Plan

**Project Title:** AI Resume Analyzer: JD-Based Resume Evaluation Using LangChain and Prompt Engineering  
**Context:** College Prompt Engineering Assignment (2-Student Team)  
**Tech Stack:** Python 3.10+, Streamlit, LangChain (`langchain-core`, `langchain-google-genai`), Google Gemini API, Pydantic, `pypdf`, `python-dotenv`, `pytest`

---

## 1. Project Scope & Core Constraints

- **Academic Focus:** Prompt engineering (Role Prompting, Two-Stage Prompt Chaining, Few-Shot Prompting, Structured Output via Pydantic, and Anti-Fabrication Constraints) is the primary contribution.
- **Simplicity First:** Single Streamlit entry point (`app.py`) and 4 focused backend modules inside `src/`. No RAG, vector databases, embeddings, agents, LangGraph, authentication, databases, Docker, or paid infrastructure.
- **Grounded & Honest Output:**
  - Never fabricate candidate skills, experience, qualifications, or numerical metrics.
  - Use bracketed placeholders (e.g., `[X]%`, `[N] users`, `[Metric]`) when suggesting measurable bullet improvements where the original resume lacks numbers.
  - Clearly state in the UI and documentation that the match score is a **heuristic AI estimate**, not an official ATS score or recruiter hiring prediction.
- **Security:** Never hardcode or expose `GOOGLE_API_KEY`. Load secrets via `.env` and `python-dotenv`.

---

## 2. Final Folder Structure

```text
resumeanalyzer/
├── app.py                        # Single Streamlit entry point (run: streamlit run app.py)
├── src/
│   ├── __init__.py               # Package marker
│   ├── schemas.py                # Pydantic models for Stage 1 extraction & Stage 2 evaluation
│   ├── prompts.py                # Role prompts, few-shot examples, scoring rubric & templates
│   ├── analyzer.py               # Env/API key handling + 2-stage LangChain/Gemini pipeline
│   └── pdf_parser.py             # pypdf text extraction and empty/scanned PDF validation
├── tests/
│   ├── test_analyzer.py          # Unit tests for Pydantic schemas & mocked 2-stage LLM chain
│   └── test_pdf_parser.py        # Unit tests for PDF extraction & validation
├── .env.example                  # Template showing GOOGLE_API_KEY and GEMINI_MODEL
├── requirements.txt              # Minimal required Python dependencies (7 packages)
├── IMPLEMENTATION_PLAN.md        # Reference phase-by-phase plan
├── PROJECT_STATUS.md             # Progress log, decisions, and open issues
└── README.md                     # Setup instructions, prompt engineering notes & disclaimers
```

---

## 3. Team Division of Responsibilities

| Team Member | Role & Focus | Owned Files |
| :--- | :--- | :--- |
| **Person 1** | **Backend, Prompt Engineering, Output Schemas & LLM Integration** | `src/schemas.py`, `src/prompts.py`, `src/analyzer.py`, `tests/test_analyzer.py` |
| **Person 2** | **Streamlit UI, PDF Extraction, Integration, Usability & Documentation** | `src/pdf_parser.py`, `app.py`, `tests/test_pdf_parser.py`, `README.md`, `.env.example` |
| **Both** | **Prompt Review, Rubric Tuning & Final QA** | Co-review prompts/rubric, test end-to-end with sample resumes/JDs, update `PROJECT_STATUS.md` |

---

## 4. Architecture & UI-to-Backend Contracts

### 4.1 PDF Extraction Contract (`src/pdf_parser.py`)
- **Function:** `extract_text_from_pdf(pdf_file: BinaryIO) -> str`
- **Behavior:**
  - Reads uploaded PDF stream using `pypdf.PdfReader`.
  - Enforces a safe page cap (e.g., max 10 pages) and character cap (e.g., 25,000 characters).
  - Normalizes whitespace and checks that extracted text contains at least 50 characters.
  - Raises `ValueError` with a descriptive user-facing error if the PDF is empty, corrupted, or scanned/image-only.

### 4.2 Two-Stage LLM Analysis Contract (`src/analyzer.py`)
- **Function:** `analyze_resume(resume_text: str, jd_text: str) -> ResumeAnalysisResult`
- **Stage 1 — Fact & Requirement Extraction (`ExtractionResult`):**
  - *Role:* Objective Technical Document Parser.
  - *Input:* Raw `resume_text` and `jd_text`.
  - *Output (`ExtractionResult` Pydantic schema):*
    - `resume_skills: list[str]` — Explicitly stated skills/tools in the resume.
    - `summary_section: str` — Extracted summary/objective facts (or `"Not present"`).
    - `skills_section: str` — Extracted skills section overview (or `"Not present"`).
    - `projects_section: str` — Extracted projects facts (or `"Not present"`).
    - `experience_section: str` — Extracted work experience facts (or `"Not present"`).
    - `education_section: str` — Extracted education/degree facts (or `"Not present"`).
    - `sample_resume_bullets: list[str]` — Verbatim action bullets from the resume that could be improved.
    - `jd_required_skills: list[str]` — Must-have skills/qualifications from the JD.
    - `jd_preferred_skills: list[str]` — Nice-to-have/optional skills from the JD.
    - `jd_core_responsibilities: list[str]` — Key role duties from the JD.
- **Stage 2 — Rubric Evaluation & Coaching (`ResumeAnalysisResult`):**
  - *Role:* Senior Technical Recruiter & Evidence-Based Career Coach.
  - *Input:* Serialized `ExtractionResult` from Stage 1.
  - *Output (`ResumeAnalysisResult` Pydantic schema):*
    - `match_score: int` (`0` to `100`)
    - `score_explanation: str`
    - `matched_skills: list[str]`
    - `missing_skills: list[str]`
    - `section_feedback: SectionFeedback` (`summary`, `skills`, `projects`, `experience`, `education`)
    - `weaknesses: list[str]`
    - `improved_bullets: list[BulletImprovement]` (`original_bullet`, `suggested_bullet`, `rationale`)
    - `priority_fixes: list[str]` (3 highest-priority actionable fixes)

---

## 5. Heuristic Match-Scoring Rubric (0–100 Points)

1. **Required Skills & Core Qualifications (50 points):**
   - Proportional to the share of `jd_required_skills` explicitly supported in `resume_skills` / experience.
   - Unsupported or merely implied qualifications receive **0 points**.
2. **Relevant Experience & Project Alignment (30 points):**
   - Evaluates how well documented experience and projects align with `jd_core_responsibilities`.
3. **Preferred / Optional Keywords & Education Fit (10 points):**
   - Up to 10 points for `jd_preferred_skills` and degree alignment so optional keywords cannot mask missing required skills.
4. **Resume Completeness & Impact Clarity (10 points):**
   - Evaluates presence of core sections and clarity of bullet points.
5. **Hard Cap Rule:**
   - If the candidate matches **fewer than 50% of `jd_required_skills`**, `match_score` **must not exceed 50/100**.

---

## 6. Prompt Engineering Techniques Checklist

| Technique | Where Implemented | Academic Purpose |
| :--- | :--- | :--- |
| **Role Prompting** | `STAGE1_SYSTEM_PROMPT` & `STAGE2_SYSTEM_PROMPT` in `src/prompts.py` | Sets domain-specific behavior (Objective Parser in Stage 1; Evidence-Based Recruiter/Coach in Stage 2). |
| **Prompt Chaining** | `analyze_resume()` in `src/analyzer.py` | Separates factual extraction (Stage 1) from comparative evaluation (Stage 2) in 2 sequential LLM calls. |
| **Few-Shot Prompting** | `STAGE2_FEW_SHOT_EXAMPLES` in `src/prompts.py` | Demonstrates grounded skill classification and rewriting weak bullets using `[X]%` / `[Metric]` placeholders. |
| **Structured Output** | `.with_structured_output()` in `src/analyzer.py` + `src/schemas.py` | Enforces strict Pydantic schemas for reliable UI rendering and validation. |
| **Anti-Fabrication Constraints** | System instructions in `src/prompts.py` | Prevents hallucinated metrics, employers, degrees, or unverified skill matches. |

---

## 7. Detailed Phase-by-Phase Execution Plan

### Phase 1: Planning and Requirements (Completed)
- **Objective:** Define functional scope, prompt engineering strategy, minimal architecture, team split, rubric, and risk mitigations.
- **Deliverables:** `IMPLEMENTATION_PLAN.md`, `PROJECT_STATUS.md`.

### Phase 2: Project Setup & Environment Scaffolding
- **Objective:** Initialize the repository structure, dependency list, and environment variable template.
- **Planned Files:**
  - `requirements.txt` (`streamlit`, `langchain-core`, `langchain-google-genai`, `pydantic`, `pypdf`, `python-dotenv`, `pytest`)
  - `.env.example` (`GOOGLE_API_KEY=your_api_key_here`, `GEMINI_MODEL=gemini-2.5-flash`)
  - `src/__init__.py`
  - Update `PROJECT_STATUS.md`
- **Verification:** Check Python version (`>=3.10`), verify or install dependencies, and confirm `pytest` runs cleanly.

### Phase 3: Output Schemas & PDF Text Extraction
- **Objective:** Build the data contracts (`Person 1`) and the PDF text extraction utility (`Person 2`) with unit tests.
- **Planned Files:**
  - `src/schemas.py` — `ExtractionResult`, `SectionFeedback`, `BulletImprovement`, and `ResumeAnalysisResult` with field validators (`0 <= match_score <= 100`, 3 priority fixes).
  - `src/pdf_parser.py` — `extract_text_from_pdf()` using `pypdf` with empty/scanned PDF detection and page/length limits.
  - `tests/test_pdf_parser.py` — Unit tests for valid PDF extraction, empty/scanned PDF error raising, and input validation.
  - Update `PROJECT_STATUS.md`.
- **Verification:** Execute `pytest tests/test_pdf_parser.py` and verify all tests pass.

### Phase 4: Prompt Engineering & Two-Stage LLM Analyzer
- **Objective:** Implement the core prompt engineering artifacts and the 2-stage LangChain + Gemini pipeline (`Person 1`).
- **Planned Files:**
  - `src/prompts.py` — Stage 1 & Stage 2 `ChatPromptTemplate` definitions, role prompts, 100-point rubric, anti-fabrication rules, and few-shot examples.
  - `src/analyzer.py` — API key validation, `ChatGoogleGenerativeAI` initialization (`temperature=0.1`), and `analyze_resume(resume_text, jd_text)` executing Stage 1 $\rightarrow$ Stage 2 with `.with_structured_output()`.
  - `tests/test_analyzer.py` — Unit tests verifying Pydantic schema constraints, missing API key handling, and mocked 2-stage chain execution.
  - Update `PROJECT_STATUS.md`.
- **Verification:** Execute `pytest` across all test files and confirm 100% pass rate offline.

### Phase 5: Streamlit UI & End-to-End Integration
- **Objective:** Build the single-page Streamlit interface (`Person 2`) and connect it to `extract_text_from_pdf()` and `analyze_resume()`.
- **Planned Files:**
  - `app.py` — File uploader for PDF resume, text area for JD, "Analyze Resume" button, heuristic match score display with explicit ATS disclaimer banner, matched/missing skills columns, section-wise feedback tabs/expanders, weaknesses list, side-by-side bullet improvements, and top 3 priority fixes.
  - Update `PROJECT_STATUS.md`.
- **Verification:** Syntax/import check and startup smoke test of `app.py`, plus full `pytest` suite run.

### Phase 6: Testing, Documentation & Final Polish
- **Objective:** Finalize documentation (`Person 2`), review prompts & rubric (`Both`), and verify all acceptance criteria.
- **Planned Files:**
  - `README.md` — Project overview, architecture diagram, prompt engineering breakdown (Role, Chaining, Few-Shot, Structured Output, Anti-Hallucination), local setup (`streamlit run app.py`), team contributions, and ethical/ATS disclaimers.
  - Final update to `PROJECT_STATUS.md`.
- **Verification:** Run full `pytest` suite, verify all acceptance criteria, and confirm one-command local execution.

---

## 8. Risks & Mitigations Summary

- **Scanned/Image PDFs:** `pypdf` extracts `< 50` chars $\rightarrow$ raise clear `ValueError` advising user to upload a text-selectable PDF.
- **Missing API Key:** Checked before LLM invocation $\rightarrow$ show actionable setup instructions in UI.
- **Malformed LLM Output:** Mitigated via `.with_structured_output()` at `temperature=0.1` + clean exception handling.
- **Rate Limits (HTTP 429):** Restricted to 2 LLM calls per analysis using `gemini-2.5-flash` + friendly retry message on quota errors.
- **Overly Long Inputs:** Capped at 10 pages / 25,000 chars for resumes and 15,000 chars for JDs.
- **Hallucinated Metrics:** Prevented via Stage 1 fact isolation, negative constraints, and `[X]%` placeholder few-shot examples.
