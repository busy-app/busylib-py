# Device discovery

BUSY Bars announce themselves over mDNS, so an address doesn't have to be
hardcoded.

```python
from busylib import BusyBarDevices

for device in BusyBarDevices.discover():
    print(device.name, device.get_address("over_wifi"))
```

**Example output when a bar advertises itself:**

```
Front desk 192.168.1.20
```

Each line is the device name and its Wi-Fi address. Empty output means no bars
were discovered, not that the library failed; use `10.0.4.20` for a
USB-connected bar in that case.

!!! note
    Shipped firmware doesn't advertise itself under `_http._tcp` yet, so
    `discover()` can legitimately return an empty list. A USB-connected bar
    is still reachable at its well-known static address, `10.0.4.20`.

::: busylib.devices
