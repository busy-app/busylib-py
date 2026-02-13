from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Sequence

from pydantic import (
    BaseModel as PydanticBaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)
from pydantic_extra_types.color import Color

from . import exceptions


class BaseModel(PydanticBaseModel):
    """
    Base response model with domain-level validation error wrapping.

    Any pydantic validation failure is converted into a BusyBar-specific
    exception so callers can rely on a stable error hierarchy.
    """

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
        extra: Any | None = None,
    ) -> Any:
        """
        Validate input object and convert schema errors to domain exceptions.
        """
        try:
            return super().model_validate(
                obj,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
                extra=extra,
            )
        except ValidationError as exc:
            raise exceptions.BusyBarResponseValidationError(
                model=cls.__name__,
                details=str(exc),
                original=exc,
            ) from exc


class StrEnum(str, Enum):
    """
    Enum that serializes to its value.

    This keeps JSON payloads aligned with API strings.
    """

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
    CUSTOM = "custom"
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


class DeviceNameResponse(BaseModel):
    name: str | None = None
    device: str | None = None
    value: str | None = None

    model_config = ConfigDict(extra="ignore")


class DeviceNameUpdate(BaseModel):
    name: str = Field(min_length=1)

    model_config = ConfigDict(extra="ignore")


class DeviceTimeResponse(BaseModel):
    timestamp: str | None = None

    model_config = ConfigDict(extra="ignore")


HttpAccessMode = Literal["disabled", "enabled", "key"]


class HttpAccessInfo(BaseModel):
    mode: HttpAccessMode | None = None
    key_valid: bool | None = None

    model_config = ConfigDict(extra="ignore")


class TimestampInfo(BaseModel):
    timestamp: str

    model_config = ConfigDict(extra="ignore")


class BusySnapshotNotStarted(BaseModel):
    type: Literal["NOT_STARTED"]

    model_config = ConfigDict(extra="ignore")


class BusySnapshotInfinite(BaseModel):
    type: Literal["INFINITE"]
    card_id: str
    is_paused: bool

    model_config = ConfigDict(extra="ignore")


class BusySnapshotSimple(BaseModel):
    type: Literal["SIMPLE"]
    card_id: str
    time_left_ms: int
    is_paused: bool

    model_config = ConfigDict(extra="ignore")


class BusySnapshotIntervalSettings(BaseModel):
    type: Literal["INTERVAL"]
    interval_work_ms: int
    interval_rest_ms: int
    interval_work_cycles_count: int
    is_autostart_enabled: bool

    model_config = ConfigDict(extra="ignore")


class BusySnapshotInterval(BaseModel):
    type: Literal["INTERVAL"]
    card_id: str
    current_interval: int
    current_interval_time_total_ms: int
    current_interval_time_left_ms: int
    is_paused: bool
    interval_settings: BusySnapshotIntervalSettings

    model_config = ConfigDict(extra="ignore")


BusySnapshotVariant = Annotated[
    BusySnapshotNotStarted
    | BusySnapshotInfinite
    | BusySnapshotSimple
    | BusySnapshotInterval,
    Field(discriminator="type"),
]


class BusySnapshot(BaseModel):
    snapshot: BusySnapshotVariant
    snapshot_timestamp_ms: int

    model_config = ConfigDict(extra="ignore")


class AccountInfo(BaseModel):
    linked: bool | None = None
    id: str | None = None
    email: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="ignore")


class AccountState(BaseModel):
    state: Literal["error", "disconnected", "connected"] | None = None

    model_config = ConfigDict(extra="ignore")


class AccountProfile(BaseModel):
    state: Literal["dev", "prod", "local", "custom"] | None = None
    custom_url: str | None = None

    model_config = ConfigDict(extra="ignore")


class AccountLink(BaseModel):
    code: str | None = None
    expires_at: int | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateInstallDownload(BaseModel):
    speed_bytes_per_sec: int | None = None
    received_bytes: int | None = None
    total_bytes: int | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateInstallStatus(BaseModel):
    is_allowed: bool | None = None
    event: (
        Literal[
            "session_start",
            "session_stop",
            "action_begin",
            "action_done",
            "detail_change",
            "action_progress",
            "none",
        ]
        | None
    ) = None
    action: (
        Literal[
            "download",
            "sha_verification",
            "unpack",
            "prepare",
            "apply",
            "none",
        ]
        | None
    ) = None
    status: (
        Literal[
            "ok",
            "battery_low",
            "busy",
            "download_failure",
            "download_abort",
            "sha_mismatch",
            "unpack_staging_dir_failure",
            "unpack_archive_open_failure",
            "unpack_archive_unpack_failure",
            "install_manifest_not_found",
            "install_manifest_invalid",
            "install_session_config_failure",
            "install_pointer_setup_failure",
            "unknown_failure",
        ]
        | None
    ) = None
    detail: str | None = None
    download: UpdateInstallDownload | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateCheckStatus(BaseModel):
    available_version: str | None = None
    event: Literal["start", "stop", "none"] | None = None
    result: Literal["available", "not_available", "failure", "none"] | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateStatus(BaseModel):
    install: UpdateInstallStatus | None = None
    check: UpdateCheckStatus | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateChangelogResponse(BaseModel):
    changelog: str | None = None

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


class StorageStatus(BaseModel):
    total: int | None = Field(default=None, alias="total_bytes")
    used: int | None = Field(default=None, alias="used_bytes")
    free: int | None = Field(default=None, alias="free_bytes")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


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
    font: Literal["small", "medium", "medium_condensed", "big"] | None = None
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
    color: str | Sequence[int | float] | None = None
    width: int | None = Field(default=None, gt=0)
    scroll_rate: int | None = Field(default=None, gt=0)

    @field_validator("color", mode="before")
    @classmethod
    def _normalize_color(cls, value: str | Sequence[int | float] | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, (list, tuple)):
            if len(value) not in (3, 4):
                raise ValueError(
                    "Color tuple/list must have 3 (RGB) or 4 (RGBA) elements"
                )

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

        if not isinstance(value, str):
            raise ValueError("Color must be a string or RGB/RGBA tuple")

        col = Color(value)
        hex_value = col.as_hex().upper()
        if len(hex_value) == 9:  # #RRGGBBAA
            return hex_value
        if len(hex_value) == 7:  # #RRGGBB, append opaque alpha
            return f"{hex_value}FF"

        rgb = col.as_rgb_tuple()
        r, g, b = rgb[0], rgb[1], rgb[2]
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
    def _normalize_brightness(
        cls, value: BrightnessValue | None
    ) -> BrightnessValue | None:
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
