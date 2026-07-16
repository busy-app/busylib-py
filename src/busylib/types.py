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
    model_validator,
)

from . import exceptions
from ._utils import ColorInput, normalize_rgba_color


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
    UNKNOWN = "unknown"
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTING = "disconnecting"
    RECONNECTING = "reconnecting"


class WifiSecurityMethod(StrEnum):
    OPEN = "Open"
    WPA = "WPA"
    WPA2 = "WPA2"
    WEP = "WEP"
    WPA_WPA2 = "WPA/WPA2"
    WPA3 = "WPA3"
    WPA2_WPA3 = "WPA2/WPA3"
    UNSUPPORTED = "Unsupported"


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
    ANIMATION = "animation"
    COUNTDOWN = "countdown"
    RECTANGLE = "rectangle"


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


class InputEventState(StrEnum):
    PRESS = "press"
    RELEASE = "release"


class InputEvent(BaseModel):
    key: InputKey
    state: InputEventState
    timestamp_ms: int | None = None

    model_config = ConfigDict(extra="ignore")


class SuccessResponse(BaseModel):
    result: str

    model_config = ConfigDict(extra="ignore")


class LogDumpResponse(SuccessResponse):
    path: str | None = None

    model_config = ConfigDict(extra="ignore")


class VersionInfo(BaseModel):
    api_semver: str | None = None
    version: str | None = None
    branch: str | None = None
    build_date: datetime | None = None
    commit_hash: str | None = None

    model_config = ConfigDict(extra="ignore")


class StatusDevice(BaseModel):
    serial_number: str | None = None
    usb_mac: str | None = None
    wifi_mac: str | None = None
    ble_mac: str | None = None
    otp_valid: bool | None = None
    otp_model: str | None = None
    otp_timestamp: int | None = None
    firmware_security: str | None = Field(
        default=None,
        description="Firmware security status: secure, insecure, other, or unknown.",
    )

    model_config = ConfigDict(extra="ignore")


class StatusFirmware(BaseModel):
    version: str | None = None
    target: int | None = None
    branch: str | None = None
    build_date: str | None = None
    commit_hash: str | None = None
    intercom_version: str | None = None
    nwp_version: str | None = None
    matter_version: str | None = None

    model_config = ConfigDict(extra="ignore")


class StatusSystem(BaseModel):
    api_semver: str | None = None
    version: str | None = None
    uptime: str | None = None
    branch: str | None = None
    build_date: datetime | None = None
    commit_hash: str | None = None
    boot_time: int | None = None
    auto_update_enabled: bool | None = None

    model_config = ConfigDict(extra="ignore")


class NetworkInterfaceInfo(BaseModel):
    type: str | None = None

    model_config = ConfigDict(extra="ignore")


class StatusPower(BaseModel):
    state: PowerState | None = None
    battery_charge: int | None = Field(default=None, ge=0, le=100)
    battery_voltage: int | None = None
    battery_current: int | None = None
    usb_voltage: int | None = None

    model_config = ConfigDict(extra="ignore")


class Status(BaseModel):
    device: StatusDevice | None = None
    firmware: StatusFirmware | None = None
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


class TimezoneInfo(BaseModel):
    name: str
    offset: str
    abbr: str

    model_config = ConfigDict(extra="ignore")


class TimezoneListResponse(BaseModel):
    list: list[TimezoneInfo]

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


class BusyTimerInfiniteSettings(BaseModel):
    type: Literal["INFINITE"]

    model_config = ConfigDict(extra="ignore")


class BusyTimerSimpleSettings(BaseModel):
    type: Literal["SIMPLE"]
    total_time_ms: int

    model_config = ConfigDict(extra="ignore")


BusyTimerSettings = Annotated[
    BusyTimerInfiniteSettings | BusyTimerSimpleSettings | BusySnapshotIntervalSettings,
    Field(discriminator="type"),
]


class BusyBarSettings(BaseModel):
    theme: str
    show_work_phase_only: bool
    trigger_smart_home: bool

    model_config = ConfigDict(extra="ignore")


