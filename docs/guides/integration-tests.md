# Testing against a real bar

Most of the suite runs against a mock transport and needs no hardware. That
catches a lot, but not everything: a mock accepts any query string, so it
cannot tell you that the device rejects `?volume=42.0`, or that it names a
rename's source `path` and not `old_path`. Both of those shipped broken for
months.

The integration suite closes that gap. It drives one physical bar over all
three transports the library supports, and it is opt-in: nothing here runs
during a normal `pytest`.

## Connect the bar

You can use any subset of these. Each transport is skipped unless it is
configured *and* answers, so start with USB and add the others when you want
wider coverage.

**Over USB.** Plug the bar into the machine running the tests. It comes up as
a network device at `10.0.4.20` and, on current firmware, needs no access key
over USB.

**Over the local network.** Put the bar on Wi-Fi — the setup wizard does this
— and find its address with `bb.wifi_status().ip_config.address`, on the
device screen, or via discovery. If the bar has an access key set (`bb.access()`
reports `mode="key"`), you need that PIN: over Wi-Fi the key is enforced.

**Through the cloud.** Link the bar to a BUSY account, then mint a bar-scope
token in the [dashboard](https://cloud.busy.app/dashboard). An account-scope
token will not work — see [Cloud addresses](../api/cloud.md).

## Configure

Everything comes from the environment:

| Variable | Meaning |
| --- | --- |
| `BUSYBAR_TEST_USB` | address over USB, defaults to `10.0.4.20` |
| `BUSYBAR_TEST_WIFI` | address on the local network |
| `BUSYBAR_TEST_WIFI_TOKEN` | access key, if the bar has one |
| `BUSYBAR_TEST_CLOUD_TOKEN` | bar-scope cloud token |
| `BUSYBAR_TEST_MANUAL_TIMEOUT` | seconds to wait for a button press, default 30 |

## Run

```bash
uv run pytest tests/integration -m integration
```

Add `-m "integration and not manual"` to skip the one test that needs a human,
which is what you want in any unattended run.

To check a single transport, configure only that one. Unsetting
`BUSYBAR_TEST_USB` is not enough to skip USB, since it has a default — point
it at nothing instead:

```bash
BUSYBAR_TEST_USB= uv run pytest tests/integration -m "integration and not manual"
```

## Read the result

A full run against a bar reachable three ways looks like this:

```
40 passed, 2 skipped, 3 deselected
```

**Skips are expected, and the reason says which kind.** There are three:

- `endpoint is local only` — correct behaviour. Status streaming does not work
  through the cloud by design, so those tests stand down on that transport.
- `a Busy session owns the display (INTERVAL)` — the bar is mid-session.
  `display_draw` competes for the screen and a running session outranks
  everything, priority 100 included, so drawing is refused with `409`. Stopping
  the session would take the bar away from whoever is using it, so the drawing
  tests stand down instead. Stop the session on the bar to run them.
- `usb transport unavailable - ...` — the transport was configured but did not
  answer, and the message carries the error. A `403` there means a missing or
  wrong access key, not a broken bar.

Run with `-rs` to see the reasons:

```bash
uv run pytest tests/integration -m integration -rs
```

**A failure is about the device, not the mock.** These tests only assert
things a real bar decides: that a payload is accepted, that a written value
reads back, that a frame is the size the panel dictates. So a failure means
either the firmware changed its contract or this client has it wrong — which
is exactly what the suite exists to tell you.

The probe deliberately calls `/api/status` rather than `/api/version`, because
a bar in key mode answers `version` without a key. Probing with `version`
would let a transport with a bad token look usable and then fail every test
with `403`.

## The manual test

Forwarded input travels the same stream as real hardware, so the automatic
tests cannot prove the buttons, wheel and switch are wired to it. One test
asks you to use the bar:

```bash
BUSYBAR_TEST_MANUAL_TIMEOUT=120 uv run pytest \
  tests/integration/test_input_stream.py::test_physical_input_reaches_the_stream \
  -m "integration and manual" -s
```

`-s` matters: without it pytest captures the prompt and you will not see what
to do. Each input is acknowledged as it arrives, and the test finishes as soon
as it has seen all three buttons, both wheel directions and one switch move.

```
On the bar, within 120s:
  press OK, BACK and START
  turn the wheel one way and back
  move the switch to any other position
  button OK
  wheel forward (delta 1)
  switch APPS
```

If something does not appear, check the automatic counterparts first:
`test_forwarded_buttons_come_back_on_the_stream` and
`test_forwarded_wheel_movement_comes_back` use the same decoding, so if
they pass and this does not, the gap is between the hardware and the stream
rather than in this client.

### Reading input yourself

Worth knowing if you consume this stream in your own code: protobuf omits
fields holding a default value, and the first entry of every input enum is a
default. `OK` is button 0, `PRESS` is action 0, and `BUSY` is switch position
0 — so "OK pressed" and "moved to BUSY" both arrive as an empty payload:

```python
{"input": {"button_event": {}}}  # OK, pressed
{"input": {"switch_event": {}}}  # switch moved to BUSY
```

Treat a missing key as the enum's first value rather than as no data. The
wheel is safe from this, since the firmware sends `+1` and `-1` and never `0`.

## What the tests touch

Everything written is namespaced: drawings and assets use the application
name `busylib-itest`, and files go under `/ext/busylib-itest`. Values that get
changed — brightness, volume, device name — are restored afterwards, including
when the test fails.

Two things are worth knowing anyway. The device name is what discovery
advertises, so an interrupted run can leave `busylib itest` visible on the
network until you re-run. And nothing here reboots the bar, installs firmware,
unlinks the account, or touches Wi-Fi settings.
