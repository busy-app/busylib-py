# Firmware Bugs & Crash Triggers

## Crash Triggers
Requests that cause the device to hang or become unresponsive.

| Endpoint | Method | Payload | Result | Confirmed |
|----------|--------|---------|--------|-----------|
| `/api/assets/upload` | POST | Empty (no params/body) | Timeout -> Crash | **YES** |
| `/api/input` | GET | Plain HTTP (no Upgrade) | 405 Method Not Allowed | No |
| `/api/display/draw` | POST | Invalid JSON `"{invalid"` | 400 Bad Request | No |
