#!/bin/sh
set -e

export BUSY_LAN_TOKEN=5422

uv run python -m examples.remote \
    --addr 192.168.50.20 \
    --log-level DEBUG \
    $*
