<script lang="ts">
import { base } from '$app/paths';
import { fetchFromGitHub } from '$lib/fetcher';
import type { RunRecord, SummaryData } from '$lib/types';
import { onMount } from 'svelte';

type SubmitterBucket = 'Intel' | 'Non-Intel';

interface SubmitterRow {
	name: string;
	count: number;
	intelCount: number;
	nonIntelCount: number;
	orgs: string[];
	bucket: SubmitterBucket;
}

interface CompanyRow {
	company: string;
	count: number;
	models: string[];
}

	let runs = $state<RunRecord[]>([]);
	let latest = $state<RunRecord[]>([]);
	let summary = $state<SummaryData | null>(null);
	let loading = $state(true);
	let fetchError = $state('');
	let latestOnly = $state(false);
	let search = $state('');
	let expandedBucket = $state<SubmitterBucket | null>(null);
	let expandedCompanies = $state<Set<string>>(new Set());
	let selectedSubmitter = $state<string | null>(null);

const toggleBucket = (bucket: SubmitterBucket) => {
	expandedBucket = expandedBucket === bucket ? null : bucket;
};
const selectSubmitter = (name: string) => {
	selectedSubmitter = selectedSubmitter === name ? null : name;
};
const clearSubmitter = () => {
	selectedSubmitter = null;
};
const toggleCompany = (company: string) => {
	const next = new Set(expandedCompanies);
	if (next.has(company)) next.delete(company);
	else next.add(company);
	expandedCompanies = next;
};

const INTEL_WHITELIST = new Set(['wenjiao', 'lvkaokao', 'Haihao', 'INC4AI', 'Xuehao']);

onMount(() => {
	(async () => {
		try {
			const [runsRes, latestRes, summaryRes] = await Promise.all([
				fetch(`${base}/data/runs.json`),
				fetch(`${base}/data/latest.json`),
				fetch(`${base}/data/summary.json`)
			]);
			if (runsRes.ok) runs = await runsRes.json();
			if (latestRes.ok) latest = await latestRes.json();
			if (summaryRes.ok) summary = await summaryRes.json();
		} catch {
			// Static files may be unavailable during early dev startup.
		}
		loading = false;

		try {
			const result = await fetchFromGitHub();
			if (result.runs.length > 0) {
				runs = result.runs;
				latest = result.latest;
				summary = result.summary;
				fetchError = '';
			}
		} catch (e: any) {
			if (runs.length === 0) fetchError = e?.message || 'Failed to fetch data';
		}
	})();
});

const currentRows = $derived(latestOnly ? latest : runs);
const submissionRows = $derived(currentRows.filter((run) => Boolean(run.submitted_by)));

const normalizedOrgs = (run: RunRecord) => (run.orgs || []).map((org) => org.trim()).filter(Boolean);
const isIntelSubmission = (run: RunRecord) => {
	const orgs = normalizedOrgs(run);
	if (orgs.some((org) => org.toLowerCase() === 'intel')) return true;
	return orgs.length === 0 && Boolean(run.submitted_by) && INTEL_WHITELIST.has(String(run.submitted_by));
};

