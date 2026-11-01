"""Unit tests for local PII redaction utilities."""

from src.pii import (
    REDACTED_EMAIL,
    REDACTED_ID,
    REDACTED_LINK,
    REDACTED_PHONE,
    redact_pii,
)


def test_redact_pii_emails_phones_links_and_ids():
    """Verify personal emails, phone formats, profile links, and IDs are masked accurately."""
    raw_resume = (
        "JANE DOE\n"
        "Email: jane.doe+work@example.co.in | Phone: +91 98765 43210 | Alt: (555) 234-5678\n"
        "Profiles: linkedin.com/in/jane-doe, https://portfolio.janedoe.dev, github.com/janedoe.\n"
        "SSN: 123-45-6789 | PAN: ABCDE1234F | ID: 2345 6789 0123\n"
        "Software Engineer (2022 - 2025) working with Node.js, Next.js, Vue.js, and Python 3.12.4.\n"
        "Reduced latency by 35% across 10,000 daily requests."
    )

    scrubbed, stats = redact_pii(raw_resume)

    # Sensitive fields must be gone
    assert "jane.doe+work@example.co.in" not in scrubbed
    assert "98765 43210" not in scrubbed
    assert "(555) 234-5678" not in scrubbed
    assert "linkedin.com/in/jane-doe" not in scrubbed
    assert "portfolio.janedoe.dev" not in scrubbed
    assert "github.com/janedoe" not in scrubbed
    assert "123-45-6789" not in scrubbed
    assert "ABCDE1234F" not in scrubbed
    assert "2345 6789 0123" not in scrubbed

    # Markers must appear with accurate category counts
    assert REDACTED_EMAIL in scrubbed
    assert REDACTED_PHONE in scrubbed
    assert REDACTED_LINK in scrubbed
    assert REDACTED_ID in scrubbed
    assert stats["emails"] == 1
    assert stats["phones"] == 2
    assert stats["links"] == 3
    assert stats["ids"] == 3
    assert stats["total"] == 9

    # Technical frameworks, employment year ranges, versions, and metrics MUST remain intact
    assert "2022 - 2025" in scrubbed
    assert "Node.js" in scrubbed
    assert "Next.js" in scrubbed
    assert "Vue.js" in scrubbed
    assert "Python 3.12.4" in scrubbed
    assert "35%" in scrubbed
    assert "10,000" in scrubbed


def test_redact_pii_empty_and_clean_text():
    """Verify clean text without PII passes through unchanged with zero counts."""
    clean = "Backend Engineer skilled in Python, PostgreSQL, Docker (2021 - 2024)."
    scrubbed, stats = redact_pii(clean)
    assert scrubbed == clean
    assert stats["total"] == 0

    empty_out, empty_stats = redact_pii("")
    assert empty_out == ""
    assert empty_stats["total"] == 0
