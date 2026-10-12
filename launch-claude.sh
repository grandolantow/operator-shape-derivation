#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s --task-dir DIR [--task-file FILE] [--resume]\n' "${0##*/}" >&2
}

task_dir=
task_file=TASK.md
resume=false
while (($#)); do
  case "$1" in
    --task-dir)
      (($# >= 2)) || { usage; exit 2; }
      task_dir=$2
      shift 2
      ;;
    --task-file)
      (($# >= 2)) || { usage; exit 2; }
      task_file=$2
      shift 2
      ;;
    --resume)
      resume=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$task_dir" && -d "$task_dir" ]] || { printf 'launch-claude: task directory is missing\n' >&2; exit 2; }
task_dir="$(cd -- "$task_dir" && pwd -P)"
[[ -n "$task_file" && "$task_file" != */* && "$task_file" != *..* ]] || {
  printf 'launch-claude: task file must be a filename inside the task directory\n' >&2
  exit 2
}
[[ -f "$task_dir/$task_file" && ! -L "$task_dir/$task_file" ]] || {
  printf 'launch-claude: task file is missing or linked\n' >&2
  exit 2
}
[[ -f "$task_dir/.claude/workflow-bootstrap-manifest.json" ]] || {
  printf 'launch-claude: initialize the task-local workflow first\n' >&2
  exit 2
}
command -v claude >/dev/null 2>&1 || { printf 'launch-claude: claude CLI is required\n' >&2; exit 127; }

cd -- "$task_dir"
export IS_SANDBOX=1
prompt="Read $task_file and the task-local .claude/skills/ascend-op-workflow/SKILL.md, then execute the authorized workflow. Preserve the task's stop conditions and report actual evidence."
if "$resume"; then
  exec claude --dangerously-skip-permissions -c "$prompt"
else
  exec claude --dangerously-skip-permissions "$prompt"
fi
