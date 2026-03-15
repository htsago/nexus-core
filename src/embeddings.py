from __future__ import annotations

from src.config import settings


def get_embeddings():
    source = settings.EMBEDDING_SOURCE.strip().upper()

    if source == "OLLAMA":
        base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        model = settings.OLLAMA_EMBEDDING_MODEL
        if "/v1" in base_url:
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                openai_api_base=base_url,
                openai_api_key="ollama",
                model=model,
                check_embedding_ctx_length=False,
                timeout=60,
            )
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(base_url=base_url, model=model, timeout=60.0)

    if source == "OPENAI":
        if not settings.OPENAI_API_KEY:
            raise ValueError("EMBEDDING_SOURCE=OPENAI requires OPENAI_API_KEY.")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_EMBEDDING_MODEL,
            chunk_size=256,
            timeout=60,
        )

    raise ValueError(
        f"Unknown EMBEDDING_SOURCE '{settings.EMBEDDING_SOURCE}'. Valid: OLLAMA, OPENAI"
    )
