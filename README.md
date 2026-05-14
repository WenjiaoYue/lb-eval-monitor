# lb-eval-monitor

Real-time monitoring dashboard for `WenjiaoYue/lb_eval/results`. Displays quantization & evaluation status, error logs, and full benchmark results.

## Architecture

- **Frontend**: SvelteKit (static export), Vite dev server
- **Data parser**: Python `parser/scan_results.py` (supports remote GitHub API fetch)
- **Data artifacts**: `static/data/runs.json`, `latest.json`, `summary.json`

## Features

- Parses `run_*/` directories: `quant_summary.json`, `accuracy.json`, `lm_eval_results/*.json`, `session_*.md`
- Normalized run records: owner, model_id, scheme, method, status, errors, issues
- Full lm_eval results (60+ subtasks with acc / acc_norm / stderr)
- Overview cards (quant/eval success/fail counts)
- Clickable bar charts to filter by status
- Text/owner/scheme/status filters, sorting, latest-only toggle
- Expandable detail panel: quant details, eval results table, error logs, GitHub source links
- Frontend auto-refreshes data every 5 minutes

## Quick Start

```bash
npm install
```

### Option 1: Two terminals (recommended for development)

Terminal 1 — Frontend dev server:

```bash
npm run dev
```

Terminal 2 — Data refresh (fetches from GitHub every 5 minutes):

```bash
npm run parser:watch
```

### Option 2: Single command

```bash
npm run start
```

> Uses `concurrently` to run `vite dev` + `watch_remote.py` together.

## Auto-Update Mechanism

- **Backend**: `watch_remote.py` fetches latest results via GitHub Trees API every 5 minutes, parses and writes to `static/data/`
- **Frontend**: Page re-fetches JSON every 5 minutes (`cache: 'no-store'`), updates immediately on data change

To adjust the refresh interval (in seconds):

```bash
python3 parser/watch_remote.py --interval 60 --output-dir ./static/data
```

## Manual Data Refresh

Fetch from remote once:

```bash
npm run parser:remote
```

Parse from a local directory:

```bash
python3 parser/scan_results.py \
  --source-root ./source/lb_eval/results \
  --output-dir ./static/data \
  --source-repo WenjiaoYue/lb_eval \
  --source-branch main
```

## Build Static Site

```bash
npm run build
npm run preview
```

## Data Model

Each record in `runs.json`:

```json
{
  "owner": "Qwen",
  "artifact_name": "Qwen3-0.6B-autoround-W4A16",
  "model_id": "Qwen3-0.6B-autoround-W4A16",
  "scheme": "W4A16",
  "method": "autoround",
  "run_id": "run_2026-05-09-08-11-52",
  "run_timestamp": "2026-05-09T08:11:52Z",
  "auto_quant_status": "success",
  "auto_eval_status": "failed",
  "quant_details": { "original_size_mb": 1200, "quantized_size_mb": 600, "..." : "..." },
  "eval_details": { "task_results": { "piqa": { "accuracy": 0.79 } } },
  "lm_eval_results": { "results": { "hellaswag": { "acc,none": 0.33, "acc_norm,none": 0.40 } } },
  "quant_errors": [],
  "eval_errors": [],
  "updated_at": "2026-05-09T08:20:00Z"
}
```

## npm Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Build static site |
| `npm run preview` | Preview build output |
| `npm run parser:remote` | Fetch and parse from GitHub once |
| `npm run parser:watch` | Periodic fetch (default 300s interval) |
| `npm run start` | Start frontend + data refresh together |

## GitHub Actions

- `refresh.yml`: Scheduled/manual refresh of `static/data/*.json`
- `pages.yml`: Build and deploy to GitHub Pages
