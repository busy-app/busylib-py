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

On current firmware the access key is enforced only on connections arriving
over Wi-Fi — USB and localhost traffic skips the check — so a bar reached at
`10.0.4.20` usually needs no token whatever access mode it is in. Treat that
as an observation about the firmware in front of you rather than a guarantee,
and handle a `403` on the USB path too.

Over Wi-Fi, if the access mode is set to `key`, every request needs that token
and unauthenticated calls come back as `403 Forbidden`. The key is a 4–10
digit PIN:

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

## Helpers for endpoints that no longer exist

A few helpers target device endpoints that current firmware doesn't serve at
all. They fail immediately with `BusyBarRemovedEndpointError` and name their
replacement, rather than letting an opaque `404` come back:

| Helper | Use instead |
| --- | --- |
| `account_profile()`, `account_profile_set()` | `account_backend()`, `account_backend_set()` |
| `wifi_enable()`, `wifi_disable()` | `wifi_connect()`, `wifi_disconnect()` |

These did exist once — `wifi/enable` and `wifi/disable` up to firmware 0.2.0,
`account/profile` from 0.6.0-rc to 0.8.1 — but every firmware since serves
none of them, and the library targets a far newer API than those bars run. To
talk to firmware that old, pin a `busylib` version from the same era, as the
versioning policy describes; `api_request()` remains the escape hatch.

This is deliberately distinct from `BusyBarAPIVersionError`: updating the
firmware won't help, because the endpoint was withdrawn rather than added
later. `method_compatibility()` reports the same information:

```python
bb.method_compatibility("account_profile")
# {'path': '/api/account/profile', 'method': 'GET',
#  'status': 'removed', 'replacement': 'account_backend()'}
```
