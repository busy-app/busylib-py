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
await timer.start(bar, kind="simple", duration_ms=45 * 60_000)   # 45 minutes, card untouched
await timer.start(bar, kind="interval", duration_ms=25 * 60_000,
                  rest_ms=5 * 60_000, cycles=4)  # an interval of your own
await timer.start(bar, card_id=other, kind="simple",
                  duration_ms=30 * 60_000)       # a card outside both positions
await timer.set_paused(bar, True)            # pause, keeping the time actually left
await timer.set_paused(bar, False)           # resume
await timer.next_phase(bar)                  # work -> rest, at the rest length
await timer.set_session_theme(bar, "meeting")  # until this session ends
await timer.set_card_theme(bar, "busy", "meeting")  # from now on
await timer.stop(bar)                        # back to not started
```

Three things they take care of:

**A session may have settings of its own, and they do not touch the card.**
With nothing but a slot, `start()` runs what that card describes - the thing
the bar's own switch would start. Give it a kind or a length and the session
runs that instead, travelling in the snapshot: the card keeps its name, its
lengths and its theme, and the app still shows the session under that card's
name. This is what an automation wants - "a countdown for forty-five minutes"
should not rewrite a card somebody arranged by hand.

**A session can name a card the bar does not hold.** The bar keeps two cards,
one per switch position; the BUSY app keeps more. `card_id` names any of them,
and then nothing on the bar is read or written - the two cards are not involved
even by name, and the app shows the session under the card it does know. Such a
session has no card to inherit from, so its kind and lengths come from the call.

**The bar will not run just any length.** Both ends are checked, and the
firmware says so nowhere useful: a card written with a two-minute work phase
answers `OK` and keeps what it had, and a session with one comes back as
`400 Failed to parse snapshot`. An interval phase runs 5 minutes to 8 hours,
a session has 2 to 35 work phases, and a countdown - checked at the top only -
runs up to 24 hours with no floor at all. `busylib` raises before the write
rather than letting either silence through. The numbers are the firmware's own
(`applications/services/busy_timer/busy_timer_common.h`), confirmed on a bar.

**Pausing has to recompute the remaining time.** The stored snapshot's figure
was true when it was written; writing it back unchanged hands the session back
the time it already spent. `set_paused()` takes the figure from
`timer_state()`, and carries the phase across if the session moved on in the
meantime.

**A session theme and a card theme are different things.** `set_session_theme`
lasts as long as the session - stop it and the bar shows the card's theme
again, confirmed on hardware. `set_card_theme` outlasts the session and does
not change what is on screen now.

**Which themes there are is a question for the bar.** Themes are assets:
one bar has what the firmware shipped, another has one its owner uploaded, a
third is missing one its owner deleted. So there is no list to write down -
`timer.themes(bar)` reads it:

```python
options = await timer.themes(bar)  # ['back_soon', 'booked', 'busy', 'coding', ...]
```

It reads two things, because neither alone is the answer: the asset
directories, and whichever themes the bar's own cards are set to. The second
is how the firmware's built-in default gets in - it has no directory, so a
listing alone would report that a bar cannot show the theme it is showing
right now.

Setting a theme checks it against that list first, because **the device will
not**: a card naming a theme that does not exist is stored and read back
happily, and only the bar's screen shows that anything is wrong. A theme it
does not have raises `UnknownThemeError`, which carries what it does have. If
you already have the list - because you offered it to someone - pass it as
`known=` and save the lookup.

**Changing a card is for when the change should last.** A session can carry
settings of its own (see `start()` above), and that is what an automation
wants; `timer.configure()` is for the other case - when the bar's own switch
should start something different from now on, and the BUSY app should show
it:

```python
await timer.configure(bar, "busy", work_ms=25 * 60_000)
await timer.start(bar, "busy")
```

The change outlasts the session, and the bar and the phone app see it - which
is the same thing they do to each other.

**One call is enough to set something of a given length.** `duration_ms`
lands where that kind of card keeps it - the total of a countdown, the work
phase of an interval session - so a caller does not have to know which:

```python
await timer.configure(bar, "custom", kind="simple", duration_ms=40 * 60_000)
await timer.start(bar, "custom")
```

**A card can change what kind of timer it holds**, which is how a mode
that runs without a clock becomes an interval session:

```python
await timer.configure(bar, "custom", kind="interval", work_ms=25 * 60_000)
print(timer.kind_of((await bar.busy_profile("custom")).timer_settings))  # 'interval'
```

`infinite`, `simple` and `interval` are what this package calls the
firmware's `INFINITE`, `SIMPLE` and `INTERVAL`. Changing to a kind a card
was not already running replaces its timer rather than editing it, because
there is nothing to carry over - an endless card has no lengths at all -
and anything you do not pass comes from the defaults. Asking for the kind a
card already holds edits it instead, so its lengths survive.

**Phases under five minutes are dropped in silence.** The device stores
nothing and answers `{"result": "OK"}`; the card keeps what it had. Found by
bisection on firmware r971 - four minutes ignored, five, six and seven kept -
and documented nowhere, the bar's own OpenAPI even offering `120000` as its
example. `configure()` raises `PhaseTooShortError` rather than let a caller
watch a bar run the wrong timer.

**A card write needs a fresh timestamp.** The device keeps whichever copy of a
card is newer and silently discards the rest, answering `{"result": "OK"}`
either way. A card read back and written unchanged carries the stored
`profile_timestamp_ms`, which is not newer - and a bar that has never had one
written reports `0` - so the write disappears with no error at all.
`set_card_theme` stamps it for you.

Anything that rewrites a running session - pausing, `next_phase`,
`set_session_theme` - raises `TimerNotRunningError` when nothing is running,
rather than starting a session nobody asked for. Both errors these helpers
raise are importable from `busylib.features`, next to everything else a
caller catches:

```python
from busylib.features import TimerNotRunningError, UnknownThemeError, timer

try:
    await timer.set_session_theme(bar, theme)
except TimerNotRunningError:
    ...  # nothing is running, so there is no session theme to change
except UnknownThemeError as err:
    print(f"this bar has {', '.join(err.available)}")
```

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

**A length the bar will not run is reported as an unparseable snapshot.**
`400 Failed to parse snapshot` is misleading: the JSON parsed fine, and the
firmware is refusing a number. An interval phase runs 5 minutes to 8 hours
and a session has 2 to 35 work phases (`busy_timer_common.h`); a countdown is
checked at the top only. The settings themselves may be whatever you like -
they need not match the card the snapshot names.

**`busy_bar_settings` is required.** It is merged into the snapshot object on
the wire rather than sitting beside it, and a snapshot without it is refused.
Reading a snapshot gives it to you, so the active theme and
`trigger_smart_home` come along for free.

And one device quirk worth knowing if you try to make a short session for
testing: `PUT /api/busy/profiles/{slot}` answers `{"result": "OK"}` and
silently keeps the old settings when given short interval durations, so a
six-second interval session cannot be configured through the API.
