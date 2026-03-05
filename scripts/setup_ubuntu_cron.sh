#!/usr/bin/env bash
set -euo pipefail

JOB_NAME="github-topics-trending"
RUN_AT="09:00"
ACTION="install"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE=""

usage() {
  cat <<'EOF'
Usage:
  scripts/setup_ubuntu_cron.sh [options]

Options:
  --run-at HH:MM        Daily run time in local timezone (default: 09:00)
  --project-dir PATH    Project root directory (default: current repo root)
  --log-file PATH       Log file path (default: <project>/data/logs/scheduler.log)
  --status              Show current managed cron entry
  --uninstall           Remove managed cron entry
  -h, --help            Show this help

Examples:
  scripts/setup_ubuntu_cron.sh --run-at 09:00
  scripts/setup_ubuntu_cron.sh --status
  scripts/setup_ubuntu_cron.sh --uninstall
EOF
}

validate_time() {
  local value="$1"
  if [[ ! "$value" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    echo "❌ Invalid time format: $value (expected HH:MM)" >&2
    exit 1
  fi
}

ensure_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "❌ Required command not found: $name" >&2
    exit 1
  fi
}

strip_managed_block() {
  local input="$1"
  local start_marker="$2"
  local end_marker="$3"

  awk -v start="$start_marker" -v end="$end_marker" '
    $0 == start { skip = 1; next }
    $0 == end { skip = 0; next }
    !skip { print }
  ' <<<"$input"
}

show_status() {
  local start_marker="$1"
  local end_marker="$2"
  local current

  current="$(crontab -l 2>/dev/null || true)"
  echo "== managed cron block (${JOB_NAME}) =="
  awk -v start="$start_marker" -v end="$end_marker" '
    $0 == start { printing = 1; print; next }
    printing { print }
    $0 == end { printing = 0 }
  ' <<<"$current"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-at)
      RUN_AT="${2:-}"
      shift 2
      ;;
    --project-dir)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --log-file)
      LOG_FILE="${2:-}"
      shift 2
      ;;
    --status)
      ACTION="status"
      shift
      ;;
    --uninstall)
      ACTION="uninstall"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

validate_time "$RUN_AT"
ensure_command crontab
ensure_command uv

PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [[ ! -f "${PROJECT_DIR}/main.py" ]]; then
  echo "❌ main.py not found under project dir: ${PROJECT_DIR}" >&2
  exit 1
fi

if [[ -z "$LOG_FILE" ]]; then
  LOG_FILE="${PROJECT_DIR}/data/logs/scheduler.log"
fi
mkdir -p "$(dirname "$LOG_FILE")"

UV_BIN="$(command -v uv)"
HOUR="${RUN_AT%:*}"
MINUTE="${RUN_AT#*:}"
START_MARK="# >>> ${JOB_NAME} managed block >>>"
END_MARK="# <<< ${JOB_NAME} managed block <<<"

project_escaped="$(printf '%q' "$PROJECT_DIR")"
uv_escaped="$(printf '%q' "$UV_BIN")"
log_escaped="$(printf '%q' "$LOG_FILE")"
cron_command="cd ${project_escaped} && ${uv_escaped} run main.py >> ${log_escaped} 2>&1"
cron_line="${MINUTE} ${HOUR} * * * ${cron_command}"

if [[ "$ACTION" == "status" ]]; then
  show_status "$START_MARK" "$END_MARK"
  exit 0
fi

current_cron="$(crontab -l 2>/dev/null || true)"
cleaned_cron="$(strip_managed_block "$current_cron" "$START_MARK" "$END_MARK")"

if [[ "$ACTION" == "uninstall" ]]; then
  printf '%s\n' "$cleaned_cron" | crontab -
  echo "✅ Removed managed cron entry for ${JOB_NAME}."
  exit 0
fi

new_cron="$cleaned_cron"
if [[ -n "$new_cron" && "${new_cron: -1}" != $'\n' ]]; then
  new_cron+=$'\n'
fi
new_cron+="$START_MARK"$'\n'
new_cron+="$cron_line"$'\n'
new_cron+="$END_MARK"$'\n'

printf '%s' "$new_cron" | crontab -

echo "✅ Cron installed: daily at ${RUN_AT} (local time)"
echo "Log file: ${LOG_FILE}"
echo
show_status "$START_MARK" "$END_MARK"
echo
echo "手动立即运行一次："
echo "  cd ${PROJECT_DIR} && ${UV_BIN} run main.py"
