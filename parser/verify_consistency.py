#!/usr/bin/env python3
"""Cross-check static/data/latest.json against the raw lb_eval repo.

Verifies that every (model, scheme) pair in status/, pending_requests/, and
requests/ appears exactly once in our latest.json with the correct quant/eval
status semantics. Exits non-zero on any drift.

Usage: python3 parser/verify_consistency.py [--repo /path/to/lb_eval] [--data static/data]
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path


def norm_scheme(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"\((\w+)\)", value)
    return match.group(1) if match else value


def load_truth(repo: Path) -> dict[tuple[str, str], tuple[str, str, str]]:
    truth: dict[tuple[str, str], tuple[str, str, str]] = {}
    for sub in ("requests", "pending_requests", "status"):
        for path in sorted(glob.glob(str(repo / sub / "*" / "*.json"))):
            try:
                data = json.load(open(path))
            except Exception:
                continue
            model = data.get("model", "")
            scheme = norm_scheme(data.get("quant_scheme") or data.get("compute_dtype"))
            if not model or not scheme:
                continue
            truth[(model, scheme)] = (
                data.get("status", ""),
                sub,
                data.get("script", ""),
            )
    return truth


def record_key(record: dict) -> tuple[str, str]:
    owner = record.get("owner", "")
    aname = record.get("artifact_name", "")
    model_id = record.get("model_id", "") or aname
    scheme = record.get("scheme", "")
    if "/" in model_id:
        base = model_id
    else:
        base = re.sub(
            r"[-_](?:autoround|gptq|awq|compressed[_-]?tensors|smoothquant)[-_][A-Za-z0-9]+$",
            "",
            aname,
            flags=re.IGNORECASE,
        )
        base = re.sub(
            r"[-_](?:MXFP4|NVFP4|W4A16|W8A8|W8A16|INT4|INT8)$",
            "",
            base,
            flags=re.IGNORECASE,
        )
        base = f"{owner}/{base}" if owner else base
    return (base, scheme)


def expected_phases(raw_status: str, script: str) -> tuple[str, str]:
    s = (raw_status or "").strip().lower()
    sc = (script or "").strip().lower()
    if s == "finished":
        return ("success" if sc != "auto_eval" else "unknown", "success")
    if "eval fail" in s:
        return ("success" if sc != "auto_eval" else "unknown", "failed")
    if "quant fail" in s:
        return ("failed", "unknown")
    if s == "failed":
        return ("unknown", "failed") if sc == "auto_eval" else ("failed", "unknown")
    if s == "pending":
        return ("running", "unknown")
    if s == "running":
        return ("running", "unknown")
    return ("unknown", "unknown")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/home/sdp/wenjiao/5_14/lb_eval")
    parser.add_argument("--data", default="static/data")
    args = parser.parse_args()

    truth = load_truth(Path(args.repo))
    latest = json.load(open(Path(args.data) / "latest.json"))

    ours: dict[tuple[str, str], dict] = {}
    dups: list[tuple[str, str]] = []
    for record in latest:
        key = record_key(record)
        if key in ours:
            dups.append(key)
        else:
            ours[key] = record

    missing = sorted(set(truth) - set(ours))
    extra = sorted(set(ours) - set(truth))
    mismatches = []
    for key in sorted(set(truth) & set(ours)):
        raw, _src, script = truth[key]
        eq, ee = expected_phases(raw, script)
        rec = ours[key]
        if (rec.get("auto_quant_status"), rec.get("auto_eval_status")) != (eq, ee):
            mismatches.append((key, raw, script, (eq, ee),
                               (rec.get("auto_quant_status"), rec.get("auto_eval_status"))))

    print(f"truth={len(truth)}  latest={len(latest)}  "
          f"missing={len(missing)}  extra={len(extra)}  "
          f"duplicates={len(dups)}  status_mismatches={len(mismatches)}")
    for key in missing:
        print(f"  MISSING  {key}  truth={truth[key]}")
    for key in extra:
        print(f"  EXTRA    {key}  artifact={ours[key].get('artifact_name')}")
    for key in dups:
        print(f"  DUP      {key}")
    for key, raw, script, exp_, got in mismatches:
        print(f"  MISMATCH {key}  raw={raw!r} script={script}  expected={exp_}  got={got}")

    ok = not (missing or extra or dups or mismatches)
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
