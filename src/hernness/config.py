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

    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    api_token: SecretStr | None = Field(default=None, validation_alias="HERNESS_API_TOKEN")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias="HERNESS_CORS_ORIGINS",
    )
    database_path: Path = Field(
        default=Path("data/herness.sqlite3"),
        validation_alias="HERNESS_DATABASE_PATH",
    )
    maker_model: str = Field(default="gpt-4o", validation_alias="HERNESS_MAKER_MODEL")
    checker_model: str = Field(default="o3-mini", validation_alias="HERNESS_CHECKER_MODEL")
    sandbox_image: str = Field(
        default="hernness-sandbox:py311",
        validation_alias="HERNESS_SANDBOX_IMAGE",
    )
    sandbox_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias="HERNESS_SANDBOX_TIMEOUT_SECONDS",
    )
    max_iterations: int = Field(default=4, ge=1, le=10, validation_alias="HERNESS_MAX_ITERATIONS")

    def validate_openai_credentials(self) -> None:
        if self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY must be configured.")

    def validate_api_credentials(self) -> None:
        if self.api_token is None or not self.api_token.get_secret_value().strip():
            raise ValueError("HERNESS_API_TOKEN must be configured before starting the API.")

    def validate_credentials(self) -> None:
        self.validate_openai_credentials()
        self.validate_api_credentials()
