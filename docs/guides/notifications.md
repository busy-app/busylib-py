# Sending notifications

A notification on the front panel is not "some text" — it is a handful of
elements placed to the pixel on 72 × 16, and where they go depends on the
font, on whether an icon takes the left edge, and on what the firmware in
front of you can draw.

The library places them, so you describe the notification and not its
geometry:

```python
from busylib import AsyncBusyBar
from busylib.features import notify

bar = AsyncBusyBar("10.0.4.20")
await bar.version()  # so the version-dependent parts can be checked
await notify(bar, "Laundry done", icon="check", duration=10)
```

`notify()` builds the elements and draws them. To build without drawing —
to inspect the payload, or to send it yourself — use `build_notification()`,
which returns a `DisplayElements` model.

## What you can set

| Field | Meaning |
| --- | --- |
| `line_1` | The first (or only) line |
| `line_2` | A second line; giving it selects the two-line layout |
| `icon` | A name from `STOCK_ICONS`, drawn at the left edge |
| `line_1_color`, `line_2_color` | Per-line colour |
| `background_color` | Fills the panel behind everything |
| `font` | One name for both lines |
| `duration` | Seconds before the elements expire |
| `priority` | `PRIORITY_DEFAULT`, or `PRIORITY_INTERRUPT` to sit above a Busy session |
| `application_name` | Owns the drawing, and is how `display_clear` finds it |

A drawing loses to anything above it, and the device answers
`409 Not drawn due to low priority` rather than drawing it late.

## Built-in templates

There are two, and the one that suits the arguments is chosen for you:

| Template | Chosen when | Fonts |
| --- | --- | --- |
| `ONE_LINE` | no `line_2` | all seven |
| `TWO_LINES` | `line_2` given | `tiny`, `small`, `normal`, `condensed`, `bold` |

Two templates cover four layouts: an icon only changes where the text
starts, which is worked out from the icon's own width, so "with an icon" is
not a separate arrangement. The shipped icons are 5, 8 and 11 pixels wide,
which is why that offset is computed rather than fixed.

`large` and `extra_large` are missing from the two-line row because two
lines of them do not fit 16 pixels. Asking anyway is an error rather than a
silent substitution — a caller who asked for `large` and got `small` has no
way to notice.

## Writing your own

A template is anything with `name`, `fonts`, `matches()` and `render()`. The
built-ins are ordinary implementations of that protocol, so writing one is
the same work:

```python
from busylib.features import notification


class RightAligned:
    """One line, pushed against the right edge."""

    name = "right_aligned"
    fonts = ("small", "bold")

    def matches(self, spec: notification.NotificationSpec) -> bool:
        return not spec.line_2

    def render(self, spec: notification.NotificationSpec):
        right = spec.display.width - 2
        return [
            spec.text(
                "1",
                spec.line_1,
                y=8,
                align="mid_right",
                x=right,
                width=right,
            )
        ]


await notify(bar, "CUSTOM", template=RightAligned())
```

`render()` receives a `NotificationSpec` with the work you should not
repeat already done:

| On the spec | What it gives you |
| --- | --- |
| `icon` | The icon resolved to its path and width, or `None` |
| `text_x` | Where a left-anchored line starts, past the icon |
| `available_width` | What is left for text after the icon |
| `display` | The panel's `width`, `height` and name |
| `text(...)` | A text element, scrolled if it cannot fit |
| `icon_element()` | The icon element, or `None` |

`matches()` is only consulted for the built-ins, when no template was
passed. A template you pass is used regardless, so `matches()` can simply
return `True` if you never register it for selection.

### Two defaults that assume a left anchor

`spec.text()` defaults `x` to `spec.text_x` and the scroll window to
everything right of `x`. Both are right for a line anchored left, and wrong
for any other anchor:

- with `align="mid_right"` and the default `x`, the line's **right** edge
  lands at the left margin and the text runs off the panel;
- with a right-hand `x` and the default width, the room is computed as the
  few pixels right of it, and the line scrolls through a window that narrow.

Found on real hardware, where a right-aligned `CUSTOM` rendered as six lit
pixels. Pass both `x` and `width` for any anchor other than the left one, as
the example above does.

## Backgrounds need firmware 24.3.0

A background colour is drawn as a filled rectangle, and that element enters
the published API at 24.3.0 (firmware 1.0.0-rc). Below it there is no fill
primitive at all, which is why older integrations faked a background by
tiling a dense glyph across the panel.

Rather than carry a second renderer, the library refuses:

```python
from busylib.exceptions import BusyBarFeatureUnavailableError

try:
    await notify(bar, "hi", background_color=[0, 0, 90])
except BusyBarFeatureUnavailableError as err:
    print(err.feature, "needs", err.required_version, "but the bar reports", err.device_version)
```

The check is why `notify()` takes the client rather than a version: it reads
`bar.device_api_version`, which `version()` fills in. If nothing has asked
the bar yet, the version is unknown and a current device is assumed —
guessing "old" would disable the feature for everyone who never called
`version()`.

This is also the part a custom template never has to think about. The
background is added by `build_notification()`, not by the template, so a
template you write cannot forget the check.

## Icons and sounds

`STOCK_ICONS` and `STOCK_SOUNDS` name what ships on the device:

```python
from busylib.features import notification

print(sorted(notification.STOCK_ICONS))
print(sorted(notification.STOCK_SOUNDS))
```

**Expected output:**

```
['check', 'clock', 'error', 'hourglass', 'info', 'low_battery', 'setup', 'start']
['event', 'reminder', 'volume']
```

A sound is played separately, through `audio_play`, with the drawing's own
application name:

```python
await bar.audio_play(
    stock_path=notification.STOCK_SOUNDS["event"],
    application_name="home_assistant",
)
```

Paths in both catalogues carry their sub-folder and extension. The flat
`shared/<name>` form that the OpenAPI spec suggests does not resolve, and
the device answers `400 Failed to decode image` for it.
