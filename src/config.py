import os

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NexusSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(_BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    TAVILY_API_KEY: str = ""

    EMBEDDING_SOURCE: str = "LOCAL"
    HUGGINGFACE_MODEL: str = "all-MiniLM-L6-v2"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "nomic-embed-text"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    LLM_PROVIDER: str = "OLLAMA"
    LLM_MODEL: str = "llama3"
    GROQ_API_KEY: str = ""

    NEXUS_STORAGE_PATH: str = os.path.join(_BASE_DIR, "data", "indices")
    SQLITE_DB_PATH: str = os.path.join(_BASE_DIR, "data", "nexus.db")

    NEXUS_SIMILARITY_THRESHOLD: float = 0.7


settings = NexusSettings()
