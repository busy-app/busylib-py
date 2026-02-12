from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RemoteSettings(BaseSettings):
    """
    Settings for the remote CLI and renderer.
    """

    model_config = SettingsConfigDict(env_prefix="BUSYBAR_REMOTE_")

    app_id: str = Field(default="remote")
    icon_mode: str = Field(default="text")
    spacer: str = Field(default=" ")
    pixel_char: str | None = Field(default=None)
    black_pixel_mode: Literal["transparent", "space_bg"] = Field(
        default="space_bg",
    )
    invert_colors: bool = Field(default=False)
    audio_cache_dir: str | None = Field(default=None)
    audio_cache_ttl_days: float | None = Field(default=7.0)
    audio_upload_timeout_seconds: float | None = Field(default=None)
    audio_play_timeout_seconds: float | None = Field(default=None)
    background_mode: Literal["none", "match"] = Field(default="none")
    frame_mode: Literal["full", "horizontal", "none"] = Field(default="horizontal")
    frame_char: str = Field(default="·")
    key_timeout: float = Field(default=0.1)
    frame_sleep: float = Field(default=0.1)


settings = RemoteSettings()
