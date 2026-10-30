from functools import lru_cache
import secrets

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./stock_research.db"
    redis_url: str = "redis://localhost:6379/0"
    session_secret: SecretStr = Field(default_factory=lambda: SecretStr(secrets.token_urlsafe(48)))
    deepseek_api_key: SecretStr | None = None
    ifind_mcp_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_research_model: str = "deepseek-v4-pro"
    deepseek_utility_model: str = "deepseek-flash"
    ifind_use_env_proxy: bool = False
    ifind_max_requests_per_second: float = 2.0
    ifind_cache_ttl_seconds: int = 3600
    report_language: str = "zh-CN"

    @model_validator(mode="after")
    def require_production_secret(self):
        if self.is_production:
            secret = self.session_secret.get_secret_value()
            if "session_secret" not in self.model_fields_set or len(secret) < 32 or secret.startswith("change-me"):
                raise ValueError("生产部署必须为 API 和 worker 配置相同的高强度 SESSION_SECRET（至少 32 字符）")
        return self

    @field_validator("ifind_max_requests_per_second")
    @classmethod
    def valid_rate(cls, value: float) -> float:
        if value <= 0 or value > 20:
            raise ValueError("IFIND_MAX_REQUESTS_PER_SECOND 必须在 0 到 20 之间")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def secret_value(self, secret: SecretStr | None) -> str | None:
        return secret.get_secret_value() if secret is not None else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
