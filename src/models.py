from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class DocCandidate(BaseModel):
    url: str
    title: str
    score: float
    priority: int
    content_preview: str


class ChunkResult(BaseModel):
    content: str
    metadata: dict[str, Any]
    similarity_score: float | None = None
    match_type: str | None = None


class SourceRecord(BaseModel):
    id: int
    framework: str
    url: str
    checksum: str
    ingested_at: str
    chunk_count: int


# ---------------------------------------------------------------------------
# Tool output models
# ---------------------------------------------------------------------------

class DiscoverResult(BaseModel):
    framework: str
    recommended_url: str
    all_candidates: list[DocCandidate]


class IngestResult(BaseModel):
    status: str
    framework: str
    url: str
    checksum: str
    chunk_count: int
    ingested_at: str


class SemanticQueryResult(BaseModel):
    framework: str
    query: str
    threshold: float
    results: list[ChunkResult]


class HybridLookupResult(BaseModel):
    framework: str
    query: str
    results: list[ChunkResult]
    total: int


class ComplianceResult(BaseModel):
    framework: str
    verification_result: str
    sources_consulted: list[str]
    source_count: int


class MetadataResult(BaseModel):
    framework_filter: Optional[str]
    total_sources: int
    sources: list[SourceRecord]
    message: Optional[str] = None


class RefreshResult(BaseModel):
    status: str
    framework: str
    url: str
    checksum: str
    chunk_count: int
    ingested_at: str
    refresh_action: str
    message: str
    previous_checksum: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

COMPLIANCE_PROMPT = """\
You are a strict, deterministic API compliance checker.
Use ONLY the documentation context provided below. Do not add any external knowledge.

=== DOCUMENTATION CONTEXT ===
{context}
=== END CONTEXT ===

Analyse the following code snippet for API compliance:

```
{question}
```

Respond with a structured report:

VERDICT: COMPLIANT | NON-COMPLIANT | PARTIAL | INSUFFICIENT_DOCUMENTATION

ISSUES:
- <list each issue, or "None" if fully compliant>

CORRECT_USAGE:
- <cite the relevant documentation excerpt that supports or refutes each point>

RULE: If the provided documentation does not cover the code under review,
set VERDICT to INSUFFICIENT_DOCUMENTATION and do not speculate."""
