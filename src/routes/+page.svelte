<script lang="ts">
import RunDetailPanel from '$lib/components/RunDetailPanel.svelte';
import StatusBadge from '$lib/components/StatusBadge.svelte';
import { fetchFromGitHub } from '$lib/fetcher';
import type { RunRecord, SummaryData } from '$lib/types';
import { onMount } from 'svelte';

type StatusFilter = 'all' | 'failed' | 'success' | 'running';
type QuantStatusFilter = Exclude<StatusFilter, 'all'>;
type SortKey = 'submitted_time' | 'model_id' | 'artifact_name' | 'owner';
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
	let sortKey = $state<SortKey>('submitted_time');
	let sortAsc = $state(false);
	let nowStr = $state('');
	let sidebarCollapsed = $state(true);

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

// Refresh the dashboard data. `initial` controls whether the full-screen
// loading state is shown; periodic refreshes update silently in the background.
const loadData = async (initial = false) => {
	try {
		const result = await fetchFromGitHub((msg) => { if (initial) loadingMsg = msg; });
		runs = result.runs;
		latest = result.latest;
		summary = result.summary;
		fetchError = '';
	} catch (e: any) {
		// Only surface errors on the first load; ignore transient refresh failures.
		if (initial) fetchError = e?.message || 'Failed to fetch data';
	} finally {
		if (initial) loading = false;
	}
};

// Auto-refresh interval (ms): keep the open page in sync with the cached data.
const DATA_REFRESH_MS = 5 * 60 * 1000;

onMount(() => {
	tickClock();
	const clockInterval = setInterval(tickClock, 1000);
	loadData(true);
	const dataInterval = setInterval(() => loadData(false), DATA_REFRESH_MS);
	return () => { clearInterval(clockInterval); clearInterval(dataInterval); };
});

const currentRows = $derived(runs);
const owners = $derived(['all', ...new Set(runs.map((r) => r.owner).filter(Boolean)).values()]);
const SCHEME_TOKENS = ['W4A16', 'MXFP4', 'NVFP4'];
const extractScheme = (run: RunRecord) => {
	const raw = run.pipeline?.quant_scheme || run.scheme || '';
	if (raw) return raw;
	// Eval-only jobs carry the scheme only inside the artifact/model name.
	const hay = `${run.artifact_name || ''} ${run.model_id || ''}`.toUpperCase();
	return SCHEME_TOKENS.find((tok) => hay.includes(tok)) || '';
};
const displayScheme = (run: RunRecord) => {
	const raw = extractScheme(run);
	return raw === 'W4A16' ? 'INT4 (W4A16)' : raw;
};
const displayMethod = (run: RunRecord) => {
	const hay = `${run.method || ''} ${run.artifact_name || ''}`.toLowerCase();
	if (hay.includes('rtn')) return 'RTN';
	if (hay.includes('tuning') || hay.includes('autoround') || hay.includes('auto_eval') || String(run.method || '').trim()) return 'TUNING';
	return '-';
};
const schemes = $derived(['all', ...new Set(runs.map(displayScheme).filter(Boolean)).values()]);
const submitters = $derived([...new Set(runs.map((r) => String(r.submitted_by || '')).filter(Boolean)).values()]);

const statusBucket = (run: RunRecord): QuantStatusFilter => {
if (run.auto_quant_status === 'failed' || run.auto_eval_status === 'failed') return 'failed';
if (run.auto_quant_status === 'success' && (run.auto_eval_status == null || run.auto_eval_status === 'success')) return 'success';
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
const left = sortValue(a, sortKey);
const right = sortValue(b, sortKey);
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
sortAsc = key !== 'submitted_time';
};

const failedRuns = $derived(runs.filter((r) => statusBucket(r) === 'failed'));
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
const diffMs = Math.max(0, now.getTime() - d.getTime());
const diffH = Math.floor(diffMs / 3600000);
if (diffH < 1) {
	const diffMin = Math.floor(diffMs / 60000);
	return diffMin < 1 ? 'just now' : `${diffMin}m ago`;
}
if (diffH < 24) return `${diffH}h ago`;
const diffD = Math.floor(diffH / 24);
if (diffD < 7) return `${diffD}d ago`;
return d.toLocaleDateString('en-CA');
};

const submittedTime = (run: RunRecord) =>
	run.pipeline?.submitted_time || run.run_timestamp || run.updated_at || '';

