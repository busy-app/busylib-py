from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_extra_types.color import Color


class StrEnum(str, Enum):
    """Enum that serializes to its value."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class WifiState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"


class WifiSecurityMethod(StrEnum):
    OPEN = "Open"
    WPA = "WPA"
    WPA2 = "WPA2"
    WEP = "WEP"
    WPA_WPA2 = "WPA/WPA2"
    WPA3 = "WPA3"
    WPA2_WPA3 = "WPA2/WPA3"


class WifiIpMethod(StrEnum):
    DHCP = "dhcp"
    STATIC = "static"


class WifiIpType(StrEnum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class PowerState(StrEnum):
    DISCHARGING = "discharging"
    CHARGING = "charging"
    CHARGED = "charged"


class ElementType(StrEnum):
    FILE = "file"
    DIR = "dir"


class DisplayElementType(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class DisplayName(StrEnum):
    FRONT = "front"
    BACK = "back"


class InputKey(StrEnum):
    UP = "up"
    DOWN = "down"
    OK = "ok"
    BACK = "back"
    START = "start"
    BUSY = "busy"
    STATUS = "status"
    OFF = "off"
    APPS = "apps"
    SETTINGS = "settings"


class SuccessResponse(BaseModel):
    result: str

    model_config = ConfigDict(extra="ignore")


class VersionInfo(BaseModel):
    api_semver: str | None = None
    version: str | None = None
    branch: str | None = None
    build_date: datetime | None = None
    commit_hash: str | None = None

    model_config = ConfigDict(extra="ignore")


class StatusSystem(BaseModel):
    version: str | None = None
    uptime: str | None = None
    branch: str | None = None
    build_date: datetime | None = None
    commit_hash: str | None = None

    model_config = ConfigDict(extra="ignore")


class StatusPower(BaseModel):
    state: PowerState | None = None
    battery_charge: int | None = Field(default=None, ge=0, le=100)
    battery_voltage: int | None = None
    battery_current: int | None = None
    usb_voltage: int | None = None

    model_config = ConfigDict(extra="ignore")


class Status(BaseModel):
    system: StatusSystem | None = None
    power: StatusPower | None = None

    model_config = ConfigDict(extra="ignore")


class StorageFileElement(BaseModel):
    type: Literal["file"] = "file"
    name: str
    size: int = Field(ge=0)

    model_config = ConfigDict(extra="ignore")


class StorageDirElement(BaseModel):
    type: Literal["dir"] = "dir"
    name: str

    model_config = ConfigDict(extra="ignore")


StorageListElement = StorageFileElement | StorageDirElement


class StorageList(BaseModel):
    list: list[StorageListElement]

    model_config = ConfigDict(extra="ignore")


class DisplayElementBase(BaseModel):
    id: str
    timeout: int | None = Field(default=None, gt=0)
    display: DisplayName | None = DisplayName.FRONT

    model_config = ConfigDict(extra="allow")


class TextElement(DisplayElementBase):
    type: Literal["text"] = "text"
    x: int
    y: int
    text: str
    font: str = "default"
    align: (
        Literal[
            "top_left",
            "top_mid",
            "top_right",
            "mid_left",
            "center",
            "mid_right",
            "bottom_left",
            "bottom_mid",
            "bottom_right",
        ]
        | None
    ) = None
    color: str | None = None
    width: int | None = Field(default=None, gt=0)
    scroll_rate: int | None = Field(default=None, gt=0)

    @field_validator("color", mode="before")
    @classmethod
    def _normalize_color(cls, value: str | Sequence[int | float] | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, (list, tuple)):
            if len(value) not in (3, 4):
                raise ValueError("Color tuple/list must have 3 (RGB) or 4 (RGBA) elements")

            def to_channel(component: int | float) -> int:
                # Accept 0-1 floats or 0-255 ints
                if isinstance(component, float):
                    scaled = component * 255 if component <= 1 else component
                    return int(round(scaled))
                return int(component)

            r, g, b = [max(0, min(255, to_channel(c))) for c in value[:3]]
            alpha_component = value[3] if len(value) == 4 else 255
            alpha = max(0, min(255, to_channel(alpha_component)))
            return f"#{r:02X}{g:02X}{b:02X}{alpha:02X}"

        col = Color(value)
        try:
            hex_value = col.as_hex(include_alpha=True).upper()
        except TypeError:
            hex_value = col.as_hex().upper()
        if len(hex_value) == 9:  # #RRGGBBAA
            return hex_value
        if len(hex_value) == 7:  # #RRGGBB, append opaque alpha
            return f"{hex_value}FF"

        r, g, b = col.as_rgb_tuple()
        return f"#{r:02X}{g:02X}{b:02X}FF"


class ImageElement(DisplayElementBase):
    type: Literal["image"] = "image"
    x: int
    y: int
    path: str


DisplayElement = TextElement | ImageElement


class DisplayElements(BaseModel):
    app_id: str = Field(min_length=1)
    elements: list[DisplayElement]

    model_config = ConfigDict(extra="ignore")


class DisplayBrightnessInfo(BaseModel):
    front: str | None = None
    back: str | None = None

    model_config = ConfigDict(extra="ignore")


BrightnessValue = Annotated[int, Field(ge=0, le=100)] | Literal["auto"]


class DisplayBrightnessUpdate(BaseModel):
    front: BrightnessValue | None = None
    back: BrightnessValue | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("front", "back")
    @classmethod
    def _normalize_brightness(cls, value: BrightnessValue | None) -> BrightnessValue | None:
        if isinstance(value, str) and value != "auto":
            raise ValueError("Brightness string value must be 'auto'")
        return value


class AudioVolumeInfo(BaseModel):
    volume: float | None = Field(default=None, ge=0, le=100)

    model_config = ConfigDict(extra="ignore")


class AudioVolumeUpdate(BaseModel):
    volume: float = Field(ge=0, le=100)

    model_config = ConfigDict(extra="forbid")


class WifiIpConfig(BaseModel):
    ip_method: WifiIpMethod | None = None
    ip_type: WifiIpType | None = None
    address: str | None = None
    mask: str | None = None
    gateway: str | None = None

    model_config = ConfigDict(extra="ignore")


class Network(BaseModel):
    ssid: str | None = None
    security: WifiSecurityMethod | None = None
    rssi: int | None = None

    model_config = ConfigDict(extra="ignore")


class StatusResponse(BaseModel):
    state: WifiState | None = None
    ssid: str | None = None
    bssid: str | None = None
    channel: int | None = None
    rssi: int | None = None
    security: WifiSecurityMethod | None = None
    ip_config: WifiIpConfig | None = None

    model_config = ConfigDict(extra="ignore")


class ConnectRequestConfig(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: str | None = Field(default=None, max_length=64)
    security: WifiSecurityMethod | None = None
    ip_config: WifiIpConfig | None = None

    model_config = ConfigDict(extra="forbid")


class NetworkResponse(BaseModel):
    count: int | None = None
    networks: list[Network] | None = None

    model_config = ConfigDict(extra="ignore")


class ScreenResponse(BaseModel):
    data: str

    model_config = ConfigDict(extra="ignore")


class BleStatus(BaseModel):
    state: str

    model_config = ConfigDict(extra="ignore")
