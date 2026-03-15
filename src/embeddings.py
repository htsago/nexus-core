from __future__ import annotations

from src.config import settings


def get_embeddings():
    source = settings.EMBEDDING_SOURCE.strip().upper()

    if source == "LOCAL":
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=settings.HUGGINGFACE_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

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
            )
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(base_url=base_url, model=model)

    if source == "OPENAI":
        if not settings.OPENAI_API_KEY:
            raise ValueError("EMBEDDING_SOURCE=OPENAI requires OPENAI_API_KEY.")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_EMBEDDING_MODEL,
        )

    raise ValueError(
        f"Unknown EMBEDDING_SOURCE '{settings.EMBEDDING_SOURCE}'. Valid: LOCAL, OLLAMA, OPENAI"
    )
