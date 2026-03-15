# Changelog

All notable changes to NEXUS Core are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are dated; the project does not use semantic versioning at this stage.

---

## [Unreleased]

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
