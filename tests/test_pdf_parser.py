"""Unit tests for PDF extraction and edge cases (Person 2 deliverable)."""

import io
import pytest
import zipfile
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from src.pdf_parser import (
    extract_text_from_document,
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_text_from_txt,
    get_pdf_page_count,
    resolve_document_text,
)


def create_sample_pdf(text: str) -> io.BytesIO:
    """Helper to generate an in-memory PDF with specified text."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    # Write lines of text
    y = 750
    for line in text.split("\n"):
        c.drawString(72, y, line)
        y -= 20
    c.save()
    buffer.seek(0)
    return buffer


def test_extract_text_valid_pdf():
    """Verify that text is correctly extracted from a valid text PDF."""
    sample_content = (
        "Jane Doe - Software Engineer\n"
        "Proficient in Python, LangChain, and Streamlit.\n"
        "Experience building scalable AI applications with Google Gemini API.\n"
        "Graduated with a Bachelor of Science in Computer Science."
    )
    pdf_buffer = create_sample_pdf(sample_content)
    extracted = extract_text_from_pdf(pdf_buffer)

    assert "Jane Doe" in extracted
    assert "Python" in extracted
    assert "Gemini" in extracted
    assert len(extracted) >= 50


def test_extract_text_bytes_input():
    """Verify extract_text_from_pdf supports raw bytes."""
    sample_content = (
        "Alice Smith - Data Scientist\n"
        "Experienced in machine learning, statistical modeling, and Python.\n"
        "Extensive work with Pandas, PyTorch, and cloud computing deployments."
    )
    pdf_bytes = create_sample_pdf(sample_content).getvalue()
    extracted = extract_text_from_pdf(pdf_bytes)

    assert "Alice Smith" in extracted
    assert "machine learning" in extracted


def test_extract_text_empty_input():
    """Verify None raises ValueError."""
    with pytest.raises(ValueError, match="No PDF file provided"):
        extract_text_from_pdf(None)


def test_extract_text_corrupted_file():
    """Verify corrupted non-PDF bytes raise a descriptive ValueError."""
    corrupted_data = b"This is definitely not a PDF file content."
    with pytest.raises(ValueError, match="Could not read the PDF file"):
        extract_text_from_pdf(corrupted_data)


def test_extract_text_blank_pdf_scanned_detection():
    """Verify a PDF with insufficient text raises a scanned/empty ValueError."""
    # Create a blank PDF using pypdf PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    with pytest.raises(ValueError, match="insufficient readable text"):
        extract_text_from_pdf(buffer, min_chars=50)


def test_extract_text_short_text_threshold():
    """Verify text shorter than min_chars triggers the scanned/short warning."""
    short_content = "Hi"
    pdf_buffer = create_sample_pdf(short_content)

    with pytest.raises(ValueError, match="insufficient readable text"):
        extract_text_from_pdf(pdf_buffer, min_chars=50)


def test_extract_text_jd_pdf_and_resolve_document_text():
    """Verify Job Description PDF extraction and resolve_document_text helper."""
    jd_content = (
        "Role: Senior Backend Engineer\n"
        "Required Qualifications: Python, FastAPI, PostgreSQL, Docker, and Pytest.\n"
        "Core Responsibilities: Build and scale distributed backend services."
    )
    jd_pdf_buffer = create_sample_pdf(jd_content)

    extracted_jd = extract_text_from_pdf(jd_pdf_buffer, document_name="Job Description PDF")
    assert "Senior Backend Engineer" in extracted_jd
    assert "PostgreSQL" in extracted_jd

    # Re-read same seekable stream via resolve_document_text
    resolved_from_pdf = resolve_document_text(pdf_source=jd_pdf_buffer, document_name="Job Description")
    assert "FastAPI" in resolved_from_pdf

    # Resolve plain text fallback
    resolved_from_text = resolve_document_text(text="  Plain   JD  text  here  ", document_name="Job Description")
    assert resolved_from_text == "Plain JD text here"

    # Empty both raises clear error
    with pytest.raises(ValueError, match="Job Description text is empty"):
        resolve_document_text(text="   ", pdf_source=None, document_name="Job Description")


def test_extract_text_password_protected_pdf():
    """Verify password-protected PDFs raise a clear password-protected error instead of scanned warning."""
    sample_pdf = create_sample_pdf(
        "Confidential Resume Content with over fifty characters for testing encryption handling."
    )
    from pypdf import PdfReader

    reader = PdfReader(sample_pdf)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("secret123")

    encrypted_buf = io.BytesIO()
    writer.write(encrypted_buf)
    encrypted_buf.seek(0)

    with pytest.raises(ValueError, match="password-protected"):
        extract_text_from_pdf(encrypted_buf, document_name="Resume PDF")
    assert get_pdf_page_count(encrypted_buf) is None


def _create_sample_docx(paragraphs: list[tuple[str, bool]], header_text: str = "") -> bytes:
    """Builds a minimal valid .docx archive in memory (with optional Word list numbering)."""
    w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body_parts = []
    for text, is_bullet in paragraphs:
        ppr = "<w:pPr><w:numPr><w:ilvl w:val='0'/><w:numId w:val='1'/></w:numPr></w:pPr>" if is_bullet else ""
        body_parts.append(f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>")

    doc_xml = (
        f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f"<w:document xmlns:w='{w_ns}'><w:body>{''.join(body_parts)}</w:body></w:document>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
        if header_text:
            hdr_xml = (
                f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
                f"<w:hdr xmlns:w='{w_ns}'><w:p><w:r><w:t>{header_text}</w:t></w:r></w:p></w:hdr>"
            )
            zf.writestr("word/header1.xml", hdr_xml.encode("utf-8"))
    return buf.getvalue()


def test_extract_text_from_docx_preserves_headers_and_bullets():
    """Verify .docx extraction parses headers, paragraphs, and Word list bullets without external deps."""
    docx_bytes = _create_sample_docx(
        [
            ("Experience", False),
            ("Engineered 12+ FastAPI microservices serving 50,000 daily requests.", True),
            ("Reduced PostgreSQL query latency by 35% through indexing.", True),
        ],
        header_text="Jordan Lee - Senior Backend Engineer",
    )
    extracted = extract_text_from_docx(docx_bytes, document_name="Resume DOCX")
    assert "Jordan Lee - Senior Backend Engineer" in extracted
    assert "- Engineered 12+ FastAPI microservices" in extracted
    assert "- Reduced PostgreSQL query latency by 35%" in extracted


def test_extract_text_from_docx_rejects_ole_and_corrupt_files():
    """Verify legacy .doc / encrypted OLE headers and invalid zips raise descriptive ValueErrors."""
    ole_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"legacy doc payload" * 10
    with pytest.raises(ValueError, match="legacy .doc|password-protected"):
        extract_text_from_docx(ole_bytes, document_name="Resume DOCX")

    with pytest.raises(ValueError, match="Could not read the Word document"):
        extract_text_from_docx(b"not a zip archive at all", document_name="Resume DOCX")


def test_extract_text_from_txt_utf8_utf16_and_binary_rejection():
    """Verify .txt extraction handles UTF-8, UTF-16 BOM, and rejects binary null-byte files."""
    txt_content = (
        "Role: Cloud Platform Engineer\n"
        "Requirements: Python, Terraform, Docker, Kubernetes, and AWS production operations."
    )
    assert "Terraform" in extract_text_from_txt(txt_content.encode("utf-8"), document_name="JD TXT")
    assert "Kubernetes" in extract_text_from_txt(txt_content.encode("utf-16"), document_name="JD TXT")

    with pytest.raises(ValueError, match="Binary content"):
        extract_text_from_txt(b"PNG\x00\x00binary_garbage_payload_with_nulls" * 4, document_name="JD TXT")


def test_extract_text_from_document_dispatcher_and_page_count():
    """Verify unified dispatcher handles .pdf, .docx, .txt, and rejects unsupported formats."""
    pdf_buf = create_sample_pdf(
        "Candidate Resume with Python, SQL, Docker, and FastAPI backend engineering experience."
    )
    assert get_pdf_page_count(pdf_buf) == 1
    assert "FastAPI" in extract_text_from_document(pdf_buf, filename="resume.pdf", document_name="Resume")

    docx_bytes = _create_sample_docx(
        [("Job Description requiring Python, PostgreSQL, Docker, and cloud deployment skills.", False)]
    )
    assert "PostgreSQL" in extract_text_from_document(docx_bytes, filename="jd.docx", document_name="JD")

    txt_bytes = b"Job Description requiring Python, FastAPI, PostgreSQL, and automated testing."
    assert "automated testing" in extract_text_from_document(txt_bytes, filename="jd.txt", document_name="JD")

    with pytest.raises(ValueError, match="Legacy .doc"):
        extract_text_from_document(b"dummy", filename="old_resume.doc", document_name="Resume")

    with pytest.raises(ValueError, match="Unsupported file format"):
        extract_text_from_document(b"dummy", filename="image.png", document_name="Resume")
