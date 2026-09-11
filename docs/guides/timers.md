# Working with timers

## The bar does not run a clock you can read

`GET /api/busy/snapshot` does not tell you what the timer is doing now. It
returns the **last snapshot that was applied**, exactly as it was applied,
together with the moment that happened. Read it twice a minute apart and you
get the same numbers back both times.

That is deliberate, not a gap. It is how the apps keep one timer in step
across several clients: whoever changes the timer writes a snapshot, the
freshest timestamp wins, and every client works out the current state for
itself. The bar is the shared store, not the clock.

So a snapshot on its own is a starting point plus a date. To get from there
to "what is the timer doing", you advance it by the time that has passed —
which is what `timer_state()` does.

!!! note
    "Snapshot" means two unrelated things in this library. Here it is the
    timer's state on the device. In
    [Reading device state](device-state.md) it is
    `collect_device_snapshot()`, a gathered picture of battery, Wi-Fi and
    the rest.

## Asking what the timer is doing

```python
from busylib import BusyBar
from busylib.features import timer_state

bar = BusyBar("10.0.4.20")
state = timer_state(bar.busy_snapshot())

print(state.mode)          # not_started / infinite / simple / interval
print(state.phase)         # work / rest / None
print(state.time_left_ms)
print(state.is_running)
```

`timer_state()` takes the current wall clock by default. Pass `now_ms` to ask
about another moment — which is the whole point of the model: one read
answers for any time, without polling.

## The four kinds of timer

| `mode` | What it is | `phase` | `time_left_ms` |
| --- | --- | --- | --- |
| `not_started` | No session | `None` | `None` |
| `infinite` | Runs until stopped | `work` | `None` — nothing to count down to |
| `simple` | One countdown | `None` | Remaining, `0` once finished |
| `interval` | Pomodoro: work and rest, repeated | `work` / `rest` | Remaining in the current interval |

## How an interval session is laid out

Two words that are easy to mix up, and that the firmware keeps distinct: an
**interval** is one stretch of work or of rest, and a **cycle** is a work
interval plus the rest that follows it. `interval_work_cycles_count`
configures cycles; `current_interval` reports intervals.

An interval session is a run of intervals, numbered from zero, alternating
work and rest. `current_interval` in the snapshot is that number, and it is
the only thing you need:

- **even index → work, odd index → rest.**

Not the interval's length. Reading the phase off durations happens to work
when work and rest differ, and falls apart when someone configures both to
25 minutes — the index has no such gap.

A session of *n* cycles runs `n` work periods with rest between them, and
**stops after the last work** — there is no rest at the end. So three cycles
of 20 minutes' work and 5 minutes' rest look like this:

| Index | Phase | From | To |
| --- | --- | --- | --- |
| 0 | work | 0:00 | 20:00 |
| 1 | rest | 20:00 | 25:00 |
| 2 | work | 25:00 | 45:00 |
| 3 | rest | 45:00 | 50:00 |
| 4 | work | 50:00 | 70:00 |
| 5 | — | session over | |

Index 5 is never a live interval; reaching it is the session ending. In
general the session ends at index `cycles * 2 - 1`.

## A worked example

One read, then the state at whatever moment you ask about — the same
20/5/3 session as the table above:

```python
snapshot = bar.busy_snapshot()          # read once
started = snapshot.snapshot_timestamp_ms

for minutes in (0, 21, 26, 46, 71):
    state = timer_state(snapshot, now_ms=started + minutes * 60_000)
    print(minutes, state.phase, state.interval, state.time_left_ms, state.is_finished)
```

**Expected output:**

```
0 work 0 1200000 False
21 rest 1 240000 False
26 work 2 1140000 False
46 rest 3 240000 False
71 None 5 0 True
```

At 21 minutes the first work period is over and rest has four minutes to
run. At 71 the session has finished, so no phase applies.

## Pausing

A paused snapshot is already the answer: paused time does not pass, so
`timer_state()` hands back what the snapshot says however long ago it was
written.

