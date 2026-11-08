from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_mode: Literal["production", "dev-mock"] = "production"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://mi:mi@localhost:5433/meeting_intel"
    database_url_test: str = "postgresql+psycopg://mi:mi@localhost:5433/meeting_intel_test"

    aws_region: str = "ap-south-1"
    s3_bucket: str = Field(min_length=3)
    s3_prefixes: str = "avoma/"
    metadata_dir: str = "/data/metadata"

    bedrock_embed_model: str = "amazon.titan-embed-text-v2:0"
    embed_dim: int = 512
    embed_concurrency: int = 32
    bedrock_chat_model: str = "zai.glm-5"
    semantic_max_distance: float = 0.6

    jwt_secret: str = Field(min_length=16)
    jwt_ttl_min: int = 720
    cookie_secure: bool = False
    admin_email: str | None = None
    admin_password: str | None = None

    presign_ttl_sec: int = 900

    @property
    def s3_prefix_list(self) -> list[str]:
        return [p.strip() for p in self.s3_prefixes.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
