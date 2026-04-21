"""
PDF text extraction using PyMuPDF (fitz).

Handles resume PDFs uploaded by the user. Returns plain text suitable for
passing to the Anthropic API or storing in the database.

Does NOT: interpret, structure, or summarize the resume content. That is the
responsibility of the agent or caller.
"""

import io
from pathlib import Path

import fitz  # PyMuPDF


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF given its raw bytes (e.g. from Streamlit uploader)."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        return "\n".join(pages).strip()
    except Exception as e:
        raise ValueError(f"Could not parse PDF: {e}") from e


def extract_text_from_pdf_path(path: str | Path) -> str:
    """Extract plain text from a PDF file on disk."""
    try:
        doc = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        return "\n".join(pages).strip()
    except Exception as e:
        raise ValueError(f"Could not parse PDF at {path}: {e}") from e
