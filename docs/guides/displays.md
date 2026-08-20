# Drawing on the displays

A BUSY Bar has two displays, and every draw call targets one of them
explicitly:

| Display | Size | Kind |
| --- | --- | --- |
| `DisplayName.FRONT` | 72 × 16 | RGB LED matrix, ~16M colours |
| `DisplayName.BACK` | 160 × 80 | Monochrome OLED, 16 shades of grey |

Those numbers matter: an element positioned outside its display is accepted by
the device but never becomes visible. The client checks for this and logs a
warning rather than failing, so watch for it while developing:

```
Element status y=20 exceeds front height=16
```

You can read the specs from the library instead of hardcoding them:

```python
from busylib import display

spec = display.get_display_spec(display.DisplayName.FRONT)
print(spec.width, spec.height)
```

**Expected output:**

```
72 16
```

This is the front display's drawable width and height in pixels; coordinates
must stay within those bounds to be visible.

## Elements

`display_draw` takes a `DisplayElements` payload holding a list of elements.
Every element carries an `id`, a `type`, coordinates, and the `display` it
belongs to.

```python
from busylib import types

payload = types.DisplayElements(
    application_name="my-app",
    elements=[...],
    priority=None,
    led_notification_color=None,
)
```

`application_name` groups everything your app draws, which is what
`display_clear` and `assets_delete` operate on.

Creating this payload prints nothing and does not update the bar. It becomes
visible only after you pass it to `display_draw`.

### Text

```python
types.TextElement(
    id="status",
    type="text",
    x=2,
    y=4,
    text="BUILDING",
    font="small",
    display=types.DisplayName.FRONT,
)
```

Fonts: `tiny`, `small`, `normal`, `condensed`, `bold`, `large`, `extra_large`,
`global`.

This creates a local element model only. It has no output or device effect
until it is included in a `DisplayElements` payload and drawn.

Alignment (`align`) accepts `top_left`, `top_mid`, `top_right`, `mid_left`,
`center`, `mid_right`, `bottom_left`, `bottom_mid`, `bottom_right`.

Text longer than its `width` can scroll, controlled by `scroll_rate`,
`scroll_start_delay`, and `scroll_repeat_delay`. Use `timeout` or
`display_until` to make an element disappear on its own.

### Images

```python
types.ImageElement(
    id="icon",
    type="image",
    x=0,
    y=0,
    path="icon.png",
    display=types.DisplayName.BACK,
)
```

`path` refers to a file already uploaded for your application — see
[Assets and storage](assets-and-storage.md). Use `stock_path` instead to
reference artwork that ships with the device. `opacity` blends the image
against what's underneath.

This also only creates a payload. Once drawn, the image is rendered on the
back display at `(0, 0)` using the uploaded file named `icon.png`.

## Replacing versus adding

By default a draw call adds to what's on screen. To clear the display before
drawing in one step:

```python
bb.display_draw(payload, clear_before_draw=True)
```

To wipe it entirely:

```python
bb.display_clear(application_name="my-app")
```

**Expected result:** neither call prints output. The first call clears the
whole display before drawing `payload`; the second removes only `my-app`'s
elements and leaves other applications' drawings alone.

## Text that came from somewhere else

Text arriving from an API, a commit message, or a chat room can contain emoji
and control characters the firmware won't render. Let the client strip them:

```python
bb.display_draw(payload, sanitize_text=True)
```

Each substitution is logged, so you can see what was removed and why.
The call itself prints nothing; the bar receives the cleaned text rather than
characters the firmware cannot render.

## Reading the screen back

`frame()` returns the current contents of a display as a `Frame`, which is how
the `remote` example mirrors the bar in a terminal:

```python
frame = bb.frame(0)  # 0 = front, 1 = back
print(len(frame.data))
```

**Expected output for the front display:**

```
3456
```

That is `72 * 16 * 3`: three bytes per front-display pixel. The back display
produces `160 * 80 * 3`, or `38400` bytes.

The bytes are RGB. The device orders colour blue-first and its own protobuf
calls that format `RGB888` anyway, so the library reorders on the way out
rather than passing the firmware's name along — see
[Displays and frames](../api/display.md). `screen()` still returns the same
bytes without the wrapper.

The HTTP endpoint returns base64-encoded, uncompressed framebuffer data despite
advertising `Content-Type: image/bmp`; the client decodes that for you. Live
frames also arrive in the device state stream — see
[Device state](device-state.md).
