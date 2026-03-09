"""WebSearch tool: SearXNG discovery + bounded page fetch and extraction."""

import re
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from tool import Tool

# Limits
MAX_SEARCH_RESULTS = 5
MAX_PAGES_TO_FETCH = 3
MAX_CHARS_PER_PAGE = 4000
MAX_TOTAL_CHARS = 10000
PAGE_FETCH_TIMEOUT = 10.0
SEARCH_TIMEOUT = 15.0

# Skip these URL patterns (PDFs, binaries, etc.)
SKIP_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".zip",
        ".tar",
        ".gz",
        ".exe",
        ".dmg",
        ".apk",
        ".mp3",
        ".mp4",
        ".avi",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
    }
)


def _get_searxng_base_url() -> str:
    from .workflow import get_session_settings, get_workflow_session_id

    session_id = get_workflow_session_id()
    settings = get_session_settings(session_id)
    url = str(settings.get("searxng_url", "http://127.0.0.1:8080")).strip()
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def _search_searxng(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict[str, Any]]:
    base = _get_searxng_base_url()
    search_url = f"{base}/search?q={quote_plus(query)}&format=json"
    results: list[dict[str, Any]] = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        with httpx.Client(timeout=SEARCH_TIMEOUT, headers=headers) as client:
            resp = client.get(search_url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        hint = ""
        if e.response.status_code == 403:
            hint = " (SearXNG may block requests: check instance allows API access, or try a different URL in Settings)"
        return [{"error": f"{e}{hint}", "title": "Search failed", "url": "", "content": ""}]
    except Exception as e:
        return [{"error": str(e), "title": "Search failed", "url": "", "content": ""}]

    raw = data.get("results")
    if not isinstance(raw, list):
        return results

    seen_urls: set[str] = set()
    for item in raw:
        if len(results) >= max_results:
            break
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        norm = url.rstrip("/")
        if norm in seen_urls:
            continue
        seen_urls.add(norm)
        title = item.get("title") or ""
        content = item.get("content") or ""
        results.append(
            {
                "title": str(title)[:200],
                "url": url,
                "snippet": str(content)[:500],
            }
        )

    return results


def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fetch_page(url: str) -> str:
    try:
        with httpx.Client(timeout=PAGE_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception:
        return ""


def _build_evidence_bundle(
    query: str,
    search_results: list[dict[str, Any]],
    extracted_pages: list[dict[str, Any]],
) -> str:
    parts = [
        f"Web search results for: {query}",
        "",
        "Top results:",
    ]
    for i, r in enumerate(search_results[:MAX_SEARCH_RESULTS], 1):
        title = r.get("title", "")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        parts.append(f"{i}. {title}")
        parts.append(f"   URL: {url}")
        if snippet:
            parts.append(f"   Snippet: {snippet[:300]}...")
        parts.append("")

    if extracted_pages:
        parts.append("Extracted evidence from fetched pages:")
        parts.append("")
        total = 0
        for i, p in enumerate(extracted_pages, 1):
            title = p.get("title", "")
            url = p.get("url", "")
            content = p.get("content", "")
            remaining = MAX_TOTAL_CHARS - total
            if remaining <= 0:
                break
            excerpt = content[:min(len(content), remaining, MAX_CHARS_PER_PAGE)]
            total += len(excerpt)
            parts.append(f"- Source {i}: {title}")
            parts.append(f"  URL: {url}")
            parts.append(f"  {excerpt}")
            if len(content) > len(excerpt):
                parts.append("  [truncated]")
            parts.append("")

    return "\n".join(parts)


def _web_search_impl(query: str, max_results: int = 5) -> str:
    if not query or not str(query).strip():
        return "Error: query is required."

    query = str(query).strip()
    max_results = min(max(int(max_results) if max_results else MAX_SEARCH_RESULTS, 10), MAX_SEARCH_RESULTS)

    search_results = _search_searxng(query, max_results=max_results)

    if not search_results:
        return f"No search results for: {query}"

    if search_results and "error" in search_results[0]:
        return f"Search failed: {search_results[0].get('error', 'Unknown error')}"

    extracted_pages: list[dict[str, Any]] = []
    total_chars = 0

    for r in search_results[:MAX_PAGES_TO_FETCH]:
        if total_chars >= MAX_TOTAL_CHARS:
            break
        url = r.get("url", "")
        if not url:
            continue
        html = _fetch_page(url)
        if not html:
            continue
        text = _extract_main_text(html)
        if not text:
            continue
        chunk = text[:MAX_CHARS_PER_PAGE]
        total_chars += len(chunk)
        extracted_pages.append(
            {
                "title": r.get("title", ""),
                "url": url,
                "content": chunk,
            }
        )

    return _build_evidence_bundle(query, search_results, extracted_pages)


class WebSearch(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="web_search_tool",
            description="Search the web for information. Returns search results and extracted content from top pages.",
            handler=self._handler,
        )

    def _handler(self, query: str, max_results: int = 5) -> str:
        return _web_search_impl(query=query, max_results=max_results)
