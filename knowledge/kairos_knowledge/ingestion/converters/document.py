"""PDF / DOCX / PPTX / XLSX -> Markdown via markitdown (optional extra `ingest`)."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft

from .base import draft, okf_path, require_path, slug

SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx"}


def markitdown_available() -> bool:
    return importlib.util.find_spec("markitdown") is not None


def _pdf_text(path: Path) -> str:
    """PDF text in reading order. markitdown's PDF path guesses tables from column gaps, which turns a resume or a
    report into one-word table cells and runs words together; plain text extraction keeps sentences whole."""
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
            # Bullet glyphs come out as private-use or replacement characters: make them Markdown list items.
            pages.append("\n".join(("- " + line[1:].strip()) if line[:1] in ("•", "", "�", "●", "▪")
                                   else line for line in text.splitlines()))
    return "\n\n".join(p for p in pages if p.strip())


def _convert(path: Path) -> tuple[str, str | None]:
    if path.suffix.lower() == ".pdf" and importlib.util.find_spec("pdfplumber") is not None:
        try:
            text = _pdf_text(path)
            if text.strip():
                return text, None
        except Exception:  # noqa: BLE001 — fall back to markitdown for PDFs pdfplumber cannot read
            pass
    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert(str(path))
    return result.text_content or "", getattr(result, "title", None)


class DocumentConverter:
    name = "document"
    source_types = [IngestSourceType.FILE]

    def can_convert(self, request: IngestRequest) -> bool:
        p = Path(request.uri)
        return p.is_file() and p.suffix.lower() in SUFFIXES and markitdown_available()

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        src = require_path(request)
        if not src.is_file() or src.suffix.lower() not in SUFFIXES:
            raise KairosError("BAD_REQUEST", f"unsupported document: {src}")
        try:
            text, title = await asyncio.to_thread(_convert, src)
        except Exception as e:  # markitdown raises parser-specific errors
            raise KairosError("BAD_REQUEST", f"cannot convert {src}: {e}") from e
        if not text.strip():
            raise KairosError("BAD_REQUEST", f"{src} contains no extractable text")
        title = (title or "").strip() or src.stem.replace("-", " ").replace("_", " ").title()
        return [draft(request, okf_path(request, slug(src.stem)), text, str(src), type="note", title=title,
                      description=f"Imported from {src.name}", tags=["document", src.suffix.lower().lstrip(".")],
                      source="document", trust="unverified")]
