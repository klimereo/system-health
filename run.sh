#!/bin/sh
# Run from source (development). Creates .venv on first use.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m syshealth "$@"
