from fastmcp.exceptions import ToolError

from src.models import ChunkResult, HybridLookupResult, SemanticQueryResult


def register(mcp) -> None:
    @mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
    def nexus_semantic_query(framework: str, query: str, k: int = 5) -> SemanticQueryResult:
        """Semantic FAISS search, threshold-gated."""
        from src.config import settings
        from src.retrieval import semantic_query

        try:
            raw = semantic_query(framework, query, k)
        except ValueError as exc:
            raise ToolError(str(exc))

        is_sentinel = len(raw) == 1 and "message" in raw[0] and not raw[0].get("content")
        return SemanticQueryResult(
            framework=framework,
            query=query,
            threshold=settings.NEXUS_SIMILARITY_THRESHOLD,
            results=[] if is_sentinel else [ChunkResult(**r) for r in raw],
        )

    @mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
    def nexus_hybrid_lookup(framework: str, query: str, k: int = 5) -> HybridLookupResult:
        """Hybrid FAISS + FTS5 retrieval, deduplicated by content."""
        from src.retrieval import hybrid_lookup

        try:
            raw = hybrid_lookup(framework, query, k)
        except ValueError as exc:
            raise ToolError(str(exc))

        return HybridLookupResult(
            framework=raw["framework"],
            query=raw["query"],
            results=[ChunkResult(**r) for r in raw.get("results", [])],
            total=raw.get("total", 0),
        )
