# lb-eval-monitor (v2)

A static monitoring dashboard for `XuehaoSun/lb_eval/results`.

## Architecture

- **Frontend**: SvelteKit (static export)
- **Data parser**: Python (`parser/scan_results.py`)
- **Artifacts**: JSON files in `static/data/`

## v2 features

- Robust parser traversal for both:
  - aggregate files like `results_*.json`
  - per-run folders (`run_*/quant_summary.json`, `accuracy.json`, `session_eval_*.md`, `session_quant_*.md`)
- Normalized run records with stable dashboard fields:
  - `owner`, `artifact_name`, `model_id`, `scheme`, `method`
  - `run_id`, `run_timestamp`, `run_path`, `updated_at`
  - quant/eval statuses, errors, issues, summary
  - task list and metrics preview (`piqa`, `mmlu`, `hellaswag` when present)
  - source URLs to run/session/aggregate artifacts in `XuehaoSun/lb_eval`
- Outputs generated to:
  - `static/data/runs.json`
  - `static/data/latest.json`
  - `static/data/summary.json`
- Dashboard usability improvements:
  - overview cards (total/latest and quant/eval success/fail)
  - filters (text, owner, scheme, status)
  - all runs vs latest-only toggle
  - sorting by updated/owner/model/artifact
  - detail side panel with issues, summary, tasks/metrics, source links
  - stronger status badges for failures/partial runs

## Data model

Each row in `runs.json` follows this shape:

```json
{
  "owner": "Qwen",
  "artifact_name": "Qwen3-0.6B-autoround-W4A16",
  "model_id": "Qwen3-0.6B-autoround-W4A16",
  "scheme": "W4A16",
  "method": "autoround",
  "run_id": "run_2026-05-09-08-11-52",
  "run_timestamp": "2026-05-09T08:11:52Z",
  "run_path": "Qwen/Qwen3-0.6B-autoround-W4A16/run_2026-05-09-08-11-52",
  "auto_quant_status": "success",
  "auto_eval_status": "failed",
  "quant_errors": [],
  "eval_errors": ["..."],
  "issues": ["..."],
  "summary": "...",
  "tasks": ["piqa", "hellaswag"],
  "metrics_preview": { "piqa": 0.79 },
  "quant_num_gpus": 1,
  "eval_num_gpus": 1,
  "session_eval_url": "https://github.com/XuehaoSun/lb_eval/blob/main/results/...",
  "session_quant_url": "https://github.com/XuehaoSun/lb_eval/blob/main/results/...",
  "aggregate_result_url": "https://github.com/XuehaoSun/lb_eval/blob/main/results/...",
  "updated_at": "2026-05-09T08:20:00Z"
}
```

## Local development

```bash
npm install
npm run dev
```

## Refresh data locally

Clone source repo to `source/lb_eval` (or adjust path):

```bash
python3 parser/scan_results.py \
  --source-root ./source/lb_eval/results \
  --output-dir ./static/data \
  --source-repo XuehaoSun/lb_eval \
  --source-branch main
```

Then run:

```bash
npm run build
```

## GitHub Actions

- `refresh.yml`: scheduled/manual refresh of `static/data/*.json` from `XuehaoSun/lb_eval`
- `pages.yml`: build + deploy static SvelteKit site to GitHub Pages
