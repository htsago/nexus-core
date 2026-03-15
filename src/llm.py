from __future__ import annotations

from src.config import settings


def get_llm():
    provider = settings.LLM_PROVIDER.strip().upper()

    if provider == "OLLAMA":
        from langchain_ollama import OllamaLLM

        return OllamaLLM(
            base_url=settings.OLLAMA_BASE_URL, model=settings.LLM_MODEL, temperature=0
        )

    if provider == "OPENAI":
        if not settings.OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER=OPENAI requires OPENAI_API_KEY.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=settings.OPENAI_API_KEY, model=settings.LLM_MODEL, temperature=0
        )

    if provider == "GROQ":
        if not settings.GROQ_API_KEY:
            raise ValueError("LLM_PROVIDER=GROQ requires GROQ_API_KEY.")
        from langchain_groq import ChatGroq

        return ChatGroq(
            api_key=settings.GROQ_API_KEY, model=settings.LLM_MODEL, temperature=0
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Valid: OLLAMA, OPENAI, GROQ"
    )
