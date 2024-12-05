from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from sechat import Server


class WebhookSettings(BaseModel):
    host: str
    port: int
    secret: str


class GitHubSettings(BaseModel):
    app_id: int
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

    webhook: WebhookSettings
    github: GitHubSettings
    chat: ChatSettings
