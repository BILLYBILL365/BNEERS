from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"

    # Spending caps (USD)
    DAILY_HARD_CAP_ADS: float = 100.0
    DAILY_HARD_CAP_APIS: float = 50.0
    WEEKLY_SOFT_CAP_TOTAL: float = 500.0
    MONTHLY_HARD_CEILING: float = 2000.0

    # Agent heartbeat timeout (seconds)
    AGENT_HEARTBEAT_TIMEOUT: int = 120

def get_settings() -> Settings:
    return Settings()
