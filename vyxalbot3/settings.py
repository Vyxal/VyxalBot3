from typing import Type
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from sechat import Server


class WebhookSettings(BaseModel):
    host: str
    port: int
    secret: str


class GitHubSettings(BaseModel):
    app_id: int
    account: str
    private_key: str


class ChatSettings(BaseModel):
    email: str
    password: str
    server: Server
    room: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_nested_delimiter="__"
    )

    database_url: str
    webhook: WebhookSettings
    github: GitHubSettings
    chat: ChatSettings


class RepositoryProduction(BaseModel):
    base: str
    head: str


class ProductionConfiguration(BaseModel):
    default_repository: str | None = None
    repositories: dict[str, RepositoryProduction] = {}


class SupplementaryConfiguration(BaseSettings):
    model_config = SettingsConfigDict(toml_file="supplementary.toml")

    production: ProductionConfiguration = ProductionConfiguration()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (TomlConfigSettingsSource(settings_cls),)
