# Busy Bar App/Script Agent Guide

## Core Rules

- Answer in the language the user uses for the request.
- Inspect the installed/local `busylib` before using unfamiliar APIs: client methods, `busylib.types`, README, and examples.
- Do not invent `busylib` methods, enum values, element fields, or payload shapes.
- Prefer public `busylib` methods over direct HTTP calls. Use `prepare_request()` only for batching, diagnostics, custom transports, or tests.
- Check that the local library, firmware OpenAPI spec, and generated protobuf modules are current enough for the requested feature.
- In consuming projects, upgrade or pin `busylib` intentionally instead of assuming latest methods exist.
- If an API is missing, add a small compatibility branch or fail with a clear error.
- Do not print tokens, Wi-Fi passwords, cookies, auth codes, or full secrets.

## Busy Bar Mindset

- Busy Bar is an ambient status device, not a general-purpose screen.
- Optimize for glanceability: short text, stable positions, high contrast, quiet defaults.
- Treat LEDs, brightness, audio, display, storage, and network calls as real-world effects.
- Local-first behavior is preferred. Offline should be a state, not a crash loop.
- Repeated effects need limits: bounded polling, backoff, cancellation, cleanup, and dry-run mode.

## Client Lifecycle

- Use sync `BusyBar` for simple scripts and CLI tools.
- Use `AsyncBusyBar` for watchers, dashboards, bots, web apps, and concurrent workflows.
- Reuse one client per device/workflow; do not create clients inside polling loops.
- Close clients with `with BusyBar(...)`, `async with AsyncBusyBar(...)`, or explicit `close()`/`aclose()`.
- Call `version()` once on startup and choose compatibility behavior deliberately:
  - `compatibility_mode="warn"` for scripts and prototypes;
  - `compatibility_mode="strict"` for production fail-fast behavior;
  - `compatibility_mode="none"` only for known mixed fleets or experiments.
- Use `client.method_compatibility("method_name")` for helpers that may require newer firmware/OpenAPI.
- Handle `BusyBarAPIError`, `BusyBarProtocolError`, and transport errors at workflow boundaries.
- Use explicit finite timeouts when the client or transport allows it.

## Payloads, Display, Audio

- Prefer `busylib.types` models for display payloads and reusable workflows.
- Use plain dicts only for short one-off scripts or low-level prepared requests.
- Do not mix model instances and ad-hoc dict fragments unless the API explicitly accepts it.
- Validate config before touching the device: host, app name, file paths, asset paths, element ids, display names, coordinates, polling intervals.
- Build display payloads as data first, then send them.
- Always set display element `type`; keep `elements` non-empty and small.
- Use stable element `id` values: one id per logical status line, icon, or timer.
- Keep text short enough for the target display. Prefer fixed positions over recalculating layout on every tick.
- Do not animate by redrawing the whole screen unless explicitly requested.
- Use clear-before-draw behavior only if supported by the installed `busylib` and only for whole-screen replacement.
- Reuse uploaded assets and cache conversions/generated images/rendered payloads.
- Audio and visual alerts need maximum duration and a clear stop path.

## Script Shape

Most projects should stay simple:

- Config: device host, token, app name, intervals, file paths, feature flags.
- State: last device state, current mode, timers, cached assets, retry counters.
- Device API: the only place that calls `BusyBar` / `AsyncBusyBar`.
- Workflow: behavior such as "meeting started -> draw status -> play sound".
- Output: logs, CLI text, files, metrics, UI updates.

Do not mix argument parsing, device calls, retries, and business decisions into
one long loop. For larger tools, put device calls behind a small class or module
so tests can mock them.

Events are just triggers. A timer tick, webhook, websocket message, CLI command,
or UI action should parse input, update state, and call a workflow function.

## Minimal Script Pattern

Use this shape for non-trivial scripts:

```python
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from busylib import BusyBar, types

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    device: str
    app_name: str = "busy-script"
    dry_run: bool = False


def parse_args() -> Config:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--app-name", default="busy-script")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return Config(args.device, args.app_name, args.dry_run)


def build_payload(config: Config) -> types.DisplayElements:
    return types.DisplayElements(
        application_name=config.app_name,
        elements=[
            types.TextElement(
                id="status",
                type="text",
                text="Ready",
                font="small",
                x=0,
                y=0,
                display=types.DisplayName.FRONT,
            )
        ],
    )


def run(config: Config) -> None:
    payload = build_payload(config)
    if config.dry_run:
        logger.info("Dry run payload: %s", payload)
        return
    with BusyBar(config.device) as bb:
        bb.version()
        bb.display_draw(payload)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run(parse_args())
```

## Coding Style

- Write clear Python for the runtime the user actually has.
- Type hints are useful when they clarify data or behavior.
- Pydantic models, dataclasses, TypedDict, and plain dicts are all acceptable when they fit the job.
- Keep workflow functions small enough to test or replace.
- Prefer explicit mappings over long `if` chains for command/state dispatch.
- Make scripts easy to stop with Ctrl+C without leaving audio, display, files, clients, or background tasks stuck.

## Tests And Checks

- Add tests for parsing, scheduling, retries, payload generation, and error handling.
- Test display/audio payloads with `httpx.MockTransport` before hitting a real device.
- Test repeated failures and recovery paths for watchers.
- Run checks available in the current project. In this repository, prefer:

```bash
make test
```

When available in the consuming project, also run:

```bash
uv run pytest -q
uv run pyright src tests
uv run python -m pre_commit run --all-files
```
