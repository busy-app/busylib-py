# Stock assets

Every BUSY Bar ships with pictures, animations, sounds, fonts and themes
already on it. Referencing one costs nothing and needs no upload - which makes
it the first thing to reach for, before [converting and uploading your
own](assets-and-storage.md).

They live under `/ext/apps_assets/`, in two trees:

| Tree | What it is |
| --- | --- |
| `shared/` | For anyone: icons, status animations, fonts, notification sounds |
| `busy/` | The BUSY timer's own decoration - session animations, indicators, its themes |

## How to reference one

Anything that draws or plays takes **`stock_path`** for a built-in and `path`
for a file you uploaded. A stock path is the tree, the folder and the file
name with its extension - relative to `/ext/apps_assets/`:

```python
from busylib import BusyBar, types

with BusyBar("192.168.1.50", token=PIN) as bar:
    bar.display_draw(
        types.DisplayElements(
            application_name="my-app",
            elements=[
                types.ImageElement(
                    id="10", x=0, y=4,
                    stock_path="shared/images/clock_5x5.image",
                ),
            ],
        )
    )

    bar.audio_play(
        stock_path="shared/sounds/calendar_event_starts.snd",
        application_name="my-app",
    )
```

The folder and the extension are both required: the flat `shared/clock` form
the OpenAPI spec suggests is refused by the device.

The size is in the file name, and it is the size you have to lay out around -
`clock_5x5.image` is five pixels square. `_front_` and `_back_` say which
display an asset was drawn for: the front is a 72x16 strip, the back a 16x16
square. Nothing stops you drawing either one anywhere; it will just look wrong.

## What is there

The set follows the firmware, so the tables below are a map rather than a
contract - [ask the bar](#reading-the-map-from-a-bar) when it matters. The
counts come from a bar, and `make stock-assets` puts them back in sync:

<!-- begin stock assets map -->
Counted on firmware `r971`:

| | Folder | How many |
| --- | --- | --- |
| Icons and pictures | `shared/images/` | 84, 66 of them the `dt_*` sticker set |
| Status animations | `shared/animations/` | 19 |
| Fonts | `shared/fonts/` | 10 |
| Notification sounds | `shared/sounds/` | 3 |
| Timer animations | `busy/animations/` | 22 |
| Timer pictures | `busy/images/` | 13 |
| Timer sounds | `busy/sounds/` | 3 |
| Themes | `busy/themes/` | 12 |
<!-- end stock assets map -->

### Icons

Eight of them have names in `busylib`, because [notifications](notifications.md)
lay themselves out around one and need its width:

| Name | File | Width |
| --- | --- | --- |
| `check` | `shared/images/checkmark_front_8x8.image` | 8 |
| `error` | `shared/images/error_front_8x8.image` | 8 |
| `info` | `shared/images/info_front_8x8.image` | 8 |
| `low_battery` | `shared/images/low_battery_front_8x8.image` | 8 |
| `clock` | `shared/images/clock_5x5.image` | 5 |
| `hourglass` | `shared/images/hourglass_5x5.image` | 5 |
| `start` | `shared/images/start_11x11.image` | 11 |
| `setup` | `shared/images/setup_11x11.image` | 11 |

```python
from busylib.features import notification

await notification.notify(bar, "Laundry done", icon="check", application_name="my-app")
```

`notification.icons(bar)` returns every image the bar actually holds, each with
the width read from its file header - the `dt_*` sticker set included (food,
faces, activities: `dt_coffee`, `dt_emoji_happy`, `dt_work` ...). Pass a
`StockIcon` from that list anywhere a name is taken.

### Animations

`shared/animations/` holds the twelve status animations, one per theme, as
72x16 strips - `dnd_72x16.anim`, `meeting_72x16.anim`, `lunch_72x16.anim`,
`flow_72x16.anim`, `coding_72x16.anim`, `on_air_72x16.anim`,
`on_call_72x16.anim`, `booked_72x16.anim`, `back_soon_72x16.anim`,
`chill_time_72x16.anim`, `keep_out_72x16.anim`,
`low_social_battery_72x16.anim` - plus the calendar, spinner and transition
pieces the firmware uses.

`busy/animations/` is the timer's own: progress, particles, the start logos and
the transitions between phases.

```python
types.AnimationElement(
    id="10", x=0, y=0, loop=True,
    stock_path="shared/animations/dnd_72x16.anim",
)   # one element of a DisplayElements payload, as above
```

### Sounds

| Stock path | When the firmware uses it |
| --- | --- |
| `shared/sounds/calendar_event_starts.snd` | An event is starting |
| `shared/sounds/calendar_reminder_ends.snd` | A reminder is over |
| `shared/sounds/volume_change.snd` | The volume moved |
| `busy/sounds/countdown_tick.snd` | A session's last seconds |
| `busy/sounds/countdown_finish.snd` | A phase ended |
| `busy/sounds/session_completed.snd` | The whole session ended |

The first three have short names in `notification.STOCK_SOUNDS` (`event`,
`reminder`, `volume`) and are what `notify(sound=...)` takes.

### Fonts

Text names a font rather than pointing at one: `tiny`, `small`, `normal`,
`condensed`, `bold`, `large`, `extra_large`, and `superscript` - which the
firmware added in OpenAPI 27.6 for the raised digits a countdown draws. The
largest do not fit two lines on the front display, which is why
`notification.TWO_LINE_FONTS` is the shorter list.

### Themes

`busy/themes/<name>/theme.json` - twelve of them, and they are what a session
looks like on the bar. They are chosen by name, not by path:

```python
from busylib.features import timer

await timer.themes(bar)                      # what this bar has
await timer.start(bar, theme="meeting")      # for this session only
await timer.set_card_theme(bar, "busy", "dnd")  # from now on
```

A theme a bar does not have raises `UnknownThemeError` rather than being
written and silently ignored. See [timers](timers.md).

## Reading the map from a bar

Firmware adds and removes assets, and an owner can upload their own, so the
bar is the only authority:

```python
listing = await bar.storage_list("/ext/apps_assets/shared/images")
print([item.name for item in listing.list])
```

`notification.icons(bar)` and `timer.themes(bar)` do exactly this for the two
cases where a name has to be offered to a person - an icon picker, a theme
dropdown - and neither has a list written down in the library to go stale.
