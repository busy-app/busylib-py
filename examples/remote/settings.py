from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from examples.remote.constants import ICON_SETS


class RemoteSettings(BaseSettings):
    """
    Settings for the remote CLI and renderer.
    """

    model_config = SettingsConfigDict(env_prefix="BUSYBAR_REMOTE_")

    app_id: str = Field(default="remote")
    icon_mode: str = Field(default="nerd")
    spacer: str = Field(default=" ")
    pixel_char: str = Field(default=ICON_SETS["nerd"]["pixel"])
    black_pixels_transparent: bool = Field(default=False)
    frame_mode: Literal["full", "horizontal", "none"] = Field(default="horizontal")
    frame_char: str = Field(default="·")
    key_timeout: float = Field(default=0.1)
    frame_sleep: float = Field(default=0.1)


settings = RemoteSettings()
