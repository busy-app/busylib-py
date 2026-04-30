#!/bin/sh
set -e

ADDR=${1:-"10.0.4.20"}
shift

TOKEN=${1:-}
shift

# workdir must be root of git
export PYTHONPATH=.

# simple run command
uv run python examples/bc/main.py \
    --addr ${ADDR} \
    --token ${TOKEN} \
    $@
