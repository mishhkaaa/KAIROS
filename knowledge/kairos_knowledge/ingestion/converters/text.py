"""Plain text and source code -> one OKF note each (uploads and folders of this computer are full of these)."""
from __future__ import annotations

from pathlib import Path

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft

from .base import draft, okf_path, read_text, require_path, slug

PROSE = {".txt", ".text", ".log", ".rst"}
CODE = {".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".sql": "sql", ".sh": "bash",
        ".ps1": "powershell", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".ini": "ini", ".json": "json",
        ".java": "java", ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".html": "html", ".css": "css"}
SUFFIXES = PROSE | set(CODE)
MAX_BYTES = 512 * 1024  # a note, not a data dump


class TextConverter:
    name = "text"
    source_types = [IngestSourceType.FILE]

    def can_convert(self, request: IngestRequest) -> bool:
        p = Path(request.uri)
        return p.is_file() and p.suffix.lower() in SUFFIXES

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        src = require_path(request)
        if src.stat().st_size > MAX_BYTES:
            raise KairosError("BAD_REQUEST", f"{src.name} is larger than {MAX_BYTES // 1024} KB")
        text = read_text(src)
        if not text.strip():
            raise KairosError("BAD_REQUEST", f"{src.name} is empty")
        suffix = src.suffix.lower()
        lang = CODE.get(suffix)
        body = f"```{lang}\n{text.rstrip()}\n```\n" if lang else text
        return [draft(request, okf_path(request, slug(src.stem) + ("-" + suffix.lstrip(".") if lang else "")), body, str(src),
                      type="note", title=src.name if lang else src.stem.replace("-", " ").replace("_", " ").strip().title(),
                      description=f"Imported from {src.name}", tags=["code", lang] if lang else ["text"],
                      source="file", trust="unverified")]
