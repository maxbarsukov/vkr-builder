#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Name the tool answers to in usage lines, hints and help.
export VKR_PROG="./$(basename "${BASH_SOURCE[0]}")"

find_python() {
  local cmd candidate
  for cmd in python3 python py; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      continue
    fi
    if [[ "$cmd" == "py" ]]; then
      candidate=(py -3)
    else
      candidate=("$cmd")
    fi
    if "${candidate[@]}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
      PYTHON=("${candidate[@]}")
      return 0
    fi
  done
  return 1
}

if ! find_python; then
  printf '
  x Python 3.10 or newer was not found
' >&2
  printf '    tried: python3, python, py -3

' >&2
  printf '    try  installing Python, or adding it to PATH

' >&2
  exit 1
fi

exec "${PYTHON[@]}" "$ROOT/main.py" "$@"
