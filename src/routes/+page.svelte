<script lang="ts">
import { base } from '$app/paths';
import RunDetailPanel from '$lib/components/RunDetailPanel.svelte';
import StatusBadge from '$lib/components/StatusBadge.svelte';
import { fetchFromGitHub } from '$lib/fetcher';
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
	let loadingMsg = $state('Initializing...');
	let fetchError = $state('');
	let selected = $state<RunRecord | null>(null);
	let latestOnly = $state(false);
	let search = $state('');
	let owner = $state('all');
	let scheme = $state('all');
	let status = $state<StatusFilter>('all');
	let statusScope = $state<'all' | 'quant' | 'eval'>('all');
	let sortKey = $state<SortKey>('updated_at');
	let sortAsc = $state(false);
	let nowStr = $state('');

	const tickClock = () => {
		nowStr = new Date().toLocaleString('sv-SE', {
			timeZone: 'Asia/Shanghai',
			year: 'numeric', month: '2-digit', day: '2-digit',
			hour: '2-digit', minute: '2-digit', second: '2-digit'
		}).replace(',', '');
	};

onMount(() => {
tickClock();
const clockInterval = setInterval(tickClock, 1000);
(async () => {
try {
// Load static JSON first (instant display)
const [runsRes, latestRes, summaryRes] = await Promise.all([
	fetch(`${base}/data/runs.json`),
	fetch(`${base}/data/latest.json`),
	fetch(`${base}/data/summary.json`)
]);
if (runsRes.ok) runs = await runsRes.json();
if (latestRes.ok) latest = await latestRes.json();
if (summaryRes.ok) summary = await summaryRes.json();
} catch {
// Static files not available
}
loading = false;

// Then try to refresh from GitHub API in background
try {
const result = await fetchFromGitHub();
if (result.runs.length > 0) {
	runs = result.runs;
	latest = result.latest;
	summary = result.summary;
	fetchError = '';
}
} catch (e: any) {
// GitHub API not reachable — static data already displayed
if (runs.length === 0) {
	fetchError = e?.message || 'Failed to fetch data';
}
}
})();

return () => { clearInterval(clockInterval); };
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

const sortIcon = (key: SortKey) => {
if (sortKey !== key) return '';
return sortAsc ? ' \u2191' : ' \u2193';
};
</script>

<div class="shell">
<header class="hero-wrap">
	<div class="hero">
		<div class="hero-content">
			<h1>lb_eval Monitor</h1>
			<p class="hero-desc">Automated quantization and evaluation pipeline dashboard for LLM leaderboard models.</p>
			<div class="hero-pills">
				<a class="hero-link" href="{base}/stats">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
					Statistics
				</a>
				<div class="hero-pill">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
					Server time (Asia/Shanghai): {nowStr}
				</div>
				<div class="hero-pill">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
					Source: XuehaoSun/lb_eval/results
				</div>
			</div>
		</div>
	</div>
</header>

<main class="content">
	<!-- KPI Cards -->
	<section class="kpi-row">
		<div class="kpi-card kpi-card--blue">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
				<span class="kpi-label">Total Runs</span>
			</div>
			<span class="kpi-value">{summary.total_runs}</span>
		</div>
		<div class="kpi-card kpi-card--teal">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
				<span class="kpi-label">Models</span>
			</div>
			<span class="kpi-value">{summary.latest_models_count}</span>
		</div>
		<div class="kpi-card kpi-card--red">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
				<span class="kpi-label">Failed</span>
			</div>
			<span class="kpi-value">{summary.quant.failed + summary.eval.failed}</span>
		</div>
		<div class="kpi-card kpi-card--green">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
				<span class="kpi-label">Quant Pass</span>
			</div>
			<span class="kpi-value">{quantTotal > 0 ? pct(summary.quant.success, quantTotal) : '0'}%</span>
		</div>
	</section>

	<!-- Status Bars -->
	<section class="status-bars">
		<div class="status-bar-card">
			<div class="sbar-header">
				<h3>Quantization Pipeline</h3>
				<span class="sbar-total">{quantTotal} runs</span>
			</div>
			<div class="sbar-track">
				{#if quantTotal > 0}
				<button class="sbar-fill sbar-fill--success" style="width: {pct(summary.quant.success, quantTotal)}%" onclick={() => filterByBar('quant', 'success')} aria-label="Filter quant success"></button>
				<button class="sbar-fill sbar-fill--failed" style="width: {pct(summary.quant.failed, quantTotal)}%" onclick={() => filterByBar('quant', 'failed')} aria-label="Filter quant failed"></button>
				<button class="sbar-fill sbar-fill--running" style="width: {pct(summary.quant.running, quantTotal)}%" onclick={() => filterByBar('quant', 'running')} aria-label="Filter quant running"></button>
				<button class="sbar-fill sbar-fill--unknown" style="width: {pct(summary.quant.unknown, quantTotal)}%" onclick={() => filterByBar('quant', 'unknown')} aria-label="Filter quant unknown"></button>
				{/if}
			</div>
			<div class="sbar-legend">
				<button class="legend-btn" onclick={() => filterByBar('quant', 'success')}><span class="ldot ldot--success"></span>Success <strong>{summary.quant.success}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('quant', 'failed')}><span class="ldot ldot--failed"></span>Failed <strong>{summary.quant.failed}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('quant', 'running')}><span class="ldot ldot--running"></span>Running <strong>{summary.quant.running}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('quant', 'unknown')}><span class="ldot ldot--unknown"></span>Unknown <strong>{summary.quant.unknown}</strong></button>
			</div>
		</div>

		<div class="status-bar-card">
			<div class="sbar-header">
				<h3>Evaluation Pipeline</h3>
				<span class="sbar-total">{evalTotal} runs</span>
			</div>
			<div class="sbar-track">
				{#if evalTotal > 0}
				<button class="sbar-fill sbar-fill--success" style="width: {pct(summary.eval.success, evalTotal)}%" onclick={() => filterByBar('eval', 'success')} aria-label="Filter eval success"></button>
				<button class="sbar-fill sbar-fill--failed" style="width: {pct(summary.eval.failed, evalTotal)}%" onclick={() => filterByBar('eval', 'failed')} aria-label="Filter eval failed"></button>
				<button class="sbar-fill sbar-fill--running" style="width: {pct(summary.eval.running, evalTotal)}%" onclick={() => filterByBar('eval', 'running')} aria-label="Filter eval running"></button>
				<button class="sbar-fill sbar-fill--unknown" style="width: {pct(summary.eval.unknown, evalTotal)}%" onclick={() => filterByBar('eval', 'unknown')} aria-label="Filter eval unknown"></button>
				{/if}
			</div>
			<div class="sbar-legend">
				<button class="legend-btn" onclick={() => filterByBar('eval', 'success')}><span class="ldot ldot--success"></span>Success <strong>{summary.eval.success}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('eval', 'failed')}><span class="ldot ldot--failed"></span>Failed <strong>{summary.eval.failed}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('eval', 'running')}><span class="ldot ldot--running"></span>Running <strong>{summary.eval.running}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('eval', 'unknown')}><span class="ldot ldot--unknown"></span>Unknown <strong>{summary.eval.unknown}</strong></button>
			</div>
		</div>
	</section>

	<!-- Failed runs alert -->
	{#if failedRuns.length > 0}
	<section class="alert-banner">
		<div class="alert-banner-header">
			<div class="alert-icon-wrap">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
			</div>
			<span>Needs Attention -- {failedRuns.length} failed run{failedRuns.length > 1 ? 's' : ''}</span>
		</div>
		<div class="alert-items">
			{#each failedRuns.slice(0, 5) as run}
			<button class="alert-row" onclick={() => selectRun(run)}>
				<span class="alert-model">{run.owner}/{run.model_id}</span>
				<span class="alert-badges">
					{#if run.auto_quant_status === 'failed'}<StatusBadge status="failed" /> quant{/if}
					{#if run.auto_eval_status === 'failed'}<StatusBadge status="failed" /> eval{/if}
				</span>
				<span class="alert-msg">{(run.eval_errors[0] || run.quant_errors[0] || run.issues[0] || '').slice(0, 80)}{(run.eval_errors[0] || run.quant_errors[0] || run.issues[0] || '').length > 80 ? '...' : ''}</span>
			</button>
			{/each}
			{#if failedRuns.length > 5}
			<button class="alert-more" onclick={() => { status = 'failed'; }}>View all {failedRuns.length} failures</button>
			{/if}
		</div>
	</section>
	{/if}

	<!-- Filter bar -->
	<section class="filter-bar">
		<div class="filter-search">
			<svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
			<input bind:value={search} placeholder="Search model, error, issue..." aria-label="Search" />
		</div>
		<select bind:value={owner} aria-label="Owner filter">{#each owners as item}<option value={item}>{item === 'all' ? 'All owners' : item}</option>{/each}</select>
		<select bind:value={scheme} aria-label="Scheme filter">{#each schemes as item}<option value={item}>{item === 'all' ? 'All schemes' : item}</option>{/each}</select>
		<select bind:value={status} aria-label="Status filter">
			<option value="all">All status</option>
			<option value="failed">Failed</option>
			<option value="success">Success</option>
			<option value="running">Running</option>
			<option value="unknown">Unknown</option>
		</select>
		<label class="toggle-label">
			<input type="checkbox" bind:checked={latestOnly} />
			<span class="toggle-text">Latest only</span>
		</label>
	</section>

	{#if loading}
	<div class="loading-state">
		<div class="spinner"></div>
		<span>{loadingMsg}</span>
	</div>
	{:else}
	{#if fetchError}
	<div class="error-banner">
		<span>⚠️ {fetchError}</span>
		<button onclick={() => location.reload()}>Retry</button>
	</div>
	{/if}
	<div class="results-meta">
		<span class="results-count">{filteredRows.length} runs</span>
		{#if statusScope !== 'all'}
		<span class="active-pill">
			{statusScope} = {status}
			<button class="pill-clear" onclick={clearScopeFilter} aria-label="Clear filter">x</button>
		</span>
		{/if}
	</div>

	<!-- Detail panel above table -->
	<div bind:this={detailRef}>
		<RunDetailPanel run={selected} onClose={() => (selected = null)} />
	</div>

	<section class="table-card" bind:this={tableRef}>
		<div class="table-scroll">
		<table>
			<thead>
				<tr>
					<th><button type="button" onclick={() => setSort('updated_at')}>Updated{sortIcon('updated_at')}</button></th>
					<th><button type="button" onclick={() => setSort('owner')}>Owner{sortIcon('owner')}</button></th>
					<th><button type="button" onclick={() => setSort('model_id')}>Model / Artifact{sortIcon('model_id')}</button></th>
					<th>Scheme</th>
					<th>Pipeline</th>
					<th>Quant</th>
					<th>Eval</th>
					<th>Errors</th>
				</tr>
			</thead>
			<tbody>
				{#if filteredRows.length === 0}
				<tr><td colspan="8" class="empty-row">No runs match current filters.</td></tr>
				{:else}
				{#each filteredRows as run}
				<tr
					class:active={selected?.run_path === run.run_path}
					class:row-failed={statusBucket(run) === 'failed'}
					onclick={() => selectRun(run)}
				>
					<td class="cell-time">{formatTime(run.updated_at)}</td>
					<td class="cell-owner">{run.owner}</td>
					<td class="cell-model">
						<span class="model-name">{run.model_id}</span>
						{#if run.artifact_name !== run.model_id}
						<span class="model-artifact">{run.artifact_name}</span>
						{/if}
					</td>
					<td class="cell-scheme"><span class="scheme-tag">{run.scheme}</span><span class="method-text">{run.method}</span></td>
					<td><span class="pipeline-badge pipeline-badge--{run.pipeline?.status || 'unknown'}">{run.pipeline?.status || '-'}</span></td>
					<td><StatusBadge status={run.auto_quant_status} /></td>
					<td><StatusBadge status={run.auto_eval_status} /></td>
					<td class="cell-errors">
						{#if errorCount(run) > 0}
						<span class="err-badge">{errorCount(run)}</span>
						<span class="err-msg">{(run.eval_errors[0] || run.quant_errors[0] || '').slice(0, 50)}</span>
						{:else if run.issues.length > 0}
						<span class="issue-msg">{run.issues[0].slice(0, 50)}</span>
						{:else}
						<span class="no-errors">--</span>
						{/if}
					</td>
				</tr>
				{/each}
				{/if}
			</tbody>
		</table>
		</div>
	</section>
	{/if}
</main>
</div>

<style>
/* ── Shell ── */
.shell {
	min-height: 100vh;
	display: flex;
	flex-direction: column;
	background: #eef2f7;
	color: #1e293b;
}

/* ── Hero header ── */
.hero-wrap {
	padding: 1.5rem 3rem 0;
	max-width: 1600px;
	margin: 0 auto;
	width: 100%;
}
.hero {
	background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 40%, #60a5fa 100%);
	border-radius: 18px;
	padding: 2rem 2.5rem 1.75rem;
	position: relative;
	overflow: hidden;
}
.hero::before {
	content: '';
	position: absolute;
	top: -60%;
	right: -5%;
	width: 420px;
	height: 420px;
	border-radius: 50%;
	background: rgba(255,255,255,0.06);
	pointer-events: none;
}
.hero::after {
	content: '';
	position: absolute;
	bottom: -40%;
	right: 12%;
	width: 280px;
	height: 280px;
	border-radius: 50%;
	background: rgba(255,255,255,0.04);
	pointer-events: none;
}
.hero-content {
	position: relative;
	z-index: 1;
}
.hero h1 {
	margin: 0;
	font-size: 1.625rem;
	font-weight: 800;
	color: #fff;
	letter-spacing: -0.02em;
}
.hero-desc {
	margin: 0.5rem 0 0;
	font-size: 0.875rem;
	color: rgba(255,255,255,0.75);
	line-height: 1.5;
}
.hero-pills {
	display: flex;
	flex-wrap: wrap;
	gap: 0.625rem;
	margin-top: 1.25rem;
}
.hero-pill {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	padding: 0.4rem 1rem;
	background: rgba(255,255,255,0.15);
	border: 1px solid rgba(255,255,255,0.22);
	border-radius: 999px;
	font-size: 0.8125rem;
	color: #fff;
	backdrop-filter: blur(4px);
	font-variant-numeric: tabular-nums;
}
.hero-link {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	padding: 0.4rem 1rem;
	background: #fff;
	border: 1px solid rgba(255,255,255,0.38);
	border-radius: 999px;
	font-size: 0.8125rem;
	font-weight: 700;
	color: #1d4ed8;
	text-decoration: none;
	box-shadow: 0 10px 24px rgba(15,23,42,0.12);
}
.hero-link:hover {
	background: #eff6ff;
}

/* ── Content ── */
.content {
	max-width: 1600px;
	margin: 0 auto;
	padding: 1.75rem 3rem 4rem;
	width: 100%;
}

/* ── KPI Cards ── */
.kpi-row {
	display: grid;
	grid-template-columns: repeat(4, 1fr);
	gap: 1rem;
	margin-bottom: 1.5rem;
}
.kpi-card {
	background: #fff;
	border-radius: 14px;
	padding: 1.25rem 1.5rem;
	display: flex;
	flex-direction: column;
	gap: 0.5rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
	transition: box-shadow 0.2s, transform 0.2s;
}
.kpi-card:hover {
	box-shadow: 0 4px 16px rgba(0,0,0,0.1);
	transform: translateY(-1px);
}
.kpi-top {
	display: flex;
	align-items: center;
	gap: 0.5rem;
	color: #64748b;
}
.kpi-label {
	font-size: 0.75rem;
	font-weight: 500;
	color: #64748b;
}
.kpi-value {
	font-size: 2rem;
	font-weight: 800;
	line-height: 1;
	letter-spacing: -0.02em;
	color: #0f172a;
}
.kpi-card--red .kpi-value { color: #dc2626; }
.kpi-card--green .kpi-value { color: #059669; }

/* ── Status Bars ── */
.status-bars {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 1rem;
	margin-bottom: 1.5rem;
}
.status-bar-card {
	background: #fff;
	border-radius: 14px;
	padding: 1.25rem 1.5rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.sbar-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 0.875rem;
}
.sbar-header h3 {
	margin: 0;
	font-size: 0.9375rem;
	font-weight: 700;
	color: #0f172a;
}
.sbar-total {
	font-size: 0.75rem;
	color: #94a3b8;
	font-weight: 500;
}
.sbar-track {
	display: flex;
	height: 10px;
	border-radius: 5px;
	overflow: hidden;
	background: #e2e8f0;
	margin-bottom: 0.75rem;
}
.sbar-fill {
	border: none;
	padding: 0;
	cursor: pointer;
	transition: filter 0.15s;
}
.sbar-fill:hover { filter: brightness(1.1); }
.sbar-fill--success { background: #10b981; }
.sbar-fill--failed { background: #ef4444; }
.sbar-fill--running { background: #f59e0b; }
.sbar-fill--unknown { background: #94a3b8; }
.sbar-legend {
	display: flex;
	flex-wrap: wrap;
	gap: 0.375rem;
}
.legend-btn {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	background: #f8fafc;
	border: 1px solid #e2e8f0;
	padding: 0.3rem 0.625rem;
	border-radius: 6px;
	cursor: pointer;
	font-size: 0.75rem;
	color: #475569;
	transition: background 0.15s, border-color 0.15s;
}
.legend-btn:hover {
	background: #f1f5f9;
	border-color: #cbd5e1;
}
.legend-btn strong {
	color: #0f172a;
	font-weight: 700;
}
.ldot {
	display: inline-block;
	width: 8px;
	height: 8px;
	border-radius: 50%;
	flex-shrink: 0;
}
.ldot--success { background: #10b981; }
.ldot--failed { background: #ef4444; }
.ldot--running { background: #f59e0b; }
.ldot--unknown { background: #94a3b8; }

/* ── Alert banner ── */
.alert-banner {
	background: #fff;
	border: 1px solid #fecaca;
	border-left: 4px solid #ef4444;
	border-radius: 14px;
	padding: 1.25rem 1.5rem;
	margin-bottom: 1.5rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.alert-banner-header {
	display: flex;
	align-items: center;
	gap: 0.625rem;
	margin-bottom: 0.875rem;
	font-size: 0.875rem;
	font-weight: 700;
	color: #b91c1c;
}
.alert-icon-wrap {
	width: 28px;
	height: 28px;
	border-radius: 8px;
	background: #fef2f2;
	display: flex;
	align-items: center;
	justify-content: center;
	color: #dc2626;
	flex-shrink: 0;
}
.alert-items {
	display: flex;
	flex-direction: column;
	gap: 0.5rem;
}
.alert-row {
	display: grid;
	grid-template-columns: minmax(180px, auto) auto 1fr;
	gap: 1rem;
	align-items: center;
	padding: 0.625rem 1rem;
	background: #fef2f2;
	border: 1px solid #fecaca;
	border-radius: 10px;
	cursor: pointer;
	text-align: left;
	font-size: 0.8125rem;
	transition: background 0.15s;
}
.alert-row:hover {
	background: #fee2e2;
}
.alert-model { font-weight: 600; color: #0f172a; }
.alert-badges { display: flex; align-items: center; gap: 0.375rem; font-size: 0.75rem; color: #64748b; }
.alert-msg { color: #64748b; font-size: 0.75rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-more {
	background: none;
	border: none;
	color: #dc2626;
	cursor: pointer;
	font-size: 0.8125rem;
	font-weight: 700;
	padding: 0.5rem 0;
	text-align: left;
	transition: color 0.15s;
}
.alert-more:hover { color: #991b1b; }

/* ── Filter bar ── */
.filter-bar {
	display: flex;
	align-items: center;
	gap: 0.625rem;
	margin-bottom: 1rem;
	flex-wrap: wrap;
}
.filter-search {
	position: relative;
	flex: 1;
	min-width: 240px;
}
.search-icon {
	position: absolute;
	left: 0.875rem;
	top: 50%;
	transform: translateY(-50%);
	color: #94a3b8;
	pointer-events: none;
}
.filter-search input {
	width: 100%;
	padding: 0.5rem 0.875rem 0.5rem 2.25rem;
	border: 1px solid #e2e8f0;
	border-radius: 10px;
	background: #fff;
	font-size: 0.8125rem;
	color: #0f172a;
	box-shadow: 0 1px 2px rgba(0,0,0,0.04);
	transition: border-color 0.15s, box-shadow 0.15s;
}
.filter-search input::placeholder { color: #94a3b8; }
.filter-search input:focus {
	outline: none;
	border-color: #3b82f6;
	box-shadow: 0 0 0 3px rgba(59,130,246,0.12);
}
.filter-bar select {
	padding: 0.5rem 0.75rem;
	border: 1px solid #e2e8f0;
	border-radius: 10px;
	background: #fff;
	font-size: 0.8125rem;
	color: #0f172a;
	cursor: pointer;
	min-width: 130px;
	box-shadow: 0 1px 2px rgba(0,0,0,0.04);
	transition: border-color 0.15s;
}
.filter-bar select:focus {
	outline: none;
	border-color: #3b82f6;
	box-shadow: 0 0 0 3px rgba(59,130,246,0.12);
}
.toggle-label {
	display: flex;
	align-items: center;
	gap: 0.375rem;
	cursor: pointer;
	white-space: nowrap;
	padding: 0.5rem 0.75rem;
	background: #fff;
	border: 1px solid #e2e8f0;
	border-radius: 10px;
	box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.toggle-label input[type="checkbox"] {
	accent-color: #2563eb;
	width: 15px;
	height: 15px;
}
.toggle-text {
	font-size: 0.8125rem;
	color: #475569;
	font-weight: 500;
}

/* ── Loading ── */
.loading-state {
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 0.75rem;
	padding: 5rem 0;
	color: #64748b;
	font-size: 0.875rem;
}
.error-banner {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 0.75rem 1.25rem;
	margin-bottom: 1rem;
	background: #fef2f2;
	border: 1px solid #fecaca;
	border-radius: 10px;
	color: #991b1b;
	font-size: 0.8125rem;
}
.error-banner button {
	padding: 0.35rem 0.75rem;
	background: #dc2626;
	color: #fff;
	border: none;
	border-radius: 6px;
	cursor: pointer;
	font-size: 0.75rem;
	font-weight: 600;
}
.spinner {
	width: 22px;
	height: 22px;
	border: 2.5px solid #e2e8f0;
	border-top-color: #2563eb;
	border-radius: 50%;
	animation: spin 0.6s linear infinite;
}
@keyframes spin {
	to { transform: rotate(360deg); }
}

/* ── Results meta ── */
.results-meta {
	display: flex;
	align-items: center;
	gap: 0.625rem;
	margin-bottom: 0.75rem;
}
.results-count {
	font-size: 0.8125rem;
	color: #64748b;
	font-weight: 600;
}
.active-pill {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	padding: 0.25rem 0.75rem;
	background: #eff6ff;
	border: 1px solid #bfdbfe;
	border-radius: 999px;
	font-size: 0.75rem;
	color: #1d4ed8;
	font-weight: 600;
}
.pill-clear {
	border: none;
	background: none;
	color: #dc2626;
	cursor: pointer;
	font-size: 0.8125rem;
	font-weight: 800;
	padding: 0 0.125rem;
	line-height: 1;
}
.pill-clear:hover { color: #991b1b; }

/* ── Table ── */
.table-card {
	background: #fff;
	border-radius: 14px;
	overflow: hidden;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.table-scroll {
	overflow-x: auto;
}
table {
	width: 100%;
	border-collapse: collapse;
}
thead {
	background: #f8fafc;
	border-bottom: 1px solid #e2e8f0;
}
th {
	padding: 0.75rem 1rem;
	text-align: left;
	font-size: 0.6875rem;
	font-weight: 700;
	color: #64748b;
	text-transform: uppercase;
	letter-spacing: 0.06em;
	white-space: nowrap;
}
th button {
	background: none;
	border: none;
	font-weight: 700;
	font-size: 0.6875rem;
	color: #64748b;
	text-transform: uppercase;
	letter-spacing: 0.06em;
	cursor: pointer;
	padding: 0;
	transition: color 0.15s;
}
th button:hover { color: #2563eb; }
td {
	padding: 0.75rem 1rem;
	font-size: 0.8125rem;
	border-bottom: 1px solid #f1f5f9;
	vertical-align: middle;
	color: #334155;
}
tbody tr {
	cursor: pointer;
	transition: background 0.12s;
}
tbody tr:hover { background: #f8fafc; }
tbody tr.active {
	background: #eff6ff;
	box-shadow: inset 3px 0 0 #2563eb;
}
tbody tr.row-failed {
	background: #fef2f2;
}
tbody tr.row-failed:hover {
	background: #fee2e2;
}
tbody tr.row-failed.active {
	background: #fee2e2;
	box-shadow: inset 3px 0 0 #ef4444;
}
.empty-row {
	text-align: center;
	color: #94a3b8;
	padding: 3rem 1rem;
	font-style: italic;
}

/* Cell specifics */
.cell-time {
	white-space: nowrap;
	font-size: 0.75rem;
	color: #64748b;
	font-weight: 500;
}
.cell-owner {
	font-weight: 600;
	color: #1e293b;
}
.cell-model {
	display: flex;
	flex-direction: column;
	gap: 0.125rem;
}
.model-name {
	font-weight: 700;
	color: #0f172a;
}
.model-artifact {
	font-size: 0.6875rem;
	color: #94a3b8;
}
.cell-scheme {
	display: flex;
	flex-direction: column;
	gap: 0.125rem;
}
.scheme-tag {
	font-weight: 600;
	font-size: 0.75rem;
	color: #1e293b;
}
.method-text {
	font-size: 0.6875rem;
	color: #94a3b8;
}
.cell-errors {
	max-width: 300px;
}
.err-badge {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	min-width: 22px;
	height: 22px;
	background: #ef4444;
	color: #fff;
	font-weight: 700;
	font-size: 0.6875rem;
	padding: 0 0.375rem;
	border-radius: 999px;
	margin-right: 0.5rem;
}
.err-msg {
	font-size: 0.75rem;
	color: #64748b;
}
.issue-msg {
	font-size: 0.75rem;
	color: #94a3b8;
}
.no-errors {
	color: #cbd5e1;
}

/* Pipeline badge */
.pipeline-badge {
	display: inline-flex;
	align-items: center;
	padding: 0.1875rem 0.5rem;
	border-radius: 6px;
	font-size: 0.6875rem;
	font-weight: 600;
	text-transform: capitalize;
	white-space: nowrap;
}
.pipeline-badge--pending { background: rgba(99, 102, 241, 0.1); color: #4f46e5; }
.pipeline-badge--running { background: rgba(245, 158, 11, 0.1); color: #d97706; }
.pipeline-badge--succeeded { background: rgba(16, 185, 129, 0.1); color: #059669; }
.pipeline-badge--failed { background: rgba(239, 68, 68, 0.1); color: #dc2626; }
.pipeline-badge--cancelled { background: rgba(107, 114, 128, 0.1); color: #6b7280; }
.pipeline-badge--unknown { background: rgba(107, 114, 128, 0.06); color: #9ca3af; }

/* ── Responsive ── */
@media (max-width: 1280px) {
	.hero-wrap { padding: 1.25rem 2rem 0; }
	.content { padding: 1.5rem 2rem 3rem; }
}
@media (max-width: 1024px) {
	.kpi-row { grid-template-columns: repeat(2, 1fr); }
	.status-bars { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
	.hero-wrap { padding: 1rem 1.25rem 0; }
	.hero { padding: 1.5rem 1.25rem 1.25rem; border-radius: 14px; }
	.hero h1 { font-size: 1.25rem; }
	.hero-pills { flex-direction: column; gap: 0.5rem; }
	.hero-pill { font-size: 0.75rem; }
	.content { padding: 1.25rem 1.25rem 2rem; }
	.kpi-row { grid-template-columns: 1fr 1fr; gap: 0.75rem; }
	.kpi-card { padding: 1rem 1.25rem; }
	.kpi-value { font-size: 1.5rem; }
	.filter-bar { flex-direction: column; }
	.filter-search { min-width: 100%; }
	.filter-bar select { width: 100%; }
	.toggle-label { width: 100%; }
	.alert-row { grid-template-columns: 1fr; }
}
</style>
