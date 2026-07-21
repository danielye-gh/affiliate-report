#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "========================================"
echo " Affiliate Report - macOS / Linux Setup"
echo "========================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Install Python 3.9+."
  exit 1
fi

echo "[1/3] Creating virtual environment .venv ..."
if [[ -x .venv/bin/python ]]; then
  if ! .venv/bin/python --version >/dev/null 2>&1; then
    echo "      Broken .venv detected - recreating ..."
    rm -rf .venv
    python3 -m venv .venv
  else
    echo "      Already exists, skipping."
  fi
else
  if [[ -d .venv ]]; then
    echo "      Incomplete .venv detected - recreating ..."
    rm -rf .venv
  fi
  python3 -m venv .venv
fi

echo "[2/3] Installing dependencies ..."
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .

echo "[3/3] Checking config ..."
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "      Copied .env.example to .env - edit .env with API credentials."
  else
    echo "      .env not found - contact admin for credentials."
  fi
else
  echo "      .env already exists."
fi

mkdir -p data/reports data/config

echo
echo "Setup complete."
echo "Next: edit .env, then run:"
echo "  ./report.sh                 # GUI"
echo "  ./report.sh 2026 5          # CLI full run"
echo "  ./report.sh 2026 5 skip     # skip API fetch"
echo
