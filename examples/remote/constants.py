from __future__ import annotations

ICON_SETS: dict[str, dict[str, str]] = {
    "emoji": {
        "pixel": "⬤",
        "device": "📟",
        "system": "🛠",
        "storage": "💾",
        "time": "⏰",
        "brightness": "💡",
        "volume": "🔊",
        "wifi": "📶",
        "wifi_low": "📶",
        "wifi_mid": "📶",
        "wifi_high": "📶",
        "battery_full": "🔋",
        "battery_low": "🪫",
        "usb_connected": "🔌",
        "usb_disconnected": "❌",
        "link_connected": "🔗",
        "link_disconnected": "⛓️‍💥",
        "update_available": "⬆️",
    },
    "nerd": {
        "pixel": "",
        "device": "󰌢",
        "system": "",
        "storage": "󰋊",
        "time": "",
        "brightness": "󰃟",
        "volume": "",
        "wifi": "",
        "wifi_low": "󰤟",
        "wifi_mid": "󰤢",
        "wifi_high": "󰤥",
        "battery_full": "",
        "battery_low": "",
        "usb_connected": "",
        "usb_disconnected": "",
        "link_connected": "󰌷",
        "link_disconnected": "󰌸",
        "update_available": "󰏔",
    },
    "text": {
        "pixel": "*",
        "device": "NAME",
        "system": "SYS",
        "storage": "DISK",
        "time": "TIME",
        "brightness": "BRI",
        "volume": "VOL",
        "wifi": "WIFI",
        "wifi_low": "WIFI1",
        "wifi_mid": "WIFI2",
        "wifi_high": "WIFI3",
        "battery_full": "HB",
        "battery_low": "LB!",
        "usb_connected": "USB",
        "usb_disconnected": "NOUSB",
        "link_connected": "LINK",
        "link_disconnected": "NOLINK",
        "update_available": "UPDATE",
    },
}

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_TERMINAL_SIZE = (80, 24)
DEFAULT_HELP_MIN_COLS = 60
DEFAULT_HELP_PAD = 2
DEFAULT_HELP_MARGIN = 4
DEFAULT_HELP_MIN_WIDTH = 10
BYTES_KIB = 1024

TEXT_HTTP_POLL = "Polling /api/screen every {interval}s from {addr}"
TEXT_WS_STREAM = "Streaming screen from {addr}"
TEXT_WS_STREAM_VERBOSE = "Streaming via WebSocket from {base}/api/screen/ws"
TEXT_STREAMING_INFO = "{protocol} {host}"
SWITCH_DISPLAY_SEQUENCES = (b"\t", b"\x12")
TEXT_INIT_START = "Initializing remote stream"
TEXT_INIT_CONNECTING = "Connecting to bar at {addr}"
TEXT_INIT_WS = "Opening WebSocket stream"
TEXT_INIT_HTTP = "Starting HTTP polling"
TEXT_INIT_WAIT_FRAME = "Waiting for the first frame"
TEXT_INIT_STREAMING = "First frame received; streaming started"
TEXT_STREAM_EMPTY = "Stream frame empty; skipping"
TEXT_STREAM_LEN = "Stream frame len={size} (expected {expected})"
TEXT_POLL_FAIL = "Polling failed: %s"
TEXT_POLL_LEN = "Received frame len={size} (expected {expected})"
TEXT_SNAPSHOT_FAIL = "Snapshot update failed: %s"
TEXT_USB_FAIL = "USB check failed: %s"
TEXT_LINK_FAIL = "Link status check failed: %s"
TEXT_UPDATE_FAIL = "Update check failed: %s"
TEXT_STOPPED = "Stopped"
TEXT_ERR_TIMEOUT = "Connection to bar timed out"
TEXT_ERR_CONNECT = "Connection to bar failed: {details}"
TEXT_ARG_DESC = "Stream screen to console"
TEXT_ARG_ADDR = "Device address"
TEXT_ARG_TOKEN = "Bearer token"
TEXT_ARG_HTTP = "Poll /api/screen over HTTP instead of websocket; seconds between polls"
TEXT_ARG_SPACER = "String inserted between pixels"
TEXT_ARG_LOG_LEVEL = "Logging level"
TEXT_ARG_LOG_FILE = "Log file path (disabled by default)"
TEXT_ARG_NO_INPUT = "Disable forwarding terminal keys to /api/input"
TEXT_ARG_KEYMAP = "Optional JSON keymap file"
TEXT_ARG_FRAME = "Frame mode around display: full, horizontal, none"
