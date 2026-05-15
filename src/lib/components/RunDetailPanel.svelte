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
<section class="panel">
	<div class="panel-head">
		<div class="panel-title">
			<h2>{#if run.run_path}<a href="https://github.com/XuehaoSun/lb_eval/tree/main/results/{run.run_path}" target="_blank" rel="noreferrer" class="title-link">{run.model_id.includes('/') ? run.model_id : run.owner + ' / ' + run.model_id}</a>{:else}{run.model_id.includes('/') ? run.model_id : run.owner + ' / ' + run.model_id}{/if}</h2>
			<div class="panel-meta">
				<StatusBadge status={run.auto_quant_status} /> <span class="meta-label">quant</span>
				<StatusBadge status={run.auto_eval_status} /> <span class="meta-label">eval</span>
				<span class="meta-divider"></span>
				<span class="meta-text">{run.scheme} / {run.method}</span>
				<span class="meta-divider"></span>
				<span class="meta-text">{formatTime(run.updated_at)}</span>
			</div>
		</div>
		<button type="button" class="close-btn" onclick={onClose} aria-label="Close">
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
		</button>
	</div>

	<div class="panel-body" class:single-col={!run.quant_details && !run.eval_details && !run.pipeline && run.tasks.length === 0}>
		{#if run.quant_details || run.eval_details || run.tasks.length > 0 || Object.keys(run.metrics_preview).length > 0}
		<div class="col">
			{#if run.quant_details}
			<div class="card">
				<h3>Quantization Details</h3>
				<div class="info-grid">
					<div class="info-item"><span class="info-label">Source Model</span><span class="info-value">{run.quant_details.model_id || run.model_id}</span></div>
					<div class="info-item"><span class="info-label">Original Size</span><span class="info-value">{formatSize(run.quant_details.original_size_mb)}</span></div>
					<div class="info-item"><span class="info-label">Quantized Size</span><span class="info-value">{formatSize(run.quant_details.quantized_size_mb)}</span></div>
					<div class="info-item"><span class="info-label">Compression</span><span class="info-value">{run.quant_details.compression_ratio != null ? `${(run.quant_details.compression_ratio * 100).toFixed(1)}%` : '-'}</span></div>
					<div class="info-item"><span class="info-label">Duration</span><span class="info-value">{formatDuration(run.quant_details.duration_seconds)}</span></div>
					<div class="info-item"><span class="info-label">Format</span><span class="info-value">{run.quant_details.export_format || '-'}</span></div>
					<div class="info-item"><span class="info-label">Device</span><span class="info-value">{run.quant_details.device || '-'} ({run.quant_num_gpus || '?'} GPU)</span></div>
					{#if run.quant_details.hf_repo}
					<div class="info-item full"><span class="info-label">HuggingFace</span><a href={run.quant_details.hf_repo} target="_blank" rel="noreferrer" class="info-link">{run.quant_details.hf_repo}</a></div>
					{/if}
				</div>
			</div>
			{/if}

			{#if run.eval_details || run.tasks.length > 0}
			<div class="card">
				<h3>Evaluation Results</h3>
				{#if run.eval_details}
				<div class="eval-meta">
					{#if run.eval_details.eval_framework}<span>Framework: <strong>{run.eval_details.eval_framework}</strong></span>{/if}
					{#if run.eval_details.duration_seconds}<span>Duration: <strong>{formatDuration(run.eval_details.duration_seconds)}</strong></span>{/if}
					<span>GPUs: <strong>{run.eval_num_gpus || '?'}</strong></span>
				</div>
				{/if}

				{#if run.eval_details?.task_results && Object.keys(run.eval_details.task_results).length > 0}
				<div class="bench-wrap">
				<table class="bench">
					<thead><tr><th>Task</th><th>Accuracy</th><th>Stderr</th></tr></thead>
					<tbody>
					{#each Object.entries(run.eval_details.task_results) as [task, result]}
					<tr>
						<td>{task}</td>
						<td class="mono">{result.accuracy != null ? (typeof result.accuracy === 'number' ? (result.accuracy * 100).toFixed(2) + '%' : result.accuracy) : '-'}</td>
						<td class="mono muted">{result.accuracy_stderr != null ? '\u00B1' + (typeof result.accuracy_stderr === 'number' ? (result.accuracy_stderr * 100).toFixed(2) + '%' : result.accuracy_stderr) : '-'}</td>
					</tr>
					{/each}
					</tbody>
				</table>
				</div>
				{:else if Object.keys(run.metrics_preview).length > 0}
				<div class="bench-wrap">
				<table class="bench">
					<thead><tr><th>Task</th><th>Score</th></tr></thead>
					<tbody>
					{#each Object.entries(run.metrics_preview) as [task, value]}
					<tr><td>{task}</td><td class="mono">{formatMetric(value)}</td></tr>
					{/each}
					</tbody>
				</table>
				</div>
				{:else if run.tasks.length > 0}
				<div class="chips">{#each run.tasks as task}<span class="chip">{task}</span>{/each}</div>
				{/if}
			</div>
			{/if}
		</div>
		{/if}

		<!-- Right column: Errors + Issues + Links -->
		<div class="col">
			{#if run.quant_errors.length > 0 || run.eval_errors.length > 0}
			<div class="card card--error">
				<h3>Error Logs</h3>
				{#if run.quant_errors.length > 0}
				<h4>Quantization Errors</h4>
				{#each run.quant_errors as err}
				<pre class="err-block">{err}</pre>
				{/each}
				{/if}
				{#if run.eval_errors.length > 0}
				<h4>Evaluation Errors</h4>
				{#each run.eval_errors as err}
				<pre class="err-block">{err}</pre>
				{/each}
				{/if}
			</div>
			{/if}

			{#if run.summary}
			<div class="card">
				<h3>Summary</h3>
				<p class="summary-text">{run.summary}</p>
			</div>
			{/if}

			{#if run.issues.length > 0}
			<div class="card">
				<h3>Issues ({run.issues.length})</h3>
				<ul class="issues-list">
					{#each run.issues as issue}
					<li>{issue}</li>
					{/each}
				</ul>
			</div>
			{/if}

			{#if run.pipeline}
			<div class="card">
				<h3>Pipeline Status</h3>
				<div class="pipeline-timeline">
					<div class="pipeline-step" class:step-done={run.pipeline.submitted_time} class:step-active={run.pipeline.status === 'pending' && !run.pipeline.triggered_time}>
						<span class="step-dot"></span>
						<span class="step-label">Submitted</span>
						<span class="step-time">{run.pipeline.submitted_time ? formatTime(run.pipeline.submitted_time) : '-'}</span>
					</div>
					<div class="pipeline-step" class:step-done={run.pipeline.triggered_time && run.pipeline.status !== 'pending'} class:step-active={run.pipeline.status === 'running' || (run.pipeline.triggered_time && run.pipeline.status === 'pending')}>
						<span class="step-dot"></span>
						<span class="step-label">Running</span>
						<span class="step-time">{run.pipeline.triggered_time ? formatTime(run.pipeline.triggered_time) : '-'}</span>
					</div>
					<div class="pipeline-step" class:step-done={run.pipeline.status === 'succeeded'} class:step-failed={run.pipeline.status === 'failed'}>
						<span class="step-dot"></span>
						<span class="step-label">{run.pipeline.status === 'failed' ? 'Failed' : 'Succeeded'}</span>
						<span class="step-time">{run.pipeline.status === 'succeeded' || run.pipeline.status === 'failed' ? formatTime(run.run_timestamp) : '-'}</span>
					</div>
				</div>
				<div class="info-grid" style="margin-top: 0.75rem;">
					{#if run.pipeline.job_type}<div class="info-item"><span class="info-label">Job Type</span><span class="info-value">{run.pipeline.job_type}</span></div>{/if}
					{#if run.pipeline.quant_scheme}<div class="info-item"><span class="info-label">Scheme</span><span class="info-value">{run.pipeline.quant_scheme}</span></div>{/if}
					{#if run.pipeline.hardware}<div class="info-item"><span class="info-label">Hardware</span><span class="info-value">{run.pipeline.hardware} × {run.pipeline.gpu_nums || '?'}</span></div>{/if}
					{#if run.pipeline.params}<div class="info-item"><span class="info-label">Params</span><span class="info-value">{run.pipeline.params}B</span></div>{/if}
					{#if run.pipeline.model_weight_gb}<div class="info-item"><span class="info-label">Model Size</span><span class="info-value">{run.pipeline.model_weight_gb} GB</span></div>{/if}
					{#if run.pipeline.quant_model_size_gb}<div class="info-item"><span class="info-label">Quant Size</span><span class="info-value">{run.pipeline.quant_model_size_gb} GB</span></div>{/if}
					{#if run.pipeline.ci_run_id}<div class="info-item"><span class="info-label">CI Run</span><span class="info-value">#{run.pipeline.ci_run_id}</span></div>{/if}
				</div>
			</div>
			{/if}

			<div class="card">
				<h3>Source & Links</h3>
				<div class="links-row">
					{#if run.session_eval_url}<a href={run.session_eval_url} target="_blank" rel="noreferrer" class="link-pill">Session Eval Log</a>{/if}
					{#if run.session_quant_url}<a href={run.session_quant_url} target="_blank" rel="noreferrer" class="link-pill">Session Quant Log</a>{/if}
					{#if run.aggregate_result_url}<a href={run.aggregate_result_url} target="_blank" rel="noreferrer" class="link-pill">Aggregate Result</a>{/if}
				</div>
				<div class="run-meta">
					<span>Run: <code>{run.run_id}</code></span>
					<span>Path: <code>{run.run_path}</code></span>
				</div>
			</div>
		</div>
	</div>
</section>
{/if}

<style>
.panel {
	margin-bottom: 1.25rem;
	border-radius: 14px;
	background: #fff;
	overflow: hidden;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.panel-head {
	display: flex;
	justify-content: space-between;
	align-items: flex-start;
	padding: 1rem 1.75rem;
	background: linear-gradient(135deg, #1d4ed8, #3b82f6);
	border-bottom: none;
}
.panel-title h2 {
	margin: 0;
	font-size: 1rem;
	font-weight: 700;
	color: #fff;
}
.title-link {
	color: #fff;
	text-decoration: none;
}
.title-link:hover {
	text-decoration: underline;
	opacity: 0.9;
}
.panel-meta {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 0.375rem;
	margin-top: 0.375rem;
	font-size: 0.8125rem;
}
.meta-label {
	font-size: 0.75rem;
	color: rgba(255,255,255,0.7);
	margin-right: 0.25rem;
}
.meta-divider {
	width: 1px;
	height: 14px;
	background: rgba(255,255,255,0.25);
	margin: 0 0.375rem;
}
.meta-text {
	font-size: 0.8125rem;
	color: rgba(255,255,255,0.8);
}
.close-btn {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 30px;
	height: 30px;
	border: 1px solid rgba(255,255,255,0.2);
	background: rgba(255,255,255,0.1);
	border-radius: 6px;
	cursor: pointer;
	color: rgba(255,255,255,0.8);
	transition: background 0.15s;
	flex-shrink: 0;
}
.close-btn:hover { background: rgba(255,255,255,0.2); }

.panel-body {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 1rem;
	padding: 1.125rem 1.75rem;
	max-height: 560px;
	overflow: auto;
}
.panel-body.single-col {
	grid-template-columns: 1fr;
}
.col {
	display: flex;
	flex-direction: column;
	gap: 1rem;
}
.card {
	padding: 0.875rem 1.125rem;
	border: 1px solid #e2e8f0;
	border-radius: 10px;
	background: #f8fafc;
}
.card h3 {
	margin: 0 0 0.625rem;
	font-size: 0.6875rem;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.06em;
	color: #475569;
	display: flex;
	align-items: center;
	gap: 0.5rem;
}
.card h4 {
	margin: 0.75rem 0 0.375rem;
	font-size: 0.75rem;
	font-weight: 700;
	color: #334155;
}
.card--error {
	background: #fef2f2;
	border-color: #fecaca;
}
.card--error h3 { color: #b91c1c; }

/* Info grid */
.info-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 0.5rem 1rem;
}
.info-item { display: flex; flex-direction: column; font-size: 0.8125rem; }
.info-item.full { grid-column: 1 / -1; }
.info-label { font-size: 0.6875rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; margin-bottom: 0.125rem; }
.info-value { font-weight: 700; color: #0f172a; }
.info-link { color: #2563eb; text-decoration: none; font-size: 0.75rem; word-break: break-all; font-weight: 600; }
.info-link:hover { text-decoration: underline; }

/* Eval meta */
.eval-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 0.875rem;
	margin-bottom: 0.625rem;
	font-size: 0.8125rem;
	color: #475569;
}

/* Benchmark table */
.bench-wrap {
	overflow-x: auto;
}
.bench {
	width: 100%;
	border-collapse: collapse;
	font-size: 0.8125rem;
}
.bench th, .bench td {
	padding: 0.5rem 0.625rem;
	text-align: left;
	border-bottom: 1px solid #e2e8f0;
}
.bench th {
	color: #64748b;
	font-weight: 600;
	font-size: 0.6875rem;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	background: #f1f5f9;
}
.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-weight: 700; font-size: 0.75rem; color: #0f172a; }
.muted { color: #94a3b8; font-weight: 400; }

/* Errors */
.err-block {
	margin: 0.375rem 0;
	padding: 0.75rem;
	background: #fff;
	border: 1px solid #fecaca;
	border-radius: 8px;
	font-family: 'SF Mono', 'Fira Code', monospace;
	font-size: 0.6875rem;
	line-height: 1.6;
	white-space: pre-wrap;
	word-break: break-word;
	color: #991b1b;
	max-height: 160px;
	overflow: auto;
}

/* Summary & issues */
.summary-text { margin: 0; font-size: 0.8125rem; line-height: 1.6; color: #334155; }
.issues-list {
	margin: 0;
	padding-left: 1.25rem;
	font-size: 0.8125rem;
	line-height: 1.6;
	max-height: 160px;
	overflow: auto;
}
.issues-list li { margin-bottom: 0.25rem; color: #475569; }

/* Chips */
.chips { display: flex; flex-wrap: wrap; gap: 0.375rem; }
.chip {
	padding: 0.25rem 0.625rem;
	background: #eff6ff;
	color: #1d4ed8;
	border: 1px solid #bfdbfe;
	border-radius: 6px;
	font-size: 0.6875rem;
	font-weight: 600;
}

/* Links */
.links-row {
	display: flex;
	flex-wrap: wrap;
	gap: 0.5rem;
	margin-bottom: 0.75rem;
}
.link-pill {
	font-size: 0.75rem;
	color: #2563eb;
	text-decoration: none;
	padding: 0.25rem 0.625rem;
	background: #eff6ff;
	border: 1px solid #bfdbfe;
	border-radius: 6px;
	font-weight: 600;
	transition: background 0.15s;
}
.link-pill:hover { background: #dbeafe; }
.run-meta {
	display: flex;
	flex-direction: column;
	gap: 0.3rem;
	font-size: 0.75rem;
	color: #64748b;
}
.run-meta code { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.6875rem; color: #334155; background: #f1f5f9; padding: 0.125rem 0.375rem; border-radius: 4px; }

/* Pipeline timeline */
.pipeline-timeline {
	display: flex;
	align-items: flex-start;
	gap: 0;
	position: relative;
}
.pipeline-step {
	flex: 1;
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 0.25rem;
	position: relative;
}
.pipeline-step::before {
	content: '';
	position: absolute;
	top: 7px;
	left: 50%;
	width: 100%;
	height: 2px;
	background: #e5e7eb;
	z-index: 0;
}
.pipeline-step:last-child::before { display: none; }
.step-dot {
	width: 14px;
	height: 14px;
	border-radius: 50%;
	background: #e5e7eb;
	border: 2px solid #d1d5db;
	position: relative;
	z-index: 1;
}
.step-done .step-dot { background: #10b981; border-color: #059669; }
.step-active .step-dot { background: #f59e0b; border-color: #d97706; animation: pulse 1.5s infinite; }
.step-failed .step-dot { background: #ef4444; border-color: #dc2626; }
.step-label { font-size: 0.6875rem; font-weight: 600; color: #6b7280; text-align: center; }
.step-done .step-label { color: #059669; }
.step-active .step-label { color: #d97706; }
.step-failed .step-label { color: #dc2626; }
.step-time { font-size: 0.625rem; color: #9ca3af; text-align: center; }
@keyframes pulse {
	0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
	50% { box-shadow: 0 0 0 4px rgba(245, 158, 11, 0); }
}

@media (max-width: 900px) {
	.panel-body { grid-template-columns: 1fr; }
	.panel-head { padding: 0.875rem 1.25rem; }
	.panel-body { padding: 0.875rem 1.25rem; }
}
</style>
