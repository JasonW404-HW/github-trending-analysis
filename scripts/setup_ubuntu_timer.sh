#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="github-topics-trending"
RUN_AT="09:00"
DRY_RUN=0
ACTION="install"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

usage() {
  cat <<'EOF'
Usage:
  scripts/setup_ubuntu_timer.sh [options]

Options:
  --run-at HH:MM        Daily run time in local timezone (default: 09:00)
  --project-dir PATH    Project root directory (default: current repo root)
  --service-name NAME   Systemd unit base name (default: github-topics-trending)
  --dry-run             Print generated unit files without applying
  --status              Show current timer/service status
  --uninstall           Remove timer/service from user systemd
  -h, --help            Show this help

Examples:
  scripts/setup_ubuntu_timer.sh --run-at 09:00
  scripts/setup_ubuntu_timer.sh --status
  scripts/setup_ubuntu_timer.sh --uninstall
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

ensure_user_systemd_bus() {
  if ! systemctl --user show-environment >/dev/null 2>&1; then
    cat <<'EOF' >&2
❌ 当前环境不可用 systemd --user（无法连接 user bus）。
可改用 cron 方案：
  scripts/setup_ubuntu_cron.sh --run-at 09:00
EOF
    exit 1
  fi
}

write_unit_files() {
  local uv_bin="$1"
  local service_file="$2"
  local timer_file="$3"

  cat >"$service_file" <<EOF
[Unit]
Description=GitHub Topics Trending daily pipeline
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
ExecStart=${uv_bin} run main.py
Environment=PYTHONUNBUFFERED=1
EOF

  cat >"$timer_file" <<EOF
[Unit]
Description=Run GitHub Topics Trending daily at ${RUN_AT} (local time)

[Timer]
OnCalendar=*-*-* ${RUN_AT}:00
Persistent=true
AccuracySec=1m
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF
}

show_status() {
  echo "== systemd user timer status =="
  systemctl --user status "${SERVICE_NAME}.timer" --no-pager || true
  echo
  echo "== next schedule =="
  systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager || true
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
    --service-name)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
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
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
TIMER_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"

if [[ "$ACTION" == "status" ]]; then
  show_status
  exit 0
fi

if [[ "$ACTION" == "uninstall" ]]; then
  echo "🧹 Removing ${SERVICE_NAME} timer/service from user systemd..."
  systemctl --user disable --now "${SERVICE_NAME}.timer" >/dev/null 2>&1 || true
  rm -f "$SERVICE_FILE" "$TIMER_FILE"
  systemctl --user daemon-reload
  echo "✅ Removed: ${SERVICE_FILE} and ${TIMER_FILE}"
  exit 0
fi

ensure_command systemctl
ensure_command uv
ensure_user_systemd_bus
UV_BIN="$(command -v uv)"

if [[ ! -f "${PROJECT_DIR}/main.py" ]]; then
  echo "❌ main.py not found under project dir: ${PROJECT_DIR}" >&2
  exit 1
fi

mkdir -p "$SYSTEMD_USER_DIR"

if [[ "$DRY_RUN" -eq 1 ]]; then
  tmp_service="$(mktemp)"
  tmp_timer="$(mktemp)"
  write_unit_files "$UV_BIN" "$tmp_service" "$tmp_timer"

  echo "== ${SERVICE_FILE} =="
  cat "$tmp_service"
  echo
  echo "== ${TIMER_FILE} =="
  cat "$tmp_timer"

  rm -f "$tmp_service" "$tmp_timer"
  exit 0
fi

write_unit_files "$UV_BIN" "$SERVICE_FILE" "$TIMER_FILE"

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.timer"

echo "✅ Timer installed: ${SERVICE_NAME}.timer"
systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager

echo
echo "手动立即运行一次："
echo "  systemctl --user start ${SERVICE_NAME}.service"
echo
echo "查看最近日志："
echo "  journalctl --user -u ${SERVICE_NAME}.service -n 200 --no-pager"
echo
echo "如需在注销后仍继续触发定时任务，请执行："
echo "  sudo loginctl enable-linger ${USER}"
