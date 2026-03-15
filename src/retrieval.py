from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_community.vectorstores import FAISS

from src.config import settings
from src.db import fts_search
from src.embeddings import get_embeddings
from src.models import COMPLIANCE_PROMPT


def _load_faiss(framework: str) -> FAISS:
    faiss_dir = Path(settings.NEXUS_STORAGE_PATH) / framework
    if not faiss_dir.exists():
        raise ValueError(
            f"No FAISS index for '{framework}'. Run nexus_ingest_and_clean first."
        )
    return FAISS.load_local(
        str(faiss_dir), get_embeddings(), allow_dangerous_deserialization=True
    )


def semantic_query(framework: str, query: str, k: int = 5) -> list[dict[str, Any]]:
    """FAISS similarity search, threshold-filtered."""
    index = _load_faiss(framework)
    threshold = settings.NEXUS_SIMILARITY_THRESHOLD
    pairs = index.similarity_search_with_relevance_scores(query, k=k)
    results = [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "similarity_score": round(float(s), 4),
        }
        for doc, s in pairs
        if float(s) >= threshold
    ]
    if not results:
        return [{"message": f"No results above threshold {threshold} for '{query}'", "results": []}]
    return results


def hybrid_lookup(framework: str, query: str, k: int = 5) -> dict[str, Any]:
    """Merge FAISS semantic and FTS5 keyword results, deduplicated."""
    try:
        semantic = semantic_query(framework, query, k)
        if len(semantic) == 1 and "message" in semantic[0] and not semantic[0].get("content"):
            semantic = []
    except ValueError:
        raise

    keyword = [
        {
            "content": r["content"],
            "metadata": {
                "framework": r["framework"],
                "url": r["url"],
                "chunk_id": r["chunk_id"],
            },
            "match_type": "keyword",
        }
        for r in fts_search(framework, query, k)
    ]

    seen: set[str] = set()
    combined: list[dict] = []
    for r in semantic:
        c = r.get("content", "")
        if c and c not in seen:
            seen.add(c)
            r["match_type"] = "semantic"
            combined.append(r)
    for r in keyword:
        c = r.get("content", "")
        if c and c not in seen:
            seen.add(c)
            combined.append(r)

    return {"framework": framework, "query": query, "results": combined, "total": len(combined)}


def verify_compliance(framework: str, code_snippet: str) -> dict[str, Any]:
    """RetrievalQA compliance check; never speculates beyond the index."""
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import PromptTemplate

    from src.llm import get_llm

    index = _load_faiss(framework)
    retriever = index.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 6, "score_threshold": settings.NEXUS_SIMILARITY_THRESHOLD},
    )
    source_docs = retriever.invoke(code_snippet)

    if not source_docs:
        return {
            "framework": framework,
            "verification_result": (
                "VERDICT: INSUFFICIENT_DOCUMENTATION\n\nISSUES:\n"
                "- No documentation chunks above the similarity threshold were found.\n\n"
                "CORRECT_USAGE:\n- Run nexus_ingest_and_clean to index more documentation pages."
            ),
            "sources_consulted": [],
            "source_count": 0,
        }

    context = "\n\n".join(d.page_content for d in source_docs)
    source_urls = list({d.metadata.get("url", "unknown") for d in source_docs})

    chain = (
        PromptTemplate(template=COMPLIANCE_PROMPT, input_variables=["context", "question"])
        | get_llm()
        | StrOutputParser()
    )
    result_text = chain.invoke({"context": context, "question": code_snippet})

    return {
        "framework": framework,
        "verification_result": result_text,
        "sources_consulted": source_urls,
        "source_count": len(source_docs),
    }
