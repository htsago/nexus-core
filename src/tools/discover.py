from typing import Optional

from fastmcp.exceptions import ToolError

from src.config import settings
from src.models import DiscoverResult, DocCandidate


def register(mcp) -> None:
    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    def nexus_discover_source(framework: str, hint: Optional[str] = None) -> DiscoverResult:
        """Discover official documentation URLs for framework using Tavily search."""
        if not settings.TAVILY_API_KEY:
            raise ToolError("TAVILY_API_KEY is not configured. Set it in .env and restart the server.")
        try:
            from tavily import TavilyClient
        except ImportError:
            raise ToolError("tavily-python is not installed. Run: pip install tavily-python")

        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        queries = [
            f"{framework} llms.txt official documentation",
            f"{framework} github.com official documentation README",
            f"{framework} official documentation site:readthedocs.io OR site:docs.",
            f"{framework} documentation API reference",
        ]
        if hint:
            queries.insert(0, hint)

        candidates: list[DocCandidate] = []
        seen: set[str] = set()
        for query in queries:
            try:
                resp = client.search(query=query, search_depth="advanced", max_results=5)
            except Exception:
                continue
            for r in resp.get("results", []):
                url = r.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                url_lower = url.lower()
                priority = (
                    1 if "llms.txt" in url_lower
                    else 2 if "github.com" in url_lower
                    and ("/blob/" in url_lower or "readme" in url_lower or "/docs/" in url_lower)
                    else 3
                )
                candidates.append(DocCandidate(
                    url=url,
                    title=r.get("title", ""),
                    score=r.get("score", 0.0),
                    priority=priority,
                    content_preview=r.get("content", "")[:300],
                ))

        if not candidates:
            raise ToolError(
                f"No documentation sources found for '{framework}'."
                " Try a more specific name or provide a hint."
            )

        candidates.sort(key=lambda c: (c.priority, -c.score))
        return DiscoverResult(
            framework=framework,
            recommended_url=candidates[0].url,
            all_candidates=candidates[:10],
        )
