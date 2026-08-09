#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
mkdir -p data/logs reports/daily
exec .venv/bin/python -m backend.services.daily_run --financial-scope watchlist
