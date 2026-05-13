<script lang="ts">
import StatusBadge from '$lib/components/StatusBadge.svelte';
import type { RunRecord } from '$lib/types';

let { run = null, onClose }: { run: RunRecord | null; onClose: () => void } = $props();

const formatMetric = (value: number | string) => {
if (typeof value === 'number') return value.toFixed(4);
return value;
};
</script>

{#if run}
<aside class="panel">
<div class="panel-header">
<h2>{run.model_id}</h2>
			<button type="button" onclick={onClose} aria-label="Close detail panel">✕</button>
</div>

<div class="kv"><strong>artifact:</strong> {run.artifact_name}</div>
<div class="kv"><strong>owner:</strong> {run.owner}</div>
<div class="kv"><strong>scheme/method:</strong> {run.scheme} / {run.method}</div>
<div class="kv"><strong>run id:</strong> {run.run_id}</div>
<div class="kv"><strong>updated:</strong> {run.updated_at}</div>
<div class="kv"><strong>run path:</strong> <code>{run.run_path}</code></div>
<div class="kv"><strong>quant:</strong> <StatusBadge status={run.auto_quant_status} /></div>
<div class="kv"><strong>eval:</strong> <StatusBadge status={run.auto_eval_status} /></div>

{#if run.summary}
<section>
<h3>Summary</h3>
<p>{run.summary}</p>
</section>
{/if}

{#if run.issues.length}
<section>
<h3>Issues</h3>
<ul>{#each run.issues as issue}<li>{issue}</li>{/each}</ul>
</section>
{/if}

{#if run.tasks.length}
<section>
<h3>Tasks</h3>
<div class="chips">{#each run.tasks as task}<span>{task}</span>{/each}</div>
</section>
{/if}

{#if Object.keys(run.metrics_preview).length}
<section>
<h3>Metrics preview</h3>
<ul>
{#each Object.entries(run.metrics_preview) as [task, value]}
<li><strong>{task}</strong>: {formatMetric(value)}</li>
{/each}
</ul>
</section>
{/if}

<section>
<h3>Source links</h3>
<ul>
{#if run.aggregate_result_url}<li><a href={run.aggregate_result_url} target="_blank" rel="noreferrer">Aggregate result</a></li>{/if}
{#if run.session_eval_url}<li><a href={run.session_eval_url} target="_blank" rel="noreferrer">Session eval</a></li>{/if}
{#if run.session_quant_url}<li><a href={run.session_quant_url} target="_blank" rel="noreferrer">Session quant</a></li>{/if}
</ul>
</section>
</aside>
{/if}

<style>
.panel {
position: sticky;
top: 1rem;
align-self: start;
padding: 1rem;
border: 1px solid #e5e7eb;
border-radius: 0.75rem;
background: #fff;
max-height: calc(100vh - 2rem);
overflow: auto;
}
.panel-header {
display: flex;
justify-content: space-between;
align-items: center;
}
button {
border: 1px solid #d1d5db;
background: #fff;
border-radius: 0.5rem;
}
code {
word-break: break-all;
}
.kv {
margin: 0.3rem 0;
}
h3 {
margin: 1rem 0 0.4rem;
}
ul {
margin: 0;
padding-left: 1rem;
}
.chips {
display: flex;
flex-wrap: wrap;
gap: 0.3rem;
}
.chips span {
padding: 0.15rem 0.45rem;
background: #f3f4f6;
border-radius: 999px;
font-size: 0.75rem;
}
</style>
