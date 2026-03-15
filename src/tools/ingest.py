from fastmcp.exceptions import ToolError

from src.models import IngestResult


def register(mcp) -> None:
    @mcp.tool(annotations={"openWorldHint": True, "destructiveHint": False})
    def nexus_ingest_and_clean(framework: str, url: str) -> IngestResult:
        """Fetch url, strip HTML noise, chunk, and start indexing in background.

        Returns immediately. When status='indexing', use nexus_ingest_status(job_id)
        to poll until status='ingested'.
        """
        from src.ingestion import ingest_url

        try:
            return IngestResult(**ingest_url(framework, url))
        except Exception as exc:
            raise ToolError(str(exc))

    @mcp.tool()
    def nexus_ingest_status(job_id: str) -> IngestResult:
        """Poll the status of a background ingest job started by nexus_ingest_and_clean.

        Returns status='indexing' while embedding is in progress,
        status='ingested' when done, or status='error' on failure.
        """
        from src.ingestion import get_ingest_status

        try:
            return IngestResult(**get_ingest_status(job_id))
        except KeyError as exc:
            raise ToolError(str(exc))
