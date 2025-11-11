import dataclasses
import enum
import typing as tp

class WifiState(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"

class WifiSecurityMethod(enum.Enum):
    OPEN = "Open"
    WPA = "WPA"
    WPA2 = "WPA2"
    WEP = "WEP"
    WPA_WPA2 = "WPA/WPA2"
    WPA3 = "WPA3"
    WPA2_WPA3 = "WPA2/WPA3"


class WifiIpMethod(enum.Enum):
    DHCP = "dhcp"
    STATIC = "static"


class WifiIpType(enum.Enum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class PowerState(enum.Enum):
    DISCHARGING = "discharging"
    CHARGING = "charging"
    CHARGED = "charged"


class ElementType(enum.Enum):
    FILE = "file"
    DIR = "dir"


class DisplayElementType(enum.Enum):
    TEXT = "text"
    IMAGE = "image"


class DisplayName(enum.Enum):
    FRONT = "front"
    BACK = "back"


class InputKey(enum.Enum):
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

@dataclasses.dataclass(frozen=True)
class SuccessResponse:
    result: str


@dataclasses.dataclass(frozen=True)
class Error:
    error: str
    code: int | None = None


@dataclasses.dataclass(frozen=True)
class VersionInfo:
    api_semver: str


@dataclasses.dataclass(frozen=True)
class StatusSystem:
    version: str | None = None
    uptime: str | None = None


@dataclasses.dataclass(frozen=True)
class StatusPower:
    state: PowerState | None = None
    battery_charge: int | None = None
    battery_voltage: int | None = None
    battery_current: int | None = None
    usb_voltage: int | None = None


@dataclasses.dataclass(frozen=True)
class Status:
    system: StatusSystem | None = None
    power: StatusPower | None = None


@dataclasses.dataclass(frozen=True)
class StorageFileElement:
    type: tp.Literal["file"]
    name: str
    size: int


@dataclasses.dataclass(frozen=True)
class StorageDirElement:
    type: tp.Literal["dir"]
    name: str


StorageListElement = StorageFileElement | StorageDirElement


@dataclasses.dataclass(frozen=True)
class StorageList:
    list: list[StorageListElement]


@dataclasses.dataclass(frozen=True)
class TextElement:
    id: str
    type: tp.Literal["text"]
    x: int
    y: int
    text: str
    timeout: int | None = None
    display: DisplayName | None = DisplayName.FRONT


@dataclasses.dataclass(frozen=True)
class ImageElement:
    id: str
    type: tp.Literal["image"]
    x: int
    y: int
    path: str
    timeout: int | None = None
    display: DisplayName | None = DisplayName.FRONT


DisplayElement = TextElement | ImageElement


@dataclasses.dataclass(frozen=True)
class DisplayElements:
    app_id: str
    elements: list[DisplayElement]


@dataclasses.dataclass(frozen=True)
class DisplayBrightnessInfo:
    front: str | None = None
    back: str | None = None


@dataclasses.dataclass(frozen=True)
class AudioVolumeInfo:
    volume: float | None = None


@dataclasses.dataclass(frozen=True)
class WifiIpConfig:
    ip_method: WifiIpMethod | None = None
    ip_type: WifiIpType | None = None
    address: str | None = None
    mask: str | None = None
    gateway: str | None = None


@dataclasses.dataclass(frozen=True)
class Network:
    ssid: str | None = None
    security: WifiSecurityMethod | None = None
    rssi: int | None = None


@dataclasses.dataclass(frozen=True)
class StatusResponse:
    state: WifiState | None = None
    ssid: str | None = None
    bssid: str | None = None
    channel: int | None = None
    rssi: int | None = None
    security: WifiSecurityMethod | None = None
    ip_config: WifiIpConfig | None = None


@dataclasses.dataclass(frozen=True)
class ConnectRequestConfig:
    ssid: str | None = None
    password: str | None = None
    security: WifiSecurityMethod | None = None
    ip_config: WifiIpConfig | None = None


@dataclasses.dataclass(frozen=True)
class NetworkResponse:
    count: int | None = None
    networks: list[Network] | None = None


@dataclasses.dataclass(frozen=True)
class ScreenResponse:
    data: str  # base64 encoded image data

@dataclasses.dataclass(frozen=True)
class BleStatus:
    state: str
