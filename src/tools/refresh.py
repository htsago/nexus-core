from fastmcp.exceptions import ToolError

from src.models import RefreshResult


def register(mcp) -> None:
    @mcp.tool(annotations={"openWorldHint": True, "destructiveHint": False})
    def nexus_refresh_index(framework: str, url: str) -> RefreshResult:
        """Re-ingest url if its content has changed (checksum-based)."""
        from src.db import get_source
        from src.ingestion import ingest_url

        existing = get_source(framework, url)
        try:
            result = ingest_url(framework, url)
        except Exception as exc:
            raise ToolError(str(exc))

        if result["status"] == "unchanged":
            refresh_action, message, prev = "no_change", "Source unchanged. Index is up to date.", None
        elif existing:
            refresh_action = "re_ingested"
            message = "Source changed. Index has been refreshed."
            prev = existing["checksum"]
        else:
            refresh_action, message, prev = "initial_ingest", "New source ingested for the first time.", None

        return RefreshResult(
            status=result["status"],
            framework=framework,
            url=url,
            checksum=result["checksum"],
            chunk_count=result["chunk_count"],
            ingested_at=result["ingested_at"],
            refresh_action=refresh_action,
            message=message,
            previous_checksum=prev,
        )
