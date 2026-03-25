from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    TESTING: bool = False

    # Spending caps (USD)
    DAILY_HARD_CAP_ADS: float = 100.0
    DAILY_HARD_CAP_APIS: float = 50.0
    WEEKLY_SOFT_CAP_TOTAL: float = 500.0
    MONTHLY_HARD_CEILING: float = 2000.0

    # Agent heartbeat timeout (seconds)
    AGENT_HEARTBEAT_TIMEOUT: int = 120

    ANTHROPIC_API_KEY: str = ""

    # Model selection
    LLM_MODEL_SMART: str = "claude-sonnet-4-6"
    LLM_MODEL_FAST: str = "claude-haiku-4-5-20251001"

def get_settings() -> Settings:
    return Settings()
