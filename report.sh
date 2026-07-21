#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "[ERROR] Not installed yet. Run ./setup.sh first."
  exit 1
fi

if ! .venv/bin/python --version >/dev/null 2>&1; then
  echo "[ERROR] Virtual environment is broken."
  echo "Delete .venv, then run ./setup.sh again."
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "[ERROR] .env not found. Run ./setup.sh and add API credentials."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
PY=".venv/bin/python"

if [[ $# -eq 0 ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "macOS: system Tk/GUI often crashes on Sequoia (1507/1506 abort)."
    echo "Use CLI to generate reports:"
    echo "  ./report.sh 2026 5"
    echo "  ./report.sh 2026 5 skip"
    echo
    echo "To force GUI anyway:  ./report.sh gui"
    echo "To fix GUI properly:   brew install python@3.12 python-tk@3.12"
    echo "                       rm -rf .venv && /opt/homebrew/bin/python3.12 -m venv .venv && ./setup.sh"
    exit 1
  fi
  exec "$PY" -u -m affiliate_report.gui.report_app
fi

if [[ "${1:-}" == "gui" ]]; then
  exec "$PY" -u -m affiliate_report.gui.report_app
fi

if [[ "${1:-}" == "update" ]]; then
  exec "$PY" -u -m affiliate_report.updater
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: ./report.sh [YEAR MONTH [skip]]"
  echo
  echo "Run without args to open the GUI."
  echo
  echo "Examples:"
  echo "  ./report.sh 2026 5          full run"
  echo "  ./report.sh 2026 5 skip     skip API fetch"
  exit 1
fi

YEAR="$1"
MONTH="$2"
mkdir -p data/reports
MM="$(printf '%02d' "$MONTH")"
OUTPUT="data/reports/Affiliate_report_${YEAR}_${MM}.xlsx"

# macOS ships Bash 3.2; with `set -u`, empty arrays are "unbound".
SKIP_FETCH=0
if [[ "${3:-}" == "skip" || "${3:-}" == "SKIP" ]]; then
  SKIP_FETCH=1
fi

echo "========================================"
echo " Affiliate report for ${YEAR}-${MONTH}"
echo "========================================"
echo

if [[ "$SKIP_FETCH" -eq 1 ]]; then
  affiliate-report report --year "$YEAR" --month "$MONTH" --output "$OUTPUT" --skip-fetch
else
  affiliate-report report --year "$YEAR" --month "$MONTH" --output "$OUTPUT"
fi

echo
echo "Done. Report saved:"
echo "  $(pwd)/$OUTPUT"
echo
