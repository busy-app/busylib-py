# Clients

`BusyBar` is the synchronous client and `AsyncBusyBar` is its `async`/`await`
counterpart. Both compose the same set of endpoint mixins, so the method
surface is identical apart from the coroutines.

```python
from busylib import AsyncBusyBar, BusyBar

bb = BusyBar("10.0.4.20")

async_bb = AsyncBusyBar(addr="10.0.4.20", token="my-access-key")
```

Creating either client has no terminal output and does not contact the device.
The first endpoint call performs the connection; see the
[quick start](../index.md) for its expected output.

::: busylib.client.BusyBar
    options:
      inherited_members: true

::: busylib.client.AsyncBusyBar
    options:
      inherited_members: true

## Prepared requests

::: busylib.client.PreparedRequest
