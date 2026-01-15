#!/bin/sh
set -e

ADDR="192.168.50.20"
ADDR="10.0.4.20"

BIN=$1
shift

export BUSY_LAN_TOKEN="5422"
export BUSY_CLOUD_TOKEN="Wo-ya5FdOqeZppblL69qe0orjZIGnUdWA0nkZAdi7-k"

uv run python -m examples.${BIN} \
    --addr ${ADDR} \
    --log-level DEBUG \
    --log-file ${BIN}.log \
    $@
