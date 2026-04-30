# Yandex Rasp Example

Render upcoming departures/arrivals for a station from Yandex Rasp API on Busy Bar.

API reference:
- https://yandex.ru/dev/rasp/doc/ru/reference/schedule-on-station

## Setup

```bash
export BUSYBAR_RASP_API_KEY="<your_yandex_rasp_api_key>"
export BUSYBAR_RASP_DEPARTURE_STATION="s9600213"
export BUSYBAR_RASP_DESTINATION_STATION="c213" # optional
export BUSYBAR_RASP_TRANSPORT_TYPES="bus" # optional
```

`.env` is loaded automatically by searching upward from `examples/rasp`.

Optional Busy Bar connection parameters:

```bash
export BUSYBAR_RASP_ADDR="http://10.0.4.20"
export BUSYBAR_RASP_TOKEN="<busybar_token>"
export BUSYBAR_RASP_WARNING_THRESHOLDS="40,30,20,10"
export BUSYBAR_RASP_CACHE_FILE="examples/rasp/.cache/segments.json"
```

## Run

```bash
python -m examples.rasp
```

Override stations from CLI:

```bash
python -m examples.rasp --departure-station s9600213
python -m examples.rasp --departure-station s9600213 --destination-station c213
python -m examples.rasp -f s9600213 -t c213
python -m examples.rasp -f s9600213 -t c213 --transport-types bus
```

Traffic-light rendering with custom thresholds:

```bash
python -m examples.rasp -f s9600213 -t c213 --warning-thresholds 40,30,20,10
```

Route rotation:
- by default keeps 6 nearest routes in memory;
- shows one page (2 routes) for 5 seconds and rotates to the next page.

```bash
python -m examples.rasp -f s9600213 -t c213 --max-routes 6 --rotate-every-sec 5
```

Cache behavior:
- After successful fetch, segments are saved to `--cache-file`.
- On next start, cache is loaded first and countdown is recalculated immediately.
- If API currently returns empty list, periodic refetch continues with `--refresh-without-schedule-sec`.

Print formatted raw response without Busy Bar rendering:

```bash
python -m examples.rasp --api-key <key> --departure-station s9600213 --print-only
python -m examples.rasp -k <key> -f s9600213 -t c213 --print-only
```
