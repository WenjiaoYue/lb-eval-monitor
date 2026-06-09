#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMMON_TASKS = ("piqa", "mmlu", "hellaswag")
STATUS_PRIORITY = {"failed": 0, "running": 1, "success": 2}
STATUS_JOB_TYPE = "quantization & evaluation"


def read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def to_iso_utc(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_status(value: Any) -> str:
    if value is None:
        return "running"
    text = str(value).strip().lower()
    if not text:
        return "running"
    if any(token in text for token in ("fail", "error", "exception", "traceback")):
        return "failed"
    if any(token in text for token in ("success", "succeed", "pass", "done", "complete")):
        return "success"
    if any(token in text for token in ("running", "pending", "progress", "started", "queue")):
        return "running"
    return "running"


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def pick_timestamp(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_run_timestamp(run_id: str | None, fallback_iso: str | None) -> str:
    timestamp_match = re.search(r"run_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})", run_id or "")
    if timestamp_match:
        y, mo, d, h, mi, s = timestamp_match.groups()
        return f"{y}-{mo}-{d}T{h}:{mi}:{s}Z"
    return fallback_iso or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def normalize_scheme(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "unknown":
        return ""
    match = re.search(r"\((\w+)\)", text)
    return match.group(1) if match else text


def lifecycle_scheme(data: dict[str, Any]) -> str:
    return normalize_scheme(data.get("quant_scheme")) or normalize_scheme(data.get("compute_dtype"))


def extract_org_list(*values: Any) -> list[str]:
    orgs: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if value not in (None, ""):
            orgs.append(str(value).strip())

    for value in values:
        add(value)
    return dedupe([org for org in orgs if org])


def extract_errors(raw: Any) -> list[str]:
    errors: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                errors.append(item.strip())
            elif isinstance(item, dict):
                text = first_nonempty(item.get("message"), item.get("error"), item.get("detail"))
                if text:
                    errors.append(str(text).strip())
    elif isinstance(raw, dict):
        text = first_nonempty(raw.get("message"), raw.get("error"), raw.get("detail"))
        if text:
            errors.append(str(text).strip())
    elif isinstance(raw, str):
        errors.append(raw.strip())
    return dedupe([e for e in errors if e])


def read_failure_log(run_dir: Path, phase: str | None = None) -> str | None:
    candidates: list[Path] = []
    if phase == "eval":
        candidates.extend(sorted(run_dir.glob("logs/*eval*.log")))
        candidates.extend(sorted(run_dir.glob("session_eval_*.md"), key=lambda p: p.stat().st_mtime, reverse=True))
    else:
        candidates.extend(run_dir / "logs" / log_name for log_name in ("quantize.log", "setup_env.log"))
        for pattern in ("session_fix_setup_env_*.md", "session_fix_quantize_*.md", "session_quant_*.md"):
            candidates.extend(sorted(run_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True))
    candidates.extend(sorted(run_dir.glob("logs/*.log")))

    seen: set[Path] = set()
    for log_path in candidates:
        if log_path in seen:
            continue
        seen.add(log_path)
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8", errors="ignore").strip()
            if content:
                return content
    return None


def find_quant_log_path(run_dir: Path) -> Path | None:
    for rel_path in ("logs/setup_env.log", "logs/quantize.log"):
        log_path = run_dir / rel_path
        if log_path.exists():
            return log_path
    for pattern in ("session_fix_setup_env_*.md", "session_fix_quantize_*.md", "session_quant_*.md"):
        matches = sorted(run_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]
    return None


def extract_issues_from_markdown(content: str) -> list[str]:
    issues: list[str] = []
    for line in content.splitlines():
        clean = line.strip("- *\t ")
        if not clean:
            continue
        lower = clean.lower()
        if any(token in lower for token in ("error", "failed", "exception", "traceback")):
            issues.append(clean)
            if len(issues) >= 6:
                break
    return dedupe(issues)


def extract_summary_from_markdown(content: str) -> str | None:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return None

    for idx, line in enumerate(lines):
        lower = line.lower()
        if lower.startswith(("summary", "final summary", "overall summary")):
            if idx + 1 < len(lines):
                return lines[idx + 1][:280]
            return line[:280]

    for line in reversed(lines):
        lower = line.lower()
        if "summary" in lower or "completed" in lower or "failed" in lower:
            return line[:280]

    return lines[-1][:280]


def metrics_preview_from_accuracy(data: dict[str, Any]) -> dict[str, float | str]:
    preview: dict[str, float | str] = {}
    candidates = []

    if isinstance(data.get("results"), dict):
        candidates.append(data["results"])
    if isinstance(data.get("tasks"), dict):
        candidates.append(data["tasks"])
    candidates.append(data)

    for blob in candidates:
        if not isinstance(blob, dict):
            continue
        for task in COMMON_TASKS:
            if task in preview:
                continue
            task_payload = blob.get(task)
            if isinstance(task_payload, dict):
                for key in ("accuracy", "acc_norm,none", "acc,none", "acc", "score", "exact_match"):
                    if key in task_payload:
                        preview[task] = task_payload[key]
                        break
            elif task_payload not in (None, ""):
                preview[task] = task_payload

    return preview


def classify_status(quant_status: str, eval_status: str) -> str:
    if "failed" in (quant_status, eval_status):
        return "failed"
    if quant_status == "success" and eval_status == "success":
        return "success"
    if "running" in (quant_status, eval_status):
        return "running"
    return "running"


def build_file_url(repo: str, branch: str, path_from_repo_root: str | None) -> str | None:
    if not path_from_repo_root:
        return None
    return f"https://github.com/{repo}/blob/{branch}/{path_from_repo_root}"


def lifecycle_status_url(data: dict[str, Any], repo: str, branch: str) -> str | None:
    path = data.get("_lifecycle_path")
    if isinstance(path, str) and path.startswith("status/"):
        return build_file_url(repo, branch, path)
    return None


def request_status_url(owner: str | None, request_filename: Any, repo: str, branch: str) -> str | None:
    filename = str(request_filename or "").strip()
    if not owner or not filename.endswith(".json"):
        return None
    return build_file_url(repo, branch, f"status/{owner}/{filename}")


def comparable_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{8}T\d{6}Z", text):
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except ValueError:
        return ""


def status_filename_meta(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    match = re.match(r"^(?:status|requests|pending_requests)/([^/]+)/(.+?)_(?:quant|eval)_request_False_(.+)\.json$", path)
    if not match:
        return {}
    owner, model_name, tail = match.groups()
    tokens = [token for token in tail.split("_") if token]
    scheme = next((token for token in tokens if re.fullmatch(r"(?:W\d+A\d+|MXFP\d+|NVFP\d+)", token, re.IGNORECASE)), "")
    method = next((token for token in tokens if token.upper() in ("RTN", "TUNING")), "")
    time = next((token for token in tokens if re.fullmatch(r"\d{8}T\d{6}Z", token)), "")
    return {"owner": owner, "model_name": model_name, "scheme": scheme, "method": method.upper(), "time": time}


def parse_aggregate_candidates(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    candidates: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if any(k in node for k in ("run_id", "run_path", "run_dir", "model_id", "artifact_name", "auto_quant_status", "auto_eval_status")):
                item = dict(node)
                item["__aggregate_path"] = str(path)
                candidates.append(item)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return candidates


def index_aggregates(results_root: Path) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for file in sorted(results_root.rglob("results_*.json")):
        for candidate in parse_aggregate_candidates(file):
            run_path = candidate.get("run_path") or candidate.get("run_dir")
            run_id = candidate.get("run_id")
            key = str(run_path or run_id or "").replace("results/", "", 1).strip("/")
            if not key:
                continue
            existing = lookup.get(key)
            if existing is None:
                lookup[key] = candidate
                continue
            old_status = classify_status(normalize_status(existing.get("auto_quant_status")), normalize_status(existing.get("auto_eval_status")))
            new_status = classify_status(normalize_status(candidate.get("auto_quant_status")), normalize_status(candidate.get("auto_eval_status")))
            if STATUS_PRIORITY[new_status] < STATUS_PRIORITY[old_status]:
                lookup[key] = candidate
    return lookup


def extract_quant_details(quant_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract rich quantization details from quant_summary.json."""
    if not isinstance(quant_data, dict):
        return None
    details: dict[str, Any] = {}
    for key in ("original_size_mb", "quantized_size_mb", "compression_ratio",
                "duration_seconds", "hf_repo", "export_format", "device",
                "model_id", "output_dir", "quantized_model_dir"):
        val = quant_data.get(key)
        if val is not None and val != "":
            details[key] = val
    return details if details else None


def extract_eval_details(accuracy_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract detailed evaluation results from accuracy.json."""
    if not isinstance(accuracy_data, dict):
        return None
    details: dict[str, Any] = {}

    # Duration
    dur = accuracy_data.get("duration_seconds")
    if dur is not None:
        try:
            details["duration_seconds"] = float(dur)
        except (ValueError, TypeError):
            details["duration_seconds"] = dur

    # Eval framework
    fw = accuracy_data.get("eval_framework")
    if fw:
        details["eval_framework"] = fw

    # Full task results with accuracy + stderr
    raw_tasks = accuracy_data.get("tasks")
    if isinstance(raw_tasks, dict):
        task_results: dict[str, Any] = {}
        for task_name, task_val in raw_tasks.items():
            if isinstance(task_val, dict):
                task_results[task_name] = task_val
            elif task_val is not None:
                task_results[task_name] = {"accuracy": task_val}
        if task_results:
            details["task_results"] = task_results
    elif isinstance(raw_tasks, list):
        # If tasks is a list of strings, no detailed results available
        pass

    return details if details else None


def record_from_run_dir(
    run_dir: Path,
    results_root: Path,
    aggregate_index: dict[str, dict[str, Any]],
    source_repo: str,
    source_branch: str,
) -> dict[str, Any]:
    rel_path = run_dir.relative_to(results_root)
    owner = rel_path.parts[0] if len(rel_path.parts) > 0 else ""
    artifact_name = rel_path.parts[1] if len(rel_path.parts) > 1 else ""
    run_id = run_dir.name

    quant_summary_path = run_dir / "quant_summary.json"
    accuracy_path = run_dir / "accuracy.json"
    request_path = run_dir / "request.json"
    session_eval_path = sorted(run_dir.glob("session_eval_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    session_quant_path = sorted([*run_dir.glob("session_quant_*.md"), *run_dir.glob("session_fix_quantize_*.md"), *run_dir.glob("session_fix_setup_env_*.md")], key=lambda p: p.stat().st_mtime, reverse=True)

    quant_data = read_json(quant_summary_path) if quant_summary_path.exists() else None
    accuracy_data = read_json(accuracy_path) if accuracy_path.exists() else None
    request_data = read_json(request_path) if request_path.exists() else None

    aggregate = aggregate_index.get(str(rel_path)) or aggregate_index.get(run_id) or {}
    aggregate_path = aggregate.get("__aggregate_path")

    quant_status = normalize_status(
        first_nonempty(
            (quant_data or {}).get("status") if isinstance(quant_data, dict) else None,
            aggregate.get("auto_quant_status"),
        )
    )
    eval_status = normalize_status(
        first_nonempty(
            (accuracy_data or {}).get("status") if isinstance(accuracy_data, dict) else None,
            aggregate.get("auto_eval_status"),
        )
    )

    quant_errors = extract_errors((quant_data or {}).get("errors") if isinstance(quant_data, dict) else None)
    if quant_status == "failed":
        failure_log = read_failure_log(run_dir, "quant")
        if failure_log:
            quant_errors = [failure_log]
    eval_errors = extract_errors((accuracy_data or {}).get("errors") if isinstance(accuracy_data, dict) else None)
    if eval_status == "failed" and not eval_errors:
        failure_log = read_failure_log(run_dir, "eval")
        if failure_log:
            eval_errors = [failure_log]

    session_issues: list[str] = []
    summary: str | None = None

    if session_eval_path:
        content = session_eval_path[0].read_text(encoding="utf-8", errors="ignore")
        session_issues.extend(extract_issues_from_markdown(content))
        summary = extract_summary_from_markdown(content)
    if not summary and session_quant_path:
        content = session_quant_path[0].read_text(encoding="utf-8", errors="ignore")
        session_issues.extend(extract_issues_from_markdown(content))
        summary = extract_summary_from_markdown(content)

    issues = dedupe(quant_errors + eval_errors + session_issues)

    quant_num_gpus = first_nonempty(
        (quant_data or {}).get("num_gpus") if isinstance(quant_data, dict) else None,
        (quant_data or {}).get("gpus") if isinstance(quant_data, dict) else None,
        aggregate.get("quant_num_gpus"),
    )
    eval_num_gpus = first_nonempty(
        (accuracy_data or {}).get("num_gpus") if isinstance(accuracy_data, dict) else None,
        aggregate.get("eval_num_gpus"),
    )

    tasks: list[str] = []
    if isinstance(accuracy_data, dict):
        raw_tasks = accuracy_data.get("tasks")
        if isinstance(raw_tasks, dict):
            tasks = [str(t) for t in raw_tasks.keys()]
        elif isinstance(raw_tasks, list):
            tasks = [str(t) for t in raw_tasks]
        elif isinstance(accuracy_data.get("results"), dict):
            tasks = [str(k) for k in accuracy_data["results"].keys()]

    metrics_preview = metrics_preview_from_accuracy(accuracy_data) if isinstance(accuracy_data, dict) else {}

    updated_at = pick_timestamp(
        to_iso_utc(run_dir.stat().st_mtime),
        to_iso_utc(quant_summary_path.stat().st_mtime) if quant_summary_path.exists() else None,
        to_iso_utc(accuracy_path.stat().st_mtime) if accuracy_path.exists() else None,
    )

    eval_rel = (rel_path / session_eval_path[0].name).as_posix() if session_eval_path else None
    quant_log_path = find_quant_log_path(run_dir)
    quant_rel = (rel_path / quant_log_path.relative_to(run_dir)).as_posix() if quant_log_path else None
    aggregate_rel = Path(aggregate_path).relative_to(results_root.parent).as_posix() if aggregate_path else None

    return {
        "owner": owner,
        "artifact_name": artifact_name,
        "model_id": first_nonempty(aggregate.get("model_id"), (quant_data or {}).get("model_id") if isinstance(quant_data, dict) else None, artifact_name),
        "submitted_by": first_nonempty(aggregate.get("submitted_by")),
        "orgs": extract_org_list(aggregate.get("orgs"), aggregate.get("org"), aggregate.get("organizations")),
        "scheme": first_nonempty((quant_data or {}).get("scheme") if isinstance(quant_data, dict) else None, aggregate.get("scheme"), ""),
        "method": first_nonempty((quant_data or {}).get("method") if isinstance(quant_data, dict) else None, aggregate.get("method"), ""),
        "run_id": run_id,
        "run_timestamp": parse_run_timestamp(run_id, to_iso_utc(run_dir.stat().st_mtime)),
        "run_path": rel_path.as_posix(),
        "auto_quant_status": quant_status,
        "auto_eval_status": eval_status,
        "quant_errors": quant_errors,
        "eval_errors": eval_errors,
        "issues": issues,
        "summary": first_nonempty(summary, aggregate.get("summary"), ""),
        "tasks": tasks,
        "metrics_preview": metrics_preview,
        "quant_num_gpus": quant_num_gpus,
        "eval_num_gpus": eval_num_gpus,
        # Quant details from quant_summary.json
        "quant_details": extract_quant_details(quant_data),
        # Eval details from accuracy.json
        "eval_details": extract_eval_details(accuracy_data),
        "session_eval_url": build_file_url(source_repo, source_branch, f"results/{eval_rel}" if eval_rel else None),
        "session_quant_url": build_file_url(source_repo, source_branch, f"results/{quant_rel}" if quant_rel else None),
        "aggregate_result_url": build_file_url(source_repo, source_branch, aggregate_rel),
        "status_url": request_status_url(owner, aggregate.get("request_filename"), source_repo, source_branch),
        "request_filename": first_nonempty(aggregate.get("request_filename")),
        "request_submitted_time": first_nonempty(
            (request_data or {}).get("submitted_time") if isinstance(request_data, dict) else None,
            aggregate.get("submitted_time"),
        ),
        "updated_at": updated_at,
    }


def record_from_aggregate_only(
    aggregate: dict[str, Any],
    results_root: Path,
    source_repo: str,
    source_branch: str,
) -> dict[str, Any] | None:
    run_path = str(first_nonempty(aggregate.get("run_path"), aggregate.get("run_dir"), "")).strip()
    run_id = str(first_nonempty(aggregate.get("run_id"), "")).strip()
    if not run_path and not run_id:
        return None

    norm_path = run_path.replace("results/", "", 1).strip("/") if run_path else ""
    parts = Path(norm_path).parts if norm_path else ()
    owner = first_nonempty(aggregate.get("owner"), parts[0] if len(parts) > 0 else "")
    artifact_name = first_nonempty(aggregate.get("artifact_name"), parts[1] if len(parts) > 1 else aggregate.get("model_id") or "")

    quant_status = normalize_status(aggregate.get("auto_quant_status"))
    eval_status = normalize_status(aggregate.get("auto_eval_status"))

    quant_errors = extract_errors(aggregate.get("quant_errors") or aggregate.get("errors"))
    eval_errors = extract_errors(aggregate.get("eval_errors"))
    issues = dedupe(quant_errors + eval_errors + extract_errors(aggregate.get("issues")))

    aggregate_path = aggregate.get("__aggregate_path")
    aggregate_rel = Path(aggregate_path).relative_to(results_root.parent).as_posix() if aggregate_path else None

    return {
        "owner": owner,
        "artifact_name": artifact_name,
        "model_id": first_nonempty(aggregate.get("model_id"), artifact_name),
        "submitted_by": first_nonempty(aggregate.get("submitted_by")),
        "orgs": extract_org_list(aggregate.get("orgs"), aggregate.get("org"), aggregate.get("organizations")),
        "scheme": first_nonempty(aggregate.get("scheme"), ""),
        "method": first_nonempty(aggregate.get("method"), ""),
        "run_id": run_id or (parts[-1] if parts else "aggregate_only"),
        "run_timestamp": parse_run_timestamp(run_id, first_nonempty(aggregate.get("run_timestamp"), aggregate.get("updated_at"))),
        "run_path": norm_path or run_id,
        "auto_quant_status": quant_status,
        "auto_eval_status": eval_status,
        "quant_errors": quant_errors,
        "eval_errors": eval_errors,
        "issues": issues,
        "summary": str(first_nonempty(aggregate.get("summary"), "")),
        "tasks": aggregate.get("tasks") if isinstance(aggregate.get("tasks"), list) else [],
        "metrics_preview": aggregate.get("metrics_preview") if isinstance(aggregate.get("metrics_preview"), dict) else {},
        "quant_num_gpus": aggregate.get("quant_num_gpus"),
        "eval_num_gpus": aggregate.get("eval_num_gpus"),
        "session_eval_url": build_file_url(source_repo, source_branch, aggregate.get("session_eval_path")),
        "session_quant_url": build_file_url(source_repo, source_branch, aggregate.get("session_quant_path")),
        "aggregate_result_url": build_file_url(source_repo, source_branch, aggregate_rel),
        "status_url": request_status_url(owner, aggregate.get("request_filename"), source_repo, source_branch),
        "request_filename": first_nonempty(aggregate.get("request_filename")),
        "request_submitted_time": first_nonempty(aggregate.get("submitted_time")),
        "updated_at": pick_timestamp(first_nonempty(aggregate.get("updated_at"), aggregate.get("run_timestamp"))),
        "quant_details": None,
        "eval_details": None,
    }


def build_latest(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (str(record.get("owner", "")), str(record.get("artifact_name", "")))
        existing = by_key.get(key)
        if existing is None or str(record.get("run_timestamp", "")) > str(existing.get("run_timestamp", "")):
            by_key[key] = record
    return sorted(by_key.values(), key=lambda item: str(item.get("updated_at", "")), reverse=True)


def build_summary(all_runs: list[dict[str, Any]], latest_runs: list[dict[str, Any]]) -> dict[str, Any]:
    # Status counters are computed over the latest run per model so they match
    # leaderboard-style per-model accounting. `total_runs` still reflects raw count.
    quant_counter = Counter(record.get("auto_quant_status", "running") for record in latest_runs)
    eval_counter = Counter(record.get("auto_eval_status", "running") for record in latest_runs)
    pipeline_counter = Counter(
        (record.get("pipeline") or {}).get("status", "pending") for record in latest_runs
    )
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_runs": len(all_runs),
        "latest_models_count": len(latest_runs),
        "quant": {
            "success": quant_counter.get("success", 0),
            "failed": quant_counter.get("failed", 0),
            "running": quant_counter.get("running", 0),
        },
        "eval": {
            "success": eval_counter.get("success", 0),
            "failed": eval_counter.get("failed", 0),
            "running": eval_counter.get("running", 0),
        },
        "pipeline": {
            "pending": pipeline_counter.get("pending", 0),
            "running": pipeline_counter.get("running", 0),
            "succeeded": pipeline_counter.get("succeeded", 0),
            "failed": pipeline_counter.get("failed", 0),
            "cancelled": pipeline_counter.get("cancelled", 0),
        },
    }


def dedupe_same_model_runs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    output: list[dict[str, Any]] = []

    def key_for(record: dict[str, Any]) -> tuple[str, str, str] | None:
        run_id = str(record.get("run_id") or "")
        if not run_id:
            return None
        return (
            str(record.get("owner") or ""),
            str(first_nonempty(record.get("model_id"), record.get("artifact_name"), "")),
            run_id,
        )

    def score(record: dict[str, Any]) -> int:
        return (
            (100 if record.get("quant_errors") or record.get("eval_errors") else 0)
            + (30 if record.get("session_quant_url") else 0)
            + (20 if record.get("session_eval_url") else 0)
            + (10 if record.get("pipeline") else 0)
            + (5 if record.get("aggregate_result_url") else 0)
        )

    for record in records:
        key = key_for(record)
        if key is None:
            output.append(record)
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            output.append(record)
            continue
        if score(record) > score(existing):
            by_key[key] = record
            output[output.index(existing)] = record

    return output


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Lifecycle / pipeline status (status/, requests/, pending_requests/)
# ---------------------------------------------------------------------------

def _normalize_pipeline_status(raw_status: str | None) -> str:
    """Normalize the status field from lifecycle JSON files."""
    if not raw_status:
        return "pending"
    text = raw_status.strip().lower()
    if text == "finished":
        return "succeeded"
    if "fail" in text:
        return "failed"
    if text in ("pending", "queued"):
        return "pending"
    if text in ("running", "started"):
        return "running"
    if "cancel" in text:
        return "cancelled"
    return text


def _lifecycle_failed_phase(raw_status: str | None) -> str | None:
    """Return 'quant' or 'eval' when raw lifecycle status names the failed phase."""
    if not raw_status:
        return None
    text = raw_status.strip().lower()
    if "fail" not in text:
        return None
    if "eval" in text:
        return "eval"
    if "quant" in text:
        return "quant"
    return None


def _phase_statuses_from_lifecycle(lifecycle_data: dict[str, Any]) -> tuple[str, str]:
    """Map the lifecycle status value to quant/eval dashboard statuses."""
    norm_status = _normalize_pipeline_status(lifecycle_data.get("status"))
    phase = _lifecycle_failed_phase(lifecycle_data.get("status"))
    script = str(lifecycle_data.get("script") or "").lower()

    if norm_status == "succeeded":
        return "success", "success"
    if norm_status in ("pending", "running", "cancelled"):
        return "running", "running"
    if norm_status == "failed":
        if phase == "eval" or script == "auto_eval":
            return "success", "failed"
        return "failed", "running"
    return "running", "running"


def _lifecycle_rank(data: dict[str, Any], dirname: str) -> tuple[int, int, str]:
    source_rank = {"requests": 0, "pending_requests": 1, "status": 2}.get(dirname, 0)
    status_rank = {
        "pending": 0,
        "running": 1,
        "cancelled": 1,
        "failed": 2,
        "succeeded": 3,
    }.get(_normalize_pipeline_status(data.get("status")), 0)
    timestamp = str(first_nonempty(data.get("triggered_time"), data.get("submitted_time"), ""))
    return source_rank, status_rank, timestamp


def _lifecycle_method(data: dict[str, Any]) -> str:
    meta = status_filename_meta(data.get("_lifecycle_path"))
    return str(first_nonempty(data.get("method"), meta.get("method"), "") or "").strip().upper()


def _lifecycle_time(data: dict[str, Any]) -> str:
    meta = status_filename_meta(data.get("_lifecycle_path"))
    return comparable_time(first_nonempty(meta.get("time"), data.get("submitted_time"), data.get("triggered_time")))


def _record_method(record: dict[str, Any]) -> str:
    haystack = f"{record.get('method', '')} {record.get('artifact_name', '')}".upper()
    if "TUNING" in haystack:
        return "TUNING"
    if "RTN" in haystack:
        return "RTN"
    return ""


def _methods_compatible(status_method: str, record_method: str) -> bool:
    status_method = status_method.upper()
    record_method = record_method.upper()
    if status_method == "TUNING":
        return record_method == "TUNING"
    if status_method in ("", "RTN"):
        return record_method in ("", "RTN")
    return status_method == record_method


def _model_key_from_status(data: dict[str, Any]) -> str:
    """Build a matching key from a status/request file. E.g. 'Qwen/Qwen3-0.6B::MXFP4'

    Eval-only entries may not carry `quant_scheme`; fall back to `compute_dtype`
    (e.g. "INT4 (W4A16)") so the resulting key still includes a scheme.
    """
    model = data.get("model", "")
    scheme = lifecycle_scheme(data)
    return f"{model}::{scheme}"


def _model_key_from_record(record: dict[str, Any]) -> str:
    """Build matching key from a run record."""
    owner = record.get("owner", "")
    # model_id can be: 'Qwen3-0.6B-autoround-W4A16' or 'Qwen/Qwen3-0.6B' etc.
    model_id = record.get("model_id", "")
    scheme = record.get("scheme", "")

    # If model_id already contains owner prefix (e.g. 'Qwen/Qwen3-0.6B'), use it directly
    if "/" in model_id:
        base_model = model_id
    else:
        # Strip method-scheme suffixes to get base model name
        base_model = model_id
        for suffix in (f"-autoround-{scheme}", f"-gptq-{scheme}", f"-awq-{scheme}",
                       f"-{scheme}", f"_{scheme}"):
            if base_model.endswith(suffix):
                base_model = base_model[:-len(suffix)]
                break
        base_model = f"{owner}/{base_model}"

    return f"{base_model}::{scheme}"


def _base_model_from_record(record: dict[str, Any]) -> str:
    """Best-effort base HF model id from a run record, ignoring scheme/method suffixes.

    Used as a fallback match key (model-only) for eval-only jobs where the
    record has no scheme but the lifecycle entry knows it.
    """
    owner = record.get("owner", "") or ""
    model_id = record.get("model_id", "") or record.get("artifact_name", "") or ""
    if "/" in model_id:
        base = model_id
    else:
        base = model_id
        # Strip trailing "-<method>-<SCHEME>" pattern (e.g. -autoround-W4A16)
        base = re.sub(r"[-_](?:autoround|gptq|awq|smoothquant|compressed[_-]?tensors)[-_][A-Za-z0-9]+$",
                      "", base, flags=re.IGNORECASE)
        base = f"{owner}/{base}" if owner else base
    return base


def load_lifecycle_index(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load status/, requests/, and pending_requests/ data without collapsing distinct requests."""
    entries: list[dict[str, Any]] = []
    model_only: dict[str, dict[str, Any]] = {}

    for dirname in ("requests", "pending_requests", "status"):
        lifecycle_dir = repo_root / dirname
        if not lifecycle_dir.exists():
            continue
        for json_file in sorted(lifecycle_dir.rglob("*.json")):
            data = read_json(json_file)
            if not isinstance(data, dict):
                continue
            key = _model_key_from_status(data)
            if not key or "::" not in key:
                continue
            candidate = dict(data)
            candidate["_lifecycle_dir"] = dirname
            candidate["_lifecycle_path"] = str(json_file.relative_to(repo_root))
            entries.append(candidate)
            model_name = data.get("model", "")
            if model_name:
                existing = model_only.get(model_name)
                if existing is None or _lifecycle_rank(candidate, dirname) >= _lifecycle_rank(existing, str(existing.get("_lifecycle_dir", ""))):
                    model_only[model_name] = candidate

    return entries, model_only


def extract_pipeline_info(lifecycle_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract pipeline status info from a lifecycle record."""
    if not lifecycle_data:
        return None
    info: dict[str, Any] = {}

    status = lifecycle_data.get("status")
    if status:
        info["status"] = _normalize_pipeline_status(status)
        info["raw_status"] = str(status)

    for field in ("submitted_time", "triggered_time", "ci_run_id",
                  "job_type", "quant_scheme", "hardware", "gpu_nums",
                  "model_weight_gb", "quant_model_size_gb", "params"):
        val = lifecycle_data.get(field)
        if val is not None and val != "" and val != -1:
            info[field] = val

    return info if info else None


def record_from_lifecycle(
    data: dict[str, Any],
    source_repo: str,
    source_branch: str,
) -> dict[str, Any]:
    """Build a run record straight from a status/lifecycle entry.

    The status folder is the source of truth for model/scheme/status. Result
    details (logs, metrics, sessions) are merged in later, and only once the
    job has reached a terminal state (finished/failed).
    """
    model = data.get("model", "")
    parts = model.split("/", 1)
    owner = parts[0] if len(parts) > 1 else ""
    base_model = parts[1] if len(parts) > 1 else model

    scheme = lifecycle_scheme(data)
    submitted = data.get("submitted_time", "")
    triggered = data.get("triggered_time")
    quant_status, eval_status = _phase_statuses_from_lifecycle(data)

    return {
        "owner": owner,
        "artifact_name": f"{base_model}-{scheme}" if scheme else base_model,
        "model_id": model or base_model,
        "submitted_by": first_nonempty(data.get("submitted_by")),
        "orgs": extract_org_list(data.get("orgs"), data.get("org"), data.get("organizations")),
        "scheme": scheme,
        "method": "autoround" if "auto_quant" in str(data.get("script", "")) else str(data.get("script", "")),
        "run_id": "",
        "run_timestamp": submitted or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run_path": "",
        "auto_quant_status": quant_status,
        "auto_eval_status": eval_status,
        "quant_errors": [],
        "eval_errors": [],
        "issues": [],
        "summary": "",
        "tasks": [],
        "metrics_preview": {},
        "quant_num_gpus": data.get("quant_gpu_nums") or data.get("gpu_nums"),
        "eval_num_gpus": data.get("eval_gpu_nums") or data.get("gpu_nums"),
        "quant_details": None,
        "eval_details": None,
        "pipeline": extract_pipeline_info(data),
        "session_eval_url": None,
        "session_quant_url": None,
        "aggregate_result_url": None,
        "status_url": lifecycle_status_url(data, source_repo, source_branch),
        "updated_at": triggered or submitted or "",
    }


def scan_results(
    source_root: Path,
    output_dir: Path,
    source_repo: str,
    source_branch: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    aggregate_index = index_aggregates(source_root)

    # Load lifecycle data (status/, requests/, pending_requests/)
    # The repo root is one level above source_root (results/)
    repo_root = source_root.parent
    lifecycle_index, lifecycle_model_only = load_lifecycle_index(repo_root)
    print(f"Loaded {len(lifecycle_index)} lifecycle entries from status/requests/pending_requests")

    def _apply_lifecycle(rec: dict[str, Any], lc_data: dict[str, Any] | None) -> None:
        rec["pipeline"] = extract_pipeline_info(lc_data) if lc_data else None
        if not lc_data:
            return
        status_url = lifecycle_status_url(lc_data, source_repo, source_branch)
        if status_url:
            rec["status_url"] = status_url
        quant_status, eval_status = _phase_statuses_from_lifecycle(lc_data)
        rec["auto_quant_status"] = quant_status
        rec["auto_eval_status"] = eval_status
        rec["submitted_by"] = first_nonempty(lc_data.get("submitted_by"), rec.get("submitted_by"))
        rec["orgs"] = extract_org_list(lc_data.get("orgs"), lc_data.get("org"), lc_data.get("organizations"), rec.get("orgs"))
        # Status is authoritative, so it replaces missing or stale local values
        # from results such as "unknown".
        lc_scheme = lifecycle_scheme(lc_data)
        if lc_scheme:
            rec["scheme"] = lc_scheme
        phase = _lifecycle_failed_phase(lc_data.get("status"))
        if rec["auto_quant_status"] == "failed":
            failure_log = read_failure_log(source_root / str(rec.get("run_path", "")), phase or "quant")
            if failure_log:
                rec["quant_errors"] = [failure_log]
        elif rec["auto_eval_status"] == "failed":
            failure_log = read_failure_log(source_root / str(rec.get("run_path", "")), phase or "eval")
            if failure_log:
                rec["eval_errors"] = [failure_log]
        rec["issues"] = dedupe(rec.get("quant_errors", []) + rec.get("eval_errors", []) + extract_errors(rec.get("issues")))

    def _run_model_key(record: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(record.get("owner") or ""),
            str(first_nonempty(record.get("model_id"), record.get("artifact_name"), "")),
            str(record.get("run_id") or ""),
        )

    def _record_scheme(record: dict[str, Any]) -> str:
        scheme = str(record.get("scheme") or "")
        if scheme:
            return scheme
        haystack = f"{record.get('artifact_name', '')} {record.get('model_id', '')}".upper()
        for token in ("W4A16", "MXFP4", "NVFP4"):
            if token in haystack:
                return token
        return ""

    def _record_base_key(record: dict[str, Any]) -> str:
        clone = dict(record)
        if not clone.get("scheme"):
            clone["scheme"] = _record_scheme(record)
        return _model_key_from_record(clone)

    def _time_distance(status_time: str, record: dict[str, Any]) -> int:
        target = comparable_time(first_nonempty(record.get("request_submitted_time"), record.get("run_timestamp")))
        if not status_time or not target:
            return 10**12
        try:
            left = datetime.strptime(status_time, "%Y%m%dT%H%M%SZ")
            right = datetime.strptime(target, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return 10**12
        return int(abs((left - right).total_seconds()))

    def _detail_match_score(status_data: dict[str, Any], record: dict[str, Any]) -> tuple[int, int, str] | None:
        if _model_key_from_status(status_data) != _record_base_key(record):
            return None
        if not _methods_compatible(_lifecycle_method(status_data), _record_method(record)):
            return None
        status_path = str(status_data.get("_lifecycle_path") or "")
        request_filename = str(record.get("request_filename") or "")
        exact_request = bool(request_filename and status_path.endswith(f"/{request_filename}"))
        status_time = _lifecycle_time(status_data)
        distance = _time_distance(status_time, record)
        return (0 if exact_request else 1, distance, str(record.get("run_timestamp") or ""))

    def _find_detail_for_status(status_data: dict[str, Any], details: list[dict[str, Any]]) -> dict[str, Any] | None:
        best: tuple[tuple[int, int, str], dict[str, Any]] | None = None
        for detail in details:
            score = _detail_match_score(status_data, detail)
            if score is None:
                continue
            if best is None or score < best[0]:
                best = (score, detail)
        return best[1] if best else None

    def _has_lifecycle_for_record(record: dict[str, Any]) -> bool:
        return any(_detail_match_score(data, record) is not None for data in lifecycle_index)

    # ── 1. Collect result-detail records from the results/ tree ──
    # These are not the primary list; they only supply details that get merged
    # into a status entry once that model reaches a terminal state.
    detail_records: list[dict[str, Any]] = []
    seen_run_paths: set[str] = set()
    seen_run_model_keys: set[tuple[str, str, str]] = set()
    for run_dir in sorted([p for p in source_root.rglob("run_*") if p.is_dir()]):
        rec = record_from_run_dir(run_dir, source_root, aggregate_index, source_repo, source_branch)
        detail_records.append(rec)
        seen_run_paths.add(str(rec.get("run_path", "")))
        seen_run_model_keys.add(_run_model_key(rec))
    for aggregate in aggregate_index.values():
        candidate = record_from_aggregate_only(aggregate, source_root, source_repo, source_branch)
        if not candidate:
            continue
        if str(candidate.get("run_path", "")) in seen_run_paths:
            continue
        if _run_model_key(candidate) in seen_run_model_keys:
            continue
        detail_records.append(candidate)
        seen_run_model_keys.add(_run_model_key(candidate))

    # ── 2. Index details by match key, keeping the most recent per key ──
    detail_by_key: dict[str, dict[str, Any]] = {}
    detail_by_model: dict[str, dict[str, Any]] = {}

    def _stash(index: dict[str, dict[str, Any]], key: str, rec: dict[str, Any]) -> None:
        if not key:
            return
        current = index.get(key)
        if current is None or str(rec.get("run_timestamp", "")) > str(current.get("run_timestamp", "")):
            index[key] = rec

    for rec in detail_records:
        _stash(detail_by_key, _model_key_from_record(rec), rec)
        _stash(detail_by_model, _base_model_from_record(rec), rec)

    # ── 3. Build the primary list from status/ (the source of truth) ──
    # scheme/status/model come from the lifecycle entry. We only reach into
    # results/ for run details once the status is finished or failed.
    detail_merge_fields = (
        "owner", "artifact_name", "model_id", "method",
        "run_id", "run_timestamp", "run_path",
        "quant_errors", "eval_errors", "issues", "summary", "tasks",
        "metrics_preview", "quant_num_gpus", "eval_num_gpus",
        "quant_details", "eval_details",
        "session_eval_url", "session_quant_url", "aggregate_result_url", "updated_at",
        "status_url",
    )
    records: list[dict[str, Any]] = []
    matched_detail_ids: set[int] = set()
    for data in lifecycle_index:
        record = record_from_lifecycle(data, source_repo, source_branch)
        norm_status = _normalize_pipeline_status(data.get("status"))
        if norm_status in ("succeeded", "failed"):
            detail = _find_detail_for_status(data, detail_records)
            if detail is not None:
                for field in detail_merge_fields:
                    value = detail.get(field)
                    if value not in (None, "", [], {}):
                        record[field] = value
                matched_detail_ids.add(id(detail))
        # Status stays authoritative for scheme/status and (re)reads failure logs.
        _apply_lifecycle(record, data)
        records.append(record)
    print(f"Built {len(records)} records from status/ (source of truth)")

    # ── 4. Keep result runs that have no status entry (legacy / orphans) ──
    orphan_count = 0
    for rec in detail_records:
        if id(rec) in matched_detail_ids:
            continue
        lc_data = (
            lifecycle_model_only.get(_base_model_from_record(rec))
        )
        if lc_data is not None or _has_lifecycle_for_record(rec):
            continue  # already represented by the status-driven loop
        _apply_lifecycle(rec, None)
        records.append(rec)
        orphan_count += 1
    if orphan_count:
        print(f"Added {orphan_count} result runs with no status entry")

    records = dedupe_same_model_runs(records)
    records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    latest = build_latest(records)
    summary = build_summary(records, latest)

    write_json(output_dir / "runs.json", records)
    write_json(output_dir / "latest.json", latest)
    write_json(output_dir / "summary.json", summary)

    return records, latest, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan lb_eval results into dashboard JSON artifacts")
    parser.add_argument("--source-root", type=Path, default=None, help="Path to local lb_eval/results directory")
    parser.add_argument("--output-dir", type=Path, default=Path("static/data"), help="Output directory")
    parser.add_argument("--source-repo", default="XuehaoSun/lb_eval", help="GitHub source repository")
    parser.add_argument("--source-branch", default="main", help="GitHub source branch")
    parser.add_argument("--remote", action="store_true", help="Fetch data from GitHub API instead of local directory")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Remote GitHub fetcher
# ---------------------------------------------------------------------------

_NEEDED_PATTERNS = re.compile(
    r"(results_.*\.json$)"
    r"|(run_[^/]+/quant_summary\.json$)"
    r"|(run_[^/]+/accuracy\.json$)"
    r"|(run_[^/]+/logs/(?:setup_env|quantize)\.log$)"
    r"|(run_[^/]+/session_.*\.md$)"
)

# Prefixes for lifecycle directories (status tracking)
_LIFECYCLE_PREFIXES = ("status/", "requests/", "pending_requests/")


def _gh_api(url: str, token: str | None = None) -> Any:
    """Fetch a GitHub API endpoint and return parsed JSON."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_raw(repo: str, branch: str, filepath: str, dest: Path, token: str | None = None) -> None:
    """Download a single file from raw.githubusercontent.com."""
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{filepath}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                dest.write_bytes(resp.read())
            return
        except TimeoutError:
            if attempt == 3:
                raise
            print(f"  retry {attempt}/3 after timeout: {filepath}")
        except urllib.error.URLError as exc:
            if attempt == 3 or not isinstance(exc.reason, TimeoutError):
                raise
            print(f"  retry {attempt}/3 after timeout: {filepath}")


def fetch_remote_results(
    repo: str,
    branch: str,
    results_prefix: str = "results",
    dest_dir: Path | None = None,
) -> Path:
    """Fetch needed files from the remote repo into a local temp directory.

    Returns the path to the local results root (equivalent to --source-root).
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    tree_url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    print(f"Fetching tree from {tree_url} ...")
    tree_data = _gh_api(tree_url, token)
    entries = tree_data.get("tree", [])

    # Filter to files under results/ that match needed patterns
    needed: list[str] = []
    for entry in entries:
        path: str = entry.get("path", "")
        if entry.get("type") != "blob":
            continue
        if path.startswith(f"{results_prefix}/"):
            # Skip lm_eval_results files
            if "lm_eval_results" in path:
                continue
            rel = path[len(results_prefix) + 1:]  # strip "results/"
            if _NEEDED_PATTERNS.search(rel):
                needed.append(path)
        # Also fetch lifecycle directories (status/, requests/, pending_requests/)
        elif any(path.startswith(prefix) for prefix in _LIFECYCLE_PREFIXES):
            if path.endswith(".json"):
                needed.append(path)

    print(f"Found {len(needed)} files to download from {repo}")

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="lb_eval_remote_"))
    results_root = dest_dir / results_prefix

    for i, filepath in enumerate(needed, 1):
        dest = dest_dir / filepath
        try:
            _download_raw(repo, branch, filepath, dest, token)
        except urllib.error.HTTPError as exc:
            print(f"  [{i}/{len(needed)}] SKIP {filepath} ({exc.code})")
            continue
        if i % 20 == 0 or i == len(needed):
            print(f"  [{i}/{len(needed)}] downloaded")

    # Ensure run_* directories exist even if empty (so rglob finds them)
    for entry in entries:
        path: str = entry.get("path", "")
        if entry.get("type") != "tree":
            continue
        if not path.startswith(f"{results_prefix}/"):
            continue
        rel = path[len(results_prefix) + 1:]
        if re.search(r"run_\d{4}-\d{2}-\d{2}", rel):
            (dest_dir / path).mkdir(parents=True, exist_ok=True)

    print(f"Remote results cached at {results_root}")
    return results_root


def main() -> int:
    args = parse_args()

    if args.remote:
        source_root = fetch_remote_results(
            repo=args.source_repo,
            branch=args.source_branch,
        )
    elif args.source_root is not None:
        source_root = args.source_root
    else:
        raise SystemExit("Either --remote or --source-root must be provided")

    if not source_root.exists() or not source_root.is_dir():
        raise SystemExit(f"Source root does not exist or is not a directory: {source_root}")

    runs, latest, summary = scan_results(
        source_root=source_root,
        output_dir=args.output_dir,
        source_repo=args.source_repo,
        source_branch=args.source_branch,
    )

    print(f"Generated {len(runs)} runs, {len(latest)} latest records")
    print(f"Summary: {json.dumps(summary, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
