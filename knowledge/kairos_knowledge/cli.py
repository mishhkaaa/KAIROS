"""kairos-okf: validate / ingest / reindex / search from the terminal. Owner: P2."""

from __future__ import annotations

import asyncio
import json

import typer
from kairos_contracts.schema import IngestRequest, IngestSourceType, SearchQuery
from kairos_contracts.testing.fakes import user_principal
from kairos_contracts.wiring import ServiceBundle, Settings

from . import factory

app = typer.Typer(add_completion=False, help="KAIROS OKF bundle: validate, ingest, reindex, search.")


def _build_settings_and_services() -> tuple[Settings, ServiceBundle]:
    from kairos_contracts.testing.fakes import FakeMarkdownConverter, FakeModelRouter, InMemoryEventBus

    settings = Settings.from_env()
    services = ServiceBundle(settings=settings, models=FakeModelRouter(), event_bus=InMemoryEventBus())
    services.firewall = factory.build_context_firewall(settings, services)
    if settings.modes.get("converters") == "real":
        # P4's converters live inside this package; kairosd/wiring.py picks them the same way.
        from .ingestion.factory import build_converters

        services.converters = build_converters(settings, services)
    else:
        services.converters = [FakeMarkdownConverter()]
    return settings, services


def _knowledge_service():
    settings, services = _build_settings_and_services()
    return factory.build_knowledge_service(settings, services)


@app.command()
def validate() -> None:
    """Lint the OKF bundle (frontmatter, links, titles, index.md)."""
    from .okf import OKFBundle
    from .validation import validate_bundle

    settings, _ = _build_settings_and_services()
    report = validate_bundle(OKFBundle(settings.okf_dir))
    for issue in report.issues:
        typer.echo(f"[{issue.severity}] {issue.okf_file}: {issue.message}")
    typer.echo(f"{report.files_checked} files checked, {len(report.issues)} issues, ok={report.ok}")
    raise typer.Exit(0 if report.ok else 1)


@app.command()
def reindex(paths: list[str] = typer.Argument(None, help="Specific /org paths, or all when omitted")) -> None:
    """Rebuild the derived indexes."""

    async def go() -> int:
        svc = _knowledge_service()
        return await svc.reindex(paths or None)

    count = asyncio.run(go())
    typer.echo(f"reindexed {count} objects")


@app.command()
def search(text: str, top_k: int = 8, scope: str = "/org") -> None:
    """Hybrid search over the bundle."""

    async def go():
        svc = _knowledge_service()
        return await svc.search(SearchQuery(text=text, scope=[scope], top_k=top_k), user_principal())

    ev = asyncio.run(go())
    for h in ev.hits:
        flags = f" [{','.join(h.firewall_flags)}]" if h.firewall_flags else ""
        typer.echo(f"{h.score:.4f}  {h.path}{flags}\n    {h.snippet}")
    typer.echo(f"{len(ev.hits)} hits, {ev.total_candidates} candidates, {ev.filtered_by_policy} hidden by policy")


@app.command()
def ingest(path: str, target: str = "/org") -> None:
    """Ingest a file or directory of Markdown into the bundle."""
    from pathlib import Path

    source_type = IngestSourceType.FILE if Path(path).is_file() else IngestSourceType.DIRECTORY

    async def go():
        svc = _knowledge_service()
        return await svc.ingest(IngestRequest(source_type=source_type, uri=path, target_path=target))

    result = asyncio.run(go())
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


def main() -> None:
    app()
