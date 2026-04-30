# Quick Start

## Install

```bash
python -m pip install busylib
```

For local development inside this repository:

```bash
python -m pip install -e . --group dev
```

## Minimal Client Setup

```python
from busylib.client import AsyncBusyBar

client = AsyncBusyBar(addr="192.168.1.42", token="<token>")
```

## Next Step

Continue with the showcase walkthrough:

- [Now Playing](showcase/now-playing.md)
