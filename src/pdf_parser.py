"""Document text extraction and input resolution utilities (.pdf, .docx, .txt).

Uses pypdf for PDFs and Python's standard library (zipfile + xml.etree.ElementTree)
for Word (.docx) and plain text (.txt) files, validating minimum readable character
length and enforcing page limits.
"""

import io
from pathlib import Path
import re
from typing import BinaryIO, List, Optional, Union
import xml.etree.ElementTree as ET
import zipfile
from pypdf import PdfReader
from pypdf.errors import PdfReadError

DEFAULT_MAX_PAGES = 10
DEFAULT_MIN_CHARS = 50
SUPPORTED_UPLOAD_EXTENSIONS = ("pdf", "docx", "txt")

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_BULLET_START_RE = re.compile(r"^(?:[-*•◦▪▸►‣]|\d+[.)])\s+")


def _normalize_extracted_text(text: str) -> str:
    """Normalizes line endings, horizontal whitespace, and consecutive blank lines."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _read_source_bytes(
    source: Union[BinaryIO, bytes, str, Path], label: str
) -> bytes:
    """Reads raw bytes from bytes, a file-like stream, or a filesystem path."""
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        path = Path(source)
        try:
            return path.read_bytes()
        except Exception as exc:
            raise ValueError(f"Could not read file ({label}): {exc}") from exc
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except Exception:
            pass
    raw = source.read()
    if hasattr(source, "seek"):
        try:
            source.seek(0)
        except Exception:
            pass
    if isinstance(raw, str):
        return raw.encode("utf-8")
    return raw


def get_pdf_page_count(pdf_source: Union[BinaryIO, bytes, str, Path]) -> Optional[int]:
    """Returns the page count of a valid unlocked PDF, or None if unreadable."""
    if pdf_source is None:
        return None
    try:
        if isinstance(pdf_source, bytes):
            stream: Union[BinaryIO, str, Path] = io.BytesIO(pdf_source)
        elif isinstance(pdf_source, (str, Path)):
            stream = pdf_source
        else:
            if hasattr(pdf_source, "seek"):
                pdf_source.seek(0)
            stream = pdf_source

        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            return None
        count = len(reader.pages)
        if hasattr(pdf_source, "seek"):
            try:
                pdf_source.seek(0)
            except Exception:
                pass
        return count
    except Exception:
        return None


def extract_text_from_pdf(
    pdf_source: Union[BinaryIO, bytes, str, Path],
    max_pages: int = DEFAULT_MAX_PAGES,
    min_chars: int = DEFAULT_MIN_CHARS,
    document_name: str = "PDF",
) -> str:
    """Extracts and normalizes text from a PDF file (Resume or Job Description).

    Args:
        pdf_source: File-like object (e.g. Streamlit UploadedFile), bytes, or file path.
        max_pages: Maximum number of pages to parse (default 10).
        min_chars: Minimum character count required to consider the PDF text-readable.
        document_name: Human-readable label for clear validation error messages.

    Returns:
        Cleaned text content extracted from the PDF.

    Raises:
        ValueError: If the PDF is corrupted, password-protected, empty, or scanned.
    """
    label = (document_name or "PDF").strip()

    if pdf_source is None:
        if label == "PDF":
            raise ValueError("No PDF file provided.")
        raise ValueError(f"No PDF file provided for {label}.")

    if isinstance(pdf_source, bytes):
        stream: Union[BinaryIO, str, Path] = io.BytesIO(pdf_source)
    else:
        stream = pdf_source
        if hasattr(stream, "seek"):
            try:
                stream.seek(0)
            except Exception:
                pass

    try:
        reader = PdfReader(stream)
    except (PdfReadError, Exception) as exc:
        target = f" ({label})" if label != "PDF" else ""
        raise ValueError(
            f"Could not read the PDF file{target}. The file may be corrupted, password-protected, or invalid. Details: {exc}"
        ) from exc

    if reader.is_encrypted:
        target = f" ({label})" if label != "PDF" else ""
        try:
            decrypt_status = reader.decrypt("")
        except Exception as exc:
            raise ValueError(
                f"Could not read the PDF file{target}. The file is password-protected. Please upload an unlocked PDF."
            ) from exc
        if not decrypt_status:
            raise ValueError(
                f"Could not read the PDF file{target}. The file is password-protected. Please upload an unlocked PDF."
            )

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError(f"The uploaded {label} contains zero pages.")

    pages_to_read = min(total_pages, max_pages)
    extracted_fragments = []

    for page_idx in range(pages_to_read):
        try:
            page = reader.pages[page_idx]
            page_text = page.extract_text()
            if page_text:
                extracted_fragments.append(page_text)
        except Exception:
            continue

    combined_text = "\n".join(extracted_fragments).strip()
    combined_text = re.sub(r"[ \t]+", " ", combined_text)
    combined_text = re.sub(r"\n{3,}", "\n\n", combined_text)

    if len(combined_text) < min_chars:
        raise ValueError(
            f"The uploaded {label} yielded insufficient readable text ({len(combined_text)} characters, minimum {min_chars}). "
            "The file may be an image scan or empty. Please provide a text-selectable PDF."
        )

    return combined_text


def _local_xml_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _extract_paragraphs_from_word_xml(xml_bytes: bytes) -> List[str]:
    """Extracts paragraph strings from a WordprocessingML XML part, preserving list bullets."""
    root = ET.fromstring(xml_bytes)
    paragraphs: List[str] = []

    for elem in root.iter():
        if _local_xml_tag(elem.tag) != "p":
            continue

        is_list_item = False
        fragments: List[str] = []

        for node in elem.iter():
            local = _local_xml_tag(node.tag)
            if local == "numPr":
                is_list_item = True
            elif local == "t" and node.text:
                fragments.append(node.text)
            elif local == "tab":
                fragments.append(" ")
            elif local in ("br", "cr"):
                fragments.append("\n")

        raw_para = "".join(fragments).strip()
        if not raw_para:
            continue

        cleaned_para = re.sub(r"[ \t]+", " ", raw_para)
        if is_list_item and not _BULLET_START_RE.match(cleaned_para):
            cleaned_para = f"- {cleaned_para}"
        paragraphs.append(cleaned_para)

    return paragraphs


def extract_text_from_docx(
    docx_source: Union[BinaryIO, bytes, str, Path],
    min_chars: int = DEFAULT_MIN_CHARS,
    document_name: str = "DOCX",
) -> str:
    """Extracts and normalizes text from a Microsoft Word (.docx) file."""
    label = (document_name or "DOCX").strip()

    if docx_source is None:
        raise ValueError(f"No DOCX file provided for {label}.")

    raw_bytes = _read_source_bytes(docx_source, label)
    if not raw_bytes:
        raise ValueError(f"The uploaded {label} file is empty.")

    if raw_bytes.startswith(_OLE_MAGIC):
        raise ValueError(
            f"Could not read {label}. The file is either password-protected or saved in the legacy .doc format. "
            "Please upload an unlocked .docx, .pdf, or .txt file."
        )

    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            names = archive.namelist()
            if "word/document.xml" not in names:
                raise ValueError(
                    f"Could not read {label}. The file is not a valid Word (.docx) document."
                )

            header_parts = sorted(
                n for n in names if n.startswith("word/header") and n.endswith(".xml")
            )
            footer_parts = sorted(
                n for n in names if n.startswith("word/footer") and n.endswith(".xml")
            )
            ordered_parts = [*header_parts, "word/document.xml", *footer_parts]

            all_paragraphs: List[str] = []
            for part_name in ordered_parts:
                xml_bytes = archive.read(part_name)
                all_paragraphs.extend(_extract_paragraphs_from_word_xml(xml_bytes))
    except ValueError:
        raise
    except (zipfile.BadZipFile, ET.ParseError, KeyError, Exception) as exc:
        raise ValueError(
            f"Could not read the Word document ({label}). The file may be corrupted or invalid. Details: {exc}"
        ) from exc

    combined_text = _normalize_extracted_text("\n".join(all_paragraphs))

    if len(combined_text) < min_chars:
        raise ValueError(
            f"The uploaded {label} yielded insufficient readable text ({len(combined_text)} characters, minimum {min_chars}). "
            "Please provide a document with complete text."
        )

    return combined_text


def extract_text_from_txt(
    txt_source: Union[BinaryIO, bytes, str, Path],
    min_chars: int = DEFAULT_MIN_CHARS,
    document_name: str = "TXT",
) -> str:
    """Extracts and normalizes text from a plain text (.txt) file."""
    label = (document_name or "TXT").strip()

    if txt_source is None:
        raise ValueError(f"No text file provided for {label}.")

    raw_bytes = _read_source_bytes(txt_source, label)
    if not raw_bytes:
        raise ValueError(f"The uploaded {label} file is empty.")

    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            decoded = raw_bytes.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Could not decode UTF-16 text file ({label}): {exc}") from exc
    else:
        if b"\x00" in raw_bytes:
            raise ValueError(
                f"Could not read {label} as plain text. Binary content was detected; please upload a .txt, .docx, or .pdf file."
            )
        try:
            decoded = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = raw_bytes.decode("latin-1")

    combined_text = _normalize_extracted_text(decoded)

    if len(combined_text) < min_chars:
        raise ValueError(
            f"The uploaded {label} yielded insufficient readable text ({len(combined_text)} characters, minimum {min_chars}). "
            "Please provide fuller text."
        )

    return combined_text


def extract_text_from_document(
    file_source: Union[BinaryIO, bytes, str, Path],
    filename: str = "",
    max_pages: int = DEFAULT_MAX_PAGES,
    min_chars: int = DEFAULT_MIN_CHARS,
    document_name: str = "Document",
) -> str:
    """Extracts readable text from a .pdf, .docx, or .txt upload by extension or magic bytes."""
    label = (document_name or "Document").strip()
    if file_source is None:
        raise ValueError(f"No file provided for {label}.")

    inferred_name = filename or getattr(file_source, "name", "")
    if not inferred_name and isinstance(file_source, (str, Path)):
        inferred_name = str(file_source)

    ext = Path(inferred_name).suffix.lower() if inferred_name else ""

    if ext == ".pdf":
        pdf_label = label if label.lower().endswith("pdf") else f"{label} PDF"
        return extract_text_from_pdf(
            file_source, max_pages=max_pages, min_chars=min_chars, document_name=pdf_label
        )
    if ext == ".docx":
        docx_label = label if "docx" in label.lower() else f"{label} DOCX"
        return extract_text_from_docx(
            file_source, min_chars=min_chars, document_name=docx_label
        )
    if ext == ".txt":
        txt_label = label if "txt" in label.lower() else f"{label} TXT"
        return extract_text_from_txt(
            file_source, min_chars=min_chars, document_name=txt_label
        )
    if ext == ".doc":
        raise ValueError(
            f"Legacy .doc files are not supported for {label}. Please save the file as .docx, .pdf, or .txt."
        )
    if ext:
        raise ValueError(
            f"Unsupported file format '{ext}' for {label}. Supported formats are .pdf, .docx, and .txt."
        )

    # No extension available: inspect magic bytes
    raw_bytes = _read_source_bytes(file_source, label)
    if raw_bytes.startswith(b"%PDF"):
        return extract_text_from_pdf(
            raw_bytes, max_pages=max_pages, min_chars=min_chars, document_name=label
        )
    if raw_bytes.startswith(b"PK\x03\x04"):
        return extract_text_from_docx(
            raw_bytes, min_chars=min_chars, document_name=label
        )
    if raw_bytes.startswith(_OLE_MAGIC):
        raise ValueError(
            f"Could not read {label}. Password-protected Office files and legacy .doc files are not supported."
        )
    return extract_text_from_txt(raw_bytes, min_chars=min_chars, document_name=label)


def resolve_document_text(
    text: Optional[str] = None,
    pdf_source: Optional[Union[BinaryIO, bytes, str, Path]] = None,
    document_name: str = "Document",
    max_pages: int = DEFAULT_MAX_PAGES,
    min_chars: int = DEFAULT_MIN_CHARS,
    file_source: Optional[Union[BinaryIO, bytes, str, Path]] = None,
    filename: str = "",
) -> str:
    """Resolves readable document text from a file upload (.pdf/.docx/.txt), PDF source, or plain text."""
    if file_source is not None:
        return extract_text_from_document(
            file_source=file_source,
            filename=filename,
            max_pages=max_pages,
            min_chars=min_chars,
            document_name=document_name,
        )

    if pdf_source is not None:
        pdf_label = label if (label := document_name).lower().endswith("pdf") else f"{document_name} PDF"
        return extract_text_from_pdf(
            pdf_source=pdf_source,
            max_pages=max_pages,
            min_chars=min_chars,
            document_name=pdf_label,
        )

    if text is not None and text.strip():
        normalized = re.sub(r"[ \t]+", " ", text.strip())
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized

    raise ValueError(
        f"{document_name} text is empty. Please upload a file (.pdf, .docx, or .txt) or enter text."
    )