class BusyProfile(BaseModel):
    sort_order: int
    title: str
    id: str
    timer_settings: BusyTimerSettings
    busy_bar_settings: BusyBarSettings
    profile_timestamp_ms: int

    model_config = ConfigDict(extra="ignore")


BusyProfileSlot = Literal["busy", "custom"]


class AccountInfo(BaseModel):
    linked: bool | None = None
    id: str | None = None
    email: str | None = None
    user_id: str | None = None

    model_config = ConfigDict(extra="ignore")


class AccountState(BaseModel):
    status: str | None = None
    state: str | None = Field(default=None, exclude=True)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _sync_state_aliases(self) -> "AccountState":
        """
        Keep OpenAPI status authoritative while accepting legacy state input.
        """
        if self.status is None:
            self.status = self.state
        self.state = self.status
        return self


class AccountProfile(BaseModel):
    state: Literal["dev", "prod", "local", "custom"] | None = None
    custom_url: str | None = None

    model_config = ConfigDict(extra="ignore")


class AccountBackend(BaseModel):
    server_url: str
    client_cert_type: str
    ignore_server_cert: bool

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
    event: str | None = None
    action: str | None = None
    status: str | None = None
    detail: str | None = None
    download: UpdateInstallDownload | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateCheckStatus(BaseModel):
    available_version: str | None = None
    event: str | None = None
    status: str | None = None
    result: str | None = Field(default=None, exclude=True)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _sync_result_aliases(self) -> "UpdateCheckStatus":
        """
        Keep OpenAPI status authoritative while accepting legacy result input.
        """
        if self.status is None:
            self.status = self.result
        self.result = self.status
        return self


class UpdateStatus(BaseModel):
    install: UpdateInstallStatus | None = None
    check: UpdateCheckStatus | None = None

    model_config = ConfigDict(extra="ignore")


class UpdateChangelogResponse(BaseModel):
    changelog: str | None = None

    model_config = ConfigDict(extra="ignore")


class AutoupdateSettings(BaseModel):
    is_enabled: bool | None = None
    interval_start: str | None = None
    interval_end: str | None = None

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
DisplayFontName = Literal[
    "tiny",
    "small",
    "normal",
    "condensed",
    "bold",
    "large",
    "extra_large",
    "global",
]


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
    timeout: int | None = Field(default=None, ge=0)
    display_until: str | None = None
    x: int = Field(default=0, ge=-4096, le=4095)
    y: int = Field(default=0, ge=-4096, le=4095)
    display: DisplayName | None = DisplayName.FRONT
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

    model_config = ConfigDict(extra="allow")


class TextElement(DisplayElementBase):
    type: Literal["text"] = "text"
    text: str
    font: DisplayFontName
    color: ColorInput | None = None
    width: int | None = Field(default=None, gt=0)
    scroll_rate: int | None = Field(default=None, ge=0)
    scroll_start_delay: int | None = Field(default=None, ge=0)
    scroll_repeat_delay: int | None = Field(default=None, ge=0)

    @field_validator("color", mode="before")
    @classmethod
    def _normalize_color(cls, value: ColorInput | None) -> str | None:
        return normalize_rgba_color(value)


class ImageElement(DisplayElementBase):
    type: Literal["image"] = "image"
    path: str | None = None
    stock_path: str | None = None
    opacity: int = Field(default=100, ge=0, le=100)


class AnimationElement(DisplayElementBase):
    type: Literal["animation"] = "animation"
    path: str | None = None
    stock_path: str | None = None
    loop: bool = False
    await_previous_end: bool = False
    section: str | None = None
    opacity: int = Field(default=100, ge=0, le=100)


class CountdownElement(DisplayElementBase):
    type: Literal["countdown"] = "countdown"
    timestamp: str
    color: ColorInput | None = None
    direction: Literal["time_left", "time_since"]
    show_hours: Literal["when_non_zero", "always"]

    @field_validator("color", mode="before")
    @classmethod
    def _normalize_color(cls, value: ColorInput | None) -> str | None:
        return normalize_rgba_color(value)


