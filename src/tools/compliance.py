from fastmcp.exceptions import ToolError

from src.models import ComplianceResult


def register(mcp) -> None:
    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
    def nexus_verify_compliance(framework: str, code_snippet: str) -> ComplianceResult:
        """Verify code_snippet against indexed docs via RetrievalQA. Never speculates."""
        from src.retrieval import verify_compliance

        try:
            return ComplianceResult(**verify_compliance(framework, code_snippet))
        except Exception as exc:
            raise ToolError(str(exc))
