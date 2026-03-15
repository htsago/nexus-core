# Changelog

All notable changes to NEXUS Core are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are dated; the project does not use semantic versioning at this stage.

---

## [Unreleased]

---

## [2026-03-15] — Lower Similarity Threshold & Hybrid Lookup Improvement

### Changed

- `NEXUS_SIMILARITY_THRESHOLD` default lowered from `0.7` to `0.35`. The previous
  value was too strict for factual/structural content (release notes, changelogs,
  API reference tables) where relevant chunks typically score between 0.35–0.60.
- `hybrid_lookup` now returns a structured `message` field when both the semantic
  path and the FTS5 path produce zero results, making it easier for callers to
  distinguish "empty index" from "below threshold".

### Fixed

- Release-notes / version-number queries returned no results with the old threshold
  even after a successful ingestion of 50+ chunks. At 0.35 the correct chunks are
  now returned.

---

## [2026-03-15] — Authentication, OpenAI Embeddings & Reliability Fixes

### Added

- `src/auth.py` — `NexusOAuthProvider(OAuthProvider)`: full OAuth 2.0 + PKCE authorization
  server with dynamic client registration (RFC 7591), consent UI at `/consent`, in-memory
  access/refresh token management (TTLs: 1 h / 30 d), and PKCE code-challenge verification.
- Static Bearer token mode: `load_access_token` accepts `NEXUS_API_KEY` directly via
  `hmac.compare_digest`, enabling VS Code, LangChain, and curl to authenticate without OAuth.
- `NEXUS_API_KEY` and `NEXUS_PUBLIC_URL` settings in `src/config.py`.
- OAuth route block in `deploy/nginx.conf` (and live nginx config) to proxy
  `/authorize`, `/token`, `/register`, `/consent`, `/.well-known/` to the MCP server.
- `static/img/consent-page.png` — screenshot of the OAuth consent page.
- README **Authentication** section (static Bearer + OAuth 2.0 + PKCE) and
  **Connecting Clients** section (VS Code, Claude.ai, LangChain, curl).

### Changed

- `server.py`: wired `auth=NexusOAuthProvider()` into `FastMCP()`.
- `src/embeddings.py`: switched default to OpenAI `text-embedding-3-small` with
  `chunk_size=256` and `timeout=60` on all embedding paths.
- `src/ingestion.py`: added `started_at` (monotonic clock) tracking per job; jobs stuck in
  `indexing` state for more than 300 s are automatically retried on the next request.
- `src/models.py`: added `error: Optional[str] = None` to `IngestResult` so ingestion
  failures are visible to callers instead of being silently swallowed.
- `.vscode/mcp.json`: updated to pass `Authorization: Bearer <key>` header.

### Fixed

- Ingestion jobs that hung indefinitely now time out and are re-triggered after 300 s.
- Embedding calls that blocked forever now fail with a clear timeout error after 60 s.
- Dynamic client registration was silently disabled (`ClientRegistrationOptions(enabled=False)`
  default), causing Claude.ai to fail with "error connecting"; fixed by passing `enabled=True`.
- nginx `location / { return 404; }` catch-all blocked all OAuth endpoints; resolved by
  adding an explicit regex location block for OAuth paths.

---

## [2026-03-15] — Professional Folder Structure

### Changed

- Removed six root-level backward-compatibility stub files (`config.py`, `db.py`,
  `embeddings.py`, `ingestion.py`, `llm.py`, `retrieval.py`) that re-exported from `src/`.
  All internal imports already target `src.*` directly; the stubs were redundant clutter.
- Moved `test_tools.py` from the project root into a dedicated `tests/` directory
  (`tests/test_tools.py`), following the standard Python project layout convention.
- Updated `Dockerfile` to reflect the new layout: stub files removed from `COPY`, `tests/`
  directory added.
- Updated `README.md` project structure diagram to include `tests/` and drop the stubs.

---

## [2026-03-14] — Clean Architecture Refactor

### Changed

- Restructured the entire codebase from a single-file layout to a layered `src/` package
  following Clean Architecture conventions.
- `server.py` reduced to 42 lines; tool registration is now automatic via `pkgutil.iter_modules`
  — adding a new tool module to `src/tools/` requires no changes to `server.py`.
- All tool implementations moved to individual modules under `src/tools/`:
  `discover.py`, `ingest.py`, `query.py`, `compliance.py`, `metadata.py`, `refresh.py`.
- Core logic separated into dedicated modules under `src/`:
  `config.py`, `db.py`, `embeddings.py`, `llm.py`, `models.py`, `ingestion.py`, `retrieval.py`.
- Compliance prompt template extracted to `src/models.py`.
- All inline comments and verbose docstrings removed; docstrings rewritten to minimal English.
- Root-level legacy files (`config.py`, `db.py`, etc.) replaced with one-line re-export stubs
  for backward compatibility.

### Added

- `src/models.py` — central location for shared prompt templates.
- `CHANGELOG.md` — this file.
- Professional `README.md` with full tools reference and configuration table.

---

## [2026-03-14] — HTTP Transport and MCP Registration

### Changed

- Server transport switched from `stdio` to `streamable-http` on `http://0.0.0.0:8765/mcp`.
- `.vscode/mcp.json` updated to `type: "http"` pointing at `http://localhost:8765/mcp`.

### Added

- `.vscode/mcp.json` — VS Code MCP server registration for Copilot agent mode.

---

## [2026-03-14] — Tavily Documentation Indexing

### Added

- Indexed `tavily-python` documentation from `docs.tavily.com`:
  `llms.txt`, `quickstart.md`, `search.md`, `extract.md`, `crawl.md`.
- Indexed `langchain` documentation from `python.langchain.com`:
  agent concept page and `how_to/agent_executor`.

---

## [2026-03-13] — Initial Release

### Added

- `server.py` — FastMCP server exposing 7 MCP tools over stdio transport.
- `config.py` — pydantic-settings configuration loaded from `.env`.
- `db.py` — SQLite schema with `sources` metadata table and `content_fts` FTS5 virtual table.
- `embeddings.py` — embedding provider factory supporting `LOCAL`, `OLLAMA`, and `OPENAI`.
- `llm.py` — LLM provider factory supporting `OLLAMA`, `OPENAI`, and `GROQ`.
- `ingestion.py` — full ingestion pipeline: HTTP fetch, BeautifulSoup4 HTML cleaning,
  `RecursiveCharacterTextSplitter` chunking, FAISS indexing, SQLite FTS5 storage.
- `retrieval.py` — `semantic_query`, `hybrid_lookup`, and `verify_compliance` implementations.
- `requirements.txt` — pinned dependency set.
- `.env.template` — configuration template.
- FAISS index shards pre-built for `fastapi`, `langchain`, and `tavily-python`.
- `test_tools.py` — integration test suite against the live HTTP endpoint.

### Design Decisions

- SHA-256 checksum gating: re-ingestion is skipped when source content is unchanged,
  ensuring the index remains stable under repeated calls.
- Similarity threshold (`NEXUS_SIMILARITY_THRESHOLD`, default `0.7`) gates all vector
  search results; the server returns a structured message rather than low-confidence hits.
- `nexus_verify_compliance` uses an LCEL chain with an explicit instruction to respond
  `INSUFFICIENT_DOCUMENTATION` when indexed content does not cover the query — preventing
  hallucinated compliance verdicts.
- FAISS index is fully rebuilt from FTS5 chunks on any URL update, eliminating stale vectors.
