<script lang="ts">
import { base } from '$app/paths';
import RunDetailPanel from '$lib/components/RunDetailPanel.svelte';
import StatusBadge from '$lib/components/StatusBadge.svelte';
import type { RunRecord, SummaryData } from '$lib/types';
import { onMount } from 'svelte';

type StatusFilter = 'all' | 'failed' | 'success' | 'running' | 'unknown';
type SortKey = 'updated_at' | 'model_id' | 'artifact_name' | 'owner';

	let runs = $state<RunRecord[]>([]);
	let latest = $state<RunRecord[]>([]);
	let summary = $state<SummaryData>({
		generated_at: '',
		total_runs: 0,
		latest_models_count: 0,
		quant: { success: 0, failed: 0, running: 0, unknown: 0 },
		eval: { success: 0, failed: 0, running: 0, unknown: 0 }
	});

	let loading = $state(true);
	let selected = $state<RunRecord | null>(null);
	let latestOnly = $state(false);
	let search = $state('');
	let owner = $state('all');
	let scheme = $state('all');
	let status = $state<StatusFilter>('all');
	let statusScope = $state<'all' | 'quant' | 'eval'>('all');
	let sortKey = $state<SortKey>('updated_at');
	let sortAsc = $state(false);

onMount(() => {
(async () => {
try {
const [runsRes, latestRes, summaryRes] = await Promise.all([
fetch(`${base}/data/runs.json`),
fetch(`${base}/data/latest.json`),
fetch(`${base}/data/summary.json`)
]);
runs = runsRes.ok ? await runsRes.json() : [];
latest = latestRes.ok ? await latestRes.json() : [];
summary = summaryRes.ok ? await summaryRes.json() : summary;
} finally {
loading = false;
}
})();

// Auto-refresh data every 5 minutes
const interval = setInterval(async () => {
try {
const [runsRes, latestRes, summaryRes] = await Promise.all([
fetch(`${base}/data/runs.json`, { cache: 'no-store' }),
fetch(`${base}/data/latest.json`, { cache: 'no-store' }),
fetch(`${base}/data/summary.json`, { cache: 'no-store' })
]);
if (runsRes.ok) runs = await runsRes.json();
if (latestRes.ok) latest = await latestRes.json();
if (summaryRes.ok) summary = await summaryRes.json();
} catch { /* silent retry next interval */ }
}, 5 * 60 * 1000);

return () => clearInterval(interval);
});

const currentRows = $derived(latestOnly ? latest : runs);
const owners = $derived(['all', ...new Set(runs.map((r) => r.owner).filter(Boolean)).values()]);
const schemes = $derived(['all', ...new Set(runs.map((r) => r.scheme).filter(Boolean)).values()]);

const statusBucket = (run: RunRecord): StatusFilter => {
if (run.auto_quant_status === 'failed' || run.auto_eval_status === 'failed') return 'failed';
if (run.auto_quant_status === 'success' && run.auto_eval_status === 'success') return 'success';
if (run.auto_quant_status === 'running' || run.auto_eval_status === 'running') return 'running';
return 'unknown';
};

const filteredRows = $derived.by(() => {
const keyword = search.trim().toLowerCase();
return currentRows
.filter((run) => (owner === 'all' ? true : run.owner === owner))
.filter((run) => (scheme === 'all' ? true : run.scheme === scheme))
.filter((run) => {
if (status === 'all') return true;
if (statusScope === 'quant') return run.auto_quant_status === status;
if (statusScope === 'eval') return run.auto_eval_status === status;
return statusBucket(run) === status;
})
.filter((run) => {
if (!keyword) return true;
const joined = [run.model_id, run.artifact_name, run.owner, run.summary, run.issues.join(' '), run.eval_errors.join(' '), run.quant_errors.join(' '), run.run_id]
.join(' ')
.toLowerCase();
return joined.includes(keyword);
})
.sort((a, b) => {
const left = String(a[sortKey] ?? '');
const right = String(b[sortKey] ?? '');
const cmp = left.localeCompare(right);
return sortAsc ? cmp : -cmp;
});
});

