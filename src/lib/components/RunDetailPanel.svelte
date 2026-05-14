<script lang="ts">
import StatusBadge from '$lib/components/StatusBadge.svelte';
import type { RunRecord } from '$lib/types';

let { run = null, onClose }: { run: RunRecord | null; onClose: () => void } = $props();

const formatMetric = (value: number | string) => {
if (typeof value === 'number') return value.toFixed(4);
return value;
};

const formatTime = (iso: string) => {
if (!iso) return '-';
try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

const formatSize = (mb: number | undefined) => {
if (mb == null) return '-';
if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
return `${mb.toFixed(1)} MB`;
};

const formatDuration = (sec: number | string | undefined) => {
if (sec == null) return '-';
const s = typeof sec === 'string' ? parseFloat(sec) : sec;
if (isNaN(s)) return String(sec);
if (s < 60) return `${s.toFixed(0)}s`;
if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
};
</script>

{#if run}
<section class="detail-panel">
<div class="detail-header">
<div class="detail-title">
<h2>{run.owner} / {run.model_id}</h2>
<div class="detail-meta">
<StatusBadge status={run.auto_quant_status} /> quant
<StatusBadge status={run.auto_eval_status} /> eval
<span class="meta-sep">|</span>
<span>{run.scheme} / {run.method}</span>
<span class="meta-sep">|</span>
<span>{formatTime(run.updated_at)}</span>
</div>
</div>
			<button type="button" class="close-btn" onclick={onClose} aria-label="Close">✕</button>
</div>

<div class="detail-body" class:single-col={!run.quant_details && !run.eval_details && !run.lm_eval_results && run.tasks.length === 0}>
<!-- Left column: Info + Quant + Eval details (only if data exists) -->
{#if run.quant_details || run.eval_details || run.lm_eval_results || run.tasks.length > 0 || Object.keys(run.metrics_preview).length > 0}
<div class="detail-col">
<!-- Quant Details -->
{#if run.quant_details}
<div class="detail-card">
<h3>Quantization Details</h3>
<div class="detail-grid">
<div class="dg-item"><span class="dg-label">Source Model</span><span class="dg-value">{run.quant_details.model_id || run.model_id}</span></div>
<div class="dg-item"><span class="dg-label">Original Size</span><span class="dg-value">{formatSize(run.quant_details.original_size_mb)}</span></div>
<div class="dg-item"><span class="dg-label">Quantized Size</span><span class="dg-value">{formatSize(run.quant_details.quantized_size_mb)}</span></div>
<div class="dg-item"><span class="dg-label">Compression</span><span class="dg-value">{run.quant_details.compression_ratio != null ? `${(run.quant_details.compression_ratio * 100).toFixed(1)}%` : '-'}</span></div>
<div class="dg-item"><span class="dg-label">Duration</span><span class="dg-value">{formatDuration(run.quant_details.duration_seconds)}</span></div>
<div class="dg-item"><span class="dg-label">Format</span><span class="dg-value">{run.quant_details.export_format || '-'}</span></div>
<div class="dg-item"><span class="dg-label">Device</span><span class="dg-value">{run.quant_details.device || '-'} ({run.quant_num_gpus || '?'} GPU)</span></div>
{#if run.quant_details.hf_repo}
<div class="dg-item full"><span class="dg-label">HuggingFace</span><a href={run.quant_details.hf_repo} target="_blank" rel="noreferrer" class="dg-link">{run.quant_details.hf_repo}</a></div>
{/if}
</div>
</div>
{/if}

<!-- Eval Details & Benchmark Results -->
{#if run.eval_details || run.tasks.length > 0}
<div class="detail-card">
<h3>Evaluation Results</h3>
{#if run.eval_details}
<div class="eval-meta">
{#if run.eval_details.eval_framework}<span>Framework: <strong>{run.eval_details.eval_framework}</strong></span>{/if}
{#if run.eval_details.duration_seconds}<span>Duration: <strong>{formatDuration(run.eval_details.duration_seconds)}</strong></span>{/if}
<span>GPUs: <strong>{run.eval_num_gpus || '?'}</strong></span>
</div>
{/if}

{#if run.eval_details?.task_results && Object.keys(run.eval_details.task_results).length > 0}
<table class="bench-table">
<thead><tr><th>Task</th><th>Accuracy</th><th>Stderr</th></tr></thead>
<tbody>
{#each Object.entries(run.eval_details.task_results) as [task, result]}
<tr>
<td>{task}</td>
<td class="metric-val">{result.accuracy != null ? (typeof result.accuracy === 'number' ? (result.accuracy * 100).toFixed(2) + '%' : result.accuracy) : '-'}</td>
<td class="metric-stderr">{result.accuracy_stderr != null ? '±' + (typeof result.accuracy_stderr === 'number' ? (result.accuracy_stderr * 100).toFixed(2) + '%' : result.accuracy_stderr) : '-'}</td>
</tr>
{/each}
</tbody>
</table>
{:else if Object.keys(run.metrics_preview).length > 0}
<table class="bench-table">
<thead><tr><th>Task</th><th>Score</th></tr></thead>
<tbody>
{#each Object.entries(run.metrics_preview) as [task, value]}
<tr><td>{task}</td><td class="metric-val">{formatMetric(value)}</td></tr>
{/each}
</tbody>
</table>
{:else if run.tasks.length > 0}
<div class="chips">{#each run.tasks as task}<span class="chip">{task}</span>{/each}</div>
{/if}
</div>
{/if}

<!-- Full lm_eval benchmark results -->
{#if run.lm_eval_results}
<div class="detail-card">
<h3>Full Benchmark Results (lm_eval)
{#if run.lm_eval_results.total_time_seconds}
<span class="eval-time">{formatDuration(run.lm_eval_results.total_time_seconds)}</span>
{/if}
{#if run.lm_eval_results_url}
<a href={run.lm_eval_results_url} target="_blank" rel="noreferrer" class="source-link">View Raw</a>
{/if}
</h3>
{#if run.lm_eval_results.model_path}
<div class="eval-meta"><span>Model: <strong>{run.lm_eval_results.model_path}</strong></span></div>
{/if}
<table class="bench-table lm-eval-table">
<thead><tr><th>Task</th><th>Acc</th><th>Stderr</th><th>Acc Norm</th><th>Stderr</th></tr></thead>
<tbody>
{#each Object.entries(run.lm_eval_results.results) as [task, m]}
<tr>
<td class="task-name">{m.alias || task}</td>
<td class="metric-val">{m['acc,none'] != null ? (m['acc,none'] * 100).toFixed(2) + '%' : '-'}</td>
<td class="metric-stderr">{m['acc_stderr,none'] != null ? '±' + (m['acc_stderr,none'] * 100).toFixed(2) + '%' : '-'}</td>
<td class="metric-val">{m['acc_norm,none'] != null ? (m['acc_norm,none'] * 100).toFixed(2) + '%' : '-'}</td>
<td class="metric-stderr">{m['acc_norm_stderr,none'] != null ? '±' + (m['acc_norm_stderr,none'] * 100).toFixed(2) + '%' : '-'}</td>
</tr>
{/each}
</tbody>
</table>
</div>
{/if}
</div>
{/if}

<!-- Right column: Errors + Issues + Links -->
<div class="detail-col">
<!-- Errors -->
{#if run.quant_errors.length > 0 || run.eval_errors.length > 0}
<div class="detail-card error-card">
<h3>Error Logs</h3>
{#if run.quant_errors.length > 0}
<h4>Quantization Errors</h4>
{#each run.quant_errors as err}
<pre class="error-entry">{err}</pre>
{/each}
{/if}
{#if run.eval_errors.length > 0}
<h4>Evaluation Errors</h4>
{#each run.eval_errors as err}
<pre class="error-entry">{err}</pre>
{/each}
{/if}
</div>
{/if}

<!-- Summary -->
{#if run.summary}
<div class="detail-card">
<h3>Summary</h3>
<p class="summary-text">{run.summary}</p>
</div>
{/if}

<!-- Issues -->
{#if run.issues.length > 0}
<div class="detail-card">
<h3>Issues from Session ({run.issues.length})</h3>
<ul class="issues-list">
{#each run.issues as issue}
<li>{issue}</li>
{/each}
</ul>
</div>
{/if}

<!-- Source links & run info -->
<div class="detail-card">
<h3>Source & Links</h3>
<div class="links-grid">
{#if run.session_eval_url}<a href={run.session_eval_url} target="_blank" rel="noreferrer">Session Eval Log</a>{/if}
{#if run.session_quant_url}<a href={run.session_quant_url} target="_blank" rel="noreferrer">Session Quant Log</a>{/if}
{#if run.lm_eval_results_url}<a href={run.lm_eval_results_url} target="_blank" rel="noreferrer">lm_eval Results JSON</a>{/if}
{#if run.aggregate_result_url}<a href={run.aggregate_result_url} target="_blank" rel="noreferrer">Aggregate Result</a>{/if}
</div>
<div class="run-info">
<span>Run: <code>{run.run_id}</code></span>
<span>Path: <code>{run.run_path}</code></span>
</div>
</div>
</div>
</div>
</section>
{/if}

<style>
.detail-panel {
margin-bottom: 1rem;
border: 1px solid #e5e7eb;
border-radius: 0.75rem;
background: #fff;
overflow: hidden;
}
.detail-header {
display: flex;
justify-content: space-between;
align-items: flex-start;
padding: 0.85rem 1rem;
background: #f8fafc;
border-bottom: 1px solid #e5e7eb;
}
.detail-title h2 {
margin: 0;
font-size: 1.05rem;
}
.detail-meta {
display: flex;
align-items: center;
flex-wrap: wrap;
gap: 0.4rem;
margin-top: 0.3rem;
font-size: 0.82rem;
color: #4b5563;
}
.meta-sep { color: #d1d5db; }
.close-btn {
border: 1px solid #d1d5db;
background: #fff;
border-radius: 0.4rem;
cursor: pointer;
padding: 0.2rem 0.5rem;
font-size: 1rem;
}
.close-btn:hover { background: #f3f4f6; }

.detail-body {
display: grid;
grid-template-columns: 1fr 1fr;
gap: 0.75rem;
padding: 0.85rem 1rem;
max-height: 500px;
overflow: auto;
}
.detail-body.single-col {
grid-template-columns: 1fr;
}
.detail-col {
display: flex;
flex-direction: column;
gap: 0.75rem;
}
.detail-card {
padding: 0.7rem;
border: 1px solid #f3f4f6;
border-radius: 0.5rem;
background: #fafafa;
}
.detail-card h3 {
margin: 0 0 0.5rem;
font-size: 0.8rem;
text-transform: uppercase;
letter-spacing: 0.03em;
color: #6b7280;
}
.detail-card h4 {
margin: 0.5rem 0 0.3rem;
font-size: 0.78rem;
color: #374151;
}
.error-card { background: #fef2f2; border-color: #fecaca; }
.error-card h3 { color: #991b1b; }

/* Detail grid for quant info */
.detail-grid {
display: grid;
grid-template-columns: 1fr 1fr;
gap: 0.3rem 0.75rem;
}
.dg-item { display: flex; flex-direction: column; font-size: 0.8rem; }
.dg-item.full { grid-column: 1 / -1; }
.dg-label { color: #6b7280; font-size: 0.72rem; text-transform: uppercase; }
.dg-value { font-weight: 600; color: #111827; }
.dg-link { color: #2563eb; text-decoration: none; font-size: 0.78rem; word-break: break-all; }
.dg-link:hover { text-decoration: underline; }

/* Eval meta */
.eval-meta {
display: flex;
flex-wrap: wrap;
gap: 0.75rem;
margin-bottom: 0.5rem;
font-size: 0.8rem;
color: #4b5563;
}

/* Benchmark table */
.bench-table {
width: 100%;
border-collapse: collapse;
font-size: 0.82rem;
}
.bench-table th, .bench-table td {
padding: 0.3rem 0.5rem;
text-align: left;
border-bottom: 1px solid #e5e7eb;
}
.bench-table th { color: #6b7280; font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }
.metric-val { font-family: monospace; font-weight: 600; }
.metric-stderr { font-family: monospace; font-size: 0.75rem; color: #6b7280; }

/* Errors */
.error-entry {
margin: 0.3rem 0;
padding: 0.5rem;
background: #fff5f5;
border: 1px solid #fecaca;
border-radius: 0.4rem;
font-family: monospace;
font-size: 0.75rem;
line-height: 1.5;
white-space: pre-wrap;
word-break: break-word;
color: #7f1d1d;
max-height: 150px;
overflow: auto;
}

/* Summary & issues */
.summary-text { margin: 0; font-size: 0.82rem; line-height: 1.5; color: #374151; }
.issues-list {
margin: 0;
padding-left: 1rem;
font-size: 0.8rem;
line-height: 1.5;
max-height: 150px;
overflow: auto;
}
.issues-list li { margin-bottom: 0.2rem; color: #4b5563; }

/* Chips */
.chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.chip { padding: 0.15rem 0.5rem; background: #eff6ff; color: #1d4ed8; border-radius: 999px; font-size: 0.75rem; }

/* Links */
.links-grid {
display: flex;
flex-wrap: wrap;
gap: 0.5rem;
margin-bottom: 0.5rem;
}
.links-grid a {
font-size: 0.8rem;
color: #2563eb;
text-decoration: none;
padding: 0.2rem 0.5rem;
background: #eff6ff;
border-radius: 0.3rem;
}
.links-grid a:hover { text-decoration: underline; }
.run-info {
display: flex;
flex-direction: column;
gap: 0.2rem;
font-size: 0.75rem;
color: #6b7280;
}
.run-info code { font-family: monospace; font-size: 0.72rem; }

@media (max-width: 900px) {
.detail-body { grid-template-columns: 1fr; }
}

/* lm_eval full table */
.lm-eval-table { max-height: 400px; display: block; overflow-y: auto; }
.lm-eval-table thead, .lm-eval-table tbody, .lm-eval-table tr { display: table; width: 100%; table-layout: fixed; }
.lm-eval-table thead { position: sticky; top: 0; background: #fafafa; z-index: 1; }
.task-name { font-size: 0.78rem; word-break: break-word; }
.eval-time { font-size: 0.7rem; font-weight: 400; color: #6b7280; margin-left: 0.5rem; }
.source-link { font-size: 0.7rem; font-weight: 400; color: #2563eb; text-decoration: none; margin-left: 0.5rem; }
.source-link:hover { text-decoration: underline; }
</style>
