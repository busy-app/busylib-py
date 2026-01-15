from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSYLIB_")

    base_url: str = Field(
        validation_alias="URL",
        default="http://10.0.4.20",
    )
    cloud_base_url: str = Field(
        validation_alias="CLOUD_URL",
        default="https://proxy.dev.busy.app",
    )


settings = Settings()
