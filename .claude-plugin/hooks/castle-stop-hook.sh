#!/bin/bash
# Cognitive Castle Stop Hook — thin wrapper calling the Python CLI.
# All logic lives in cognitive_castle.hooks_cli for cross-harness extensibility.
run_castle_hook() {
  if command -v castle >/dev/null 2>&1; then
    castle hook run "$@"
    return $?
  fi
  if command -v python3 >/dev/null 2>&1 && python3 -c "import cognitive_castle" >/dev/null 2>&1; then
    python3 -m cognitive_castle hook run "$@"
    return $?
  fi
  if command -v python >/dev/null 2>&1 && python -c "import cognitive_castle" >/dev/null 2>&1; then
    python -m cognitive_castle hook run "$@"
    return $?
  fi
  echo "Cognitive Castle hook error: could not find a runnable castle command or cognitive_castle module" >&2
  return 1
}

run_castle_hook --hook stop --harness claude-code
