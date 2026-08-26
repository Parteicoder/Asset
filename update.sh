#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

git pull --ff-only
python3 scripts/selbsttest.py

echo "Aktualisiert."
