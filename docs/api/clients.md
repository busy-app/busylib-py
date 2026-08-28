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

## Using your own HTTP session

A host application often already owns a connection pool and wants everything
to go through it. Home Assistant, for example, hands integrations a shared
`aiohttp` session; opening a second pool beside it wastes connections and
sidesteps the host's timeouts and tracing.

`httpx2` transports are the seam for that, and `busylib[aiohttp]` ships one:

```python
from busylib import AsyncBusyBar
from busylib.transports import AiohttpTransport

bb = AsyncBusyBar("10.0.4.20", transport=AiohttpTransport(session))
```

Every client method then rides the session you passed. The session is
borrowed, never closed — `aclose()` on the client leaves it usable, because
whoever handed it over still owns it.

Status streaming is unaffected either way: it speaks WebSocket through
`websockets` rather than the HTTP transport, so it keeps its own connection.

::: busylib.transports
