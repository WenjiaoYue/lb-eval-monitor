<script lang="ts">
import StatusBadge from '$lib/components/StatusBadge.svelte';
import type { RunRecord } from '$lib/types';
import { tick } from 'svelte';

let { run = null, onClose }: { run: RunRecord | null; onClose: () => void } = $props();
let panelBody: HTMLElement | undefined = $state();
let evalOpen = $state(false);

const evalResultCount = $derived(
	run
		? (Object.keys(run.eval_details?.task_results ?? {}).length
			|| Object.keys(run.metrics_preview ?? {}).length
			|| run.tasks.length)
		: 0
);

$effect(() => {
	// Re-collapse the Evaluation Results section whenever a different run opens.
	run;
	evalOpen = false;
});

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

const hasLogs = (record: RunRecord) => record.quant_errors.length > 0 || record.eval_errors.length > 0;

const displayMethod = (record: RunRecord) => {
	const hay = `${record.method || ''} ${record.artifact_name || ''}`.toLowerCase();
	if (hay.includes('rtn')) return 'RTN';
	if (hay.includes('tuning')) return 'TUNING';
	if (record.status_url && !String(record.status_url.split('/').pop() || '').toLowerCase().includes('_tuning')) return 'RTN';
	if (hay.includes('autoround') || hay.includes('auto_eval') || String(record.method || '').trim()) return 'TUNING';
	return '-';
};

const scrollToBottom = (el: Element | null | undefined) => {
	if (el instanceof HTMLElement) {
		el.scrollTop = el.scrollHeight;
		el.scrollTo({ top: el.scrollHeight, behavior: 'auto' });
	}
};

const scrollNestedLogsToBottom = () => {
		panelBody?.querySelectorAll('.err-scroll').forEach(scrollToBottom);
};

const scrollOpenContentToBottom = async () => {
	await tick();
	for (let i = 0; i < 8; i += 1) {
		await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
		scrollNestedLogsToBottom();
	}
};

$effect(() => {
	if (run) void scrollOpenContentToBottom();
});
</script>

