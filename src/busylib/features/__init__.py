from __future__ import annotations

from .app_assets import sync_app_assets
from .dashboard import (
    DeviceSnapshot,
    DeviceStateStore,
    apply_state_stream_update,
    collect_device_snapshot,
)

from .input_events import (
    ButtonEvent,
    EncoderEvent,
    InputEvent,
    SelectorEvent,
    input_events,
)

# The timer's control helpers are deliberately not re-exported here:
# `start`, `stop` and `next_phase` say nothing on their own at this level.
# Import the module and call them through it - `timer.start(client)`.
from . import assets, timer
from .timer import (
    TimerClient,
    TimerNotRunningError,
    PhaseTooShortError,
    TimerKind,
    TimerState,
    UnknownThemeError,
    kind_of,
    kind_of_snapshot,
    phase_of,
    timer_state,
)
from . import notification
from .assets import (
    Asset,
    AssetKind,
    copy_to_application,
    discover_assets,
)
from .notification import (
    BUILT_IN_TEMPLATES,
    NotificationSpec,
    Template,
    build_notification,
    notify,
    select_template,
)

__all__ = [
    "DeviceSnapshot",
    "DeviceStateStore",
    "collect_device_snapshot",
    "apply_state_stream_update",
    "assets",
    "Asset",
    "AssetKind",
    "copy_to_application",
    "discover_assets",
    "sync_app_assets",
    "build_notification",
    "notify",
    "BUILT_IN_TEMPLATES",
    "NotificationSpec",
    "Template",
    "select_template",
    "TimerState",
    "timer_state",
    "timer",
    "notification",
    "TimerClient",
    "TimerNotRunningError",
    "UnknownThemeError",
    "kind_of",
    "kind_of_snapshot",
    "PhaseTooShortError",
    "TimerKind",
    "ButtonEvent",
    "EncoderEvent",
    "InputEvent",
    "SelectorEvent",
    "input_events",
    "phase_of",
]
