#!/bin/sh
set -e

export BUSYLIB_LAN_TOKEN=5422

uv run python -m examples.bc \
    --addr 192.168.50.20 \
    --log-level DEBUG \
    $*
