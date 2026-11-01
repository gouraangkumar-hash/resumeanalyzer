"""Unit tests for local deterministic resume structure and writing health checks."""

from src.resume_health import analyze_resume_health, is_quantified_bullet
from src.schemas import ExtractionResult


def test_is_quantified_bullet_distinguishes_real_metrics_from_versions_and_years():
    """Verify genuine scale/impact metrics count while years and tech versions do not."""
    assert is_quantified_bullet("Built backend services using Python 3.11 and AWS S3 in 2023.") is False
    assert is_quantified_bullet("Integrated OAuth2 authentication on EC2 instances in 2024.") is False

    assert is_quantified_bullet("Engineered 12+ REST APIs handling 50,000 daily requests.") is True
    assert is_quantified_bullet("Reduced p95 query latency by 42% through composite indexing.") is True
    assert is_quantified_bullet("Saved $28,000 annually by automating cloud cleanup jobs.") is True
    assert is_quantified_bullet("Cut build pipeline runtime from 18 minutes to 5 minutes.") is True
    assert is_quantified_bullet("Doubled test coverage with zero downtime across releases.") is True


def test_analyze_resume_health_detects_passive_verbs_pronouns_and_sections():
    """Verify health report flags passive openings, first-person pronouns, and brief length."""
    sample_resume = (
        "Summary\n"
        "I am a Software Engineer I working on web applications with my team.\n\n"
        "Experience\n"
        "- Responsible for maintaining internal billing endpoints in Python 3.11.\n"
        "- Worked on frontend dashboards using React in 2023.\n"
        "- Reduced API error rates by 35% across 8 microservices.\n\n"
        "Education\n"
        "B.S. in Computer Science\n"
    )
    report = analyze_resume_health(sample_resume, page_count=1)

    assert report["is_exact_pages"] is True
    assert report["page_count"] == 1
    assert report["length_status"] == "Too Brief"
    assert report["total_bullets"] == 3
    assert report["quantified_bullets"] == 1
    assert report["quantification_pct"] == 33
    assert report["weak_verb_count"] == 2
    assert report["has_first_person"] is True
    assert report["phrasing_status"] == "Needs Tightening"
    assert "Summary" in report["sections_present"]
    assert "Experience" in report["sections_present"]
    assert "Education" in report["sections_present"]
    assert "Projects" in report["sections_missing"]


def test_analyze_resume_health_does_not_flag_roman_numeral_title_as_pronoun():
    """Verify 'Software Engineer I' is not misclassified as first-person pronoun 'I'."""
    clean_resume = " ".join(["Backend"] * 380) + (
        "\nSummary\nSoftware Engineer I focused on distributed systems.\n"
        "Skills\nPython, PostgreSQL, Docker\n"
        "Experience\n"
        "- Engineered 15+ endpoints reducing latency by 40%.\n"
        "- Automated CI workflows saving 6 hours per week.\n"
        "Projects\n"
        "- Built log analytics pipeline processing 2GB per hour.\n"
        "Education\nB.S. Computer Science"
    )
    ext = ExtractionResult(resume_skills=["Python", "PostgreSQL"])
    report = analyze_resume_health(clean_resume, page_count=None, extraction=ext)

    assert report["has_first_person"] is False
    assert report["weak_verb_count"] == 0
    assert report["phrasing_status"] == "Direct & Active"
    assert report["length_status"] == "Balanced"
    assert report["quantification_pct"] == 100
    assert report["sections_missing"] == []
