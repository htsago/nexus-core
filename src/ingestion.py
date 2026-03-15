from __future__ import annotations

import hashlib
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import settings
from src.db import get_all_fts_chunks, get_source, replace_fts_chunks, upsert_source
from src.embeddings import get_embeddings

_NOISE_TAGS = ["nav", "header", "footer", "aside", "script", "style", "noscript", "iframe"]
_NOISE_CLASSES = [
    "nav", "navbar", "menu", "sidebar", "side-bar", "cookie", "banner",
    "advertisement", "advert", "ad-", "breadcrumb", "pagination", "toc",
    "table-of-contents", "announcement", "promo",
]
_NOISE_IDS = ["nav", "sidebar", "menu", "footer", "header", "toc", "breadcrumb"]

_HEADERS_BOT = {
    "User-Agent": "NEXUS-Core/1.0 (deterministic RAG indexer)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── GitHub URL patterns ────────────────────────────────────────────────────────
_GH_BLOB   = re.compile(r"github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)")
_GH_REL    = re.compile(r"github\.com/([^/]+)/([^/]+)/releases")
_GH_ROOT   = re.compile(r"github\.com/([^/]+)/([^/]+)/?$")
_GH_RAW    = re.compile(r"raw\.githubusercontent\.com")


def _github_api(path: str) -> dict | list:
    """Call GitHub REST API (unauthenticated, public repos only)."""
    url = f"https://api.github.com/{path.lstrip('/')}"
    r = requests.get(url, headers={"Accept": "application/vnd.github+json",
                                   "User-Agent": "NEXUS-Core/1.0"}, timeout=20)
    r.raise_for_status()
    return r.json()


def _fetch_url(url: str) -> tuple[str, bool]:
    """Return (text_content, is_markdown).

    Applies smart routing:
    - GitHub blob  → raw.githubusercontent.com
    - GitHub releases page → GitHub API JSON → rendered text
    - GitHub repo root → README via API
    - raw.githubusercontent → fetch directly as markdown
    - Everything else → HTTP GET with bot UA, fallback to browser UA
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # ── raw GitHub (already a raw URL) ────────────────────────────────────────
    if _GH_RAW.search(host):
        r = requests.get(url, headers=_HEADERS_BOT, timeout=30)
        r.raise_for_status()
        return r.text, True

    # ── GitHub blob (file view) → convert to raw ──────────────────────────────
    m = _GH_BLOB.search(url)
    if m:
        owner, repo, branch, path = m.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        r = requests.get(raw_url, headers=_HEADERS_BOT, timeout=30)
        r.raise_for_status()
        return r.text, path.endswith(".md") or path.endswith(".rst") or path.endswith(".txt")

    # ── GitHub releases page → API ─────────────────────────────────────────────
    m = _GH_REL.search(url)
    if m:
        owner, repo = m.group(1), m.group(2)
        releases = _github_api(f"repos/{owner}/{repo}/releases")
        if not isinstance(releases, list):
            releases = [releases]
        lines: list[str] = []
        for rel in releases[:10]:  # top 10 most-recent releases
            tag = rel.get("tag_name", "")
            name = rel.get("name", "") or tag
            body = (rel.get("body", "") or "")[:800]  # cap body per release
            published = rel.get("published_at", "")
            lines.append(f"## {name} ({tag}) — {published}\n\n{body}\n")
        return "\n".join(lines), True

    # ── GitHub repo root → README via API ─────────────────────────────────────
    m = _GH_ROOT.search(url)
    if m:
        owner, repo = m.group(1), m.group(2)
        try:
            data = _github_api(f"repos/{owner}/{repo}/readme")
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return content, True
        except Exception:
            pass  # fall through to regular fetch

    # ── Everything else: bot UA, fallback to browser UA ───────────────────────
    exc_last: Exception | None = None
    for headers in (_HEADERS_BOT, _HEADERS_BROWSER):
        try:
            r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            r.raise_for_status()
            return r.text, False
        except requests.RequestException as exc:
            exc_last = exc
    raise RuntimeError(f"Failed to fetch '{url}': {exc_last}") from exc_last



def _clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in _NOISE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()
    for el in list(soup.find_all(class_=True)):
        if not el.attrs:
            continue
        classes = " ".join(el.attrs.get("class", []) or [])
        if any(f in classes.lower() for f in _NOISE_CLASSES):
            el.decompose()
    for el in list(soup.find_all(id=True)):
        if not el.attrs:
            continue
        el_id = el.attrs.get("id", "") or ""
        if any(f in el_id.lower() for f in _NOISE_IDS):
            el.decompose()
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="readme")
        or soup.find(id="content")
        or soup.find("div", {"class": "content"})
        or soup.find("div", {"class": "docs-content"})
        or soup.find("div", {"class": "markdown-body"})
        or soup.body
    )
    return (main or soup).get_text(separator="\n", strip=True)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _faiss_dir(framework: str) -> Path:
    path = Path(settings.NEXUS_STORAGE_PATH) / framework
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Background-job registry ───────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}          # job_id → result dict
_FRAME_LOCKS: dict[str, threading.Lock] = {}
_LOCK_GUARD = threading.Lock()


def _get_frame_lock(framework: str) -> threading.Lock:
    with _LOCK_GUARD:
        if framework not in _FRAME_LOCKS:
            _FRAME_LOCKS[framework] = threading.Lock()
        return _FRAME_LOCKS[framework]


def _docs_from_chunks(framework: str, url: str, chunks: list[str]) -> list[Document]:
    return [
        Document(
            page_content=c,
            metadata={"framework": framework, "url": url, "chunk_id": i},
        )
        for i, c in enumerate(chunks)
    ]


def _rebuild_faiss(framework: str, embeddings) -> FAISS:
    rows = get_all_fts_chunks(framework)
    if not rows:
        raise ValueError(f"No FTS5 chunks for framework '{framework}'.")
    docs = [
        Document(
            page_content=r["content"],
            metadata={"framework": r["framework"], "url": r["url"], "chunk_id": r["chunk_id"]},
        )
        for r in rows
    ]
    return FAISS.from_documents(docs, embeddings, distance_strategy=DistanceStrategy.COSINE)


def _embed_and_save(
    job_id: str,
    framework: str,
    url: str,
    chunks: list[str],
    checksum: str,
    existing,
) -> None:
    """Background thread: embed chunks and persist index."""
    lock = _get_frame_lock(framework)
    lock.acquire()
    try:
        embeddings = get_embeddings()
        faiss_dir = _faiss_dir(framework)
        replace_fts_chunks(framework, url, chunks)

        if existing:
            index = _rebuild_faiss(framework, embeddings)
        else:
            docs = _docs_from_chunks(framework, url, chunks)
            try:
                index = FAISS.load_local(
                    str(faiss_dir), embeddings, allow_dangerous_deserialization=True
                )
                index.add_documents(docs)
            except Exception:
                index = FAISS.from_documents(
                    docs, embeddings, distance_strategy=DistanceStrategy.COSINE
                )

        index.save_local(str(faiss_dir))
        ingested_at = datetime.now(timezone.utc).isoformat()
        upsert_source(framework, url, checksum, ingested_at, len(chunks))
        _JOBS[job_id] = {
            "status": "ingested",
            "framework": framework,
            "url": url,
            "checksum": checksum,
            "chunk_count": len(chunks),
            "ingested_at": ingested_at,
        }
    except Exception as exc:
        _JOBS[job_id] = {
            "status": "error",
            "framework": framework,
            "url": url,
            "checksum": checksum,
            "chunk_count": 0,
            "ingested_at": "",
            "error": str(exc),
        }
    finally:
        lock.release()


def ingest_url(framework: str, url: str) -> dict:
    """Fetch, clean, chunk, then embed in a background thread.

    Returns immediately with status='indexing' and a job_id.
    When content is unchanged, returns status='unchanged' synchronously.
    """
    try:
        raw_text, is_markdown = _fetch_url(url)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch '{url}': {exc}") from exc

    checksum = _sha256(raw_text)
    existing = get_source(framework, url)
    if existing and existing["checksum"] == checksum:
        return {
            "status": "unchanged",
            "framework": framework,
            "url": url,
            "checksum": checksum,
            "chunk_count": existing["chunk_count"],
            "ingested_at": existing["ingested_at"],
            "job_id": None,
        }

    clean_text = raw_text if is_markdown else _clean_html(raw_text)
    if not clean_text.strip():
        raise ValueError(f"No extractable text content found at '{url}'.")

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=200, length_function=len
    ).split_text(clean_text)
    if not chunks:
        raise ValueError(f"Text splitter produced zero chunks for '{url}'.")
    chunks = chunks[:50]  # cap per source to keep embedding time predictable

    # Deterministic job ID so the same (framework, url, checksum) never starts twice
    job_id = _sha256(f"{framework}:{url}:{checksum}")[:16]
    existing_job = _JOBS.get(job_id, {})
    _job_timed_out = (
        existing_job.get("status") == "indexing"
        and time.monotonic() - existing_job.get("started_at", 0) > 300
    )
    if job_id not in _JOBS or existing_job.get("status") == "error" or _job_timed_out:
        _JOBS[job_id] = {
            "status": "indexing",
            "framework": framework,
            "url": url,
            "checksum": checksum,
            "chunk_count": len(chunks),
            "ingested_at": "",
            "job_id": job_id,
            "started_at": time.monotonic(),
        }
        threading.Thread(
            target=_embed_and_save,
            args=(job_id, framework, url, chunks, checksum, existing),
            daemon=True,
        ).start()

    return {k: v for k, v in _JOBS[job_id].items() if k != "started_at"}


def get_ingest_status(job_id: str) -> dict:
    """Return the current state of a background ingest job."""
    if job_id not in _JOBS:
        raise KeyError(f"No job with id '{job_id}'")
    return {k: v for k, v in _JOBS[job_id].items() if k != "started_at"}
