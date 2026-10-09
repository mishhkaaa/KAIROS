"""WebResearcherAgent: answers from the public web when /org does not know.

Everything goes through the kernel: it searches with ``browser.open`` on a search engine's results page and reads the
top results with ``browser.open``, each a governed syscall (policy web-researcher-v1, audited, screenshotted) in a
browser sandbox whose only route out is the public internet. Page text is untrusted data: it is quoted, never obeyed.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlsplit

from kairos_contracts.schema import AgentResult, AgentResultStatus, Risk

from kairos_agents.sdk import KairosAgent, plural, propose_action, think

log = logging.getLogger("kairos.agents.web")

# Search engines tried in order: one that answers a headless browser with a bot challenge is skipped for the next.
# Wikipedia's search API answers automated readers (search engines show a headless browser a bot check from many
# networks), so it is tried first; its JSON comes back as the page text.
WIKI_SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit=4"
SEARCH_URLS = (
    "https://www.mojeek.com/search?q={q}",
    "https://lite.duckduckgo.com/lite/?q={q}",
    "https://www.bing.com/search?q={q}&setlang=en",
)
MAX_PAGES = 2
PAGE_CHARS = 3500
_SKIP_HOSTS = ("duckduckgo.com", "duck.com", "bing.com", "bing.net", "google.", "microsoft.com", "msn.com", "live.com",
               "mojeek.com", "youtube.com", "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com")


def _target(href: str) -> str:
    """Where a results-page link really goes: search engines wrap results in redirect links."""
    parts = urlsplit(href)
    q = parse_qs(parts.query)
    if parts.netloc.endswith("duckduckgo.com") and parts.path.startswith("/l/"):
        return (q.get("uddg") or [""])[0]
    if parts.netloc.endswith("bing.com") and parts.path.startswith("/ck/"):
        u = (q.get("u") or [""])[0]
        if u.startswith("a1"):
            try:
                return base64.urlsafe_b64decode(u[2:] + "=" * (-len(u[2:]) % 4)).decode()
            except ValueError:
                return ""
    return href


_ASK_PHRASES = ("search the web", "search online", "search the internet", "on the internet", "on the web", "online",
                "google it", "look it up", "please")


def wiki_results(page_text: str) -> list[str]:
    try:
        hits = json.loads(page_text).get("query", {}).get("search", [])
    except (ValueError, AttributeError):
        return []
    return ["https://en.wikipedia.org/wiki/" + quote_plus(h["title"].replace(" ", "_"), safe="_()") for h in hits if h.get("title")]


def search_query(goal: str) -> str:
    """The words to search for: the question without "search the web" and the like."""
    q = goal
    for phrase in _ASK_PHRASES:
        q = q.replace(phrase, " ").replace(phrase.capitalize(), " ")
    return " ".join(q.replace("?", " ").split()).strip(" .") or goal


def result_links(links: list[str], limit: int = 6) -> list[str]:
    """The result URLs on a search engine's results page, in order, without the engine's own and social links."""
    out: list[str] = []
    for href in links:
        target = _target(href)
        if urlsplit(href).netloc.endswith("bing.com") or (target == href and any(
                urlsplit(x).netloc.endswith("bing.com") for x in links[:3])):
            if target == href:
                continue  # on a Bing page only its wrapped result links are results; the rest is navigation
        host = urlsplit(target).netloc.lower()
        if not target.startswith(("http://", "https://")) or not host or any(s in host for s in _SKIP_HOSTS):
            continue
        if "y.js" in target or "ad_provider" in target:
            continue  # ads
        if target not in out:
            out.append(target)
        if len(out) == limit:
            break
    return out


class WebResearcherAgent(KairosAgent):
    async def _open(self, ctx: Any, url: str, why: str) -> dict[str, Any] | None:
        req = propose_action(ctx, capability="browser.open", tool="browser", operation="open", arguments={"url": url},
                             justification=why, evidence=[], risk=Risk.LOW, resource=url)
        try:
            res = await ctx.syscall(req)
        except Exception as e:  # noqa: BLE001 — one unreachable page must not end the research
            await ctx.log(f"web-researcher: {url} could not be opened: {e}", level="warning")
            return None
        out = res.tool_result.output if res.tool_result else None
        if not out:
            await ctx.log(f"web-researcher: {url}: {res.status.value} {res.reason or ''}", level="warning")
        return out

    async def run(self, goal: str, ctx: Any) -> AgentResult:
        query = search_query(str((ctx.inputs or {}).get("query") or goal))[:200]
        await think(ctx, "search", f"Searching the public web for: {query}")
        wiki = await self._open(ctx, WIKI_SEARCH.format(q=quote_plus(query)), f"Encyclopedia search for: {query}")
        urls: list[str] = wiki_results((wiki or {}).get("text", ""))
        for engine in SEARCH_URLS if not urls else ():
            results = await self._open(ctx, engine.format(q=quote_plus(query)), f"Web search for: {query}")
            urls = result_links((results or {}).get("links") or [])
            if urls:
                break
            await ctx.log(f"web-researcher: no results from {urlsplit(engine).netloc} (a bot check?), trying the next engine")
        await ctx.log(f"web-researcher: {len(urls)} results", data={"urls": urls})
        pages: list[dict[str, str]] = []
        for url in urls:
            if len(pages) == MAX_PAGES or ctx.cancelled():
                break
            page = await self._open(ctx, url, f"Read a search result for: {query}")
            text = (page or {}).get("text", "").strip()
            if len(text) > 200:
                pages.append({"url": (page or {}).get("url") or url, "title": (page or {}).get("title", ""), "text": text[:PAGE_CHARS]})
                await think(ctx, "read", f"Read {pages[-1]['title'] or url}")
        await think(ctx, "summarize", f"Read {plural(len(pages), 'web page')} from {plural(len(urls), 'search result')}.")
        status = AgentResultStatus.COMPLETED if pages else AgentResultStatus.FAILED
        summary = (f"Read {plural(len(pages), 'web page')} for: {query}" if pages
                   else f"The web search found nothing readable for: {query}")
        return AgentResult(pid=ctx.pid, agent=ctx.manifest.name, status=status, summary=summary,
                           output={"query": query, "results": urls, "pages": pages, "urls_opened": [p["url"] for p in pages]},
                           evidence=[p["url"] for p in pages])
