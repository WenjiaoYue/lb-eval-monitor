#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import ssl
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


DEFAULT_RECIPIENTS = ["wenjiao.yue@intel.com"]
SMTP_SERVER = "smtpauth.intel.com"
SMTP_PORT = 587
INTEL_WHITELIST = {"wenjiao", "lvkaokao", "Haihao", "INC4AI", "Xuehao"}


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def previous_friday_start(now: datetime) -> datetime:
    today = now.astimezone(timezone.utc).date()
    days_since_friday = (today.weekday() - 4) % 7
    if days_since_friday == 0 and now.time() < time(0, 0):
        days_since_friday = 7
    return datetime.combine(today - timedelta(days=days_since_friday), time.min, tzinfo=timezone.utc)


def default_report_window(now: datetime) -> tuple[datetime, datetime]:
    end = previous_friday_start(now)
    return end - timedelta(days=7), end


def load_runs(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return [item for item in payload if isinstance(item, dict)]


def refresh_runs(source_repo: str, source_branch: str) -> Path:
    """Fetch the remote repo and regenerate runs.json (with submitter/lifecycle
    data) into a fresh temp dir, so the report never relies on a stale watcher."""
    import sys
    import tempfile

    sys.path.insert(0, str(Path(__file__).parent))
    from scan_results import fetch_remote_results, scan_results

    out_dir = Path(tempfile.mkdtemp(prefix="lb_eval_weekly_"))
    source_root = fetch_remote_results(repo=source_repo, branch=source_branch)
    scan_results(
        source_root=source_root,
        output_dir=out_dir,
        source_repo=source_repo,
        source_branch=source_branch,
    )
    return out_dir / "runs.json"


def normalized_orgs(run: dict[str, Any]) -> list[str]:
    orgs = run.get("orgs") or []
    if not isinstance(orgs, list):
        return []
    return [str(org).strip() for org in orgs if str(org).strip()]


def is_intel_submission(run: dict[str, Any]) -> bool:
    orgs = normalized_orgs(run)
    if any(org.lower() == "intel" for org in orgs):
        return True
    submitter = run.get("submitted_by")
    return not orgs and bool(submitter) and str(submitter) in INTEL_WHITELIST


def company_from_run(run: dict[str, Any]) -> str:
    model_id = str(run.get("model_id") or "")
    if "/" in model_id:
        return model_id.split("/", 1)[0] or "unknown"
    return str(run.get("owner") or "unknown")


def model_from_run(run: dict[str, Any]) -> str:
    return str(run.get("model_id") or run.get("artifact_name") or "unknown")


def run_time(run: dict[str, Any]) -> datetime | None:
    return parse_iso_datetime(str(run.get("run_timestamp") or ""))


def in_window(run: dict[str, Any], start: datetime, end: datetime) -> bool:
    timestamp = run_time(run)
    return timestamp is not None and start <= timestamp < end


def count_submitters(runs: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for run in runs:
        submitter = run.get("submitted_by")
        if submitter:
            counter[str(submitter)] += 1
    return counter


def count_companies(runs: list[dict[str, Any]]) -> Counter[str]:
    return Counter(company_from_run(run) for run in runs)


def format_window_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def text_bar(value: int, max_value: int, width: int = 18) -> str:
    if max_value <= 0 or value <= 0:
        return ""
    filled = max(1, round((value / max_value) * width))
    return "#" * filled


def html_bar(value: int, max_value: int, color: str) -> str:
    width = 0 if max_value <= 0 else max(6, round((value / max_value) * 100))
    return (
        '<div style="width:160px;height:12px;background:#cbd5e1;border-radius:999px;overflow:hidden;">'
        f'<div style="width:{width}%;height:12px;background:{color};border-radius:999px;"></div>'
        "</div>"
    )


def top_delta_rows(total: Counter[str], weekly: Counter[str], limit: int) -> list[tuple[str, int, int]]:
    names = set(total) | set(weekly)
    rows = [(name, total.get(name, 0), weekly.get(name, 0)) for name in names if weekly.get(name, 0) > 0]
    return sorted(rows, key=lambda item: (-item[2], -item[1], item[0].lower()))[:limit]


def build_text_report(
    runs: list[dict[str, Any]],
    weekly_runs: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    top_limit: int,
) -> str:
    total_submitters = count_submitters(runs)
    weekly_submitters = count_submitters(weekly_runs)
    total_companies = count_companies(runs)
    weekly_companies = count_companies(weekly_runs)
    intel_weekly = sum(1 for run in weekly_runs if is_intel_submission(run))
    intel_total = sum(1 for run in runs if is_intel_submission(run))

    lines = [
        "lb-eval Weekly Statistics",
        f"Report period: {format_window_date(start)} 00:00 UTC ~ {format_window_date(end)} 00:00 UTC",
        "",
        "Summary",
        f"Total submissions: {len(runs)} (+{len(weekly_runs)} this week)",
        f"Unique submitters: {len(total_submitters)} (+{len([name for name, count in weekly_submitters.items() if count > 0])} active this week)",
        f"Model company records: {sum(total_companies.values())} (+{sum(weekly_companies.values())} this week)",
        f"Intel submissions: {intel_total} (+{intel_weekly} this week)",
        f"Non-Intel submissions: {len(runs) - intel_total} (+{len(weekly_runs) - intel_weekly} this week)",
        "",
        "Top Submitters This Week",
    ]

    submitter_rows = top_delta_rows(total_submitters, weekly_submitters, top_limit)
    max_submitter_delta = max([row[2] for row in submitter_rows], default=0)
    if submitter_rows:
        for name, total_count, weekly_count in submitter_rows:
            lines.append(f"{name}: {total_count} total, +{weekly_count} this week {text_bar(weekly_count, max_submitter_delta)}")
    else:
        lines.append("No new submitter activity this week.")

    lines.extend(["", "Top Model Companies This Week"])
    company_rows = top_delta_rows(total_companies, weekly_companies, top_limit)
    max_company_delta = max([row[2] for row in company_rows], default=0)
    if company_rows:
        for name, total_count, weekly_count in company_rows:
            lines.append(f"{name}: {total_count} total, +{weekly_count} this week {text_bar(weekly_count, max_company_delta)}")
    else:
        lines.append("No new model-company activity this week.")

    lines.extend(["", "New Models This Week"])
    for run in sorted(weekly_runs, key=lambda item: (model_from_run(item).lower(), str(item.get("submitted_by") or "")))[:25]:
        submitter = str(run.get("submitted_by") or "").strip()
        suffix = f" by {submitter}" if submitter else " (auto-generated)"
        lines.append(f"- {model_from_run(run)}{suffix}")
    if not weekly_runs:
        lines.append("No new models this week.")

    return "\n".join(lines)


def table_rows(rows: list[tuple[str, int, int]], color: str) -> str:
    max_delta = max([row[2] for row in rows], default=0)
    if not rows:
        return '<tr><td colspan="4" style="padding:14px;color:#334155;">No new activity this week.</td></tr>'
    cells = []
    for name, total_count, weekly_count in rows:
        cells.append(
            "<tr>"
            f'<td style="padding:11px 14px;border-top:1px solid #cbd5e1;font-weight:700;color:#0b1220;">{html.escape(name)}</td>'
            f'<td style="padding:11px 14px;border-top:1px solid #cbd5e1;text-align:right;color:#0b1220;">{total_count}</td>'
            f'<td style="padding:11px 14px;border-top:1px solid #cbd5e1;text-align:right;color:#0b1220;font-weight:800;">+{weekly_count}</td>'
            f'<td style="padding:11px 14px;border-top:1px solid #cbd5e1;">{html_bar(weekly_count, max_delta, color)}</td>'
            "</tr>"
        )
    return "".join(cells)


def metric_card(label: str, total: int, delta: int, color: str) -> str:
    return (
        '<td style="padding:0 10px 10px 0;">'
        '<div style="background:#ffffff;border:2px solid #cbd5e1;border-radius:10px;padding:14px 16px;min-width:150px;">'
        f'<div style="font-size:12px;color:#334155;font-weight:700;text-transform:uppercase;">{html.escape(label)}</div>'
        f'<div style="margin-top:8px;font-size:26px;line-height:1;font-weight:800;color:#0b1220;">{total}</div>'
        f'<div style="margin-top:6px;color:{color};font-size:13px;font-weight:800;">+{delta} this week</div>'
        "</div></td>"
    )


def build_html_report(
    runs: list[dict[str, Any]],
    weekly_runs: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    top_limit: int,
) -> str:
    total_submitters = count_submitters(runs)
    weekly_submitters = count_submitters(weekly_runs)
    total_companies = count_companies(runs)
    weekly_companies = count_companies(weekly_runs)
    submitter_rows = top_delta_rows(total_submitters, weekly_submitters, top_limit)
    company_rows = top_delta_rows(total_companies, weekly_companies, top_limit)
    intel_weekly = sum(1 for run in weekly_runs if is_intel_submission(run))
    intel_total = sum(1 for run in runs if is_intel_submission(run))
    active_submitters = len([name for name, count in weekly_submitters.items() if count > 0])

    model_items = []
    for run in sorted(weekly_runs, key=lambda item: (model_from_run(item).lower(), str(item.get("submitted_by") or "")))[:25]:
        model = model_from_run(run)
        submitter = str(run.get("submitted_by") or "").strip()
        model_url = f"https://huggingface.co/{model}"
        by_html = (
            f'<span style="color:#334155;">by {html.escape(submitter)}</span>'
            if submitter
            else '<span style="color:#64748b;">auto-generated</span>'
        )
        model_items.append(
            f'<li style="margin:0 0 7px;"><a href="{html.escape(model_url)}" style="color:#1d4ed8;text-decoration:none;font-weight:700;">{html.escape(model)}</a> '
            f'{by_html}</li>'
        )
    if not model_items:
        model_items.append('<li style="color:#334155;">No new models this week.</li>')

    spacer = '<tr><td style="height:18px;line-height:18px;font-size:0;">&nbsp;</td></tr>'

    return f"""
<!doctype html>
<html>
<body style="margin:0;padding:0;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#0b1220;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0;padding:0;background:#ffffff;">
    <tr><td align="center" style="padding:24px 12px;">
      <table role="presentation" width="920" cellpadding="0" cellspacing="0" style="width:920px;max-width:920px;">

        <tr><td style="background:#0f3a6b;border-radius:16px;padding:26px;">
          <div style="font-size:13px;font-weight:700;color:#bfdbfe;">lb-eval Weekly Statistics</div>
          <div style="margin:8px 0 0;font-size:28px;line-height:1.2;font-weight:800;color:#ffffff;">{format_window_date(start)} ~ {format_window_date(end)}</div>
          <div style="margin:10px 0 0;color:#e2e8f0;font-size:14px;">Weekly new submitters and model-company submission volume.</div>
        </td></tr>

        {spacer}

        <tr><td>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
            {metric_card("Submissions", len(runs), len(weekly_runs), "#1d4ed8")}
            {metric_card("Submitters", len(total_submitters), active_submitters, "#0f766e")}
            {metric_card("Company records", sum(total_companies.values()), sum(weekly_companies.values()), "#c2410c")}
            {metric_card("Intel submissions", intel_total, intel_weekly, "#1d4ed8")}
          </tr></table>
        </td></tr>

        {spacer}

        <tr><td style="background:#ffffff;border:2px solid #cbd5e1;border-radius:14px;padding:16px;">
          <div style="padding:18px 22px;background:#1d4ed8;color:#ffffff;font-size:18px;font-weight:800;border-radius:10px;">Top Submitters This Week</div>
          <div style="padding:14px 6px 0;">
            <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:14px;">
              <thead><tr style="background:#ffffff;color:#334155;text-transform:uppercase;font-size:11px;">
                <th align="left" style="padding:10px 14px;">Submitter</th><th align="right" style="padding:10px 14px;">Total</th><th align="right" style="padding:10px 14px;">This Week</th><th align="left" style="padding:10px 14px;">Volume</th>
              </tr></thead>
              <tbody>{table_rows(submitter_rows, "#1d4ed8")}</tbody>
            </table>
          </div>
        </td></tr>

        {spacer}

        <tr><td style="background:#ffffff;border:2px solid #cbd5e1;border-radius:14px;padding:16px;">
          <div style="padding:18px 22px;background:#c2410c;color:#ffffff;font-size:18px;font-weight:800;border-radius:10px;">Top Model Companies This Week</div>
          <div style="padding:14px 6px 0;">
            <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:14px;">
              <thead><tr style="background:#ffffff;color:#334155;text-transform:uppercase;font-size:11px;">
                <th align="left" style="padding:10px 14px;">Company</th><th align="right" style="padding:10px 14px;">Total</th><th align="right" style="padding:10px 14px;">This Week</th><th align="left" style="padding:10px 14px;">Volume</th>
              </tr></thead>
              <tbody>{table_rows(company_rows, "#c2410c")}</tbody>
            </table>
          </div>
        </td></tr>

        {spacer}

        <tr><td style="background:#ffffff;border:2px solid #cbd5e1;border-radius:14px;padding:18px;">
          <div style="font-size:18px;font-weight:800;margin-bottom:12px;color:#0b1220;">New Models This Week</div>
          <ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.45;color:#0b1220;">{"".join(model_items)}</ul>
        </td></tr>

        {spacer}

        <tr><td style="color:#475569;font-size:12px;line-height:1.5;padding:0 2px;">
          Window: {format_window_date(start)} 00:00 UTC to {format_window_date(end)} 00:00 UTC. Weekly rows are based on run_timestamp. Company uses the model_id prefix before "/", or owner when model_id has no prefix.
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
""".strip()


def send_email(
    sender: str,
    password: str,
    recipients: list[str],
    subject: str,
    text_body: str,
    html_body: str,
    smtp_ca_file: Path | None,
    insecure_smtp_tls: bool,
) -> None:
    message = MIMEMultipart("alternative")
    message["From"] = Header(sender)
    message["To"] = Header(", ".join(recipients))
    message["Subject"] = Header(subject, "utf-8")
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl._create_unverified_context() if insecure_smtp_tls else ssl.create_default_context(cafile=smtp_ca_file)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls(context=context)
        smtp.login(sender, password)
        smtp.sendmail(sender, recipients, message.as_string())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send weekly lb-eval stats email")
    parser.add_argument("--data", type=Path, default=Path("static/data/runs.json"), help="Path to runs.json")
    parser.add_argument("-e", "--email", required=True, help="Sender email address")
    parser.add_argument("-p", "--password", default=os.environ.get("MAIL_PASSWORD"), help="Sender email password; defaults to MAIL_PASSWORD")
    parser.add_argument("-r", "--recipient", action="append", dest="recipients", help="Recipient email address; can be passed multiple times")
    parser.add_argument("--start", help="Report start date in UTC, YYYY-MM-DD. Defaults to previous Friday minus 7 days")
    parser.add_argument("--end", help="Report end date in UTC, YYYY-MM-DD. Defaults to previous Friday")
    parser.add_argument("--top", type=int, default=10, help="Number of rows in each ranking table")
    parser.add_argument("--smtp-ca-file", type=Path, help="CA bundle to trust for SMTP STARTTLS")
    parser.add_argument("--insecure-smtp-tls", action="store_true", help="Skip SMTP TLS certificate verification for internal test environments")
    parser.add_argument("--no-refresh", dest="refresh", action="store_false", help="Skip fetching fresh remote data; read --data as-is")
    parser.add_argument("--source-repo", default="XuehaoSun/lb_eval", help="GitHub source repository for the data refresh")
    parser.add_argument("--source-branch", default="main", help="GitHub source branch for the data refresh")
    parser.add_argument("--dry-run", action="store_true", help="Print the plain-text report instead of sending email")
    parser.set_defaults(refresh=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    if args.start or args.end:
        if not args.start or not args.end:
            raise SystemExit("--start and --end must be provided together")
        start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        start, end = default_report_window(now)

    if start >= end:
        raise SystemExit("Report start must be before report end")

    data_path = args.data
    if args.refresh:
        try:
            print("Refreshing remote data (with submitter/lifecycle info)...")
            data_path = refresh_runs(args.source_repo, args.source_branch)
        except Exception as exc:  # noqa: BLE001 - fall back to local file on any failure
            print(f"Data refresh failed ({exc}); falling back to {args.data}")
            data_path = args.data

    runs = load_runs(data_path)
    weekly_runs = [run for run in runs if in_window(run, start, end)]
    recipients = args.recipients or DEFAULT_RECIPIENTS
    text_body = build_text_report(runs, weekly_runs, start, end, args.top)
    html_body = build_html_report(runs, weekly_runs, start, end, args.top)
    subject = (
        f"[lb-eval Weekly Stats] {format_window_date(start)} ~ {format_window_date(end)}: "
        f"+{len(weekly_runs)} submissions, +{sum(count_companies(weekly_runs).values())} model-company records"
    )

    if args.dry_run:
        print(f"To: {', '.join(recipients)}")
        print(f"Subject: {subject}")
        print()
        print(text_body)
        return 0

    if not args.password:
        raise SystemExit("Email password is required. Pass -p or set MAIL_PASSWORD.")

    send_email(
        args.email,
        args.password,
        recipients,
        subject,
        text_body,
        html_body,
        args.smtp_ca_file,
        args.insecure_smtp_tls,
    )
    print(f"Sent weekly stats email to {', '.join(recipients)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())