"""Interface PROVIDED BY P4 (Platform, Data & Demo), consumed by P2's KnowledgeService.ingest().

A converter turns one kind of source material into OKF drafts. It does NOT write files, index, or
publish events — P2's ingest pipeline does that. This keeps converters pure and easy to test.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schema import IngestRequest, IngestSourceType, OKFDraft


@runtime_checkable
class SourceConverter(Protocol):
    name: str
    """e.g. "markdown", "jira-json", "slack-export", "csv", "pdf" """

    source_types: list[IngestSourceType]

    def can_convert(self, request: IngestRequest) -> bool:
        """Cheap check (extension / sniffing). The pipeline asks every converter and uses the first True."""

    async def convert(self, request: IngestRequest) -> list[OKFDraft]:
        """Return drafts whose frontmatter validates as OKFFrontmatter and whose okf_file is under
        request.target_path (mapped with util.org_path_to_okf_file). Raise KairosError("BAD_REQUEST") on bad input."""
