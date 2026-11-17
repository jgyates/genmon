#!/bin/bash
# -------------------------------------------------------------------------------
#    FILE: run_python_versions.sh
# PURPOSE: Run the tests in tests/ on each Python version genmon supports, in
#          temporary environments made by uv (https://docs.astral.sh/uv/). uv
#          downloads a Python version it does not find on the computer. Nothing
#          is installed in genmon's own Python environment.
#
#          The versions are those of Raspberry Pi OS: 3.9 (Bullseye), 3.11
#          (Bookworm) and 3.13 (Trixie).
#
#   USAGE: from anywhere:
#              tests/run_python_versions.sh            the default versions
#              tests/run_python_versions.sh 3.9 3.14   these versions
#          with GENMON_CAPTURES set (see test_genmon_sim.py) the simulator tests
#          run too.
# -------------------------------------------------------------------------------

VERSIONS="${*:-3.9 3.11 3.13}"
GENMON="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v uv >/dev/null; then
  echo "uv is not installed, see https://docs.astral.sh/uv/getting-started/installation/"
  exit 2
fi

REQUIREMENTS="$GENMON/tests/requirements.txt"
if [ -n "$GENMON_CAPTURES" ]; then
  REQUIREMENTS="$GENMON/tests/requirements-sim.txt"
  # the tests run genmon in other folders
  export GENMON_CAPTURES="$(cd "$GENMON_CAPTURES" && pwd)"
fi

cd "$GENMON" || exit 2
FAILED=""
for VERSION in $VERSIONS; do
  echo "=== Python $VERSION"
  if ! uv run --no-project --python "$VERSION" --with-requirements "$REQUIREMENTS" \
       python -m unittest discover -s tests; then
    FAILED="$FAILED $VERSION"
  fi
done

echo
if [ -n "$FAILED" ]; then
  echo "FAILED on Python:$FAILED"
  exit 1
fi
echo "OK on Python: $VERSIONS"
