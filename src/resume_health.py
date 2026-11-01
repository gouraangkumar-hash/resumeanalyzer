"""Local, deterministic resume structure and writing quality checks.

Evaluates objective resume formatting signals in pure Python without extra model calls:
1. Word count and page-length balance
2. Bullet point count and measurable quantification rate
3. Passive or weak opening phrase detection and first-person pronoun scan
4. Standard resume section presence check
"""

import re
from typing import Dict, List, Optional

from src.schemas import ExtractionResult

_REDACTED_RE = re.compile(r"\[[A-Z ]*REDACTED\]")

_EXPLICIT_BULLET_RE = re.compile(
    r"^\s*(?:[-*\u2022\u2023\u2043\u25aa\u25ab\u25b8\u25ba\u25cf\u25cb\u25e6\uf0b7\uf0a7\uf0d8]|\d+[.)])\s+(.+)$"
)

# Tech versions & embedded-digit identifiers that should NOT count as business/engineering impact metrics
_TECH_VERSION_RE = re.compile(
    r"\b(?:python|java|node(?:\.js)?|react|angular|vue|django|flask|fastapi|spring|dotnet|\.net|c#|tls|ssl|oauth|http/?|ipv|v)\s*\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)
_ALPHANUM_TECH_TOKEN_RE = re.compile(r"\b[A-Za-z]+\d+[A-Za-z0-9.]*\b")
_CALENDAR_YEAR_RE = re.compile(r"\b(?:199\d|20[0-3]\d)\b")

_METRIC_NUMBER_RE = re.compile(
    r"(?:[$€£₹]\s*\d[\d,.]*|\b\d+(?:\.\d+)?\s*%|\b\d[\d,.]*\+?(?:\s*(?:x|ms|s|sec|seconds|mins?|minutes|hrs?|hours|days|weeks|months|tb|gb|mb|kb|rps|qps))?\b)",
    re.IGNORECASE,
)
_WRITTEN_IMPACT_RE = re.compile(
    r"\b(?:doubled|tripled|quadrupled|halved|zero\s+(?:downtime|defects|regressions|data\s+loss))\b",
    re.IGNORECASE,
)

_WEAK_OPENING_RE = re.compile(
    r"^(?:was\s+responsible\s+for|responsible\s+for|duties\s+included?|worked\s+(?:on|with)|helped(?:\s+with|\s+to)?|assisted(?:\s+with|\s+in)?|tasked\s+with|participated\s+in|was\s+involved\s+in|involved\s+in)\b",
    re.IGNORECASE,
)

_FIRST_PERSON_RE = re.compile(
    r"(?:\bI\s+(?:am|was|have|had|built|worked|led|developed|designed|managed|created|helped|implemented|engineered|delivered)\b|\b(?:my|myself)\b)",
    re.IGNORECASE,
)

_ACTION_LINE_FALLBACK_RE = re.compile(
    r"^(?:Engineered|Developed|Built|Designed|Implemented|Led|Managed|Created|Automated|Optimized|Reduced|Improved|Deployed|Architected|Maintained|Delivered|Migrated|Integrated|Refactored|Analyzed|Launched|Configured|Spearheaded|Established|Streamlined|Collaborated|Worked|Responsible|Helped|Assisted|Participated|Tasked)\b"
)

_SECTION_PATTERNS = {
    "Summary": re.compile(
        r"^\s*(?:professional\s+summary|executive\s+summary|summary|career\s+objective|objective|profile|about\s+me)\s*:?\s*$",
        re.IGNORECASE,
    ),
    "Skills": re.compile(
        r"^\s*(?:technical\s+skills|core\s+skills|skills(?:\s*&\s*tools)?|technologies|core\s+competencies|tech\s+stack)\s*:?\s*$",
        re.IGNORECASE,
    ),
    "Experience": re.compile(
        r"^\s*(?:work\s+experience|professional\s+experience|relevant\s+experience|experience|employment\s+history|work\s+history|career\s+history)\s*:?\s*$",
        re.IGNORECASE,
    ),
    "Projects": re.compile(
        r"^\s*(?:key\s+projects|technical\s+projects|personal\s+projects|academic\s+projects|selected\s+projects|projects)\s*:?\s*$",
        re.IGNORECASE,
    ),
    "Education": re.compile(
        r"^\s*(?:education(?:\s*&\s*certifications)?|academic\s+background|qualifications|degrees)\s*:?\s*$",
        re.IGNORECASE,
    ),
}


def is_quantified_bullet(bullet_text: str) -> bool:
    """Returns True if a resume bullet contains genuine quantitative metrics rather than just years or versions."""
    if not bullet_text:
        return False

    scrubbed = _REDACTED_RE.sub(" ", bullet_text)
    scrubbed = _TECH_VERSION_RE.sub(" ", scrubbed)
    scrubbed = _ALPHANUM_TECH_TOKEN_RE.sub(" ", scrubbed)
    scrubbed = _CALENDAR_YEAR_RE.sub(" ", scrubbed)

    if _METRIC_NUMBER_RE.search(scrubbed):
        return True
    if _WRITTEN_IMPACT_RE.search(scrubbed):
        return True
    return False


def _extract_resume_bullets(lines: List[str]) -> List[str]:
    """Extracts bullet lines from resume text, with a fallback for plain-text action lines."""
    explicit_bullets: List[str] = []
    for line in lines:
        match = _EXPLICIT_BULLET_RE.match(line)
        if match:
            content = match.group(1).strip()
            if len(content.split()) >= 4:
                explicit_bullets.append(content)

    if len(explicit_bullets) >= 2:
        return explicit_bullets

    fallback_bullets: List[str] = list(explicit_bullets)
    seen = set(explicit_bullets)
    for line in lines:
        stripped = line.strip()
        words = stripped.split()
        if 6 <= len(words) <= 45 and _ACTION_LINE_FALLBACK_RE.match(stripped):
            if stripped not in seen:
                seen.add(stripped)
                fallback_bullets.append(stripped)
    return fallback_bullets


def analyze_resume_health(
    resume_text: str,
    page_count: Optional[int] = None,
    extraction: Optional[ExtractionResult] = None,
) -> Dict[str, object]:
    """Runs fast, deterministic formatting and writing quality checks on the resume text."""
    raw = (resume_text or "").strip()
    word_ready_text = _REDACTED_RE.sub("contact", raw)
    word_count = len(word_ready_text.split()) if word_ready_text else 0

    exact_pages = page_count is not None and page_count > 0
    if exact_pages:
        resolved_pages = int(page_count)  # type: ignore[arg-type]
    elif word_count == 0:
        resolved_pages = 0
    else:
        resolved_pages = max(1, round(word_count / 450))

    # 1. Length & Page Balance
    if word_count < 200:
        length_status = "Too Brief"
        length_tone = "attention"
        length_note = (
            "Under 200 words. Expand role and project descriptions with concrete responsibilities and outcomes."
        )
    elif word_count < 350:
        length_status = "Slightly Brief"
        length_tone = "fair"
        length_note = (
            "Between 200 and 350 words. Consider adding fuller accomplishment details for core roles."
        )
    elif (exact_pages and resolved_pages > 2) or word_count > 950:
        length_status = "Lengthy"
        length_tone = "attention"
        length_note = (
            "Exceeds typical 1 to 2 page resume length. Trim older or less relevant bullets so key achievements stand out."
        )
    else:
        length_status = "Balanced"
        length_tone = "good"
        length_note = "Fits standard 1 to 2 page resume length expectations."

    # 2. Bullet Quantification Rate
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    bullets = _extract_resume_bullets(lines)
    total_bullets = len(bullets)
    quantified_bullets = sum(1 for b in bullets if is_quantified_bullet(b))
    quantification_pct = (
        round((quantified_bullets / total_bullets) * 100) if total_bullets > 0 else 0
    )

    if total_bullets == 0:
        quant_status = "No Bullets Found"
        quant_tone = "attention"
        quant_note = (
            "No distinct bullet points were detected. Use concise bullet points starting with strong action verbs."
        )
    elif quantification_pct >= 50:
        quant_status = "Strong"
        quant_tone = "good"
        quant_note = (
            f"{quantified_bullets} of {total_bullets} bullets include measurable numbers, percentages, or scale."
        )
    elif quantification_pct >= 25:
        quant_status = "Moderate"
        quant_tone = "fair"
        quant_note = (
            f"{quantified_bullets} of {total_bullets} bullets include metrics. Aim to quantify at least half of your bullets."
        )
    else:
        quant_status = "Low"
        quant_tone = "attention"
        quant_note = (
            f"Only {quantified_bullets} of {total_bullets} bullets include numbers. Add scope, latency, volume, or time-saved figures."
        )

    # 3. Weak / Passive Opening Phrasing & First-Person Pronouns
    weak_verb_bullets: List[str] = [b for b in bullets if _WEAK_OPENING_RE.match(b)]
    weak_verb_count = len(weak_verb_bullets)
    has_first_person = bool(_FIRST_PERSON_RE.search(raw))

    if weak_verb_count == 0 and not has_first_person:
        phrasing_status = "Direct & Active"
        phrasing_tone = "good"
        phrasing_note = "No passive opening phrases or first-person pronouns detected."
    else:
        issues: List[str] = []
        if weak_verb_count > 0:
            issues.append(
                f"{weak_verb_count} bullet{'s' if weak_verb_count != 1 else ''} start with passive phrasing (such as 'Responsible for' or 'Worked on')"
            )
        if has_first_person:
            issues.append("first-person pronouns ('I', 'my') appear in the text")
        phrasing_status = "Needs Tightening"
        phrasing_tone = "attention"
        phrasing_note = "Detected " + " and ".join(issues) + ". Replace with direct action verbs."

    # 4. Standard Section Presence
    detected_sections: Dict[str, bool] = {name: False for name in _SECTION_PATTERNS}
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 45:
            continue
        for sec_name, pattern in _SECTION_PATTERNS.items():
            if pattern.match(stripped):
                detected_sections[sec_name] = True

    if extraction is not None:
        if extraction.summary_section.strip().lower() != "not present":
            detected_sections["Summary"] = True
        if (
            extraction.skills_section.strip().lower() != "not present"
            or len(extraction.resume_skills) > 0
        ):
            detected_sections["Skills"] = True
        if extraction.experience_section.strip().lower() != "not present":
            detected_sections["Experience"] = True
        if extraction.projects_section.strip().lower() != "not present":
            detected_sections["Projects"] = True
        if extraction.education_section.strip().lower() != "not present":
            detected_sections["Education"] = True

    sections_present = [k for k, v in detected_sections.items() if v]
    sections_missing = [k for k, v in detected_sections.items() if not v]

    return {
        "word_count": word_count,
        "page_count": resolved_pages,
        "is_exact_pages": exact_pages,
        "length_status": length_status,
        "length_tone": length_tone,
        "length_note": length_note,
        "total_bullets": total_bullets,
        "quantified_bullets": quantified_bullets,
        "quantification_pct": quantification_pct,
        "quant_status": quant_status,
        "quant_tone": quant_tone,
        "quant_note": quant_note,
        "weak_verb_count": weak_verb_count,
        "weak_verb_examples": weak_verb_bullets[:5],
        "has_first_person": has_first_person,
        "phrasing_status": phrasing_status,
        "phrasing_tone": phrasing_tone,
        "phrasing_note": phrasing_note,
        "sections_present": sections_present,
        "sections_missing": sections_missing,
    }
