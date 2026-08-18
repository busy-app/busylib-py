from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The device serves its API under /api. In the cloud the same endpoints live
# under /busybar and there is no /api, so the prefix is swapped rather than
# appended when a client runs in cloud mode. See `busylib.cloud` for the
# published addresses, including the account API that shares the host.
DEVICE_API_PREFIX = "/api"
CLOUD_API_PREFIX = "/busybar"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUSYLIB_")

    # Spelled out in full rather than left to env_prefix, which would expect
    # BUSYLIB_BASE_URL. Bare URL/CLOUD_URL are deliberately not accepted: they
    # are too broad a name for a library to claim in a shared environment.
    base_url: str = Field(
        validation_alias="BUSYLIB_URL",
        default="http://10.0.4.20",
    )
    cloud_base_url: str = Field(
        validation_alias="BUSYLIB_CLOUD_URL",
        default="https://api.busy.app",
    )


settings = Settings()
