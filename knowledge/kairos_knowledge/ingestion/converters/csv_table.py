"""CSV file (budgets, rosters, bills) -> one OKF file with a Markdown table."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import IngestRequest, IngestSourceType, OKFDraft

from .base import draft, okf_path, read_text, require_path, slug

_FINANCE_HINTS = ("budget", "forecast", "bill", "cost", "payroll", "invoice", "spend")


def _cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


class CsvConverter:
    name = "csv"
    source_types = [IngestSourceType.FILE]

    def can_convert(self, request: IngestRequest) -> bool:
        p = Path(request.uri)
        return p.is_file() and p.suffix.lower() == ".csv"

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        src = require_path(request)
        try:
            rows = [r for r in csv.reader(io.StringIO(read_text(src))) if any(c.strip() for c in r)]
        except csv.Error as e:
            raise KairosError("BAD_REQUEST", f"invalid CSV {src}: {e}") from e
        if len(rows) < 2:
            raise KairosError("BAD_REQUEST", f"{src} needs a header row and at least one data row")
        header, data = [h.strip() for h in rows[0]], rows[1:]
        width = len(header)
        table = ["| " + " | ".join(_cell(h) for h in header) + " |", "|" + "---|" * width]
        for r in data:
            table.append("| " + " | ".join(_cell(c) for c in (r + [""] * width)[:width]) + " |")
        title = request.options.get("title") or src.stem.replace("-", " ").replace("_", " ").title()
        kind = request.options.get("type") or ("finance" if any(h in src.stem.lower() for h in _FINANCE_HINTS) else "note")
        return [draft(request, okf_path(request, slug(src.stem)), "\n".join([f"# {title}", "", *table]), str(src),
                      type=kind, title=title, description=f"Columns: {', '.join(header)} ({len(data)} rows)",
                      tags=["csv", kind], source="csv", trust=request.options.get("trust", "unverified"))]
