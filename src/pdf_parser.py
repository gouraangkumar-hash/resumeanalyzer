"""PDF text extraction utility for AI Resume Analyzer.

Uses pypdf to extract readable text, validate minimum length (detecting
scanned/image-only PDFs), and enforce reasonable page limits.
"""

import io
import re
from typing import BinaryIO, Union
from pypdf import PdfReader
from pypdf.errors import PdfReadError

DEFAULT_MAX_PAGES = 10
DEFAULT_MIN_CHARS = 50


def extract_text_from_pdf(
    pdf_source: Union[BinaryIO, bytes, str],
    max_pages: int = DEFAULT_MAX_PAGES,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> str:
    """Extracts and normalizes text from a PDF file.

    Args:
        pdf_source: File-like object (e.g. Streamlit UploadedFile), bytes, or file path.
        max_pages: Maximum number of pages to parse (default 10).
        min_chars: Minimum character count required to consider the PDF text-readable.

    Returns:
        Cleaned text content extracted from the PDF.

    Raises:
        ValueError: If the PDF is corrupted, empty, or scanned (insufficient text).
    """
    if pdf_source is None:
        raise ValueError("No PDF file provided.")

    # Wrap raw bytes in BytesIO if needed
    if isinstance(pdf_source, bytes):
        stream = io.BytesIO(pdf_source)
    else:
        stream = pdf_source

    try:
        reader = PdfReader(stream)
    except (PdfReadError, Exception) as exc:
        raise ValueError(
            f"Could not read the PDF file. The file may be corrupted, password-protected, or invalid. Details: {exc}"
        ) from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError("The uploaded PDF contains zero pages.")

    pages_to_read = min(total_pages, max_pages)
    extracted_fragments = []

    for page_idx in range(pages_to_read):
        try:
            page = reader.pages[page_idx]
            page_text = page.extract_text()
            if page_text:
                extracted_fragments.append(page_text)
        except Exception as exc:
            # Continue reading other pages if a single page has a minor extraction error
            continue

    combined_text = "\n".join(extracted_fragments).strip()

    # Normalize excessive whitespace and multiple newlines
    combined_text = re.sub(r"[ \t]+", " ", combined_text)
    combined_text = re.sub(r"\n{3,}", "\n\n", combined_text)

    if len(combined_text) < min_chars:
        raise ValueError(
            f"The uploaded PDF yielded insufficient readable text ({len(combined_text)} characters, minimum {min_chars}). "
            "The PDF may be an image scan or empty. Please provide a text-selectable PDF."
        )

    return combined_text
