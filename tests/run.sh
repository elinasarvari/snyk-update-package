#!/usr/bin/env bash
# Run the whole test suite. Safe: uses throwaway sandboxes, never your real repos or GitHub.
#   tests/run.sh              # fast suite (~40s)
#   RUN_MAVEN_TESTS=1 tests/run.sh   # also run a real Maven build of a tiny project
# Compact by default (a line of dots + the result) - cheap for people and assistants. Add -v for one line per test.
cd "$(dirname "$0")/.." && exec python3 -I -m unittest discover -s tests -p 'test_*.py' "$@"
