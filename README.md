# AI Resume Analyzer: JD-Based Resume Evaluation

An academic Prompt Engineering application that analyzes a candidate's resume against a job description (JD) using **LangChain**, **Google Gemini**, and **Pydantic** structured outputs within an intuitive **Streamlit** user interface.

> **Academic Context:** Developed as a college Prompt Engineering assignment demonstrating advanced prompting techniques without relying on external databases, embeddings, or agentic frameworks.

---

## Key Features

1. **Multi-Format Upload & Paste Support (`.pdf`, `.docx`, `.txt`):** Reads text-selectable PDFs (`pypdf`), Microsoft Word `.docx` files (zero external dependencies via Python `zipfile` + XML), plain text `.txt` files, or pasted text for both the candidate resume and the target job description—with automatic detection of scanned, password-protected, or legacy `.doc` files.
2. **Two-Stage Prompt Chaining:**
   - **Stage 1 (Extraction):** Extracts only stated resume facts and categorizes JD requirements into required skills, preferred skills, and core responsibilities.
   - **Stage 2 (Evaluation):** Compares the isolated facts against JD requirements using a strict 100-point rubric.
3. **Live Category Sub-Scores & Deterministic Reconciliation:** Breaks down earned points across Required Skills (`0–50`), Experience Alignment (`0–30`), Preferred & Education (`0–10`), and Clarity & Impact (`0–10`), deterministically reconciling the total and enforcing the `<50%` required-skills cap (`<= 50/100`).
4. **Skills Gap Analysis & Live Keyword Highlighter:** Color-coded skill pills (`Matched` vs. `Missing`) with a live filter bar and a document viewer highlighting matched JD keywords directly inside the candidate's resume text.
5. **Tailored Summary Draft & Interactive Bullet Revision Studio:** Generates a grounded 2–3 sentence professional summary draft and side-by-side bullet rewrites featuring **live inline inputs** for bracketed placeholders (`[X]%`, `[N]`, `[$Amount]`) so candidates can insert verified numbers without fabrication.
6. **Local Resume Structure & Writing Health Check:** Pure-Python instant diagnostics (`src/resume_health.py`) checking word/page length balance, bullet quantification rate, passive opening phrases (*"Responsible for"*, *"Worked on"*), first-person pronouns, and standard section presence.
7. **Targeted Interview Preparation:** Generates 3–5 role-specific interview preparation questions probing missing qualifications and project claims.
8. **Formatted PDF, Markdown & JSON Report Export:** One-click export as a print-ready editorial **PDF report** (`reportlab`), **Markdown report** (`.md`), or **JSON bundle** (`.json`).

---

## Prompt Engineering Techniques Demonstrated

| Technique | Implementation Location | Purpose & Academic Contribution |
| :--- | :--- | :--- |
| **Role Prompting** | `STAGE1_SYSTEM_PROMPT` & `STAGE2_SYSTEM_PROMPT` in `src/prompts.py` | Sets domain-specific personas: an objective **Technical Document Parser** for Stage 1, and a **Senior Technical Recruiter & Career Coach** for Stage 2. |
| **Prompt Chaining** | `analyze_resume()` in `src/analyzer.py` | Isolates objective factual extraction from subjective rubric evaluation in two sequential LLM calls, preventing the model from hallucinating resume facts to fit the JD. |
| **Few-Shot Prompting** | `STAGE2_SYSTEM_PROMPT` in `src/prompts.py` | Demonstrates how to classify skill gaps (e.g. MySQL vs. PostgreSQL) and how to rewrite weak bullets with placeholders (`[N] requests`, `[X]% latency`) without inventing numbers. |
| **Structured Output** | `with_structured_output()` in `src/analyzer.py` + `src/schemas.py` | Enforces Pydantic validation on all responses (`ExtractionResult` and `ResumeAnalysisResult`), preventing malformed UI rendering. |
| **Anti-Fabrication Constraints** | System prompts in `src/prompts.py` | Explicit negative constraints strictly forbid inventing skills, companies, degrees, dates, or numerical achievements. |

---

## Scoring Rubric (100 Points Total)

The match score is calculated using the following heuristic criteria:

1. **Required Skills & Core Qualifications (50 Points):** Points awarded strictly based on the proportion of required JD skills explicitly found in the candidate's resume. Unsupported skills receive **0 points**.
2. **Relevant Experience & Project Alignment (30 Points):** Evaluates how well documented work experience and projects demonstrate hands-on application of core role responsibilities.
3. **Preferred Skills & Education Fit (10 Points):** Bonus alignment for nice-to-have tools, certifications, or relevant academic degrees. Kept low so optional keywords never outweigh missing core requirements.
4. **Resume Clarity & Impact Presentation (10 Points):** Evaluates section organization and action-oriented bullet phrasing.
5. **Hard Cap Guardrail:** If the candidate matches **fewer than 50% of the required skills**, the total score **cannot exceed 50/100**, regardless of formatting or bonus keywords.

---

## Architecture