const submitterRows = $derived.by<SubmitterRow[]>(() => {
	const bySubmitter = new Map<string, SubmitterRow>();
	for (const run of submissionRows) {
		const name = String(run.submitted_by || 'unknown');
		const intel = isIntelSubmission(run);
		const row = bySubmitter.get(name) || {
			name,
			count: 0,
			intelCount: 0,
			nonIntelCount: 0,
			orgs: [],
			bucket: 'Non-Intel' as SubmitterBucket
		};
		row.count += 1;
		if (intel) row.intelCount += 1;
		else row.nonIntelCount += 1;
		row.orgs = [...new Set([...row.orgs, ...normalizedOrgs(run)])];
		row.bucket = row.intelCount >= row.nonIntelCount ? 'Intel' : 'Non-Intel';
		bySubmitter.set(name, row);
	}
	return [...bySubmitter.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
});

const filteredSubmitterRows = $derived.by(() => {
	let rows = submitterRows;
	if (selectedSubmitter) rows = rows.filter((row) => row.name === selectedSubmitter);
	const keyword = search.trim().toLowerCase();
	if (!keyword) return rows;
	return rows.filter((row) => [row.name, row.bucket, row.orgs.join(' ')].join(' ').toLowerCase().includes(keyword));
});

const intelSubmissionCount = $derived(submissionRows.filter(isIntelSubmission).length);
const nonIntelSubmissionCount = $derived(submissionRows.length - intelSubmissionCount);
const intelPeople = $derived(submitterRows.filter((row) => row.bucket === 'Intel'));
const nonIntelPeople = $derived(submitterRows.filter((row) => row.bucket === 'Non-Intel'));
const intelPeopleCount = $derived(intelPeople.length);
const nonIntelPeopleCount = $derived(submitterRows.length - intelPeopleCount);
const maxSubmitterCount = $derived(Math.max(1, ...filteredSubmitterRows.map((row) => row.count)));

const companyFromRun = (run: RunRecord) => {
	const modelId = run.model_id || '';
	if (modelId.includes('/')) return modelId.split('/')[0] || 'unknown';
	return run.owner || 'unknown';
};

const companyRows = $derived.by<CompanyRow[]>(() => {
	const scopedRows = selectedSubmitter
		? currentRows.filter((run) => String(run.submitted_by || '') === selectedSubmitter)
		: currentRows;
	const byCompany = new Map<string, CompanyRow>();
	for (const run of scopedRows) {
		const company = companyFromRun(run);
		const modelName = run.model_id || run.artifact_name || 'unknown';
		const row = byCompany.get(company) || { company, count: 0, models: [] };
		row.count += 1;
		row.models = [...new Set([...row.models, modelName])];
		byCompany.set(company, row);
	}
	return [...byCompany.values()].sort((a, b) => b.count - a.count || a.company.localeCompare(b.company));
});

const filteredCompanyRows = $derived.by(() => {
	const keyword = search.trim().toLowerCase();
	if (!keyword) return companyRows;
	return companyRows.filter((row) => [row.company, row.models.join(' ')].join(' ').toLowerCase().includes(keyword));
});

const maxCompanyCount = $derived(Math.max(1, ...filteredCompanyRows.map((row) => row.count)));
const barWidth = (value: number, max: number) => `${Math.max(3, (value / max) * 100)}%`;
const share = (value: number, total: number) => (total > 0 ? Math.round((value / total) * 100) : 0);

// Donut geometry (radius 54)
const DONUT_C = 2 * Math.PI * 54;
const intelDash = $derived(
	submissionRows.length > 0 ? (intelSubmissionCount / submissionRows.length) * DONUT_C : 0
);

const initials = (name: string) => name.slice(0, 2).toUpperCase();
</script>

<svelte:head>
	<title>Submission Statistics | lb_eval monitor</title>
</svelte:head>

<div class="shell">
	<header class="hero-wrap">
		<div class="hero">
			<div class="hero-content">
				<a class="back-link" href="{base}/">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
					Dashboard
				</a>
				<h1>Submission Statistics</h1>
				<p class="hero-desc">Submitter affiliation and model-company submission volume.</p>
			</div>
			<div class="hero-metrics">
				<div><span>{submissionRows.length}</span><small>Submissions tracked</small></div>
				<div><span>{summary?.total_runs ?? runs.length}</span><small>Total records</small></div>
			</div>
		</div>
	</header>

	<main class="content">
		<section class="toolbar">
			<div class="search-box">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
				<input bind:value={search} placeholder="Search submitter, org, company, model..." aria-label="Search statistics" />
			</div>
			<label class="toggle-label">
				<input type="checkbox" bind:checked={latestOnly} />
				<span>Latest models only</span>
			</label>
		</section>

		{#if loading}
		<div class="loading-state"><div class="spinner"></div><span>Loading statistics...</span></div>
		{:else}
		{#if fetchError}
		<div class="error-banner">{fetchError}</div>
		{/if}

		<!-- Affiliation overview: donut + breakdown -->
		<section class="overview-card">
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
					<button
						type="button"
						class="legend-item legend-item--btn"
						class:legend-item--open={expandedBucket === 'Intel'}
						onclick={() => toggleBucket('Intel')}
						aria-expanded={expandedBucket === 'Intel'}
					>
						<span class="legend-dot legend-dot--intel"></span>
						<div class="legend-text">
							<span class="legend-name">Intel employees</span>
							<span class="legend-meta">{intelPeopleCount} {intelPeopleCount === 1 ? 'person' : 'people'}</span>
						</div>
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
							<a class="people-pill-hf" href="https://huggingface.co/{person.name}" target="_blank" rel="noopener noreferrer" title="Open {person.name} on Hugging Face" aria-label="Open {person.name} on Hugging Face">
								<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
							</a>
						</div>
						{/each}
						{/if}
					</div>
					{/if}
				</div>
				<div class="legend-block">
					<button
						type="button"
						class="legend-item legend-item--btn"
						class:legend-item--open={expandedBucket === 'Non-Intel'}
						onclick={() => toggleBucket('Non-Intel')}
						aria-expanded={expandedBucket === 'Non-Intel'}
					>
						<span class="legend-dot legend-dot--external"></span>
						<div class="legend-text">
							<span class="legend-name">Non-Intel employees</span>
							<span class="legend-meta">{nonIntelPeopleCount} {nonIntelPeopleCount === 1 ? 'person' : 'people'}</span>
						</div>
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
							<a class="people-pill-hf" href="https://huggingface.co/{person.name}" target="_blank" rel="noopener noreferrer" title="Open {person.name} on Hugging Face" aria-label="Open {person.name} on Hugging Face">
								<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
							</a>
						</div>
						{/each}
						{/if}
					</div>
					{/if}
				</div>
				<p class="rule-note">Intel = <code>org/orgs</code> contains <code>Intel</code>, or <code>orgs</code> empty and submitter in the whitelist.</p>
			</div>
		</section>

		{#if selectedSubmitter}
		<div class="filter-banner">
			<span class="filter-banner-text">Filtering by submitter: <strong>{selectedSubmitter}</strong></span>
			<button type="button" class="filter-banner-clear" onclick={clearSubmitter}>
				<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
				Clear
			</button>
		</div>
		{/if}

		<div class="panel-grid">
			<!-- Submitters -->
			<section class="panel">
				<div class="panel-header">
					<h2>Submitters</h2>
					<span class="panel-count">{filteredSubmitterRows.length} people</span>
				</div>
				<div class="rank-list">
					{#if filteredSubmitterRows.length === 0}
					<div class="empty-state">No submitted_by data is available for the current records.</div>
					{:else}
					{#each filteredSubmitterRows as row}
					<div class="rank-row">
						<span class="avatar" class:avatar--intel={row.bucket === 'Intel'} class:avatar--external={row.bucket === 'Non-Intel'}>{initials(row.name)}</span>
						<div class="rank-body">
							<div class="rank-top">
								<a class="rank-name rank-name--link" href="https://huggingface.co/{row.name}" target="_blank" rel="noopener noreferrer" title="Open {row.name} on Hugging Face">{row.name}</a>
								<span class="chip" class:chip--intel={row.bucket === 'Intel'} class:chip--external={row.bucket === 'Non-Intel'}>{row.bucket}</span>
								<strong class="rank-count">{row.count}</strong>
							</div>
							<div class="track"><div class="fill" class:fill--intel={row.bucket === 'Intel'} class:fill--external={row.bucket === 'Non-Intel'} style="width: {barWidth(row.count, maxSubmitterCount)}"></div></div>
							<span class="rank-sub" title={row.orgs.length ? row.orgs.join(', ') : 'orgs empty'}>{row.orgs.length ? `orgs: ${row.orgs.join(', ')}` : 'orgs empty'}</span>
						</div>
					</div>
					{/each}
					{/if}
				</div>
			</section>

			<!-- Companies -->
			<section class="panel">
				<div class="panel-header">
					<h2>Model Companies</h2>
					<span class="panel-count">{filteredCompanyRows.length} companies</span>
				</div>
				<div class="rank-list">
					{#if filteredCompanyRows.length === 0}
					<div class="empty-state">No model records match the current filter.</div>
					{:else}
					{#each filteredCompanyRows as row}
					<div class="rank-row rank-row--expandable">
						<button type="button" class="rank-toggle" onclick={() => toggleCompany(row.company)} aria-expanded={expandedCompanies.has(row.company)}>
							<span class="avatar avatar--company">{initials(row.company)}</span>
							<div class="rank-body">
								<div class="rank-top">
									<span class="rank-name" title={row.company}>{row.company}</span>
									<span class="chip chip--muted">{row.models.length} model{row.models.length === 1 ? '' : 's'}</span>
									<strong class="rank-count">{row.count}</strong>
									<svg class="rank-caret" class:rank-caret--open={expandedCompanies.has(row.company)} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
								</div>
								<div class="track"><div class="fill fill--company" style="width: {barWidth(row.count, maxCompanyCount)}"></div></div>
								<span class="rank-sub" title={row.models.join(', ')}>{row.models.slice(0, 5).join(', ')}{row.models.length > 5 ? ` +${row.models.length - 5} more` : ''}</span>
							</div>
						</button>
						{#if expandedCompanies.has(row.company)}
						<ul class="model-list">
							{#each row.models as model}
							<li class="model-item">
								<a class="model-link" href="https://huggingface.co/{model}" target="_blank" rel="noopener noreferrer" title="Open {model} on Hugging Face">{model}</a>
							</li>
							{/each}
						</ul>
						{/if}
					</div>
					{/each}
					{/if}
				</div>
			</section>
		</div>
		{/if}
	</main>
</div>

<style>
.shell {
	min-height: 100vh;
	background: #eef2f7;
	color: #1e293b;
}
.hero-wrap {
	max-width: 1600px;
	margin: 0 auto;
	padding: 1.5rem 3rem 0;
	width: 100%;
}
.hero {
	display: flex;
	align-items: flex-end;
	justify-content: space-between;
	gap: 1.5rem;
	background: linear-gradient(135deg, #0f766e 0%, #2563eb 52%, #7c3aed 100%);
	border-radius: 18px;
	padding: 2rem 2.5rem;
	color: #fff;
	box-shadow: 0 18px 40px rgba(15,23,42,0.16);
}
.hero-content { min-width: 0; }
.back-link {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	margin-bottom: 0.9rem;
	padding: 0.35rem 0.85rem;
	border-radius: 999px;
	background: rgba(255,255,255,0.16);
	border: 1px solid rgba(255,255,255,0.24);
	color: #fff;
	font-size: 0.8125rem;
	font-weight: 700;
	text-decoration: none;
	transition: background 0.15s;
}
.back-link:hover { background: rgba(255,255,255,0.28); }
h1 {
	margin: 0;
	font-size: 1.75rem;
	font-weight: 800;
}
.hero-desc {
	margin: 0.5rem 0 0;
	color: rgba(255,255,255,0.78);
	font-size: 0.9rem;
}
.hero-metrics {
	display: flex;
	gap: 0.75rem;
	flex-shrink: 0;
}
.hero-metrics div {
	min-width: 150px;
	padding: 0.8rem 1rem;
	border-radius: 12px;
	background: rgba(255,255,255,0.14);
	border: 1px solid rgba(255,255,255,0.2);
}
.hero-metrics span {
	display: block;
	font-size: 1.5rem;
	font-weight: 800;
	line-height: 1;
}
.hero-metrics small {
	display: block;
	margin-top: 0.35rem;
	color: rgba(255,255,255,0.75);
	font-size: 0.75rem;
}
.content {
	max-width: 1600px;
	margin: 0 auto;
	padding: 1.75rem 3rem 4rem;
	width: 100%;
}

/* Toolbar */
.toolbar {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	margin-bottom: 1.25rem;
}
.search-box {
	position: relative;
	flex: 1;
}
.search-box svg {
	position: absolute;
	left: 0.875rem;
	top: 50%;
	transform: translateY(-50%);
	color: #94a3b8;
}
.search-box input {
	width: 100%;
	padding: 0.6rem 0.9rem 0.6rem 2.35rem;
	border: 1px solid #dbe4ef;
	border-radius: 10px;
	background: #fff;
	font-size: 0.85rem;
	color: #0f172a;
	box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.search-box input:focus {
	outline: none;
	border-color: #2563eb;
	box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
}
.toggle-label {
	display: flex;
	align-items: center;
	gap: 0.45rem;
	padding: 0.6rem 0.8rem;
	border: 1px solid #dbe4ef;
	border-radius: 10px;
	background: #fff;
	font-size: 0.85rem;
	font-weight: 600;
	white-space: nowrap;
	cursor: pointer;
}
.toggle-label input { accent-color: #2563eb; }

/* Overview / donut */
.overview-card {
	display: grid;
	grid-template-columns: 200px 1fr;
	gap: 1.75rem;
	align-items: center;
	background: #fff;
	border-radius: 16px;
	padding: 1.5rem 1.75rem;
	margin-bottom: 1.25rem;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.donut-wrap {
	display: flex;
	justify-content: center;
}
.donut {
	width: 180px;
	height: 180px;
	transform: rotate(-90deg);
}
.donut-bg {
	fill: none;
	stroke: #eef2f7;
	stroke-width: 16;
}
.donut-seg {
	fill: none;
	stroke-width: 16;
	stroke-linecap: round;
	transition: stroke-dasharray 0.6s ease;
}
.donut-seg--external { stroke: #f97316; }
.donut-seg--intel { stroke: #2563eb; }
.donut-num {
	fill: #0f172a;
	font-size: 26px;
	font-weight: 800;
	text-anchor: middle;
	transform: rotate(90deg);
	transform-origin: 70px 70px;
}
.donut-cap {
	fill: #94a3b8;
	font-size: 10px;
	font-weight: 600;
	text-anchor: middle;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	transform: rotate(90deg);
	transform-origin: 70px 70px;
}
.overview-legend {
	display: flex;
	flex-direction: column;
	gap: 0.75rem;
	min-width: 0;
}
.legend-item {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding: 0.75rem 1rem;
	border: 1px solid #eef2f7;
	border-radius: 12px;
	background: #f8fafc;
}
.legend-block {
	display: flex;
	flex-direction: column;
	gap: 0.5rem;
}
.legend-item--btn {
	width: 100%;
	cursor: pointer;
	text-align: left;
	font: inherit;
	transition: border-color 0.15s, background 0.15s;
}
.legend-item--btn:hover { background: #f1f5f9; border-color: #dbe4ef; }
.legend-item--open { border-color: #c7d2fe; background: #fff; }
.legend-caret {
	flex-shrink: 0;
	color: #94a3b8;
	transition: transform 0.2s ease;
}
.legend-item--open .legend-caret { transform: rotate(180deg); }
.legend-people {
	display: flex;
	flex-wrap: wrap;
	gap: 0.4rem;
	padding: 0.25rem 0.25rem 0.5rem;
}
.legend-people-empty {
	font-size: 0.78rem;
	color: #94a3b8;
	padding: 0.25rem;
}
.people-pill {
	display: inline-flex;
	align-items: center;
	gap: 0.25rem;
	padding: 0.15rem 0.3rem 0.15rem 0.15rem;
	border-radius: 999px;
	border: 1px solid #e2e8f0;
	background: #fff;
	transition: background 0.15s, border-color 0.15s;
}
.people-pill:hover { border-color: #bfdbfe; }
.people-pill--active {
	border-color: #2563eb;
	background: #eff6ff;
	box-shadow: 0 0 0 2px rgba(37,99,235,0.15);
}
.people-pill-select {
	display: inline-flex;
	align-items: center;
	gap: 0.4rem;
	padding: 0.18rem 0.4rem;
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
.people-pill-count {
	font-size: 0.7rem;
	font-weight: 800;
	color: #64748b;
	background: #f1f5f9;
	border-radius: 999px;
	padding: 0.05rem 0.4rem;
}
.people-pill-hf {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	width: 22px;
	height: 22px;
	border-radius: 50%;
	color: #94a3b8;
	flex-shrink: 0;
	transition: background 0.15s, color 0.15s;
}
.people-pill-hf:hover { background: #f1f5f9; color: #2563eb; }

/* Filter banner */
.filter-banner {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 0.75rem;
	padding: 0.7rem 1.1rem;
	margin-bottom: 1.25rem;
	border: 1px solid #c7d2fe;
	border-radius: 12px;
	background: #eff6ff;
}
.filter-banner-text {
	font-size: 0.85rem;
	color: #1e3a8a;
}
.filter-banner-text strong { font-weight: 800; }
.filter-banner-clear {
	display: inline-flex;
	align-items: center;
	gap: 0.35rem;
	padding: 0.35rem 0.75rem;
	border: 1px solid #c7d2fe;
	border-radius: 999px;
	background: #fff;
	font-size: 0.78rem;
	font-weight: 700;
	color: #1d4ed8;
	cursor: pointer;
	transition: background 0.15s;
}
.filter-banner-clear:hover { background: #dbeafe; }
.legend-dot {
	width: 12px;
	height: 12px;
	border-radius: 50%;
	flex-shrink: 0;
}
.legend-dot--intel { background: #2563eb; }
.legend-dot--external { background: #f97316; }
.legend-text {
	display: flex;
	flex-direction: column;
	min-width: 0;
	flex: 1;
}
.legend-name {
	font-weight: 700;
	font-size: 0.875rem;
	color: #0f172a;
}
.legend-meta {
	font-size: 0.75rem;
	color: #94a3b8;
}
.legend-val {
	display: flex;
	flex-direction: column;
	align-items: flex-end;
	flex-shrink: 0;
}
.legend-val strong {
	font-size: 1.25rem;
	font-weight: 800;
	color: #0f172a;
	line-height: 1;
}
.legend-val span {
	font-size: 0.75rem;
	color: #64748b;
}
.rule-note {
	margin: 0.25rem 0 0;
	font-size: 0.75rem;
	color: #94a3b8;
	line-height: 1.5;
}
.rule-note code {
	background: #eef2f7;
	color: #475569;
	padding: 0.05rem 0.3rem;
	border-radius: 4px;
	font-size: 0.72rem;
}

/* Panels */
.panel-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 1.25rem;
}
.panel {
	background: #fff;
	border-radius: 16px;
	box-shadow: 0 1px 4px rgba(0,0,0,0.06);
	overflow: hidden;
}
.panel-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 1.1rem 1.4rem;
	border-bottom: 1px solid #eef2f7;
}
.panel-header h2 {
	margin: 0;
	font-size: 1rem;
	color: #0f172a;
}
.panel-count {
	font-size: 0.75rem;
	font-weight: 700;
	color: #64748b;
	background: #f1f5f9;
	padding: 0.2rem 0.6rem;
	border-radius: 999px;
}
.rank-list {
	display: flex;
	flex-direction: column;
}
.rank-row {
	display: flex;
	align-items: flex-start;
	gap: 0.85rem;
	padding: 0.85rem 1.4rem;
	border-bottom: 1px solid #f4f7fb;
}
.rank-row:last-child { border-bottom: none; }
.rank-row:hover { background: #f8fafc; }
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
	letter-spacing: 0.02em;
	margin-top: 0.1rem;
}
.avatar--intel { background: linear-gradient(135deg, #2563eb, #60a5fa); }
.avatar--external { background: linear-gradient(135deg, #f97316, #fb923c); }
.avatar--company { background: linear-gradient(135deg, #0f766e, #14b8a6); }
.rank-body {
	flex: 1;
	min-width: 0;
}
.rank-top {
	display: flex;
	align-items: center;
	gap: 0.5rem;
	margin-bottom: 0.4rem;
}
.rank-name {
	font-weight: 700;
	font-size: 0.875rem;
	color: #0f172a;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
	min-width: 0;
}
.rank-name--link {
	color: #1d4ed8;
	text-decoration: none;
}
.rank-name--link:hover { text-decoration: underline; }
.rank-row--expandable {
	flex-direction: column;
	align-items: stretch;
	gap: 0;
	padding: 0;
}
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
}
.rank-toggle:hover { background: #f8fafc; }
.rank-caret {
	flex-shrink: 0;
	margin-left: 0.4rem;
	color: #94a3b8;
	transition: transform 0.2s ease;
}
.rank-caret--open { transform: rotate(180deg); }
.model-list {
	list-style: none;
	margin: 0;
	padding: 0 1.4rem 0.85rem 4.25rem;
	display: flex;
	flex-direction: column;
	gap: 0.35rem;
}
.model-item { min-width: 0; }
.model-link {
	display: inline-block;
	max-width: 100%;
	font-size: 0.8rem;
	color: #1d4ed8;
	text-decoration: none;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}
.model-link:hover { text-decoration: underline; }
.chip {
	flex-shrink: 0;
	padding: 0.12rem 0.5rem;
	border-radius: 999px;
	font-size: 0.65rem;
	font-weight: 800;
	white-space: nowrap;
}
.chip--intel { background: #dbeafe; color: #1d4ed8; }
.chip--external { background: #ffedd5; color: #c2410c; }
.chip--muted { background: #f1f5f9; color: #64748b; }
.rank-count {
	margin-left: auto;
	flex-shrink: 0;
	font-size: 1rem;
	font-weight: 800;
	color: #0f172a;
	font-variant-numeric: tabular-nums;
}
.track {
	height: 8px;
	background: #eef2f7;
	border-radius: 999px;
	overflow: hidden;
}
.fill {
	height: 100%;
	border-radius: 999px;
	transition: width 0.5s ease;
}
.fill--intel { background: linear-gradient(90deg, #2563eb, #60a5fa); }
.fill--external { background: linear-gradient(90deg, #f97316, #fdba74); }
.fill--company { background: linear-gradient(90deg, #0f766e, #2dd4bf); }
.rank-sub {
	display: block;
	margin-top: 0.35rem;
	font-size: 0.72rem;
	color: #94a3b8;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

/* States */
.empty-state,
.loading-state,
.error-banner {
	padding: 2.5rem 1.5rem;
	text-align: center;
	color: #64748b;
	font-size: 0.875rem;
}
.loading-state {
	display: flex;
	justify-content: center;
	align-items: center;
	gap: 0.75rem;
}
.error-banner {
	margin-bottom: 1rem;
	padding: 1rem 1.5rem;
	border: 1px solid #fecaca;
	border-radius: 12px;
	background: #fef2f2;
	color: #991b1b;
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

@media (max-width: 1100px) {
	.panel-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
	.hero-wrap { padding: 1rem 1.25rem 0; }
	.hero { flex-direction: column; align-items: stretch; padding: 1.5rem 1.25rem; }
	.hero-metrics { flex-direction: row; }
	.hero-metrics div { flex: 1; min-width: 0; }
	.content { padding: 1.25rem 1.25rem 2rem; }
	.toolbar { flex-direction: column; align-items: stretch; }
	.overview-card { grid-template-columns: 1fr; justify-items: center; }
	.overview-legend { width: 100%; }
}
</style>