from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    rl_debug: str = "1"
    rl_sec_limit: int = 5
    rl_sec_period: int = 1
    rl_sec_burst: int = 5
    rl_hour_limit: int = 10
    rl_hour_period: int = 3600
    rl_hour_burst: int = 10
    rl_fail_mode: str = "open"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
