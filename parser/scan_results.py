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
STATUS_PRIORITY = {"failed": 0, "running": 1, "success": 2, "unknown": 3}


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
        return "unknown"
    text = str(value).strip().lower()
    if not text:
        return "unknown"
    if any(token in text for token in ("fail", "error", "exception", "traceback")):
        return "failed"
    if any(token in text for token in ("success", "succeed", "pass", "done", "complete")):
        return "success"
    if any(token in text for token in ("running", "pending", "progress", "started", "queue")):
        return "running"
    return "unknown"


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
    return "unknown"


def build_file_url(repo: str, branch: str, path_from_repo_root: str | None) -> str | None:
    if not path_from_repo_root:
        return None
    return f"https://github.com/{repo}/blob/{branch}/{path_from_repo_root}"


def parse_aggregate_candidates(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    candidates: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if any(k in node for k in ("run_id", "run_path", "model_id", "artifact_name", "auto_quant_status", "auto_eval_status")):
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
            run_path = candidate.get("run_path")
            run_id = candidate.get("run_id")
            key = str(run_path or run_id or "").strip()
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


def extract_lm_eval_results(lm_eval_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract structured results from lm_eval raw results JSON.

    Returns a dict with:
      - results: per-task metrics (acc, acc_norm, etc.)
      - config: model info
      - metadata: versions, n-shot, timing
    """
    if not isinstance(lm_eval_data, dict):
        return None

    raw_results = lm_eval_data.get("results")
    if not isinstance(raw_results, dict) or not raw_results:
        return None

    # Extract per-task metrics, filtering out subtasks (those with " - " prefix in alias)
    task_metrics: dict[str, dict[str, Any]] = {}
    for task_name, task_val in raw_results.items():
        if not isinstance(task_val, dict):
            continue
        # Extract metrics we care about
        entry: dict[str, Any] = {}
        for key in ("acc,none", "acc_stderr,none", "acc_norm,none", "acc_norm_stderr,none",
                    "exact_match,none", "exact_match_stderr,none", "alias"):
            if key in task_val:
                entry[key] = task_val[key]
        if entry:
            task_metrics[task_name] = entry

    if not task_metrics:
        return None

    output: dict[str, Any] = {"results": task_metrics}

    # Config summary
    config = lm_eval_data.get("config")
    if isinstance(config, dict):
        output["model"] = config.get("model")
        model_args = config.get("model_args")
        if isinstance(model_args, dict):
            output["model_path"] = model_args.get("pretrained")

    # Timing
    total_time = lm_eval_data.get("total_evaluation_time_seconds")
    if total_time is not None:
        output["total_time_seconds"] = total_time

    return output


def record_from_run_dir(
    run_dir: Path,
    results_root: Path,
    aggregate_index: dict[str, dict[str, Any]],
    source_repo: str,
    source_branch: str,
) -> dict[str, Any]:
    rel_path = run_dir.relative_to(results_root)
    owner = rel_path.parts[0] if len(rel_path.parts) > 0 else "unknown"
    artifact_name = rel_path.parts[1] if len(rel_path.parts) > 1 else "unknown"
    run_id = run_dir.name

    quant_summary_path = run_dir / "quant_summary.json"
    accuracy_path = run_dir / "accuracy.json"
    session_eval_path = sorted(run_dir.glob("session_eval_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    session_quant_path = sorted(run_dir.glob("session_quant_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    # Find lm_eval_results JSON
    lm_eval_results_files = sorted(run_dir.rglob("lm_eval_results/**/results_*.json"), key=lambda p: p.name, reverse=True)

    quant_data = read_json(quant_summary_path) if quant_summary_path.exists() else None
    accuracy_data = read_json(accuracy_path) if accuracy_path.exists() else None
    lm_eval_data = read_json(lm_eval_results_files[0]) if lm_eval_results_files else None

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
    eval_errors = extract_errors((accuracy_data or {}).get("errors") if isinstance(accuracy_data, dict) else None)

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
    quant_rel = (rel_path / session_quant_path[0].name).as_posix() if session_quant_path else None
    aggregate_rel = Path(aggregate_path).relative_to(results_root.parent).as_posix() if aggregate_path else None
    lm_eval_rel = lm_eval_results_files[0].relative_to(results_root).as_posix() if lm_eval_results_files else None

    return {
        "owner": owner,
        "artifact_name": artifact_name,
        "model_id": first_nonempty(aggregate.get("model_id"), (quant_data or {}).get("model_id") if isinstance(quant_data, dict) else None, artifact_name),
        "scheme": first_nonempty((quant_data or {}).get("scheme") if isinstance(quant_data, dict) else None, aggregate.get("scheme"), "unknown"),
        "method": first_nonempty((quant_data or {}).get("method") if isinstance(quant_data, dict) else None, aggregate.get("method"), "unknown"),
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
        # Full lm_eval results (top-level task scores)
        "lm_eval_results": extract_lm_eval_results(lm_eval_data),
        "session_eval_url": build_file_url(source_repo, source_branch, f"results/{eval_rel}" if eval_rel else None),
        "session_quant_url": build_file_url(source_repo, source_branch, f"results/{quant_rel}" if quant_rel else None),
        "lm_eval_results_url": build_file_url(source_repo, source_branch, f"results/{lm_eval_rel}" if lm_eval_rel else None),
        "aggregate_result_url": build_file_url(source_repo, source_branch, aggregate_rel),
        "updated_at": updated_at,
    }


def record_from_aggregate_only(
    aggregate: dict[str, Any],
    results_root: Path,
    source_repo: str,
    source_branch: str,
) -> dict[str, Any] | None:
    run_path = str(first_nonempty(aggregate.get("run_path"), "")).strip()
    run_id = str(first_nonempty(aggregate.get("run_id"), "")).strip()
    if not run_path and not run_id:
        return None

    norm_path = run_path.replace("results/", "", 1).strip("/") if run_path else ""
    parts = Path(norm_path).parts if norm_path else ()
    owner = first_nonempty(aggregate.get("owner"), parts[0] if len(parts) > 0 else "unknown")
    artifact_name = first_nonempty(aggregate.get("artifact_name"), parts[1] if len(parts) > 1 else aggregate.get("model_id") or "unknown")

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
        "scheme": first_nonempty(aggregate.get("scheme"), "unknown"),
        "method": first_nonempty(aggregate.get("method"), "unknown"),
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
    quant_counter = Counter(record.get("auto_quant_status", "unknown") for record in all_runs)
    eval_counter = Counter(record.get("auto_eval_status", "unknown") for record in all_runs)
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_runs": len(all_runs),
        "latest_models_count": len(latest_runs),
        "quant": {
            "success": quant_counter.get("success", 0),
            "failed": quant_counter.get("failed", 0),
            "running": quant_counter.get("running", 0),
            "unknown": quant_counter.get("unknown", 0),
        },
        "eval": {
            "success": eval_counter.get("success", 0),
            "failed": eval_counter.get("failed", 0),
            "running": eval_counter.get("running", 0),
            "unknown": eval_counter.get("unknown", 0),
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scan_results(
    source_root: Path,
    output_dir: Path,
    source_repo: str,
    source_branch: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    aggregate_index = index_aggregates(source_root)

    records: list[dict[str, Any]] = []
    seen_run_paths: set[str] = set()

    for run_dir in sorted([p for p in source_root.rglob("run_*") if p.is_dir()]):
        record = record_from_run_dir(run_dir, source_root, aggregate_index, source_repo, source_branch)
        records.append(record)
        seen_run_paths.add(str(record.get("run_path", "")))

    for aggregate in aggregate_index.values():
        candidate = record_from_aggregate_only(aggregate, source_root, source_repo, source_branch)
        if not candidate:
            continue
        if str(candidate.get("run_path", "")) in seen_run_paths:
            continue
        records.append(candidate)

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
    parser.add_argument("--source-repo", default="WenjiaoYue/lb_eval", help="GitHub source repository")
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
    r"|(run_[^/]+/session_eval_.*\.md$)"
    r"|(run_[^/]+/session_quant_.*\.md$)"
)


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
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())


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
        if not path.startswith(f"{results_prefix}/"):
            continue
        rel = path[len(results_prefix) + 1:]  # strip "results/"
        if _NEEDED_PATTERNS.search(rel):
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
