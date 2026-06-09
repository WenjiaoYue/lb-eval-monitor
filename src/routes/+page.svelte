<script lang="ts">
import RunDetailPanel from '$lib/components/RunDetailPanel.svelte';
import StatusBadge from '$lib/components/StatusBadge.svelte';
import { fetchFromGitHub } from '$lib/fetcher';
import type { RunRecord, SummaryData } from '$lib/types';
import { onMount } from 'svelte';

type StatusFilter = 'all' | 'failed' | 'success' | 'running';
type QuantStatusFilter = Exclude<StatusFilter, 'all'>;
type SortKey = 'updated_at' | 'model_id' | 'artifact_name' | 'owner';
type SubmitterBucket = 'Intel' | 'Non-Intel';

interface SubmitterRow {
	name: string;
	count: number;
	intelCount: number;
	nonIntelCount: number;
	orgs: string[];
	bucket: SubmitterBucket;
}
interface SchemeRow {
	scheme: string;
	count: number;
	success: number;
	failed: number;
}
interface CompanyRow {
	company: string;
	count: number;
	models: string[];
}
interface QuantCounts {
	success: number;
	failed: number;
	running: number;
}

	let runs = $state<RunRecord[]>([]);
	let latest = $state<RunRecord[]>([]);
	let summary = $state<SummaryData>({
		generated_at: '',
		total_runs: 0,
		latest_models_count: 0,
		quant: { success: 0, failed: 0, running: 0 }
	});

	let loading = $state(true);
	let loadingMsg = $state('Initializing...');
	let fetchError = $state('');
	let selected = $state<RunRecord | null>(null);
	let search = $state('');
	let owner = $state('all');
	let scheme = $state('all');
	let status = $state<StatusFilter>('all');
	let sortKey = $state<SortKey>('updated_at');
	let sortAsc = $state(false);
	let nowStr = $state('');

	let expandedBucket = $state<SubmitterBucket | null>(null);
	let selectedSubmitter = $state<string | null>(null);
	let expandedCompanies = $state<Set<string>>(new Set());

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
const result = await fetchFromGitHub((msg) => { loadingMsg = msg; });
	runs = result.runs;
	latest = result.latest;
	summary = result.summary;
	fetchError = '';
} catch (e: any) {
fetchError = e?.message || 'Failed to fetch data';
} finally {
loading = false;
}
})();

return () => { clearInterval(clockInterval); };
});

const currentRows = $derived(runs);
const owners = $derived(['all', ...new Set(runs.map((r) => r.owner).filter(Boolean)).values()]);
const displayScheme = (run: RunRecord) => {
	const raw = run.pipeline?.quant_scheme || run.scheme || '';
	return raw === 'W4A16' ? 'INT4 (W4A16)' : raw;
};
const schemes = $derived(['all', ...new Set(runs.map(displayScheme).filter(Boolean)).values()]);
const submitters = $derived([...new Set(runs.map((r) => String(r.submitted_by || '')).filter(Boolean)).values()]);

const statusBucket = (run: RunRecord): QuantStatusFilter => {
if (run.auto_quant_status === 'failed') return 'failed';
if (run.auto_quant_status === 'success') return 'success';
return 'running';
};

