from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    rl_debug: str = "1"
    rl_limit: int = 5
    rl_period_seconds: int = 10
    rl_burst: int = 5
    rl_trusted_proxy_count: int = 1
    rl_fail_mode: str = "open"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
