from typing import Optional

from src.models import MetadataResult, SourceRecord


def register(mcp) -> None:
    @mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    def nexus_get_index_metadata(framework: Optional[str] = None) -> MetadataResult:
        """Return SQLite index metadata. Optionally filter by framework."""
        from src.db import list_sources

        sources = list_sources(framework)
        if not sources:
            return MetadataResult(
                framework_filter=framework,
                total_sources=0,
                sources=[],
                message=f"No index data for '{framework}'." if framework else "No frameworks indexed yet.",
            )
        return MetadataResult(
            framework_filter=framework,
            total_sources=len(sources),
            sources=[SourceRecord(**s) for s in sources],
        )