const filteredRows = $derived.by(() => {
const keyword = search.trim().toLowerCase();
return currentRows
.filter((run) => (owner === 'all' ? true : run.owner === owner))
.filter((run) => (scheme === 'all' ? true : displayScheme(run) === scheme))
.filter((run) => {
if (status === 'all') return true;
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

// ── Single model list (the only place runs are listed) + pagination ──
const PAGE_SIZE = 10;
let page = $state(1);
const tableRows = $derived(
	selectedSubmitter ? filteredRows.filter((r) => String(r.submitted_by || '') === selectedSubmitter) : filteredRows
);
const totalPages = $derived(Math.max(1, Math.ceil(tableRows.length / PAGE_SIZE)));
const pagedRows = $derived(tableRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE));
const pageStart = $derived(tableRows.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1);
const pageEnd = $derived(Math.min(page * PAGE_SIZE, tableRows.length));
$effect(() => {
	// reset to the first page whenever the active filters change
	void [search, owner, scheme, status, selectedSubmitter].join('|');
	page = 1;
});
$effect(() => {
	if (page > totalPages) page = totalPages;
});
const goToPage = (p: number) => {
	page = Math.min(totalPages, Math.max(1, p));
	scrollTo(tableRef);
};
let pageInput = $state('');
const jumpToPage = () => {
	const n = parseInt(pageInput, 10);
	if (!Number.isNaN(n)) goToPage(n);
	pageInput = '';
};

const setSort = (key: SortKey) => {
if (sortKey === key) {
sortAsc = !sortAsc;
return;
}
sortKey = key;
sortAsc = key !== 'updated_at';
};

const failedRuns = $derived(runs.filter((r) => r.auto_quant_status === 'failed'));
const errorCount = (run: RunRecord) => run.quant_errors.length + run.eval_errors.length;

let detailRef: HTMLElement | undefined = $state();
let tableRef: HTMLElement | undefined = $state();
let filtersRef: HTMLElement | undefined = $state();
const scrollTo = (el?: HTMLElement, block: ScrollLogicalPosition = 'start') =>
	queueMicrotask(() => el?.scrollIntoView({ behavior: 'smooth', block }));

const selectRun = (run: RunRecord) => {
selected = run;
scrollTo(detailRef, 'nearest');
};

const filterByBar = (s: StatusFilter) => {
status = s;
selected = null;
scrollTo(tableRef);
};

const toggleScheme = (s: string) => {
if (scheme === s && status === 'all') { scheme = 'all'; scrollTo(filtersRef); return; }
scheme = s; status = 'all'; selected = null; scrollTo(tableRef);
};

const filterSchemeStatus = (s: string, st: StatusFilter) => {
if (scheme === s && status === st) {
	scheme = 'all'; status = 'all'; scrollTo(filtersRef); return;
}
scheme = s; status = st; selected = null; scrollTo(tableRef);
};


interface ActiveFilter {
	key: string;
	label: string;
	value: string;
	clear: () => void;
}
const activeFilters = $derived.by<ActiveFilter[]>(() => {
	const list: ActiveFilter[] = [];
	if (search.trim()) list.push({ key: 'search', label: 'Search', value: search.trim(), clear: () => { search = ''; } });
	if (owner !== 'all') list.push({ key: 'owner', label: 'Owner', value: owner, clear: () => { owner = 'all'; } });
	if (scheme !== 'all') list.push({ key: 'scheme', label: 'Scheme', value: scheme, clear: () => { scheme = 'all'; } });
	if (status !== 'all') list.push({ key: 'status', label: 'Status', value: status, clear: () => { status = 'all'; } });
	if (selectedSubmitter) list.push({ key: 'submitter', label: 'Submitter', value: selectedSubmitter, clear: () => { selectedSubmitter = null; } });
	return list;
});
const clearAllFilters = () => {
	search = ''; owner = 'all'; scheme = 'all'; status = 'all'; selectedSubmitter = null;
	scrollTo(filtersRef);
};

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

const countQuant = (rows: RunRecord[]): QuantCounts => {
	const counts: QuantCounts = { success: 0, failed: 0, running: 0 };
	for (const run of rows) {
		const bucket = statusBucket(run);
		counts[bucket] += 1;
	}
	return counts;
};
const quantCounts = $derived(countQuant(latest.length > 0 ? latest : runs));
const quantTotal = $derived(quantCounts.success + quantCounts.failed + quantCounts.running);
const pct = (n: number, total: number) => total > 0 ? (n / total * 100).toFixed(1) : '0';

// ── Statistics (merged from /stats) ──
const INTEL_WHITELIST = new Set(['wenjiao', 'lvkaokao', 'Haihao', 'INC4AI', 'Xuehao']);
const normalizedOrgs = (run: RunRecord) => (run.orgs || []).map((o) => o.trim()).filter(Boolean);
const isIntelSubmission = (run: RunRecord) => {
	const orgs = normalizedOrgs(run);
	if (orgs.some((o) => o.toLowerCase() === 'intel')) return true;
	return orgs.length === 0 && Boolean(run.submitted_by) && INTEL_WHITELIST.has(String(run.submitted_by));
};

// Statistics honor the shared filters so users can narrow on demand.
const statBase = $derived(filteredRows);
const submissionRows = $derived(statBase.filter((r) => Boolean(r.submitted_by)));

const submitterRows = $derived.by<SubmitterRow[]>(() => {
	const map = new Map<string, SubmitterRow>();
	for (const run of submissionRows) {
		const name = String(run.submitted_by || '');
		const intel = isIntelSubmission(run);
		const row = map.get(name) || { name, count: 0, intelCount: 0, nonIntelCount: 0, orgs: [], bucket: 'Non-Intel' as SubmitterBucket };
		row.count += 1;
		if (intel) row.intelCount += 1; else row.nonIntelCount += 1;
		row.orgs = [...new Set([...row.orgs, ...normalizedOrgs(run)])];
		row.bucket = row.intelCount >= row.nonIntelCount ? 'Intel' : 'Non-Intel';
		map.set(name, row);
	}
	return [...map.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
});

const intelSubmissionCount = $derived(submissionRows.filter(isIntelSubmission).length);
const nonIntelSubmissionCount = $derived(submissionRows.length - intelSubmissionCount);
const intelPeople = $derived(submitterRows.filter((r) => r.bucket === 'Intel'));
const nonIntelPeople = $derived(submitterRows.filter((r) => r.bucket === 'Non-Intel'));
const intelPeopleCount = $derived(intelPeople.length);
const nonIntelPeopleCount = $derived(nonIntelPeople.length);
const maxSubmitterCount = $derived(Math.max(1, ...submitterRows.map((r) => r.count)));

const schemeRows = $derived.by<SchemeRow[]>(() => {
	const scoped = selectedSubmitter ? statBase.filter((r) => String(r.submitted_by || '') === selectedSubmitter) : statBase;
	const map = new Map<string, SchemeRow>();
	for (const run of scoped) {
		const b = statusBucket(run);
		if (b === 'running') continue;
		const s = displayScheme(run);
		const row = map.get(s) || { scheme: s, count: 0, success: 0, failed: 0 };
		row.count += 1;
		row[b] += 1;
		map.set(s, row);
	}
	return [...map.values()].sort((a, b) => b.count - a.count || a.scheme.localeCompare(b.scheme));
});

const companyFromRun = (run: RunRecord) => {
	const modelId = run.model_id || '';
	if (modelId.includes('/')) return modelId.split('/')[0] || '';
	return run.owner || '';
};
const companyRows = $derived.by<CompanyRow[]>(() => {
	const scoped = selectedSubmitter ? statBase.filter((r) => String(r.submitted_by || '') === selectedSubmitter) : statBase;
	const map = new Map<string, CompanyRow>();
	for (const run of scoped) {
		const company = companyFromRun(run);
		const modelName = run.model_id || run.artifact_name || '';
		const row = map.get(company) || { company, count: 0, models: [] };
		row.count += 1;
		row.models = [...new Set([...row.models, modelName])];
		map.set(company, row);
	}
	return [...map.values()].sort((a, b) => b.count - a.count || a.company.localeCompare(b.company));
});
const maxCompanyCount = $derived(Math.max(1, ...companyRows.map((r) => r.count)));

const share = (v: number, t: number) => (t > 0 ? Math.round((v / t) * 100) : 0);
const barWidth = (v: number, max: number) => `${Math.max(3, (v / max) * 100)}%`;
const initials = (name: string) => name.slice(0, 2).toUpperCase();
const DONUT_C = 2 * Math.PI * 54;
const intelDash = $derived(submissionRows.length > 0 ? (intelSubmissionCount / submissionRows.length) * DONUT_C : 0);

const toggleBucket = (b: SubmitterBucket) => { expandedBucket = expandedBucket === b ? null : b; };
const selectSubmitter = (name: string) => {
	if (selectedSubmitter === name) { selectedSubmitter = null; scrollTo(filtersRef); return; }
	selectedSubmitter = name; selected = null; scrollTo(tableRef);
};
const toggleCompany = (company: string) => {
	const next = new Set(expandedCompanies);
	if (next.has(company)) next.delete(company); else next.add(company);
	expandedCompanies = next;
};

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
			<p class="hero-desc">Automated quantization pipeline dashboard for LLM leaderboard models.</p>
			<div class="hero-pills">
				<a class="hero-pill" href="https://github.com/XuehaoSun/lb_eval" target="_blank" rel="noopener noreferrer">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
					Source: XuehaoSun/lb_eval/results
				</a>
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
			<span class="kpi-value">{runs.length}</span>
		</div>
		<div class="kpi-card kpi-card--teal">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
				<span class="kpi-label">Models</span>
			</div>
			<span class="kpi-value">{latest.length || runs.length}</span>
		</div>
		<div class="kpi-card kpi-card--red">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
				<span class="kpi-label">Failed</span>
			</div>
			<span class="kpi-value">{quantCounts.failed}</span>
		</div>
		<div class="kpi-card kpi-card--green">
			<div class="kpi-top">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
				<span class="kpi-label">Quant Pass</span>
			</div>
			<span class="kpi-value">{quantTotal > 0 ? pct(quantCounts.success, quantTotal) : '0'}%</span>
		</div>
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

	<!-- ═══════ OVERVIEW CHARTS (top, click to drill down below) ═══════ -->
	<section class="status-bars" bind:this={filtersRef}>
		<div class="status-bar-card">
			<div class="sbar-header">
				<h3>Quantization Pipeline</h3>
				<span class="sbar-total">{quantTotal} runs</span>
			</div>
			<div class="sbar-track">
				{#if quantTotal > 0}
				<button class="sbar-fill sbar-fill--success" style="width: {pct(quantCounts.success, quantTotal)}%" onclick={() => filterByBar('success')} aria-label="Filter quant success"></button>
				<button class="sbar-fill sbar-fill--failed" style="width: {pct(quantCounts.failed, quantTotal)}%" onclick={() => filterByBar('failed')} aria-label="Filter quant failed"></button>
				<button class="sbar-fill sbar-fill--running" style="width: {pct(quantCounts.running, quantTotal)}%" onclick={() => filterByBar('running')} aria-label="Filter quant running"></button>
				{/if}
			</div>
			<div class="sbar-legend">
				<button class="legend-btn" onclick={() => filterByBar('success')}><span class="ldot ldot--success"></span>Success <strong>{quantCounts.success}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('failed')}><span class="ldot ldot--failed"></span>Failed <strong>{quantCounts.failed}</strong></button>
				<button class="legend-btn" onclick={() => filterByBar('running')}><span class="ldot ldot--running"></span>Running <strong>{quantCounts.running}</strong></button>
			</div>
		</div>

	</section>

	<section class="stats-grid">
		<!-- Affiliation donut -->
		<div class="overview-card">
			<div class="donut-wrap">
				<svg class="donut" viewBox="0 0 140 140" role="img" aria-label="Intel vs Non-Intel submissions">
					<circle class="donut-bg" cx="70" cy="70" r="54" />
					{#if submissionRows.length > 0}
					<circle class="donut-seg donut-seg--external" cx="70" cy="70" r="54" stroke-dasharray="{DONUT_C} {DONUT_C}" />
					<circle class="donut-seg donut-seg--intel" cx="70" cy="70" r="54" stroke-dasharray="{intelDash} {DONUT_C}" />
					{/if}
					<text x="70" y="64" class="donut-num">{submissionRows.length}</text>
					<text x="70" y="84" class="donut-cap">submissions</text>
				</svg>
			</div>
			<div class="overview-legend">
				<div class="legend-block">
					<button type="button" class="legend-item legend-item--btn" class:legend-item--open={expandedBucket === 'Intel'} onclick={() => toggleBucket('Intel')} aria-expanded={expandedBucket === 'Intel'}>
						<span class="legend-dot legend-dot--intel"></span>
						<div class="legend-text"><span class="legend-name">Intel employees</span><span class="legend-meta">{intelPeopleCount} {intelPeopleCount === 1 ? 'person' : 'people'}</span></div>
						<div class="legend-val"><strong>{intelSubmissionCount}</strong><span>{share(intelSubmissionCount, submissionRows.length)}%</span></div>
						<svg class="legend-caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
					</button>
					{#if expandedBucket === 'Intel'}
					<div class="legend-people">
						{#if intelPeople.length === 0}
						<span class="legend-people-empty">No Intel submitters.</span>
						{:else}
						{#each intelPeople as person}
						<div class="people-pill" class:people-pill--active={selectedSubmitter === person.name}>
							<button type="button" class="people-pill-select" onclick={() => selectSubmitter(person.name)} aria-pressed={selectedSubmitter === person.name}>
								<span class="people-pill-name">{person.name}</span>
								<span class="people-pill-count">{person.count}</span>
							</button>
						</div>
						{/each}
						{/if}
					</div>
					{/if}
				</div>
				<div class="legend-block">
					<button type="button" class="legend-item legend-item--btn" class:legend-item--open={expandedBucket === 'Non-Intel'} onclick={() => toggleBucket('Non-Intel')} aria-expanded={expandedBucket === 'Non-Intel'}>
						<span class="legend-dot legend-dot--external"></span>
						<div class="legend-text"><span class="legend-name">Non-Intel employees</span><span class="legend-meta">{nonIntelPeopleCount} {nonIntelPeopleCount === 1 ? 'person' : 'people'}</span></div>
						<div class="legend-val"><strong>{nonIntelSubmissionCount}</strong><span>{share(nonIntelSubmissionCount, submissionRows.length)}%</span></div>
						<svg class="legend-caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
					</button>
					{#if expandedBucket === 'Non-Intel'}
					<div class="legend-people">
						{#if nonIntelPeople.length === 0}
						<span class="legend-people-empty">No Non-Intel submitters.</span>
						{:else}
						{#each nonIntelPeople as person}
						<div class="people-pill" class:people-pill--active={selectedSubmitter === person.name}>
							<button type="button" class="people-pill-select" onclick={() => selectSubmitter(person.name)} aria-pressed={selectedSubmitter === person.name}>
								<span class="people-pill-name">{person.name}</span>
								<span class="people-pill-count">{person.count}</span>
							</button>
						</div>
						{/each}
						{/if}
					</div>
					{/if}
				</div>
				<p class="rule-note">Intel = <code>orgs</code> contains <code>Intel</code>, or <code>orgs</code> empty and submitter in the whitelist. Click a bucket, then a person, to inspect their models below.</p>
			</div>
		</div>

		<!-- Scheme distribution chart -->
		<div class="stats-panel">
			<div class="panel-header">
				<h2>By Scheme{#if selectedSubmitter} · {selectedSubmitter}{/if}</h2>
				<span class="panel-count">{schemeRows.length} scheme{schemeRows.length === 1 ? '' : 's'}</span>
			</div>
			<div class="scheme-list">
				{#if schemeRows.length === 0}
				<div class="empty-state">No scheme data for the current filter.</div>
				{:else}
				{#each schemeRows as row}
				<div class="scheme-row" class:scheme-row--active={scheme === row.scheme}>
					<button type="button" class="scheme-row-head" onclick={() => toggleScheme(row.scheme)} aria-pressed={scheme === row.scheme} title="Filter by {row.scheme}">
						<span class="scheme-name" title={row.scheme}>{row.scheme}</span>
						<strong class="scheme-count">{row.count}</strong>
					</button>
					<div class="stack-track">
						{#if row.success > 0}<button type="button" class="stack-seg stack-seg--success" class:stack-seg--on={scheme === row.scheme && status === 'success'} style="width: {share(row.success, row.count)}%" title="{row.success} success — click to filter" aria-label="Filter {row.scheme} success" onclick={() => filterSchemeStatus(row.scheme, 'success')}></button>{/if}
						{#if row.failed > 0}<button type="button" class="stack-seg stack-seg--failed" class:stack-seg--on={scheme === row.scheme && status === 'failed'} style="width: {share(row.failed, row.count)}%" title="{row.failed} failed — click to filter" aria-label="Filter {row.scheme} failed" onclick={() => filterSchemeStatus(row.scheme, 'failed')}></button>{/if}
					</div>
					<div class="scheme-row-meta">
						<button type="button" class="meta-ok" onclick={() => filterSchemeStatus(row.scheme, 'success')}><span class="ldot ldot--success"></span>{row.success} ok</button>
						<button type="button" class="meta-fail" onclick={() => filterSchemeStatus(row.scheme, 'failed')}><span class="ldot ldot--failed"></span>{row.failed} failed</button>
					</div>
				</div>
				{/each}
				{/if}
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
		<select bind:value={selectedSubmitter} aria-label="Submitter filter"><option value={null}>All submitters</option>{#each submitters as item}<option value={item}>{item}</option>{/each}</select>
		<select bind:value={status} aria-label="Status filter">
			<option value="all">All status</option>
			<option value="failed">Failed</option>
			<option value="success">Success</option>
			<option value="running">Running</option>
		</select>
	</section>

	<!-- ═══════ THE single model list (content varies by active filters) ═══════ -->
	{#if activeFilters.length > 0}
	<div class="active-filters">
		<span class="active-filters-label">
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
			Active filters
		</span>
		{#each activeFilters as f (f.key)}
		<button type="button" class="filter-chip" onclick={f.clear} title="Remove {f.label} filter">
			<span class="filter-chip-key">{f.label}:</span>
			<span class="filter-chip-val">{f.value}</span>
			<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
		</button>
		{/each}
		{#if activeFilters.length > 1}
		<button type="button" class="filter-clear-all" onclick={clearAllFilters}>Clear all</button>
		{/if}
	</div>
	{/if}

	<div class="results-meta">
		<span class="results-count">{tableRows.length} runs</span>
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
					<th>Errors</th>
				</tr>
			</thead>
			<tbody>
				{#if tableRows.length === 0}
				<tr><td colspan="7" class="empty-row">No runs match current filters.</td></tr>
				{:else}
				{#each pagedRows as run}
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
					<td><span class="pipeline-badge pipeline-badge--{run.pipeline?.status || 'pending'}">{run.pipeline?.status || '-'}</span></td>
					<td><StatusBadge status={run.auto_quant_status} /></td>
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
		{#if tableRows.length > PAGE_SIZE}
		<div class="pager">
			<span class="pager-info">Showing {pageStart}-{pageEnd} of {tableRows.length}</span>
			<div class="pager-controls">
				<button type="button" class="pager-btn" onclick={() => goToPage(1)} disabled={page === 1} aria-label="First page">«</button>
				<button type="button" class="pager-btn" onclick={() => goToPage(page - 1)} disabled={page === 1} aria-label="Previous page">‹</button>
				<span class="pager-page">Page {page} / {totalPages}</span>
				<button type="button" class="pager-btn" onclick={() => goToPage(page + 1)} disabled={page === totalPages} aria-label="Next page">›</button>
				<button type="button" class="pager-btn" onclick={() => goToPage(totalPages)} disabled={page === totalPages} aria-label="Last page">»</button>
				<form class="pager-jump" onsubmit={(e) => { e.preventDefault(); jumpToPage(); }}>
					<input type="number" min="1" max={totalPages} bind:value={pageInput} placeholder="Go" aria-label="Go to page" />
					<button type="submit" class="pager-btn">Go</button>
				</form>
			</div>
		</div>
		{/if}
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
	text-decoration: none;
	transition: background 0.15s, border-color 0.15s;
}
a.hero-pill:hover {
	background: rgba(255,255,255,0.28);
	border-color: rgba(255,255,255,0.4);
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
	grid-template-columns: 1fr;
	gap: 1rem;
	margin-bottom: 1.5rem;
}
.status-bar-card {
	background: #fff;
	border-radius: 14px;
	padding: 1.25rem 1.5rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
	min-width: 0;
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
.sbar-legend {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 0.375rem;
}
.legend-btn {
	display: flex;
	align-items: center;
	justify-content: center;
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

/* ── Active filters bar ── */
.active-filters {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 0.5rem;
	padding: 0.625rem 0.875rem;
	margin-bottom: 0.75rem;
	background: #f8fafc;
	border: 1px solid #e2e8f0;
	border-radius: 0.75rem;
}
.active-filters-label {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	font-size: 0.75rem;
	font-weight: 700;
	color: #64748b;
	text-transform: uppercase;
	letter-spacing: 0.03em;
	margin-right: 0.125rem;
}
.filter-chip {
	display: inline-flex;
	align-items: center;
	gap: 0.375rem;
	padding: 0.3125rem 0.625rem;
	background: #eff6ff;
	border: 1px solid #bfdbfe;
	border-radius: 999px;
	font-size: 0.75rem;
	color: #1d4ed8;
	font-weight: 600;
	cursor: pointer;
	transition: background 0.12s, border-color 0.12s;
}
.filter-chip:hover {
	background: #fee2e2;
	border-color: #fca5a5;
	color: #b91c1c;
}
.filter-chip-key { color: #64748b; font-weight: 700; }
.filter-chip:hover .filter-chip-key { color: #b91c1c; }
.filter-chip-val { font-weight: 700; }
.filter-chip svg { opacity: 0.7; }
.filter-clear-all {
	margin-left: auto;
	padding: 0.3125rem 0.75rem;
	background: #fff;
	border: 1px solid #cbd5e1;
	border-radius: 999px;
	font-size: 0.75rem;
	color: #475569;
	font-weight: 700;
	cursor: pointer;
	transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.filter-clear-all:hover {
	background: #fef2f2;
	border-color: #fca5a5;
	color: #b91c1c;
}

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
	.sbar-legend { grid-template-columns: 1fr; }
	.filter-bar { flex-direction: column; }
	.filter-search { min-width: 100%; }
	.filter-bar select { width: 100%; }
	.toggle-label { width: 100%; }
	.alert-row { grid-template-columns: 1fr; }
}

/* ── Stats: layout ── */
.stats-grid {
	display: grid;
	grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
	gap: 1.25rem;
	margin-bottom: 1.25rem;
}
.panel-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 1.25rem;
}
.stats-panel {
	background: #fff;
	border-radius: 16px;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
	overflow: hidden;
	margin-bottom: 1.25rem;
}
.panel-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 1.1rem 1.4rem;
	border-bottom: 1px solid #eef2f7;
}
.panel-header h2 { margin: 0; font-size: 1rem; color: #0f172a; }
.panel-count {
	font-size: 0.75rem;
	font-weight: 700;
	color: #64748b;
	background: #f1f5f9;
	padding: 0.2rem 0.6rem;
	border-radius: 999px;
}
.empty-state {
	padding: 1.5rem 1.4rem;
	color: #94a3b8;
	font-size: 0.85rem;
	font-style: italic;
}

/* ── Stats: affiliation donut ── */
.overview-card {
	display: grid;
	grid-template-columns: 180px 1fr;
	gap: 1.5rem;
	align-items: center;
	background: #fff;
	border-radius: 16px;
	padding: 1.5rem 1.75rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.donut-wrap { display: flex; justify-content: center; }
.donut { width: 165px; height: 165px; transform: rotate(-90deg); }
.donut-bg { fill: none; stroke: #eef2f7; stroke-width: 16; }
.donut-seg { fill: none; stroke-width: 16; stroke-linecap: round; transition: stroke-dasharray 0.6s ease; }
.donut-seg--external { stroke: #f97316; }
.donut-seg--intel { stroke: #2563eb; }
.donut-num { fill: #0f172a; font-size: 26px; font-weight: 800; text-anchor: middle; transform: rotate(90deg); transform-origin: 70px 70px; }
.donut-cap { fill: #94a3b8; font-size: 10px; font-weight: 600; text-anchor: middle; text-transform: uppercase; letter-spacing: 0.08em; transform: rotate(90deg); transform-origin: 70px 70px; }
.overview-legend { display: flex; flex-direction: column; gap: 0.6rem; min-width: 0; }
.legend-block { display: flex; flex-direction: column; gap: 0.5rem; }
.legend-item {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding: 0.7rem 0.9rem;
	border: 1px solid #eef2f7;
	border-radius: 12px;
	background: #f8fafc;
	width: 100%;
	cursor: pointer;
	text-align: left;
	font: inherit;
	transition: border-color 0.15s, background 0.15s;
}
.legend-item--btn:hover { background: #f1f5f9; border-color: #dbe4ef; }
.legend-item--open { border-color: #c7d2fe; background: #fff; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.legend-dot--intel { background: #2563eb; }
.legend-dot--external { background: #f97316; }
.legend-text { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.legend-name { font-weight: 700; font-size: 0.875rem; color: #0f172a; }
.legend-meta { font-size: 0.75rem; color: #94a3b8; }
.legend-val { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; }
.legend-val strong { font-size: 1.25rem; font-weight: 800; color: #0f172a; line-height: 1; }
.legend-val span { font-size: 0.75rem; color: #64748b; }
.legend-caret { flex-shrink: 0; color: #94a3b8; transition: transform 0.2s ease; }
.legend-item--open .legend-caret { transform: rotate(180deg); }
.legend-people { display: flex; flex-wrap: wrap; gap: 0.4rem; padding: 0.1rem 0.1rem 0.35rem; }
.legend-people-empty { font-size: 0.78rem; color: #94a3b8; padding: 0.25rem; }
.people-pill {
	display: inline-flex;
	align-items: center;
	border-radius: 999px;
	border: 1px solid #e2e8f0;
	background: #fff;
	transition: background 0.15s, border-color 0.15s;
}
.people-pill:hover { border-color: #bfdbfe; }
.people-pill--active { border-color: #2563eb; background: #eff6ff; box-shadow: 0 0 0 2px rgba(37,99,235,0.15); }
.people-pill-select {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	padding: 0.22rem 0.6rem;
	border: none;
	background: none;
	font: inherit;
	font-size: 0.78rem;
	font-weight: 600;
	color: #1d4ed8;
	cursor: pointer;
	border-radius: 999px;
}
.people-pill-name { white-space: nowrap; }
.people-pill-count { font-size: 0.7rem; font-weight: 800; color: #64748b; background: #f1f5f9; border-radius: 999px; padding: 0.05rem 0.4rem; }
.rule-note { margin: 0.1rem 0 0; font-size: 0.72rem; color: #94a3b8; line-height: 1.5; }
.rule-note code { background: #eef2f7; color: #475569; padding: 0.05rem 0.3rem; border-radius: 4px; font-size: 0.7rem; }

/* ── Stats: scheme chart ── */
.scheme-list { display: flex; flex-direction: column; }
.scheme-row {
	display: flex;
	flex-direction: column;
	gap: 0.4rem;
	width: 100%;
	padding: 0.85rem 1.4rem;
	border: none;
	border-bottom: 1px solid #f4f7fb;
	background: none;
	transition: background 0.15s;
}
.scheme-row:last-child { border-bottom: none; }
.scheme-row:hover { background: #f8fafc; }
.scheme-row--active { background: #eff6ff; box-shadow: inset 3px 0 0 #2563eb; }
.scheme-row-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 0.5rem;
	width: 100%;
	border: none;
	background: none;
	padding: 0;
	font: inherit;
	text-align: left;
	cursor: pointer;
}
.scheme-name { font-weight: 700; font-size: 0.85rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.scheme-count { font-size: 1rem; font-weight: 800; color: #0f172a; font-variant-numeric: tabular-nums; }
.stack-track { display: flex; height: 11px; border-radius: 5px; overflow: hidden; background: #eef2f7; }
.stack-seg {
	display: block;
	height: 100%;
	border: none;
	padding: 0;
	cursor: pointer;
	transition: filter 0.12s, box-shadow 0.12s;
}
.stack-seg:hover { filter: brightness(1.08) saturate(1.1); }
.stack-seg--on { box-shadow: inset 0 0 0 2px rgba(15,23,42,0.55); }
.stack-seg--success { background: #10b981; }
.stack-seg--failed { background: #ef4444; }
.scheme-row-meta { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.scheme-row-meta button {
	display: inline-flex;
	align-items: center;
	gap: 0.3rem;
	border: 1px solid transparent;
	background: none;
	padding: 0.1rem 0.35rem;
	border-radius: 6px;
	font: inherit;
	font-size: 0.72rem;
	font-weight: 600;
	cursor: pointer;
	transition: background 0.12s, border-color 0.12s;
}
.scheme-row-meta button:hover { background: #f1f5f9; border-color: #e2e8f0; }
.scheme-row-meta .ldot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.scheme-row-meta .ldot--success { background: #10b981; }
.scheme-row-meta .ldot--failed { background: #ef4444; }
.meta-ok { color: #059669; }
.meta-fail { color: #dc2626; }

/* ── Stats: rank lists (submitters / companies) ── */
.rank-list { display: flex; flex-direction: column; }
.rank-row { display: flex; align-items: stretch; border-bottom: 1px solid #f4f7fb; }
.rank-row:last-child { border-bottom: none; }
.rank-row--active { background: #eff6ff; box-shadow: inset 3px 0 0 #2563eb; }
.rank-select {
	display: flex;
	align-items: flex-start;
	gap: 0.85rem;
	flex: 1;
	min-width: 0;
	padding: 0.85rem 0.6rem 0.85rem 1.4rem;
	border: none;
	background: none;
	font: inherit;
	text-align: left;
	cursor: pointer;
	transition: background 0.15s;
}
.rank-select:hover { background: #f8fafc; }
.rank-hf {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	width: 34px;
	flex-shrink: 0;
	color: #94a3b8;
	border-left: 1px solid #f4f7fb;
	transition: background 0.15s, color 0.15s;
}
.rank-hf:hover { background: #f1f5f9; color: #2563eb; }
.avatar {
	flex-shrink: 0;
	width: 36px;
	height: 36px;
	border-radius: 10px;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 0.72rem;
	font-weight: 800;
	color: #fff;
	margin-top: 0.1rem;
}
.avatar--intel { background: linear-gradient(135deg, #2563eb, #60a5fa); }
.avatar--external { background: linear-gradient(135deg, #f97316, #fb923c); }
.avatar--company { background: linear-gradient(135deg, #0f766e, #14b8a6); }
.rank-body { flex: 1; min-width: 0; }
.rank-top { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; }
.rank-name { font-weight: 700; font-size: 0.875rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.chip { flex-shrink: 0; padding: 0.12rem 0.5rem; border-radius: 999px; font-size: 0.65rem; font-weight: 800; white-space: nowrap; }
.chip--intel { background: #dbeafe; color: #1d4ed8; }
.chip--external { background: #ffedd5; color: #c2410c; }
.chip--muted { background: #f1f5f9; color: #64748b; }
.rank-count { margin-left: auto; flex-shrink: 0; font-size: 1rem; font-weight: 800; color: #0f172a; font-variant-numeric: tabular-nums; }
.track { height: 7px; border-radius: 4px; background: #eef2f7; overflow: hidden; margin-bottom: 0.35rem; }
.fill { height: 100%; border-radius: 4px; }
.fill--intel { background: linear-gradient(90deg, #2563eb, #60a5fa); }
.fill--external { background: linear-gradient(90deg, #f97316, #fb923c); }
.fill--company { background: linear-gradient(90deg, #0f766e, #14b8a6); }
.rank-sub { font-size: 0.72rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.rank-row--expandable { flex-direction: column; }
.rank-toggle {
	display: flex;
	align-items: flex-start;
	gap: 0.85rem;
	width: 100%;
	padding: 0.85rem 1.4rem;
	border: none;
	background: none;
	font: inherit;
	text-align: left;
	cursor: pointer;
	transition: background 0.15s;
}
.rank-toggle:hover { background: #f8fafc; }
.rank-caret { flex-shrink: 0; margin-left: 0.4rem; color: #94a3b8; transition: transform 0.2s ease; }
.rank-caret--open { transform: rotate(180deg); }
.model-list { list-style: none; margin: 0; padding: 0 1.4rem 0.85rem 4.25rem; display: flex; flex-direction: column; gap: 0.35rem; }
.model-item { min-width: 0; }
.model-link { display: inline-block; max-width: 100%; font-size: 0.8rem; color: #1d4ed8; text-decoration: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.model-link:hover { text-decoration: underline; }

/* ── Pagination ── */
.pager {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 1rem;
	flex-wrap: wrap;
	padding: 0.75rem 1.4rem;
	border-top: 1px solid #eef2f7;
	background: #fafbfd;
}
.pager-info { font-size: 0.78rem; color: #64748b; }
.pager-controls { display: flex; align-items: center; gap: 0.4rem; }
.pager-btn {
	min-width: 32px;
	height: 32px;
	padding: 0 0.5rem;
	border: 1px solid #d7dfeb;
	border-radius: 8px;
	background: #fff;
	color: #1e293b;
	font-size: 0.95rem;
	font-weight: 700;
	cursor: pointer;
	transition: background 0.15s, border-color 0.15s;
}
.pager-btn:hover:not(:disabled) { background: #eff6ff; border-color: #93c5fd; }
.pager-btn:disabled { opacity: 0.4; cursor: default; }
.pager-page { font-size: 0.78rem; font-weight: 600; color: #334155; padding: 0 0.4rem; }
.pager-jump { display: flex; align-items: center; gap: 0.3rem; margin-left: 0.4rem; }
.pager-jump input {
	width: 56px;
	height: 32px;
	padding: 0 0.4rem;
	border: 1px solid #d7dfeb;
	border-radius: 8px;
	background: #fff;
	font-size: 0.8rem;
	color: #1e293b;
}
.pager-jump input:focus { outline: none; border-color: #93c5fd; box-shadow: 0 0 0 3px rgba(59,130,246,0.12); }

@media (max-width: 1024px) {
	.stats-grid { grid-template-columns: 1fr; }
	.panel-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
	.overview-card { grid-template-columns: 1fr; justify-items: center; }
}
</style>
