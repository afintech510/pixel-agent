import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "pixel_agent"
    POSTGRES_USER: str = "pixel_user"
    POSTGRES_PASSWORD: str = "pixel_secret"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-ada-002"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # RAG
    RAG_TOP_K: int = 5
    CONFIDENCE_THRESHOLD: float = 0.7

    # Agent
    AGENT_NAME: str = "Pixel"
    AGENT_ROLE: str = "Display Specialist"

    # Uploads
    UPLOAD_DIR: str = "/uploads"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
