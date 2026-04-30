#!/bin/sh
set -e

ADDR="192.168.50.20"
ADDR="10.0.4.20"
ADDR="https://cloud.dev.busy.app"

BIN=$1
shift

# local
export BUSY_LAN_TOKEN="5422"
# account
export BUSY_CLOUD_TOKEN="Wo-ya5FdOqeZppblL69qe0orjZIGnUdWA0nkZAdi7-k"
# bar
export BUSY_CLOUD_TOKEN="nEXx2sX2avIZbh0KW9q7W_B-3gMZ4THhxBBkqSkJST4"

uv run python -m examples.${BIN} \
    --addr ${ADDR} \
    --log-level DEBUG \
    --log-file ${BIN}.log \
    $@
