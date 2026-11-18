#!/bin/bash
# -------------------------------------------------------------------------------
#    FILE: run_lint.sh
# PURPOSE: Checks the code for mistakes, the same checks as the GitHub CI:
#            - Python: the pyflakes checks of flake8 (undefined and unused
#              names, imports, f-strings, repeated dictionary keys, ...).
#              Not code style.
#            - shell scripts: shellcheck warnings and errors.
#            - spelling mistakes in code, comments and text: codespell (its
#              settings, the words to ignore, are in .codespellrc).
#          A line can be skipped with a comment, for example:
#              import smbus  # noqa: F401  (checks the library is installed)
#              # shellcheck disable=SC2024
#
#   USAGE: from anywhere (needs uv: https://docs.astral.sh/uv/):
#              bash tests/run_lint.sh
#
# -------------------------------------------------------------------------------

FLAKE8_VERSION="7.3.0"
# the shellcheck-py package version (it installs shellcheck 0.10.0)
SHELLCHECK_VERSION="0.10.0.1"
CODESPELL_VERSION="2.3.0"

GENMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$GENMON" || exit 2

FAILED=0

echo "=== Python (flake8 $FLAKE8_VERSION, pyflakes checks)"
git ls-files -z '*.py' | xargs -0 uvx "flake8==$FLAKE8_VERSION" --select=F || FAILED=1

echo "=== Shell scripts (shellcheck)"
git ls-files -z '*.sh' | xargs -0 uvx --from "shellcheck-py==$SHELLCHECK_VERSION" shellcheck --severity=warning || FAILED=1

echo "=== Spelling (codespell $CODESPELL_VERSION)"
git ls-files -z | xargs -0 uvx "codespell==$CODESPELL_VERSION" || FAILED=1

if [ "$FAILED" -ne 0 ]; then
  echo "Lint found problems"
  exit 1
fi
echo "Lint OK"
