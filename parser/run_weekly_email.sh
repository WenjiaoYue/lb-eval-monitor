#!/usr/bin/env bash
# Weekly lb-eval stats email runner (intended for cron, every Friday).
# Edit RECIPIENTS and SENDER below, then schedule with crontab (see bottom).
set -euo pipefail

# --- config -----------------------------------------------------------------
SENDER="wenjiao.yue@intel.com"

# One -r per recipient. Add as many as you need.
RECIPIENTS=(
  -r wenjiao.yue@intel.com
  -r kaokao.lv@intel.com
)

# Secret file holding the line: MAIL_PASSWORD=xxxxx  (chmod 600 it!)
SECRET_FILE="$HOME/.lb_eval_mail.env"
# ----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load MAIL_PASSWORD from the secret file (not stored in this script or crontab).
if [[ -f "$SECRET_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$SECRET_FILE"; set +a
fi

if [[ -z "${MAIL_PASSWORD:-}" ]]; then
  echo "MAIL_PASSWORD not set. Put 'MAIL_PASSWORD=...' in $SECRET_FILE (chmod 600)." >&2
  exit 1
fi

# On Friday the default window = previous Friday's 7 days, so no --start/--end needed.
exec python3 parser/send_weekly_stats_email.py \
  -e "$SENDER" \
  "${RECIPIENTS[@]}" \
  --insecure-smtp-tls

# ---------------------------------------------------------------------------
# One-time setup:
#   1) echo 'MAIL_PASSWORD=your_password_here' > ~/.lb_eval_mail.env
#      chmod 600 ~/.lb_eval_mail.env
#   2) chmod +x parser/run_weekly_email.sh
#   3) crontab -e   and add (runs every Friday 09:00 local time):
#      0 9 * * 5 /home/sdp/wenjiao/5_14/lb-eval-monitor/parser/run_weekly_email.sh >> /home/sdp/wenjiao/5_14/lb-eval-monitor/weekly_email.log 2>&1
# ---------------------------------------------------------------------------