```python
state = timer_state(snapshot)
if state.is_paused:
    print(f"paused with {state.time_left_ms} ms left in {state.phase}")
```

## Changing a timer

Every change is a snapshot write - there is no endpoint that pauses a session
or moves it on a phase - and each one has a detail that is easy to get wrong.
The helpers in `busylib.features.timer` write the right snapshot for you:

```python
from busylib.features import timer

await timer.start(bar)                       # the session the "busy" card describes
await timer.start(bar, "custom", theme="dnd")  # the other card, this session in dnd
await timer.set_paused(bar, True)            # pause, keeping the time actually left
await timer.set_paused(bar, False)           # resume
await timer.next_phase(bar)                  # work -> rest, at the rest length
await timer.set_session_theme(bar, "meeting")  # until this session ends
await timer.set_card_theme(bar, "busy", "meeting")  # from now on
await timer.stop(bar)                        # back to not started
```

Three things they take care of:

**A session's mode comes from the card, not from you.** `start()` reads the
card and builds a snapshot from its own settings, because the device rejects
one that disagrees with the card it names. To start a countdown of a different
length, write the card first.

**Pausing has to recompute the remaining time.** The stored snapshot's figure
was true when it was written; writing it back unchanged hands the session back
the time it already spent. `set_paused()` takes the figure from
`timer_state()`, and carries the phase across if the session moved on in the
meantime.

**A session theme and a card theme are different things.** `set_session_theme`
lasts as long as the session - stop it and the bar shows the card's theme
again, confirmed on hardware. `set_card_theme` outlasts the session and does
not change what is on screen now.

**Which themes there are is a question for the bar.** A theme is a free
string on the wire, and the set is whatever the firmware ships, so
`timer.themes(bar)` reads it from the bar rather than leaving a consumer to
copy a list that goes stale, or to learn it by sending a wrong one:

```python
options = await timer.themes(bar)  # ['back_soon', 'booked', 'busy', 'coding', ...]
```

**A card write needs a fresh timestamp.** The device keeps whichever copy of a
card is newer and silently discards the rest, answering `{"result": "OK"}`
either way. A card read back and written unchanged carries the stored
`profile_timestamp_ms`, which is not newer - and a bar that has never had one
written reports `0` - so the write disappears with no error at all.
`set_card_theme` stamps it for you.

Anything that rewrites a running session - pausing, `next_phase`,
`set_session_theme` - raises `TimerNotRunningError` when nothing is running,
rather than starting a session nobody asked for.

## Writing the snapshot yourself

You write a snapshot, the same way the apps do:

```python
import time

from busylib import types

profile = bar.busy_profile("busy")
settings = profile.timer_settings

bar.busy_snapshot_set(
    types.BusySnapshot(
        snapshot=types.BusySnapshotInterval(
            type="INTERVAL",
            card_id=profile.id,
            current_interval=0,                       # start at the first work period
            current_interval_time_total_ms=settings.interval_work_ms,
            current_interval_time_left_ms=settings.interval_work_ms,
            is_paused=False,
            interval_settings=settings,
            busy_bar_settings=profile.busy_bar_settings,
        ),
        snapshot_timestamp_ms=int(time.time() * 1000),
    )
)
```

Stopping is a `NOT_STARTED` snapshot with a fresh timestamp.

Two things to know, both learned the hard way:

**`interval_settings` has to match the profile.** Send durations of your own and
the device answers `400 Failed to parse snapshot` — which is misleading,
because the JSON parsed fine and it is the settings that disagree. Take them
from `busy_profile()`, as above.

**`busy_bar_settings` is required.** It is merged into the snapshot object on
the wire rather than sitting beside it, and a snapshot without it is refused.
Reading a snapshot gives it to you, so the active theme and
`trigger_smart_home` come along for free.

And one device quirk worth knowing if you try to make a short session for
testing: `PUT /api/busy/profiles/{slot}` answers `{"result": "OK"}` and
silently keeps the old settings when given short interval durations, so a
six-second pomodoro cannot be configured through the API.
