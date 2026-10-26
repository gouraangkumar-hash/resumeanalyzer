"""Unit tests for PDF extraction and edge cases (Person 2 deliverable)."""

import io
import pytest
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from src.pdf_parser import extract_text_from_pdf


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
