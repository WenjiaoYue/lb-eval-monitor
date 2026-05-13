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
	let sortKey = $state<SortKey>('updated_at');
	let sortAsc = $state(false);

onMount(async () => {
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
.filter((run) => (status === 'all' ? true : statusBucket(run) === status))
.filter((run) => {
if (!keyword) return true;
const joined = [run.model_id, run.artifact_name, run.owner, run.summary, run.issues.join(' '), run.run_id]
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

const shortIssues = (run: RunRecord) => run.issues.slice(0, 2).join(' | ');
</script>

<main>
<header>
<h1>lb_eval monitor dashboard</h1>
<p>Static monitor over <code>WenjiaoYue/lb_eval/results</code></p>
</header>

<section class="cards">
<article><h3>Total runs</h3><p>{summary.total_runs}</p></article>
<article><h3>Latest models</h3><p>{summary.latest_models_count}</p></article>
<article><h3>Quant success / fail</h3><p>{summary.quant.success} / {summary.quant.failed}</p></article>
<article><h3>Eval success / fail</h3><p>{summary.eval.success} / {summary.eval.failed}</p></article>
</section>

<section class="filters">
<input bind:value={search} placeholder="Search model/artifact/issues" aria-label="Search" />
<select bind:value={owner} aria-label="Owner filter">{#each owners as item}<option value={item}>{item}</option>{/each}</select>
<select bind:value={scheme} aria-label="Scheme filter">{#each schemes as item}<option value={item}>{item}</option>{/each}</select>
<select bind:value={status} aria-label="Status filter">
<option value="all">all</option>
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
<div class="layout">
<section class="table-wrap">
<table>
<thead>
<tr>
							<th><button type="button" onclick={() => setSort('updated_at')}>updated</button></th>
							<th><button type="button" onclick={() => setSort('owner')}>owner</button></th>
							<th><button type="button" onclick={() => setSort('model_id')}>model / artifact</button></th>
<th>scheme/method</th>
<th>quant</th>
<th>eval</th>
<th>issues</th>
</tr>
</thead>
<tbody>
{#if filteredRows.length === 0}
<tr><td colspan="7">No runs match current filters.</td></tr>
{:else}
{#each filteredRows as run}
								<tr class:active={selected?.run_path === run.run_path} onclick={() => (selected = run)}>
<td>{run.updated_at}</td>
<td>{run.owner}</td>
<td>
<strong>{run.model_id}</strong>
<div class="muted">{run.artifact_name}</div>
</td>
<td>{run.scheme} / {run.method}</td>
<td><StatusBadge status={run.auto_quant_status} /></td>
<td><StatusBadge status={run.auto_eval_status} /></td>
<td>{shortIssues(run)}</td>
</tr>
{/each}
{/if}
</tbody>
</table>
</section>
<RunDetailPanel run={selected} onClose={() => (selected = null)} />
</div>
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
padding: 1rem;
max-width: 1400px;
margin: 0 auto;
}
header p {
color: #4b5563;
}
.cards {
display: grid;
grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
gap: 0.75rem;
margin: 1rem 0;
}
.cards article {
background: #fff;
border: 1px solid #e5e7eb;
border-radius: 0.75rem;
padding: 0.75rem;
}
.cards h3 {
margin: 0;
font-size: 0.9rem;
color: #6b7280;
}
.cards p {
margin: 0.4rem 0 0;
font-size: 1.4rem;
font-weight: 700;
}
.filters {
display: grid;
grid-template-columns: 1.8fr repeat(3, minmax(120px, 0.9fr)) auto;
gap: 0.5rem;
margin-bottom: 1rem;
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
.layout {
display: grid;
grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
gap: 0.75rem;
}
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
font-size: 0.88rem;
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
.muted {
color: #6b7280;
font-size: 0.75rem;
}
@media (max-width: 1024px) {
.filters {
grid-template-columns: 1fr 1fr;
}
.layout {
grid-template-columns: 1fr;
}
}
</style>
