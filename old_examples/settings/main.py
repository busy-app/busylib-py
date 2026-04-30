import logging

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
sh = logging.StreamHandler()
logger.addHandler(sh)


class BusySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BUSY_", extra="ignore")

    address: AnyHttpUrl
    timeout: int = 1
    token: str | None = None
    app_id: str = "busylib-demo"


busy_settings = BusySettings()

logger.info("Busy settings: %s", busy_settings.model_dump_json(ensure_ascii=False))
