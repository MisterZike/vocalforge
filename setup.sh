#!/usr/bin/env bash
# VocalForge setup - creates a local venv and installs the two dependencies.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "Creating virtualenv in .venv ..."
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo
echo "VocalForge is ready."
echo "  Web UI : ./vf ui"
echo "  CLI    : ./vf render \"we are the robots\" -p daft_robot -o out/robot.wav"