{#if run}
<section class="panel">
	<div class="panel-head">
		<div class="panel-title">
			<h2>{#if run.run_path}<a href="https://github.com/XuehaoSun/lb_eval/tree/main/results/{run.run_path}" target="_blank" rel="noreferrer" class="title-link">{run.model_id.includes('/') ? run.model_id : run.owner + ' / ' + run.model_id}</a>{:else}{run.model_id.includes('/') ? run.model_id : run.owner + ' / ' + run.model_id}{/if}</h2>
			<div class="panel-meta">
				<StatusBadge status={run.auto_quant_status} /> <span class="meta-label">quant</span>
				<span class="meta-divider"></span>
				<span class="meta-text">{run.scheme} / {displayMethod(run)}</span>
			</div>
		</div>
		<button type="button" class="close-btn" onclick={onClose} aria-label="Close">
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
		</button>
	</div>

	<div class="panel-body" class:single-col={!hasLogs(run)} bind:this={panelBody}>
		<div class="col info-col">
			<div class="top-grid">
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
						<div class="info-grid pipeline-grid">
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
			</div>

			<div class="card source-card">
				<h3>Source &amp; Links</h3>
				<div class="source-grid">
					<div class="links-row">
						{#if run.session_eval_url}<a href={run.session_eval_url} target="_blank" rel="noreferrer" class="link-pill">Session Eval Log</a>{/if}
						{#if run.session_quant_url}<a href={run.session_quant_url} target="_blank" rel="noreferrer" class="link-pill">Quant / Setup Log</a>{/if}
						{#if run.aggregate_result_url}<a href={run.aggregate_result_url} target="_blank" rel="noreferrer" class="link-pill">Aggregate Result</a>{/if}
						{#if run.status_url}<a href={run.status_url} target="_blank" rel="noreferrer" class="link-pill">Status File</a>{/if}
					</div>
					<div class="run-meta">
						<span>Run: <code>{run.run_id || '-'}</code></span>
						<span>Path: <code>{run.run_path || '-'}</code></span>
					</div>
				</div>
			</div>

			{#if run.eval_details || run.tasks.length > 0}
			<div class="card eval-card" class:eval-card--open={evalOpen}>
				<button type="button" class="collapse-head eval-head" onclick={() => (evalOpen = !evalOpen)} aria-expanded={evalOpen}>
					<span class="eval-head-left">
						<h3>Evaluation Results</h3>
						{#if evalResultCount > 0}<span class="eval-count">{evalResultCount} {evalResultCount === 1 ? 'task' : 'tasks'}</span>{/if}
					</span>
					<span class="eval-toggle">
						{evalOpen ? 'Hide' : 'Show'}
						<span class="collapse-caret" class:collapse-caret--open={evalOpen} aria-hidden="true">▶</span>
					</span>
				</button>
				{#if evalOpen}
				<div class="collapse-body">
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
		</div>

		{#if hasLogs(run)}
		<div class="col log-col">
			<div class="card card--error log-card">
				<h3>Error Logs</h3>
				<div class="err-scroll">
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
			</div>
		</div>
		{/if}
	</div>
</section>
{/if}

<style>
.panel {
	margin-bottom: 1.5rem;
	border-radius: 16px;
	background: #fff;
	overflow: hidden;
	border: 1px solid #e8eef5;
	box-shadow: 0 4px 24px rgba(15,23,42,0.07), 0 1px 4px rgba(15,23,42,0.04);
}
.panel-head {
	display: flex;
	justify-content: space-between;
	align-items: flex-start;
	padding: 1.125rem 1.75rem;
	background: linear-gradient(130deg, #1340b8 0%, #1d4ed8 45%, #3b82f6 100%);
	border-bottom: none;
}
.panel-title h2 {
	margin: 0;
	font-size: 1rem;
	font-weight: 700;
	color: #fff;
	line-height: 1.3;
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
	margin-top: 0.5rem;
	font-size: 0.8125rem;
}
.meta-label {
	font-size: 0.75rem;
	color: rgba(255,255,255,0.65);
	margin-right: 0.125rem;
}
.meta-divider {
	width: 1px;
	height: 14px;
	background: rgba(255,255,255,0.22);
	margin: 0 0.375rem;
}
.meta-text {
	font-size: 0.8125rem;
	color: rgba(255,255,255,0.85);
	font-weight: 500;
}
.close-btn {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 32px;
	height: 32px;
	border: 1px solid rgba(255,255,255,0.22);
	background: rgba(255,255,255,0.1);
	border-radius: 8px;
	cursor: pointer;
	color: rgba(255,255,255,0.85);
	transition: background 0.15s, border-color 0.15s;
	flex-shrink: 0;
}
.close-btn:hover {
	background: rgba(255,255,255,0.22);
	border-color: rgba(255,255,255,0.35);
}

.panel-body {
	display: grid;
	grid-template-columns: 1fr;
	gap: 1.125rem;
	padding: 1.375rem 1.75rem;
	background: #f8fafc;
	overflow: visible;
}
.panel-body.single-col {
	grid-template-columns: 1fr;
}
.col {
	display: flex;
	flex-direction: column;
	gap: 1rem;
}
.top-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
	align-items: start;
	gap: 1rem;
}
.err-scroll {
	max-height: 55vh;
	overflow: auto;
	overscroll-behavior: auto;
}
.card {
	padding: 1rem 1.25rem;
	border: 1px solid #e8eef5;
	border-radius: 12px;
	background: #fff;
	box-shadow: 0 1px 3px rgba(15,23,42,0.04);
}
.card h3 {
	margin: 0 0 0.75rem;
	font-size: 0.6875rem;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.07em;
	color: #64748b;
	display: flex;
	align-items: center;
	gap: 0.5rem;
}
.collapse-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	width: 100%;
	padding: 0;
	margin: 0;
	background: none;
	border: none;
	cursor: pointer;
	text-align: left;
}
.collapse-head h3 {
	margin: 0;
}
.collapse-caret {
	font-size: 0.6rem;
	color: #94a3b8;
	transition: transform 0.15s ease;
}
.collapse-caret--open {
	transform: rotate(90deg);
}
.collapse-body {
	margin-top: 0.75rem;
}

/* Evaluation Results collapsible header */
.eval-card {
	padding: 0;
	overflow: hidden;
}
.eval-head {
	padding: 0.875rem 1.25rem;
	background: linear-gradient(90deg, #eff6ff, #f8fbff);
	border-bottom: 1px solid transparent;
	transition: background 0.15s, border-color 0.15s;
}
.eval-card--open .eval-head {
	border-bottom-color: #e8eef5;
}
.eval-head:hover {
	background: linear-gradient(90deg, #e0ecff, #eff6ff);
}
.eval-head-left {
	display: flex;
	align-items: center;
	gap: 0.625rem;
}
.eval-head h3 {
	color: #1d4ed8;
}
.eval-count {
	font-size: 0.6875rem;
	font-weight: 700;
	color: #1d4ed8;
	background: #dbeafe;
	border: 1px solid #bfdbfe;
	border-radius: 999px;
	padding: 0.0625rem 0.5rem;
	text-transform: none;
	letter-spacing: 0;
}
.eval-toggle {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	font-size: 0.75rem;
	font-weight: 700;
	color: #1d4ed8;
	text-transform: uppercase;
	letter-spacing: 0.04em;
}
.eval-card .collapse-body {
	margin-top: 0;
	padding: 1rem 1.25rem 1.125rem;
}
.card h4 {
	margin: 0.875rem 0 0.4rem;
	font-size: 0.75rem;
	font-weight: 700;
	color: #334155;
}
.card--error {
	background: #fff8f8;
	border-color: #fed7d7;
}
.card--error h3 { color: #c53030; }

/* Info grid */
.info-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 0.625rem 1.25rem;
}
.info-item { display: flex; flex-direction: column; font-size: 0.8125rem; }
.info-item.full { grid-column: 1 / -1; }
.info-label {
	font-size: 0.6875rem;
	color: #94a3b8;
	text-transform: uppercase;
	letter-spacing: 0.05em;
	font-weight: 600;
	margin-bottom: 0.1875rem;
}
.info-value { font-weight: 700; color: #0f172a; font-size: 0.8125rem; }
.info-link { color: #1d4ed8; text-decoration: none; font-size: 0.75rem; word-break: break-all; font-weight: 600; }
.info-link:hover { text-decoration: underline; }
.pipeline-grid { margin-top: 0.875rem; padding-top: 0.875rem; border-top: 1px solid #e8eef5; }

/* Eval meta */
.eval-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 1rem;
	margin-bottom: 0.75rem;
	font-size: 0.8125rem;
	color: #475569;
}
.eval-meta strong { color: #1e293b; }

/* Benchmark table */
.bench-wrap {
	overflow-x: auto;
	border-radius: 8px;
	border: 1px solid #e8eef5;
}
.bench {
	width: 100%;
	border-collapse: collapse;
	font-size: 0.8125rem;
}
.bench th, .bench td {
	padding: 0.5rem 0.75rem;
	text-align: left;
	border-bottom: 1px solid #e8eef5;
}
.bench tbody tr:last-child td { border-bottom: none; }
.bench th {
	color: #64748b;
	font-weight: 600;
	font-size: 0.6875rem;
	text-transform: uppercase;
	letter-spacing: 0.05em;
	background: #f8fafc;
}
.bench tbody tr:hover { background: #f8fafc; }
.mono { font-family: 'SF Mono', 'Fira Code', monospace; font-weight: 700; font-size: 0.75rem; color: #0f172a; }
.muted { color: #94a3b8; font-weight: 400; }

/* Errors */
.err-block {
	margin: 0.375rem 0;
	padding: 0.875rem;
	background: #fff;
	border: 1px solid #fed7d7;
	border-radius: 8px;
	font-family: 'SF Mono', 'Fira Code', monospace;
	font-size: 0.6875rem;
	line-height: 1.65;
	white-space: pre-wrap;
	word-break: break-word;
	color: #9b1c1c;
}

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
.source-grid {
	display: flex;
	flex-direction: column;
	gap: 0.75rem;
}
.source-grid .links-row {
	margin-bottom: 0;
}
.source-grid .run-meta {
	flex-direction: row;
	flex-wrap: wrap;
	gap: 0.4rem 1.5rem;
	padding-top: 0.75rem;
	border-top: 1px solid #f1f5f9;
}
.source-grid .run-meta span {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	min-width: 0;
	max-width: 100%;
}
.source-grid .run-meta code {
	word-break: break-all;
}
.link-pill {
	font-size: 0.75rem;
	color: #1d4ed8;
	text-decoration: none;
	padding: 0.3125rem 0.75rem;
	background: #eff6ff;
	border: 1px solid #bfdbfe;
	border-radius: 7px;
	font-weight: 600;
	transition: background 0.15s, border-color 0.15s;
}
.link-pill:hover { background: #dbeafe; border-color: #93c5fd; }
.run-meta {
	display: flex;
	flex-direction: column;
	gap: 0.3rem;
	font-size: 0.75rem;
	color: #64748b;
}
.run-meta code {
	font-family: 'SF Mono', 'Fira Code', monospace;
	font-size: 0.6875rem;
	color: #334155;
	background: #f1f5f9;
	padding: 0.125rem 0.4rem;
	border-radius: 4px;
	border: 1px solid #e2e8f0;
}

/* Pipeline timeline */
.pipeline-timeline {
	display: flex;
	align-items: flex-start;
	gap: 0;
	position: relative;
	margin-bottom: 0.25rem;
}
.pipeline-step {
	flex: 1;
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 0.3rem;
	position: relative;
}
.pipeline-step::before {
	content: '';
	position: absolute;
	top: 7px;
	left: 50%;
	width: 100%;
	height: 2px;
	background: #e8eef5;
	z-index: 0;
}
.pipeline-step:last-child::before { display: none; }
.step-dot {
	width: 15px;
	height: 15px;
	border-radius: 50%;
	background: #e8eef5;
	border: 2px solid #cbd5e1;
	position: relative;
	z-index: 1;
	transition: background 0.2s, border-color 0.2s;
}
.step-done .step-dot { background: #10b981; border-color: #059669; }
.step-active .step-dot { background: #f59e0b; border-color: #d97706; animation: pulse 1.5s infinite; }
.step-failed .step-dot { background: #ef4444; border-color: #dc2626; }
.step-label { font-size: 0.6875rem; font-weight: 600; color: #94a3b8; text-align: center; }
.step-done .step-label { color: #059669; }
.step-active .step-label { color: #d97706; }
.step-failed .step-label { color: #dc2626; }
.step-time { font-size: 0.6rem; color: #94a3b8; text-align: center; line-height: 1.4; }
@keyframes pulse {
	0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
	50% { box-shadow: 0 0 0 5px rgba(245, 158, 11, 0); }
}

/* Log column layout when errors present */
.panel-body:has(.log-col) {
	grid-template-columns: 1fr;
	gap: 1.125rem;
}
.log-card {
	display: flex;
	flex-direction: column;
}
.log-card .err-scroll {
	flex: 1;
}

@media (max-width: 900px) {
	.panel-body { padding: 1rem 1.25rem; }
	.panel-body:has(.log-col) { grid-template-columns: 1fr; }
	.top-grid { grid-template-columns: 1fr; }
	.panel-head { padding: 1rem 1.25rem; }
}
</style>
