"""Local Personally Identifiable Information (PII) redaction utilities.

Scrubs sensitive personal contact details and identifiers (emails, phone numbers,
personal profile URLs, and statutory ID patterns) locally in memory before text
is displayed in previews or transmitted to external APIs, while preserving dates,
version numbers, technical frameworks (e.g. Node.js, Next.js), and resume metrics.
"""

import re
from typing import Dict, Tuple

REDACTED_EMAIL = "[EMAIL REDACTED]"
REDACTED_PHONE = "[PHONE REDACTED]"
REDACTED_LINK = "[LINK REDACTED]"
REDACTED_ID = "[ID REDACTED]"

ALL_REDACTION_MARKERS = frozenset(
    {REDACTED_EMAIL, REDACTED_PHONE, REDACTED_LINK, REDACTED_ID}
)

# 1. Email addresses (including optional mailto: prefix)
_EMAIL_RE = re.compile(
    r"(?:mailto:)?\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)

# 2. Explicit http(s)/www URLs and common bare profile URLs (preserving Node.js, Next.js, etc.)
_URL_RE = re.compile(
    r"\b(?:"
    r"(?:https?://|www\.)[^\s<>()\"'|]+"
    r"|"
    r"(?:linkedin\.com/in|linkedin\.com/pub|github\.com|gitlab\.com|bitbucket\.org|"
    r"leetcode\.com|kaggle\.com|medium\.com|behance\.net|dribbble\.com|stackoverflow\.com/users)"
    r"/[A-Za-z0-9._~:/?#\[\]@!$&'*+,;=%-]+"
    r")",
    re.IGNORECASE,
)

# 3. Government / National ID patterns:
#    - US SSN: XXX-XX-XXXX (excluding invalid prefixes 000, 666, 9XX)
#    - Indian PAN: 5 uppercase letters + 4 digits + 1 uppercase letter
#    - 12-digit spaced national ID (e.g. 2345 6789 0123)
_SSN_RE = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_SPACED_RE = re.compile(r"(?<![0-9-])([2-9]\d{3}[ \t]\d{4}[ \t]\d{4})(?![0-9-])")

# 4. Phone numbers:
#    Carefully avoids 4-digit year ranges (2022 - 2024), ISO dates (2026-11-02), and versions (3.11.4).
_PHONE_PATTERNS = re.compile(
    r"(?:"
    # International format starting with + (e.g. +1 (555) 234-5678, +91 98765 43210, +44 20 7946 0958)
    r"(?<![A-Za-z0-9+])\+\d{1,3}[\s.-]?(?:\(\d{1,4}\)[\s.-]?)?(?:\d[\s.-]?){7,12}\d\b"
    r"|"
    # US/local area code in parentheses: (555) 234-5678
    r"(?<![A-Za-z0-9])\(\d{3}\)[\s.-]*\d{3}[\s.-]\d{4}\b"
    r"|"
    # Standard 3-3-4 separated phone number: 555-234-5678 or 555.234.5678
    r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"
    r"|"
    # 10-digit mobile format starting 6-9 (e.g. 9876543210 or 98765 43210 or 98765-43210)
    r"\b[6-9]\d{4}[-\s]?\d{5}\b"
    r")"
)


def redact_pii(text: str) -> Tuple[str, Dict[str, int]]:
    """Masks emails, profile URLs, sensitive IDs, and phone numbers in text.

    Args:
        text: Raw extracted or pasted document text.

    Returns:
        Tuple of (redacted_text, counts_by_category) where counts_by_category has keys:
        'emails', 'links', 'ids', 'phones', and 'total'.
    """
    counts = {"emails": 0, "links": 0, "ids": 0, "phones": 0, "total": 0}
    if not text:
        return "", counts

    # Step 1: Redact emails first so user@domain.com is not split by URL matchers
    def _sub_email(_match: re.Match) -> str:
        counts["emails"] += 1
        return REDACTED_EMAIL

    scrubbed = _EMAIL_RE.sub(_sub_email, text)

    # Step 2: Redact URLs while preserving trailing sentence punctuation (.,;:)
    def _sub_url(match: re.Match) -> str:
        raw = match.group(0)
        trimmed = raw.rstrip(".,;:!?)")
        trailing = raw[len(trimmed) :]
        counts["links"] += 1
        return f"{REDACTED_LINK}{trailing}"

    scrubbed = _URL_RE.sub(_sub_url, scrubbed)

    # Step 3: Redact SSN / PAN / 12-digit spaced IDs before phone matching
    def _sub_id(_match: re.Match) -> str:
        counts["ids"] += 1
        return REDACTED_ID

    scrubbed = _SSN_RE.sub(_sub_id, scrubbed)
    scrubbed = _PAN_RE.sub(_sub_id, scrubbed)
    scrubbed = _AADHAAR_SPACED_RE.sub(_sub_id, scrubbed)

    # Step 4: Redact phone numbers (verifying total digit count is 10..15)
    def _sub_phone(match: re.Match) -> str:
        candidate = match.group(0)
        digits_only = re.sub(r"\D", "", candidate)
        if 10 <= len(digits_only) <= 15:
            counts["phones"] += 1
            return REDACTED_PHONE
        return candidate

    scrubbed = _PHONE_PATTERNS.sub(_sub_phone, scrubbed)

    counts["total"] = (
        counts["emails"] + counts["links"] + counts["ids"] + counts["phones"]
    )
    return scrubbed, counts
