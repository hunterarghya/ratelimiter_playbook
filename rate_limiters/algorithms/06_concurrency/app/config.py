from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    rl_debug: str = "1"
    rl_limit: int = 2
    rl_lease_ttl_seconds: int = 30
    rl_fail_mode: str = "open"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
