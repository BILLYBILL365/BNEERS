from app.config import Settings

def test_settings_load_defaults():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379",
        SECRET_KEY="test-secret",
    )
    assert s.DAILY_HARD_CAP_ADS == 100
    assert s.DAILY_HARD_CAP_APIS == 50
    assert s.WEEKLY_SOFT_CAP_TOTAL == 500
    assert s.MONTHLY_HARD_CEILING == 2000
    assert s.ENVIRONMENT == "development"

def test_settings_spending_caps_configurable():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379",
        SECRET_KEY="test-secret",
        DAILY_HARD_CAP_ADS=200,
    )
    assert s.DAILY_HARD_CAP_ADS == 200
