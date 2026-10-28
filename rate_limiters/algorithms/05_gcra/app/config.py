from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    rl_debug: str = "1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