```mermaid
flowchart TD
    User["User"] -->|Uploads .pdf / .docx / .txt or pastes text| UI["Streamlit UI (app.py)"]
    UI -->|Document bytes| Parser["Document Parser (src/pdf_parser.py)"]
    Parser -->|Cleaned text + PII Masking| UI
    UI -->|resume_text + jd_text| Analyzer["Analyzer Service (src/analyzer.py)"]
    UI -->|Local check| Health["Resume Health Check (src/resume_health.py)"]
    
    subgraph PromptChain["Two-Stage Prompt Chain"]
        Analyzer -->|Stage 1 Prompt| LLM1["Gemini LLM (Fact Extraction)"]
        LLM1 -->|ExtractionResult Schema| Intermediate["Structured Facts JSON"]
        Intermediate -->|Stage 2 Prompt + Rubric + Few-Shot| LLM2["Gemini LLM (Rubric Evaluation)"]
        LLM2 -->|ResumeAnalysisResult + Reconciliation| FinalResult["Validated Analysis Object"]
    end
    
    FinalResult --> UI
    Health --> UI
    UI -->|Renders sub-scores, revisions, health & PDF/MD/JSON exports| User
```

---

## Project Structure

```text
resumeanalyzer/
├── app.py                        # Single Streamlit entry point (run: streamlit run app.py)
├── .streamlit/
│   └── config.toml               # Clean high-contrast light editorial theme configuration
├── src/
│   ├── __init__.py               # Package marker
│   ├── schemas.py                # Pydantic models for Stage 1 extraction & Stage 2 evaluation
│   ├── prompts.py                # Role prompts, few-shot examples, scoring rubric & templates
│   ├── analyzer.py               # Env/API key handling, 2-stage pipeline & score reconciliation
│   ├── pdf_parser.py             # .pdf, .docx, and .txt text extraction and validation
│   ├── pii.py                    # Local PII scrubbing (emails, phones, profile URLs, IDs)
│   ├── resume_health.py          # Local deterministic length, quantification & active-verb checks
│   └── ui_helpers.py             # SVG gauge, keyword highlighter, placeholder studio & PDF/MD/JSON exporters
├── tests/
│   ├── test_analyzer.py          # Unit tests for score reconciliation & mocked 2-stage LLM chain
│   ├── test_pdf_parser.py        # Unit tests for .pdf, .docx, and .txt extraction & validation
│   ├── test_pii.py               # Unit tests for local PII redaction & edge cases
│   ├── test_resume_health.py     # Unit tests for deterministic resume writing & formatting checks
│   ├── test_schemas.py           # Unit tests for Pydantic models & validation constraints
│   └── test_ui_helpers.py        # Unit tests for UI helpers, highlighting & PDF/MD/JSON report generation
├── .env.example                  # Template showing GOOGLE_API_KEY and GEMINI_MODEL
├── requirements.txt              # Required Python dependencies (8 packages including reportlab)
├── IMPLEMENTATION_PLAN.md        # Reference phase-by-phase development plan
├── PROJECT_STATUS.md             # Living progress log and architectural decision record
└── README.md                     # Project documentation, prompt design & instructions
```

---

## Team Responsibilities

| Team Member | Role | Owned Deliverables |
| :--- | :--- | :--- |
| **Person 1** | **Backend, Prompt Engineering & LLM Integration** | • `src/schemas.py` (Pydantic models)<br>• `src/prompts.py` (Prompts, few-shot, rubric, anti-fabrication rules)<br>• `src/analyzer.py` (LangChain + Gemini 2-stage chain)<br>• `tests/test_analyzer.py` (Mocked pipeline & schema tests) |
| **Person 2** | **Streamlit UI, PDF Utility, Integration & Docs** | • `src/pdf_parser.py` (PDF extraction & scanned file checks)<br>• `app.py` (Streamlit UI, input handling, results presentation)<br>• `tests/test_pdf_parser.py` (PDF edge-case tests)<br>• `README.md` & `.env.example` |
| **Both** | **Review, Rubric Tuning & QA** | Co-review prompt wording, run end-to-end testing with sample resumes, maintain `PROJECT_STATUS.md`. |

---

## Quickstart & Setup Guide

### 1. Prerequisites
- **Python 3.10 or newer** (tested on Python 3.13)
- A **Google Gemini API Key** (obtain free from [Google AI Studio](https://aistudio.google.com/))

### 2. Installation
Clone or navigate to the project directory:
```bash
cd resumeanalyzer
```

Install the dependencies:
```bash
python -m pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file from the provided template:
```bash
# Windows PowerShell:
Copy-Item .env.example .env

# macOS / Linux:
cp .env.example .env
```

Open `.env` and insert your Gemini API key:
```env
GOOGLE_API_KEY=AIzaSy...your_actual_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODEL=gemini-3.8-flash
```
*(The system defaults to `gemini-3.5-flash-lite` and automatically falls back to `gemini-3.8-flash` if the primary model encounters a quota or API error).*

### 4. Run the Application
Launch the Streamlit app with a single command:
```bash
streamlit run app.py
```
Open your web browser at `http://localhost:8501`.

### 5. Run the Automated Tests
Run the offline test suite using `pytest`:
```bash
pytest tests/
```
All unit tests run offline using mocks and in-memory PDFs; **no live Gemini API key or network connection is required to run the tests**.

---

## Important Disclaimers & Ethics

- **Heuristic Estimate, Not ATS:** The match score is an AI-generated heuristic intended to assist candidates with resume tailoring. It does **not** replicate proprietary ATS algorithms (e.g. Workday, Taleo, Greenhouse).
- **No Prediction of Hiring:** This tool does **not** guarantee or predict interview callbacks or recruiter hiring decisions.
- **Data Privacy & Local PII Masking:** Resumes and job descriptions are processed strictly in-memory, and personal contact details (emails, phone numbers, profile links, and government ID patterns) are automatically masked locally via `src/pii.py` before any text is sent to the Gemini API. No resume data is stored or logged to disk.
