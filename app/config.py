from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://docket:docket@localhost:5432/docket"
    database_url_sync: str = "postgresql+psycopg://docket:docket@localhost:5432/docket"
    test_database_url: str = "postgresql+asyncpg://docket:docket@localhost:5432/docket_test"
    test_database_url_sync: str = "postgresql+psycopg://docket:docket@localhost:5432/docket_test"


settings = Settings()
