# Device discovery

BUSY Bars announce themselves over mDNS, so an address doesn't have to be
hardcoded.

```python
from busylib import BusyBarDevices

for device in BusyBarDevices.discover():
    print(device.name, device.get_address("over_wifi"))
```

!!! note
    Shipped firmware doesn't advertise the `_busybar._tcp` service yet, so
    `discover()` can legitimately return an empty list. A USB-connected bar
    is still reachable at its well-known static address, `10.0.4.20`.

::: busylib.devices
