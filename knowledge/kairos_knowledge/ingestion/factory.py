"""Factory for P4's converters (see kairos_contracts.wiring). kairosd calls it when KAIROS_MODE_CONVERTERS=real."""
from kairos_contracts.interfaces import SourceConverter
from kairos_contracts.wiring import ServiceBundle, Settings

from .converters import (
    CsvConverter,
    DocumentConverter,
    JiraJsonConverter,
    MarkdownConverter,
    SlackConverter,
    TextConverter,
    markitdown_available,
)


def build_converters(settings: Settings, services: ServiceBundle) -> list[SourceConverter]:
    """Priority order: specific formats first; markdown (any .md file or directory) is the catch-all, so it goes last."""
    converters: list[SourceConverter] = [JiraJsonConverter(), SlackConverter(), CsvConverter()]
    if markitdown_available():
        converters.append(DocumentConverter())
    converters.append(TextConverter())
    converters.append(MarkdownConverter())
    return converters
