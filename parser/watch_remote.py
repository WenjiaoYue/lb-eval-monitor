#!/usr/bin/env python3
"""Periodically fetch remote results and regenerate static/data/*.json.

Usage:
    python3 parser/watch_remote.py [--interval 300] [--output-dir ./static/data]

This keeps running and re-fetches data every INTERVAL seconds (default: 5 min).
When used alongside `npm run dev`, the Vite dev server will detect file changes
and the browser page will auto-refresh the data.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Import from the main parser module
sys.path.insert(0, str(Path(__file__).parent))
from scan_results import fetch_remote_results, scan_results  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch remote repo and refresh data periodically")
    parser.add_argument("--interval", type=int, default=300, help="Refresh interval in seconds (default: 300)")
    parser.add_argument("--output-dir", type=Path, default=Path("static/data"), help="Output directory")
    parser.add_argument("--mirror-dir", type=Path, default=None, help="Optional: also copy generated JSON here (e.g. build/data for the deployed bundle)")
    parser.add_argument("--source-repo", default="XuehaoSun/lb_eval", help="GitHub source repository")
    parser.add_argument("--source-branch", default="main", help="GitHub source branch")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Reusable cache dir for fetched remote files (default: a fixed temp dir). Reused & cleared each cycle to avoid filling the disk.")
    args = parser.parse_args()

    # Reuse a single cache directory across cycles instead of creating a fresh
    # tempfile.mkdtemp() every refresh (which never gets cleaned up and fills the
    # disk over time). The directory is wiped at the start of each cycle so only
    # one copy of the remote files exists on disk at any moment.
    cache_dir = args.cache_dir or (Path(tempfile.gettempdir()) / "lb_eval_remote_cache")

    print(f"Starting watch mode: refreshing every {args.interval}s from {args.source_repo}")
    print(f"Output: {args.output_dir.resolve()}")
    print(f"Cache:  {cache_dir.resolve()} (reused each cycle)")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Fetching remote data...")
            # Clear the cache before each fetch so stale/removed files don't pile up.
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            cache_dir.mkdir(parents=True, exist_ok=True)
            source_root = fetch_remote_results(
                repo=args.source_repo,
                branch=args.source_branch,
                dest_dir=cache_dir,
            )
            runs, latest, summary = scan_results(
                source_root=source_root,
                output_dir=args.output_dir,
                source_repo=args.source_repo,
                source_branch=args.source_branch,
            )
            print(f"[{time.strftime('%H:%M:%S')}] Done: {len(runs)} runs, {len(latest)} latest")
            if args.mirror_dir:
                args.mirror_dir.mkdir(parents=True, exist_ok=True)
                for name in ("runs.json", "latest.json", "summary.json"):
                    src = args.output_dir / name
                    if src.exists():
                        shutil.copy2(src, args.mirror_dir / name)
                print(f"[{time.strftime('%H:%M:%S')}] Mirrored to {args.mirror_dir}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] Error: {exc}")

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            break

    print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
