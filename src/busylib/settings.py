from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The device serves its API under /api; the cloud serves the same endpoints
# under /busybar and has no /api at all, so the prefix is swapped rather than
# appended when a client runs in cloud mode.
DEVICE_API_PREFIX = "/api"
CLOUD_API_PREFIX = "/busybar"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSYLIB_")

    base_url: str = Field(
        # An explicit validation_alias bypasses env_prefix entirely, so the
        # documented BUSYLIB_* names were silently ignored and only the bare
        # ones worked. Both are accepted now, prefixed first.
        validation_alias=AliasChoices("BUSYLIB_URL", "URL"),
        default="http://10.0.4.20",
    )
    cloud_base_url: str = Field(
        validation_alias=AliasChoices("BUSYLIB_CLOUD_URL", "CLOUD_URL"),
        default="https://api.busy.app",
    )


settings = Settings()
