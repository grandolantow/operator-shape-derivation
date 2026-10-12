#!/usr/bin/env bash
set -euo pipefail

script_dir=${BASH_SOURCE[0]}
if [[ "$script_dir" == */* ]]; then
  script_dir=${script_dir%/*}
else
  script_dir=.
fi
script_dir="$(cd -- "$script_dir" && pwd -P)"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'install-claude: python3 is required\n' >&2
  exit 127
fi

# The Python entry point checks all sources and existing task entries before
# writing. It defaults to dry-run and never invokes either vendor init.sh.
exec python3 "$script_dir/init_claude_workflow.py" "$@"
