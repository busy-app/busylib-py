# Busy Bar App/Script Agent Guide

## Core Rules

- Everything written into this repository or onto GitHub is in English: code, comments, docstrings, README and docs, commit messages, pull request titles and bodies, issue and review comments. This is a public library with external contributors, so nothing else is acceptable.
- Answer in the language the user uses for the request. That applies to chat replies only, and never overrides the rule above.
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
- Test display/audio payloads with `httpx2.MockTransport` before hitting a real device.
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

## Pull Requests

- Title says what changes, in the imperative and without a ticket number.
- Body is two short paragraphs at most: what the reader gets, and why the
  previous behaviour was not enough. No walk-through of the diff, no history
  of how the change was arrived at, no checklists.
- Say what was verified against a real bar, when anything was.
- No trailers, footers or co-author lines.
- If a later change proves an earlier body wrong, correct that body rather
  than leaving the claim standing - a merged pull request is documentation.

## When The Firmware Updates

A BUSY Bar release can move things this library states as fact. Work through
this before assuming a bug is in `busylib`:

1. **Pull the protobuf schema and regenerate the state stream:**

   ```bash
   make proto-sync
   ```

   Then run the tests: a field that changed type or went away shows up there
   first. Remember two things this has already cost us: proto3 omits any
   field holding its type's default, so "missing" and "zero" arrive
   identically; and a renamed field breaks nothing loudly - when the Wi-Fi
   states became `active` and `inactive`, the old readers simply stopped
   seeing a network. Check renames against
   `git -C .cache/bsb-protobuf log -p`, and read both names for a while.

2. **Re-read the OpenAPI spec from the bar itself** (`/openapi.yaml`), not
   from a checkout: the spec on a development bar is ahead of the release,
   and the cloud's copy keyed by firmware version is the released truth.

3. **Check the stock asset map** in `docs/guides/stock-assets.md`:

   ```bash
   make stock-assets BAR=<address> PIN=<pin> CHECK=1   # report drift
   make stock-assets BAR=<address> PIN=<pin>           # write the new counts
   ```

   Icons, animations, sounds and themes come and go with the firmware. The
   counts are generated; the prose around them is not, so read what moved
   and say it in words.

4. **Re-measure the limits the firmware does not document.** Timer phases,
   cycle counts and the like are checked in `busy_timer_common.h` and refused
   with unhelpful errors - a silent `OK` for a profile, `400 Failed to parse
   snapshot` for a session. If the constants in `features/timer.py` and the
   firmware's disagree, the firmware wins.

5. **Ask what a new feature makes possible for consumers** - the Home
   Assistant integration is the first one to check - and whether anything
   this library carries as a local copy should now be read from the bar.