const setSort = (key: SortKey) => {
if (sortKey === key) {
sortAsc = !sortAsc;
return;
}
sortKey = key;
sortAsc = key !== 'updated_at';
};

const failedRuns = $derived(runs.filter((r) => r.auto_quant_status === 'failed' || r.auto_eval_status === 'failed'));
const errorCount = (run: RunRecord) => run.quant_errors.length + run.eval_errors.length;

let detailRef: HTMLElement | undefined = $state();
let tableRef: HTMLElement | undefined = $state();
const selectRun = (run: RunRecord) => {
selected = run;
queueMicrotask(() => detailRef?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
};

const filterByBar = (scope: 'quant' | 'eval', s: StatusFilter) => {
statusScope = scope;
status = s;
selected = null;
queueMicrotask(() => tableRef?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
};

const clearScopeFilter = () => { statusScope = 'all'; status = 'all'; };

const formatTime = (iso: string) => {
if (!iso) return '-';
const d = new Date(iso);
const now = new Date();
const diffMs = now.getTime() - d.getTime();
const diffH = Math.floor(diffMs / 3600000);
if (diffH < 1) return `${Math.floor(diffMs / 60000)}m ago`;
if (diffH < 24) return `${diffH}h ago`;
const diffD = Math.floor(diffH / 24);
if (diffD < 7) return `${diffD}d ago`;
return d.toLocaleDateString('en-CA');
};

const quantTotal = $derived(summary.quant.success + summary.quant.failed + summary.quant.running + summary.quant.unknown);
const evalTotal = $derived(summary.eval.success + summary.eval.failed + summary.eval.running + summary.eval.unknown);
const pct = (n: number, total: number) => total > 0 ? (n / total * 100).toFixed(1) : '0';
</script>

<main>
<header>
<div class="header-row">
<div>
<h1>lb_eval Monitor</h1>
<p>Monitoring <code>WenjiaoYue/lb_eval/results</code></p>
</div>
<div class="last-update">
{#if summary.generated_at}
<span>Last data refresh: <strong>{formatTime(summary.generated_at)}</strong></span>
{/if}
</div>
</div>
</header>

<!-- Summary overview -->
<section class="summary-grid">
<div class="summary-card">
<h3>Overview</h3>
<div class="stat-row"><span class="stat-label">Total runs</span><span class="stat-value">{summary.total_runs}</span></div>
<div class="stat-row"><span class="stat-label">Unique models</span><span class="stat-value">{summary.latest_models_count}</span></div>
<div class="stat-row"><span class="stat-label">Failed runs</span><span class="stat-value danger">{summary.quant.failed + summary.eval.failed > 0 ? summary.quant.failed + summary.eval.failed : 0}</span></div>
</div>

<div class="summary-card">
<h3>Quantization Status</h3>
<div class="bar-chart">
<button class="bar-segment success" style="width: {pct(summary.quant.success, quantTotal)}%" onclick={() => filterByBar('quant', 'success')}></button>
<button class="bar-segment failed" style="width: {pct(summary.quant.failed, quantTotal)}%" onclick={() => filterByBar('quant', 'failed')}></button>
<button class="bar-segment running" style="width: {pct(summary.quant.running, quantTotal)}%" onclick={() => filterByBar('quant', 'running')}></button>
<button class="bar-segment unknown" style="width: {pct(summary.quant.unknown, quantTotal)}%" onclick={() => filterByBar('quant', 'unknown')}></button>
</div>
<div class="bar-legend">
<button class="legend-item" onclick={() => filterByBar('quant', 'success')}><i class="dot success"></i> Success {summary.quant.success}</button>
<button class="legend-item" onclick={() => filterByBar('quant', 'failed')}><i class="dot failed"></i> Failed {summary.quant.failed}</button>
<button class="legend-item" onclick={() => filterByBar('quant', 'running')}><i class="dot running"></i> Running {summary.quant.running}</button>
<button class="legend-item" onclick={() => filterByBar('quant', 'unknown')}><i class="dot unknown"></i> Unknown {summary.quant.unknown}</button>
</div>
</div>

<div class="summary-card">
<h3>Evaluation Status</h3>
<div class="bar-chart">
<button class="bar-segment success" style="width: {pct(summary.eval.success, evalTotal)}%" onclick={() => filterByBar('eval', 'success')}></button>
<button class="bar-segment failed" style="width: {pct(summary.eval.failed, evalTotal)}%" onclick={() => filterByBar('eval', 'failed')}></button>
<button class="bar-segment running" style="width: {pct(summary.eval.running, evalTotal)}%" onclick={() => filterByBar('eval', 'running')}></button>
<button class="bar-segment unknown" style="width: {pct(summary.eval.unknown, evalTotal)}%" onclick={() => filterByBar('eval', 'unknown')}></button>
</div>
<div class="bar-legend">
<button class="legend-item" onclick={() => filterByBar('eval', 'success')}><i class="dot success"></i> Success {summary.eval.success}</button>
<button class="legend-item" onclick={() => filterByBar('eval', 'failed')}><i class="dot failed"></i> Failed {summary.eval.failed}</button>
<button class="legend-item" onclick={() => filterByBar('eval', 'running')}><i class="dot running"></i> Running {summary.eval.running}</button>
<button class="legend-item" onclick={() => filterByBar('eval', 'unknown')}><i class="dot unknown"></i> Unknown {summary.eval.unknown}</button>
</div>
</div>
</section>

<!-- Failed runs alert -->
{#if failedRuns.length > 0}
<section class="alert-section">
<h3>Needs Attention ({failedRuns.length} failed)</h3>
<div class="alert-list">
{#each failedRuns.slice(0, 5) as run}
<button class="alert-item" onclick={() => selectRun(run)}>
<span class="alert-model">{run.owner}/{run.model_id}</span>
<span class="alert-info">
{#if run.auto_quant_status === 'failed'}<StatusBadge status="failed" /> quant{/if}
{#if run.auto_eval_status === 'failed'}<StatusBadge status="failed" /> eval{/if}
</span>
<span class="alert-error">{(run.eval_errors[0] || run.quant_errors[0] || run.issues[0] || '').slice(0, 80)}{(run.eval_errors[0] || run.quant_errors[0] || run.issues[0] || '').length > 80 ? '...' : ''}</span>
</button>
{/each}
{#if failedRuns.length > 5}
<button class="alert-more" onclick={() => { status = 'failed'; }}>View all {failedRuns.length} failures →</button>
{/if}
</div>
</section>
{/if}

<!-- Filters -->
<section class="filters">
<input bind:value={search} placeholder="Search model / error / issue..." aria-label="Search" />
<select bind:value={owner} aria-label="Owner filter">{#each owners as item}<option value={item}>{item}</option>{/each}</select>
<select bind:value={scheme} aria-label="Scheme filter">{#each schemes as item}<option value={item}>{item}</option>{/each}</select>
<select bind:value={status} aria-label="Status filter">
<option value="all">all status</option>
<option value="failed">failed</option>
<option value="success">success</option>
<option value="running">running</option>
<option value="unknown">unknown</option>
</select>
<label class="latest-toggle"><input type="checkbox" bind:checked={latestOnly} /> latest only</label>
</section>

{#if loading}
<p>Loading data...</p>
{:else}
<div class="results-count">
{filteredRows.length} runs shown
{#if statusScope !== 'all'}
<span class="active-filter">
Filtering: <strong>{statusScope}</strong> = <strong>{status}</strong>
<button class="clear-filter" onclick={clearScopeFilter}>✕ clear</button>
</span>
{/if}
</div>

<!-- Detail panel above table -->
<div bind:this={detailRef}>
<RunDetailPanel run={selected} onClose={() => (selected = null)} />
</div>

<section class="table-wrap" bind:this={tableRef}>
<table>
<thead>
<tr>
							<th><button type="button" onclick={() => setSort('updated_at')}>updated</button></th>
							<th><button type="button" onclick={() => setSort('owner')}>owner</button></th>
							<th><button type="button" onclick={() => setSort('model_id')}>model / artifact</button></th>
<th>scheme/method</th>
<th>quant</th>
<th>eval</th>
<th>errors</th>
</tr>
</thead>
<tbody>
{#if filteredRows.length === 0}
<tr><td colspan="7">No runs match current filters.</td></tr>
{:else}
{#each filteredRows as run}
								<tr class:active={selected?.run_path === run.run_path} class:row-failed={statusBucket(run) === 'failed'} onclick={() => selectRun(run)}>
<td class="nowrap">{formatTime(run.updated_at)}</td>
<td>{run.owner}</td>
<td>
<strong>{run.model_id}</strong>
<div class="muted">{run.artifact_name !== run.model_id ? run.artifact_name : ''}</div>
</td>
<td><span class="nowrap">{run.scheme}</span> <span class="muted">/ {run.method}</span></td>
<td><StatusBadge status={run.auto_quant_status} /></td>
<td><StatusBadge status={run.auto_eval_status} /></td>
<td>
{#if errorCount(run) > 0}
<span class="error-count">{errorCount(run)}</span>
<span class="error-preview">{(run.eval_errors[0] || run.quant_errors[0] || '').slice(0, 50)}</span>
{:else if run.issues.length > 0}
<span class="muted">{run.issues[0].slice(0, 50)}</span>
{:else}
<span class="muted">-</span>
{/if}
</td>
</tr>
{/each}
{/if}
</tbody>
</table>
</section>
{/if}
</main>

<style>
:global(body) {
margin: 0;
font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
background: #f8fafc;
color: #111827;
}
main {
padding: 1rem 1.5rem;
max-width: 1500px;
margin: 0 auto;
}
.header-row {
display: flex;
justify-content: space-between;
align-items: flex-end;
flex-wrap: wrap;
gap: 0.5rem;
}
header h1 { margin: 0; }
header p { color: #4b5563; margin: 0.25rem 0 0; }
.last-update { font-size: 0.82rem; color: #6b7280; }

/* Summary grid */
.summary-grid {
display: grid;
grid-template-columns: minmax(180px, 0.8fr) 1fr 1fr;
gap: 0.75rem;
margin: 1rem 0;
}
.summary-card {
background: #fff;
border: 1px solid #e5e7eb;
border-radius: 0.75rem;
padding: 0.85rem 1rem;
}
.summary-card h3 {
margin: 0 0 0.6rem;
font-size: 0.85rem;
color: #6b7280;
text-transform: uppercase;
letter-spacing: 0.03em;
}
.stat-row {
display: flex;
justify-content: space-between;
padding: 0.25rem 0;
border-bottom: 1px solid #f3f4f6;
}
.stat-label { color: #374151; font-size: 0.88rem; }
.stat-value { font-weight: 700; font-size: 1rem; }
.stat-value.danger { color: #dc2626; }

/* Bar chart */
.bar-chart {
display: flex;
height: 20px;
border-radius: 4px;
overflow: hidden;
background: #f3f4f6;
margin-bottom: 0.5rem;
}
.bar-segment {
min-width: 0;
transition: width 0.3s;
border: none;
padding: 0;
cursor: pointer;
opacity: 0.9;
}
.bar-segment:hover { opacity: 1; filter: brightness(1.1); }
.bar-segment.success { background: #22c55e; }
.bar-segment.failed { background: #ef4444; }
.bar-segment.running { background: #f59e0b; }
.bar-segment.unknown { background: #9ca3af; }
.bar-legend {
display: flex;
flex-wrap: wrap;
gap: 0.6rem;
font-size: 0.78rem;
color: #4b5563;
}
.legend-item {
display: flex;
align-items: center;
gap: 0.25rem;
background: none;
border: none;
padding: 0.1rem 0.3rem;
border-radius: 0.3rem;
cursor: pointer;
font-size: 0.78rem;
color: #4b5563;
}
.legend-item:hover { background: #f3f4f6; }
.dot {
display: inline-block;
width: 8px;
height: 8px;
border-radius: 50%;
}
.dot.success { background: #22c55e; }
.dot.failed { background: #ef4444; }
.dot.running { background: #f59e0b; }
.dot.unknown { background: #9ca3af; }

/* Alert section */
.alert-section {
background: #fef2f2;
border: 1px solid #fecaca;
border-radius: 0.75rem;
padding: 0.85rem 1rem;
margin-bottom: 1rem;
}
.alert-section h3 {
margin: 0 0 0.5rem;
font-size: 0.9rem;
color: #991b1b;
}
.alert-list { display: flex; flex-direction: column; gap: 0.4rem; }
.alert-item {
display: grid;
grid-template-columns: minmax(180px, auto) auto 1fr;
gap: 0.5rem;
align-items: center;
padding: 0.4rem 0.6rem;
background: #fff;
border: 1px solid #fecaca;
border-radius: 0.5rem;
cursor: pointer;
text-align: left;
font-size: 0.82rem;
}
.alert-item:hover { background: #fff5f5; }
.alert-model { font-weight: 600; color: #111827; }
.alert-error { color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-more {
margin-top: 0.3rem;
background: none;
border: none;
color: #dc2626;
cursor: pointer;
font-size: 0.82rem;
font-weight: 500;
padding: 0.3rem 0;
}

/* Filters */
.filters {
display: grid;
grid-template-columns: 1.8fr repeat(3, minmax(120px, 0.9fr)) auto;
gap: 0.5rem;
margin-bottom: 0.5rem;
}
.filters input,
.filters select {
padding: 0.5rem;
border: 1px solid #d1d5db;
border-radius: 0.5rem;
background: #fff;
}
.latest-toggle {
display: flex;
align-items: center;
gap: 0.35rem;
font-size: 0.9rem;
}
.results-count {
font-size: 0.8rem;
color: #6b7280;
margin-bottom: 0.5rem;
display: flex;
align-items: center;
gap: 0.5rem;
}
.active-filter {
display: inline-flex;
align-items: center;
gap: 0.3rem;
padding: 0.15rem 0.5rem;
background: #eff6ff;
border: 1px solid #bfdbfe;
border-radius: 999px;
font-size: 0.75rem;
color: #1d4ed8;
}
.clear-filter {
border: none;
background: none;
color: #dc2626;
cursor: pointer;
font-size: 0.75rem;
font-weight: 600;
padding: 0 0.2rem;
}
.clear-filter:hover { text-decoration: underline; }
.table-wrap {
overflow: auto;
background: #fff;
border: 1px solid #e5e7eb;
border-radius: 0.75rem;
}
table {
width: 100%;
border-collapse: collapse;
}
th,
td {
padding: 0.5rem;
text-align: left;
border-bottom: 1px solid #f1f5f9;
vertical-align: top;
font-size: 0.84rem;
}
th button {
background: none;
border: none;
font-weight: 700;
cursor: pointer;
padding: 0;
}
tbody tr {
cursor: pointer;
}
tbody tr:hover,
tbody tr.active {
background: #f8fafc;
}
tbody tr.row-failed {
background: #fef2f2;
}
tbody tr.row-failed:hover,
tbody tr.row-failed.active {
background: #fee2e2;
}
.muted {
color: #6b7280;
font-size: 0.75rem;
}
.nowrap { white-space: nowrap; }
.error-count {
display: inline-block;
background: #fee2e2;
color: #991b1b;
font-weight: 700;
font-size: 0.72rem;
padding: 0.1rem 0.4rem;
border-radius: 999px;
margin-right: 0.3rem;
}
.error-preview {
color: #6b7280;
font-size: 0.75rem;
}
@media (max-width: 1024px) {
.summary-grid {
grid-template-columns: 1fr;
}
.filters {
grid-template-columns: 1fr 1fr;
}
}
</style>