const sortValue = (run: RunRecord, key: SortKey): string => {
	if (key === 'submitted_time') return submittedTime(run);
	return String((run as unknown as Record<string, unknown>)[key] ?? '');
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
		if (!s) continue;
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

const selectClass =
	'select-arrow min-w-[130px] cursor-pointer rounded-lg border border-slate-200 bg-white py-2 pl-3 pr-8 text-[0.8125rem] text-slate-900 shadow-sm transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15';

const navLinkClass =
	'flex items-center gap-2.5 rounded-lg px-3 py-2 text-[0.8125rem] font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-900';

const thBtnClass =
	'cursor-pointer border-0 bg-transparent p-0 text-[0.6875rem] font-bold uppercase tracking-[0.06em] text-slate-500 transition-colors hover:text-indigo-600';
const tdClass = 'border-b border-slate-100 px-4 py-3 align-middle text-[0.8125rem] text-slate-700';
const pagerBtnClass =
	'flex h-8 min-w-[32px] items-center justify-center rounded-lg border border-slate-300 bg-white px-2 text-[0.95rem] font-bold text-slate-800 transition hover:enabled:border-indigo-300 hover:enabled:bg-indigo-50 disabled:cursor-default disabled:opacity-40';

const rowClass = (run: RunRecord) => {
	const failed = statusBucket(run) === 'failed';
	const active = selected?.run_path === run.run_path;
	const base = 'cursor-pointer transition-colors';
	if (failed && active) return `${base} bg-red-100 shadow-[inset_3px_0_0_#ef4444]`;
	if (failed) return `${base} bg-red-50 hover:bg-red-100`;
	if (active) return `${base} bg-indigo-50 shadow-[inset_3px_0_0_#4f46e5]`;
	return `${base} hover:bg-slate-50`;
};
</script>

<div class="flex min-h-screen bg-slate-100 text-slate-800">
<!-- ── Sidebar ── -->
<aside class="sticky top-0 hidden h-screen shrink-0 flex-col border-r border-slate-200 bg-white transition-all duration-200 lg:flex {sidebarCollapsed ? 'w-16' : 'w-60'}">
	<div class="flex items-center gap-2.5 border-b border-slate-100 py-4 {sidebarCollapsed ? 'justify-center px-0' : 'px-5'}">
		{#if sidebarCollapsed}
		<button type="button" onclick={() => (sidebarCollapsed = false)} aria-label="Expand sidebar" title="Expand sidebar" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-500 text-white shadow-sm transition hover:brightness-110">
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
		</button>
		{:else}
		<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-500 text-white shadow-sm">
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
		</div>
		<div class="leading-tight">
			<div class="text-sm font-extrabold tracking-tight text-slate-900">lb_eval</div>
			<div class="text-[0.6875rem] font-semibold uppercase tracking-wide text-slate-400">Monitor</div>
		</div>
		<button type="button" onclick={() => (sidebarCollapsed = true)} aria-label="Collapse sidebar" title="Collapse sidebar" class="ml-auto flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700">
			<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
		</button>
		{/if}
	</div>
	<nav class="flex flex-col gap-0.5 p-3">
		<a href="#overview" class="{navLinkClass} {sidebarCollapsed ? 'justify-center px-0' : ''}" title="Overview">
			<svg class="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
			{#if !sidebarCollapsed}Overview{/if}
		</a>
		<a href="#analytics" class="{navLinkClass} {sidebarCollapsed ? 'justify-center px-0' : ''}" title="Analytics">
			<svg class="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
			{#if !sidebarCollapsed}Analytics{/if}
		</a>
		<a href="#models" class="{navLinkClass} {sidebarCollapsed ? 'justify-center px-0' : ''}" title="Models">
			<svg class="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
			{#if !sidebarCollapsed}Models{/if}
		</a>
	</nav>
	{#if !sidebarCollapsed}
	<div class="mt-auto border-t border-slate-100 p-4">
		<div class="mb-3 flex items-center gap-2 text-[0.6875rem] font-medium tabular-nums text-slate-400">
			<span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
			{nowStr || '—'} CST
		</div>
		<a class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-[0.75rem] font-semibold text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700" href="https://github.com/XuehaoSun/lb_eval" target="_blank" rel="noopener noreferrer">
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
			XuehaoSun/lb_eval
		</a>
	</div>
	{/if}
</aside>

<!-- ── Main column ── -->
<div class="flex min-w-0 flex-1 flex-col">
<header class="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white/85 px-5 py-3 backdrop-blur-md sm:px-7">
	<div class="mr-auto min-w-0">
		<h1 class="text-base font-extrabold tracking-tight text-slate-900">Low-bit LLM Dashboard</h1>
		<p class="truncate text-xs text-slate-400">Automated quantization pipeline for LLM leaderboard models</p>
	</div>
	<div class="relative w-full sm:w-64">
		<svg class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
		<input bind:value={search} placeholder="Search models, errors..." aria-label="Search" class="w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 pl-8 pr-3 text-[0.8125rem] text-slate-900 transition placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15" />
	</div>
</header>

<main class="flex-1 px-5 py-5 sm:px-7">
	<!-- KPI strip -->
	<section id="overview" class="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
		<div class="flex items-center gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70 transition hover:ring-indigo-200">
			<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
			</div>
			<div class="min-w-0">
				<span class="block text-[0.6875rem] font-semibold uppercase tracking-wide text-slate-400">Total Runs</span>
				<span class="block text-xl font-extrabold leading-tight tracking-tight text-slate-900 tabular-nums">{runs.length}</span>
			</div>
		</div>
		<div class="flex items-center gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70 transition hover:ring-violet-200">
			<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
			</div>
			<div class="min-w-0">
				<span class="block text-[0.6875rem] font-semibold uppercase tracking-wide text-slate-400">Models</span>
				<span class="block text-xl font-extrabold leading-tight tracking-tight text-slate-900 tabular-nums">{latest.length || runs.length}</span>
			</div>
		</div>
		<div class="flex items-center gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70 transition hover:ring-red-200">
			<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-600">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
			</div>
			<div class="min-w-0">
				<span class="block text-[0.6875rem] font-semibold uppercase tracking-wide text-slate-400">Failed</span>
				<span class="block text-xl font-extrabold leading-tight tracking-tight text-red-600 tabular-nums">{quantCounts.failed}</span>
			</div>
		</div>
		<div class="flex items-center gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200/70 transition hover:ring-emerald-200">
			<div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
			</div>
			<div class="min-w-0">
				<span class="block text-[0.6875rem] font-semibold uppercase tracking-wide text-slate-400">Quant Pass</span>
				<span class="block text-xl font-extrabold leading-tight tracking-tight text-emerald-600 tabular-nums">{quantTotal > 0 ? pct(quantCounts.success, quantTotal) : '0'}%</span>
			</div>
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
	<section class="mb-6 grid grid-cols-1 gap-4" bind:this={filtersRef}>
		<div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
			<div class="mb-3.5 flex items-center justify-between">
				<h3 class="text-[0.9375rem] font-bold text-slate-900">Quantization Pipeline</h3>
				<span class="text-xs font-medium text-slate-400">{quantTotal} runs</span>
			</div>
			<div class="mb-3 flex h-2.5 overflow-hidden rounded-full bg-slate-200">
				{#if quantTotal > 0}
				<button class="cursor-pointer border-0 p-0 bg-emerald-500 transition hover:brightness-110" style="width: {pct(quantCounts.success, quantTotal)}%" onclick={() => filterByBar('success')} aria-label="Filter quant success"></button>
				<button class="cursor-pointer border-0 p-0 bg-red-500 transition hover:brightness-110" style="width: {pct(quantCounts.failed, quantTotal)}%" onclick={() => filterByBar('failed')} aria-label="Filter quant failed"></button>
				<button class="cursor-pointer border-0 p-0 bg-amber-500 transition hover:brightness-110" style="width: {pct(quantCounts.running, quantTotal)}%" onclick={() => filterByBar('running')} aria-label="Filter quant running"></button>
				{/if}
			</div>
			<div class="grid grid-cols-3 gap-1.5">
				<button class="flex items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600 transition hover:border-slate-300 hover:bg-slate-100" onclick={() => filterByBar('success')}><span class="ldot ldot--success"></span>Success <strong class="font-bold text-slate-900">{quantCounts.success}</strong></button>
				<button class="flex items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600 transition hover:border-slate-300 hover:bg-slate-100" onclick={() => filterByBar('failed')}><span class="ldot ldot--failed"></span>Failed <strong class="font-bold text-slate-900">{quantCounts.failed}</strong></button>
				<button class="flex items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600 transition hover:border-slate-300 hover:bg-slate-100" onclick={() => filterByBar('running')}><span class="ldot ldot--running"></span>Running <strong class="font-bold text-slate-900">{quantCounts.running}</strong></button>
			</div>
		</div>

	</section>

	<section id="analytics" class="stats-grid">
		<!-- Affiliation donut -->
		<div class="overview-card" class:overview-card--expanded={expandedBucket}>
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
			</div>
		</div>

		<!-- Scheme distribution chart -->
		<div class="stats-panel">
			<div class="panel-header">
				<h2>By Scheme{#if selectedSubmitter} · {selectedSubmitter}{/if}</h2>
				{#if scheme !== 'all'}
				<button type="button" class="scheme-clear" onclick={() => (scheme = 'all')} title="Clear scheme filter">
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
					{scheme}
				</button>
				{:else}
				<span class="panel-count">{schemeRows.length} scheme{schemeRows.length === 1 ? '' : 's'}</span>
				{/if}
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
	<section class="mb-6 rounded-2xl border border-red-200 border-l-4 border-l-red-500 bg-white p-5 shadow-sm">
		<div class="mb-3.5 flex items-center gap-2.5 text-sm font-bold text-red-700">
			<div class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-600">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
			</div>
			<span>Needs Attention -- {failedRuns.length} failed run{failedRuns.length > 1 ? 's' : ''}</span>
		</div>
		<div class="flex flex-col gap-2">
			{#each failedRuns.slice(0, 5) as run}
			<button class="grid grid-cols-1 items-center gap-1 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-left text-[0.8125rem] transition hover:bg-red-100 sm:grid-cols-[minmax(180px,auto)_auto_1fr] sm:gap-4" onclick={() => selectRun(run)}>
				<span class="font-semibold text-slate-900">{run.owner}/{run.model_id}</span>
				<span class="flex items-center gap-1.5 text-xs text-slate-500">
					{#if run.auto_quant_status === 'failed'}<StatusBadge status="failed" /> quant{/if}
				</span>
				<span class="truncate text-xs text-slate-500">{(run.eval_errors[0] || run.quant_errors[0] || run.issues[0] || '').slice(0, 80)}{(run.eval_errors[0] || run.quant_errors[0] || run.issues[0] || '').length > 80 ? '...' : ''}</span>
			</button>
			{/each}
			{#if failedRuns.length > 5}
			<button class="py-2 text-left text-[0.8125rem] font-bold text-red-600 transition hover:text-red-800" onclick={() => { status = 'failed'; }}>View all {failedRuns.length} failures</button>
			{/if}
		</div>
	</section>
	{/if}

	<!-- Filter bar -->
	<section class="mb-4 flex flex-wrap items-center gap-2.5">
		<select bind:value={owner} aria-label="Org filter" class={selectClass}>{#each owners as item}<option value={item}>{item === 'all' ? 'All orgs' : item}</option>{/each}</select>
		<select bind:value={scheme} aria-label="Scheme filter" class={selectClass}>{#each schemes as item}<option value={item}>{item === 'all' ? 'All schemes' : item}</option>{/each}</select>
		<select bind:value={selectedSubmitter} aria-label="Submitter filter" class={selectClass}><option value={null}>All submitters</option>{#each submitters as item}<option value={item}>{item}</option>{/each}</select>
		<select bind:value={status} aria-label="Status filter" class={selectClass}>
			<option value="all">All status</option>
			<option value="failed">Failed</option>
			<option value="success">Success</option>
			<option value="running">Running</option>
		</select>
	</section>

	<!-- ═══════ THE single model list (content varies by active filters) ═══════ -->
	{#if activeFilters.length > 0}
	<div class="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5">
		<span class="mr-0.5 inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
			Active filters
		</span>
		{#each activeFilters as f (f.key)}
		<button type="button" class="group inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 transition hover:border-red-300 hover:bg-red-50 hover:text-red-700" onclick={f.clear} title="Remove {f.label} filter">
			<span class="font-bold text-slate-500 group-hover:text-red-700">{f.label}:</span>
			<span class="font-bold">{f.value}</span>
			<svg class="opacity-70" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
		</button>
		{/each}
		{#if activeFilters.length > 1}
		<button type="button" class="ml-auto rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-bold text-slate-600 transition hover:border-red-300 hover:bg-red-50 hover:text-red-700" onclick={clearAllFilters}>Clear all</button>
		{/if}
	</div>
	{/if}

	<div class="mb-3 flex items-center gap-2.5">
		<span class="text-[0.8125rem] font-semibold text-slate-500">{tableRows.length} runs</span>
	</div>

	<!-- Detail panel above table -->
	<div bind:this={detailRef}>
		<RunDetailPanel run={selected} onClose={() => (selected = null)} />
	</div>

	<section id="models" class="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-100" bind:this={tableRef}>
		<div class="overflow-x-auto">
		<table class="w-full border-collapse">
			<thead class="border-b border-slate-200 bg-slate-50">
				<tr>
					<th class="whitespace-nowrap px-4 py-3 text-left"><button type="button" class={thBtnClass} onclick={() => setSort('submitted_time')}>Submitted{sortIcon('submitted_time')}</button></th>
					<th class="whitespace-nowrap px-4 py-3 text-left"><button type="button" class={thBtnClass} onclick={() => setSort('owner')}>Owner{sortIcon('owner')}</button></th>
					<th class="whitespace-nowrap px-4 py-3 text-left"><button type="button" class={thBtnClass} onclick={() => setSort('model_id')}>Model / Artifact{sortIcon('model_id')}</button></th>
					<th class="whitespace-nowrap px-4 py-3 text-left text-[0.6875rem] font-bold uppercase tracking-[0.06em] text-slate-500">Scheme</th>
					<th class="whitespace-nowrap px-4 py-3 text-left text-[0.6875rem] font-bold uppercase tracking-[0.06em] text-slate-500">Method</th>
					<th class="whitespace-nowrap px-4 py-3 text-left text-[0.6875rem] font-bold uppercase tracking-[0.06em] text-slate-500">Status</th>
				</tr>
			</thead>
			<tbody>
				{#if tableRows.length === 0}
				<tr><td colspan="6" class="px-4 py-12 text-center italic text-slate-400">No runs match current filters.</td></tr>
				{:else}
				{#each pagedRows as run}
				<tr class={rowClass(run)} onclick={() => selectRun(run)}>
					<td class="{tdClass} whitespace-nowrap text-xs font-medium text-slate-500">{formatTime(submittedTime(run))}</td>
					<td class="{tdClass} font-semibold text-slate-800">{run.owner}</td>
					<td class={tdClass}>
						<span class="block font-bold text-slate-900">{run.model_id}</span>
						{#if run.artifact_name !== run.model_id}
						<span class="mt-0.5 block text-[0.6875rem] text-slate-400">{run.artifact_name}</span>
						{/if}
					</td>
					<td class={tdClass}><span class="text-xs font-semibold text-slate-800">{displayScheme(run) || '-'}</span></td>
					<td class={tdClass}><span class="text-[0.6875rem] text-slate-400">{displayMethod(run)}</span></td>
					<td class={tdClass}><StatusBadge status={statusBucket(run)} /></td>
				</tr>
				{/each}
				{/if}
			</tbody>
		</table>
		</div>
		{#if tableRows.length > PAGE_SIZE}
		<div class="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 bg-slate-50/60 px-5 py-3">
			<span class="text-[0.78rem] text-slate-500">Showing {pageStart}-{pageEnd} of {tableRows.length}</span>
			<div class="flex items-center gap-1.5">
				<button type="button" class={pagerBtnClass} onclick={() => goToPage(1)} disabled={page === 1} aria-label="First page">«</button>
				<button type="button" class={pagerBtnClass} onclick={() => goToPage(page - 1)} disabled={page === 1} aria-label="Previous page">‹</button>
				<span class="px-1.5 text-[0.78rem] font-semibold text-slate-700">Page {page} / {totalPages}</span>
				<button type="button" class={pagerBtnClass} onclick={() => goToPage(page + 1)} disabled={page === totalPages} aria-label="Next page">›</button>
				<button type="button" class={pagerBtnClass} onclick={() => goToPage(totalPages)} disabled={page === totalPages} aria-label="Last page">»</button>
				<form class="ml-1.5 flex items-center gap-1.5" onsubmit={(e) => { e.preventDefault(); jumpToPage(); }}>
					<input type="number" min="1" max={totalPages} bind:value={pageInput} placeholder="Go" aria-label="Go to page" class="h-8 w-14 rounded-lg border border-slate-300 bg-white px-1.5 text-sm text-slate-800 focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/15" />
					<button type="submit" class={pagerBtnClass}>Go</button>
				</form>
			</div>
		</div>
		{/if}
	</section>
	{/if}
</main>
</div>
</div>

<style>
/* ── Status Bars ── */
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
	border-top-color: #4f46e5;
	border-radius: 50%;
	animation: spin 0.6s linear infinite;
}
@keyframes spin {
	to { transform: rotate(360deg); }
}

/* ── Responsive ── */
@media (max-width: 768px) {
	.stats-grid { grid-template-columns: 1fr; }
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
.panel-header h2 { margin: 0; font-size: 1rem; font-weight: 700; color: #0f172a; }
.panel-count {
	font-size: 0.75rem;
	font-weight: 700;
	color: #64748b;
	background: #f1f5f9;
	padding: 0.2rem 0.6rem;
	border-radius: 999px;
}
.scheme-clear {
	display: inline-flex;
	align-items: center;
	gap: 0.3rem;
	font-size: 0.72rem;
	font-weight: 700;
	color: #4338ca;
	background: #eef2ff;
	border: 1px solid #c7d2fe;
	padding: 0.2rem 0.6rem 0.2rem 0.45rem;
	border-radius: 999px;
	cursor: pointer;
	max-width: 14rem;
	transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.scheme-clear:hover { background: #fee2e2; border-color: #fecaca; color: #b91c1c; }
.scheme-clear svg { flex-shrink: 0; }
.empty-state {
	padding: 1.5rem 1.4rem;
	color: #94a3b8;
	font-size: 0.85rem;
	font-style: italic;
}

/* ── Stats: affiliation donut ── */
.overview-card {
	display: grid;
	grid-template-columns: 180px minmax(0, 1fr);
	gap: 1.25rem;
	align-items: center;
	background: #fff;
	border-radius: 16px;
	padding: 1.75rem 2rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
	border: 1px solid #eef2f7;
}
.overview-card--expanded {
	grid-template-columns: 1fr;
	align-items: stretch;
}
.overview-card--expanded .donut-wrap { display: none; }
.donut-wrap { display: flex; justify-content: center; }
.donut { width: 190px; height: 190px; }
.donut-bg { fill: none; stroke: #eef2ff; stroke-width: 16; transform: rotate(-90deg); transform-origin: 70px 70px; }
.donut-seg { fill: none; stroke-width: 16; stroke-linecap: round; transition: stroke-dasharray 0.6s ease; transform: rotate(-90deg); transform-origin: 70px 70px; }
.donut-seg--external { stroke: #f59e0b; }
.donut-seg--intel { stroke: #4f46e5; }
.donut-num { fill: #0f172a; font-size: 26px; font-weight: 800; text-anchor: middle; }
.donut-cap { fill: #94a3b8; font-size: 10px; font-weight: 600; text-anchor: middle; text-transform: uppercase; letter-spacing: 0.08em; }
.overview-legend { display: flex; flex-direction: column; gap: 0.6rem; min-width: 0; }
.legend-block { display: flex; flex-direction: column; gap: 0.5rem; }
.legend-item {
	display: flex;
	align-items: center;
	gap: 0.6rem;
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
.legend-dot--intel { background: #4f46e5; }
.legend-dot--external { background: #f59e0b; }
.legend-text { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.legend-name { font-weight: 700; font-size: 0.875rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.legend-meta { font-size: 0.75rem; color: #94a3b8; white-space: nowrap; }
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
.people-pill:hover { border-color: #c7d2fe; }
.people-pill--active { border-color: #4f46e5; background: #eef2ff; box-shadow: 0 0 0 2px rgba(79,70,229,0.15); }
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
	color: #4338ca;
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
.scheme-row--active { background: #eef2ff; box-shadow: inset 3px 0 0 #4f46e5; }
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
.scheme-name { font-weight: 600; font-size: 0.8125rem; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.scheme-count { font-size: 0.8125rem; font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums; }
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
.stack-seg--on { box-shadow: inset 0 0 0 2px rgba(255,255,255,0.9); filter: brightness(0.96) saturate(1.18); }
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
	font-size: 0.75rem;
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

@media (max-width: 1024px) {
	.stats-grid { grid-template-columns: 1fr; }
	.panel-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
	.overview-card { grid-template-columns: 1fr; justify-items: center; }
}
</style>