class RectangleElement(DisplayElementBase):
    type: Literal["rectangle"] = "rectangle"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    radius: int = Field(default=0, ge=0)
    fill: Literal["none", "solid", "gradient_h", "gradient_v"] = "none"
    fill_colors: list[ColorInput] = Field(
        default_factory=lambda: ["#FFFFFFFF", "#00000000"],
        min_length=1,
        max_length=2,
    )
    border_width: int = Field(default=1, ge=0)
    border_color: ColorInput = "#FFFFFFFF"

    @field_validator("fill_colors", mode="before")
    @classmethod
    def _normalize_fill_colors(
        cls,
        value: Sequence[ColorInput | None] | None,
    ) -> list[str]:
        """
        Normalize rectangle fill colors while preserving OpenAPI list shape.
        """
        if value is None:
            return ["#FFFFFFFF", "#00000000"]
        if isinstance(value, str):
            raise ValueError("fill_colors must be a list of colors")

        colors: list[str] = []
        for item in value:
            if item is None:
                raise ValueError("fill_colors must not contain null values")
            normalized = normalize_rgba_color(item)
            if normalized is None:
                raise ValueError("fill_colors must not contain null values")
            colors.append(normalized)
        return colors

    @field_validator("border_color", mode="before")
    @classmethod
    def _normalize_border_color(
        cls,
        value: ColorInput | None,
    ) -> str | None:
        return normalize_rgba_color(value)


DisplayElement = Annotated[
    TextElement | ImageElement | AnimationElement | CountdownElement | RectangleElement,
    Field(discriminator="type"),
]


class DisplayElements(BaseModel):
    application_name: str = Field(min_length=1)
    priority: int = Field(default=50, ge=1, le=100)
    led_notification_color: ColorInput | None = None
    elements: list[DisplayElement] = Field(min_length=1)

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("led_notification_color", mode="before")
    @classmethod
    def _normalize_led_color(
        cls,
        value: ColorInput | None,
    ) -> str | None:
        return normalize_rgba_color(value)


class DisplayBrightnessInfo(BaseModel):
    value: str | None = None
    front: str | None = None
    back: str | None = None

    model_config = ConfigDict(extra="ignore")


BrightnessValue = Annotated[int, Field(ge=0, le=100)] | Literal["auto"]


class DisplayBrightnessUpdate(BaseModel):
    value: BrightnessValue

    model_config = ConfigDict(extra="forbid")

    @field_validator("value")
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


class AudioPlayRequest(BaseModel):
    path: str | None = Field(default=None, min_length=1)
    stock_path: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_source(self) -> "AudioPlayRequest":
        """
        Ensure payload references exactly one audio source style.

        Stock resources use `stock_path`; uploaded resources use `path`.
        Application context is supplied by request kwargs in client methods.
        """
        if bool(self.path) == bool(self.stock_path):
            raise ValueError("exactly one of path or stock_path must be provided")

        return self


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
    status: str | None = None
    state: str | None = Field(default=None, exclude=True)
    address: str | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _sync_state_aliases(self) -> "BleStatus":
        """
        Keep OpenAPI status authoritative while accepting legacy state input.
        """
        if self.status is None:
            self.status = self.state
        self.state = self.status
        return self


class SmartHomePairingStatus(BaseModel):
    value: str | None = None
    timestamp: int | None = None

    model_config = ConfigDict(extra="ignore")


class SmartHomePairingInfo(BaseModel):
    fabric_count: int | None = None
    latest_pairing_status: SmartHomePairingStatus | None = None

    model_config = ConfigDict(extra="ignore")


class SmartHomePairingPayload(BaseModel):
    available_until: str | None = None
    qr_code: str | None = None
    manual_code: str | None = None

    model_config = ConfigDict(extra="ignore")


class SmartHomeSwitchState(BaseModel):
    state: bool | None = None
    startup: str | None = None

    model_config = ConfigDict(extra="ignore")
