from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="vetta", validation_alias="VETTA_APP_NAME")
    environment: str = Field(default="development", validation_alias="VETTA_ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="VETTA_LOG_LEVEL")
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    api_token: SecretStr | None = Field(default=None, validation_alias="VETTA_API_TOKEN")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias="VETTA_CORS_ORIGINS",
    )
    database_path: Path = Field(
        default=Path("data/vetta.sqlite3"),
        validation_alias="VETTA_DATABASE_PATH",
    )
    maker_model: str = Field(default="gpt-4o", validation_alias="VETTA_MAKER_MODEL")
    checker_model: str = Field(default="o3-mini", validation_alias="VETTA_CHECKER_MODEL")
    sandbox_image: str = Field(
        default="vetta-sandbox:py311",
        validation_alias="VETTA_SANDBOX_IMAGE",
    )
    sandbox_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias="VETTA_SANDBOX_TIMEOUT_SECONDS",
    )
    max_iterations: int = Field(default=4, ge=1, le=10, validation_alias="VETTA_MAX_ITERATIONS")
    requests_per_minute: int = Field(
        default=30,
        ge=1,
        le=1000,
        validation_alias="VETTA_REQUESTS_PER_MINUTE",
    )
    trust_proxy: bool = Field(default=False, validation_alias="VETTA_TRUST_PROXY")
    database_url: str | None = Field(default=None, validation_alias="VETTA_DATABASE_URL")
    broker_url: str | None = Field(default=None, validation_alias="VETTA_BROKER_URL")
    result_backend: str | None = Field(default=None, validation_alias="VETTA_RESULT_BACKEND")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )

    def ensure_database_directory(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_openai_credentials(self) -> None:
        if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY must be configured.")

    def validate_api_credentials(self) -> None:
        if self.api_token is None or not self.api_token.get_secret_value().strip():
            raise ValueError("VETTA_API_TOKEN must be configured before starting the API.")

    def validate_credentials(self) -> None:
        self.validate_openai_credentials()
        self.validate_api_credentials()
