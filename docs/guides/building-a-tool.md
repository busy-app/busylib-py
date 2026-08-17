# Building a tool with busylib

The setup wizard that ships with the library is a small, real program: it
reads what a bar is currently doing, decides what's left to configure, and
changes only that. This page walks through how it's put together, because the
same shape works for most tools you'd write against a bar.

The code shown here isn't a transcription — it's pulled straight from
`examples/setup/operations.py`, so it can't drift from the program that runs.

## One function per device operation

Every interaction with the bar is its own function that takes a client and
returns plain data. No printing, no prompting, no program state:

::: examples.setup.operations.read_device_name
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

::: examples.setup.operations.rename_device
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

That separation is what makes them reusable. `read_device_name` is equally at
home in a monitoring script, and it's testable without a terminal.

## Reading state before changing it

Most operations come in pairs: read what's there, then act only if needed.
Reading is where the device's quirks live, so that's where the comments go:

::: examples.setup.operations.read_firmware_state
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

Two things worth copying from this. It reads from two endpoints because
neither has the whole answer, and it treats the second as best-effort — an
unreachable `/api/status` costs the version label, not the verdict. And it
asks the library whether the device is supported rather than comparing
version strings itself.

## Operations that need to wait

Some device actions are asynchronous: you ask, then poll for the outcome.

::: examples.setup.operations.find_available_update
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

The subtlety here cost a release fix: `available_version` keeps the result of
an *earlier* check, so acting on it while a new check is running gets a
`400 "Update not available"` back. Waiting for the device's own status to
read `available` is what makes the install stick.

## Operations that are allowed to fail

Not every failure deserves to stop the program:

::: examples.setup.operations.scan_networks
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3

A bar refuses to scan while it's associated. That's not an error worth
aborting over — the caller can just ask for an SSID instead — so the function
returns an empty list and says why in the log.

## Assembling the pipeline

With the operations in place, a step is only the conversation: what to show,
what to ask, and when the work is already done.

```python
class NameStep(SetupStep):
    key = "name"
    title = "Device name"

    async def status(self, client) -> StepStatus:
        current = await operations.read_device_name(client)
        if current and current != DEFAULT_DEVICE_NAME:
            return StepStatus(done=True, summary=current)
        return StepStatus(done=False, summary=f"{current or 'unset'} (factory default)")

    async def run(self, client, prompt) -> None:
        value = await prompt.text("Device name")
        error = validate_device_name(value)
        if error is not None:
            prompt.info(f"Invalid name: {error}")
            raise SetupCancelled
        await operations.rename_device(client, value)
```

The pipeline is then just a list, run in order:

```python
def default_steps() -> list[SetupStep]:
    return [FirmwareStep(), WifiStep(), TimezoneStep(), NameStep(), CloudStep()]
```

The wizard reads every step's `status()` concurrently, prints the checklist,
and calls `run()` only on what's still pending — which is why re-running it
after a reboot is safe.

These two blocks are implementation fragments rather than standalone scripts:
they define a setup step and its order, so they have no direct terminal output.
When the wizard runs them, the observable result is the setup checklist shown
in the [quick start](../index.md), with a completed name step rendered as
`[x] Device name ...`.

## Why this shape

Splitting the device work out from the conversation buys three things:

- **The operations are reusable.** Nothing in them assumes a wizard.
- **They're testable without a terminal.** The wizard's tests drive them with
  a fake client and a scripted prompt, and the tricky cases above — a stale
  update check, a refused scan — are covered directly.
- **The documentation stays true.** These examples are generated from the
  source, so a change to the program updates this page.

The full source is in
[`examples/setup`](https://github.com/busy-app/busylib-py/tree/main/examples/setup).
