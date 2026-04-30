# Schedules Example

This example fetches TfL bus arrivals for a stop and renders the next buses on Busy Bar.

## Setup

1. Set your TfL API key:

```bash
export BUSYBAR_SCHEDULES_PRIMARY_KEY="<your_primary_key>"
```

2. Optionally set defaults in environment:

```bash
export BUSYBAR_SCHEDULES_ADDR="http://10.0.4.20"   # optional
export BUSYBAR_SCHEDULES_TOKEN="<busybar_token>"    # optional
export BUSYBAR_SCHEDULES_STOP_ID="490004733C"
export BUSYBAR_SCHEDULES_DISPLAY="front"
```

## Run

```bash
python -m examples.schedules.main
```

Override stop id from CLI:

```bash
python -m examples.schedules.main --stop-id 490004733C
```

Pass Busy Bar token from CLI:

```bash
python -m examples.schedules.main --token <busybar_token>
```

## How to configure credentials

- Replace the stop ID. You can get it via the TfL StopPoint API (https://api.tfl.gov.uk/StopPoint/Search/oxford) and use the returned `id` value (it looks like `490004733C`).
- Replace the PRIMARY KEY. You can get it for free after registration at https://api-portal.tfl.gov.uk. After registration, enable the free subscription `500 Requests per min`; the key will then appear in your personal account.
