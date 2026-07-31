# Connecting to a bar

## Addresses

A bar plugged in over USB comes up as a network device at the well-known
address **`10.0.4.20`**, with no Wi-Fi configuration needed. Once it joins a
network it also gets a normal address on that network, and either works:

```python
from busylib import BusyBar

bb = BusyBar("10.0.4.20")          # over USB
bb = BusyBar("192.168.1.20")       # over Wi-Fi
```

## Access keys

If the bar's HTTP access mode is set to `key`, every request needs a token and
unauthenticated calls come back as `403 Forbidden`:

```python
bb = BusyBar("10.0.4.20", token="your-access-key")
```

The current mode is readable without authentication, which is what the setup
and `remote` examples use to decide whether to ask for a key:

```python
info = bb.access()
print(info.mode, info.key_valid)  # 'key' True
```

!!! note
    `key_valid` reports whether the *device* has a key configured, not whether
    the token you supplied is the right one. Don't use it to decide that no
    token is needed.

## Discovery

Rather than hardcoding an address:

```python
from busylib import BusyBarDevices

for device in BusyBarDevices.discover():
    print(device.name, device.get_address("over_wifi"))
```

Discovery browses for the `_busybar._tcp` mDNS service and classifies each
address it finds: anything in `10.0.4.*` is treated as the USB link, everything
else as Wi-Fi.

!!! warning
    Shipped firmware does not advertise `_busybar._tcp` yet, so `discover()`
    can legitimately return an empty list. The `remote` and `setup` examples
    fall back to `10.0.4.20` in that case.

## Closing the client

Both clients hold an HTTP connection pool. Use them as context managers, or
close them explicitly:

```python
with BusyBar("10.0.4.20") as bb:
    ...

async with AsyncBusyBar("10.0.4.20") as bb:
    ...
```

## Timeouts and retries

Requests carry a default timeout and are retried a few times on transport
errors. Override per call where it matters — uploads, for instance, accept a
longer timeout:

```python
bb.assets_upload("my-app", "big.png", data, timeout=60.0)
```
