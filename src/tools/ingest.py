from fastmcp.exceptions import ToolError

from src.models import IngestResult


def register(mcp) -> None:
    @mcp.tool(annotations={"openWorldHint": True, "destructiveHint": False})
    def nexus_ingest_and_clean(framework: str, url: str) -> IngestResult:
        """Fetch url, strip HTML noise, chunk, and update FAISS + FTS5 index."""
        from src.ingestion import ingest_url

        try:
            return IngestResult(**ingest_url(framework, url))
        except Exception as exc:
            raise ToolError(str(exc))
