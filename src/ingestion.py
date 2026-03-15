from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

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


def ingest_url(framework: str, url: str) -> dict:
    """Fetch, clean, chunk, and index the content at url for framework."""
    try:
        resp = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "NEXUS-Core/1.0 (deterministic RAG indexer)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch '{url}': {exc}") from exc

    checksum = _sha256(resp.text)
    existing = get_source(framework, url)
    if existing and existing["checksum"] == checksum:
        return {
            "status": "unchanged",
            "framework": framework,
            "url": url,
            "checksum": checksum,
            "chunk_count": existing["chunk_count"],
            "ingested_at": existing["ingested_at"],
        }

    clean_text = _clean_html(resp.text)
    if not clean_text.strip():
        raise ValueError(f"No extractable text content found at '{url}'.")

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=200, length_function=len
    ).split_text(clean_text)
    if not chunks:
        raise ValueError(f"Text splitter produced zero chunks for '{url}'.")

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

    return {
        "status": "ingested",
        "framework": framework,
        "url": url,
        "checksum": checksum,
        "chunk_count": len(chunks),
        "ingested_at": ingested_at,
    }
