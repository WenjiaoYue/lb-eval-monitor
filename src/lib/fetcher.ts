/**
 * Client-side fetcher: pulls data directly from GitHub API on page load.
 * Replaces pre-generated static JSON approach.
 */
import type { RunRecord, SummaryData, RunStatus, PipelineStatus, PipelineInfo, QuantDetails, EvalDetails } from './types';

const REPO = 'XuehaoSun/lb_eval';
const BRANCH = 'main';
const RAW_BASE = `https://raw.githubusercontent.com/${REPO}/${BRANCH}`;
const API_BASE = `https://api.github.com/repos/${REPO}`;

// Patterns for files we need from the results/ tree
const NEEDED_FILE_RE = /(?:^|\/)(?:quant_summary\.json|accuracy\.json|session_eval_.*\.md|session_quant_.*\.md)$/;
// Aggregate results at model level (NOT inside lm_eval_results/)
const AGGREGATE_RE = /^results\/[^/]+\/[^/]+\/results_[^/]+\.json$/;

// Lifecycle directories
const LIFECYCLE_PREFIXES = ['status/', 'requests/', 'pending_requests/'];

interface TreeEntry {
	path: string;
	type: string;
}

interface FileGroup {
	runDir: string; // e.g. "results/Qwen/Qwen3-0.6B-autoround-W4A16/run_2026-..."
	files: string[];
}

// ─── Helpers ────────────────────────────────────────────────────────────────

async function fetchRaw(path: string): Promise<string | null> {
	try {
		const resp = await fetch(`${RAW_BASE}/${path}`);
		if (!resp.ok) return null;
		return await resp.text();
	} catch {
		return null;
	}
}

async function fetchJson(path: string): Promise<any | null> {
	const text = await fetchRaw(path);
	if (!text) return null;
	try { return JSON.parse(text); } catch { return null; }
}

function normalizeStatus(value: any): RunStatus {
	if (value == null) return 'unknown';
	const text = String(value).trim().toLowerCase();
	if (!text) return 'unknown';
	if (['fail', 'error', 'exception', 'traceback'].some(t => text.includes(t))) return 'failed';
	if (['success', 'succeed', 'pass', 'done', 'complete'].some(t => text.includes(t))) return 'success';
	if (['running', 'pending', 'progress', 'started', 'queue'].some(t => text.includes(t))) return 'running';
	return 'unknown';
}

function normalizePipelineStatus(raw: string | null | undefined): PipelineStatus {
	if (!raw) return 'pending';
	const text = raw.trim().toLowerCase();
	if (text === 'finished') return 'succeeded';
	if (text.includes('fail')) return 'failed';
	if (text === 'pending' || text === 'queued') return 'pending';
	if (text === 'running' || text === 'started') return 'running';
	if (text.includes('cancel')) return 'cancelled';
	return 'unknown';
}

function firstNonempty(...values: any[]): any {
	for (const v of values) {
		if (v != null && v !== '' && !(Array.isArray(v) && v.length === 0)) return v;
	}
	return null;
}

function parseRunTimestamp(runId: string | null): string {
	const m = (runId || '').match(/run_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})/);
	if (m) return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`;
	return new Date().toISOString().replace(/\.\d+Z$/, 'Z');
}

function extractErrors(raw: any): string[] {
	const errors: string[] = [];
	if (Array.isArray(raw)) {
		for (const item of raw) {
			if (typeof item === 'string') errors.push(item.trim());
			else if (item && typeof item === 'object') {
				const text = item.message || item.error || item.detail;
				if (text) errors.push(String(text).trim());
			}
		}
	} else if (raw && typeof raw === 'object') {
		const text = raw.message || raw.error || raw.detail;
		if (text) errors.push(String(text).trim());
	} else if (typeof raw === 'string') {
		errors.push(raw.trim());
	}
	return [...new Set(errors.filter(Boolean))];
}

function extractQuantDetails(data: any): QuantDetails | null {
	if (!data || typeof data !== 'object') return null;
	const details: any = {};
	for (const key of ['original_size_mb', 'quantized_size_mb', 'compression_ratio',
		'duration_seconds', 'hf_repo', 'export_format', 'device',
		'model_id', 'output_dir', 'quantized_model_dir']) {
		if (data[key] != null && data[key] !== '') details[key] = data[key];
	}
	return Object.keys(details).length > 0 ? details : null;
}

function extractEvalDetails(data: any): EvalDetails | null {
	if (!data || typeof data !== 'object') return null;
	const details: any = {};
	if (data.duration_seconds != null) details.duration_seconds = Number(data.duration_seconds) || data.duration_seconds;
	if (data.eval_framework) details.eval_framework = data.eval_framework;
	const rawTasks = data.tasks;
	if (rawTasks && typeof rawTasks === 'object' && !Array.isArray(rawTasks)) {
		details.task_results = rawTasks;
	}
	return Object.keys(details).length > 0 ? details : null;
}

const COMMON_TASKS = ['piqa', 'mmlu', 'hellaswag'];

function metricsPreview(data: any): Record<string, number | string> {
	if (!data || typeof data !== 'object') return {};
	const preview: Record<string, number | string> = {};
	const candidates = [data.results, data.tasks, data].filter(c => c && typeof c === 'object');
	for (const blob of candidates) {
		for (const task of COMMON_TASKS) {
			if (task in preview) continue;
			const tp = blob[task];
			if (tp && typeof tp === 'object') {
				for (const key of ['accuracy', 'acc_norm,none', 'acc,none', 'acc', 'score', 'exact_match']) {
					if (key in tp) { preview[task] = tp[key]; break; }
				}
			} else if (tp != null && tp !== '') {
				preview[task] = tp;
			}
		}
	}
	return preview;
}

function buildFileUrl(relPath: string | null): string | null {
	if (!relPath) return null;
	return `https://github.com/${REPO}/blob/${BRANCH}/${relPath}`;
}

function modelKeyFromStatus(data: any): string {
	const model = data.model || '';
	let scheme = data.quant_scheme || '';
	const m = scheme.match(/\((\w+)\)/);
	if (m) scheme = m[1];
	return `${model}::${scheme}`;
}

function modelKeyFromRecord(record: RunRecord): string {
	const owner = record.owner;
	let modelId = record.model_id;
	const scheme = record.scheme;
	if (modelId.includes('/')) {
		return `${modelId}::${scheme}`;
	}
	let baseModel = modelId;
	for (const suffix of [`-autoround-${scheme}`, `-gptq-${scheme}`, `-awq-${scheme}`, `-${scheme}`, `_${scheme}`]) {
		if (baseModel.endsWith(suffix)) {
			baseModel = baseModel.slice(0, -suffix.length);
			break;
		}
	}
	return `${owner}/${baseModel}::${scheme}`;
}

function extractPipelineInfo(data: any): PipelineInfo | null {
	if (!data) return null;
	const info: any = {};
	if (data.status) info.status = normalizePipelineStatus(data.status);
	for (const field of ['submitted_time', 'triggered_time', 'ci_run_id', 'job_type',
		'quant_scheme', 'hardware', 'gpu_nums', 'model_weight_gb', 'quant_model_size_gb', 'params']) {
		if (data[field] != null && data[field] !== '' && data[field] !== -1) info[field] = data[field];
	}
	return Object.keys(info).length > 0 ? info : null;
}

// ─── Batch download with concurrency limit ──────────────────────────────────

async function batchFetchJson(paths: string[], concurrency = 6): Promise<Map<string, any>> {
	const results = new Map<string, any>();
	const queue = [...paths];
	const workers = Array.from({ length: concurrency }, async () => {
		while (queue.length > 0) {
			const path = queue.shift()!;
			const data = await fetchJson(path);
			if (data != null) results.set(path, data);
		}
	});
	await Promise.all(workers);
	return results;
}

// ─── Main fetch logic ───────────────────────────────────────────────────────

export interface FetchResult {
	runs: RunRecord[];
	latest: RunRecord[];
	summary: SummaryData;
}

export async function fetchFromGitHub(onProgress?: (msg: string) => void): Promise<FetchResult> {
	const progress = onProgress || (() => {});

	// 1. Fetch repo tree
	progress('Fetching repository tree...');
	const treeResp = await fetch(`${API_BASE}/git/trees/${BRANCH}?recursive=1`);
	if (!treeResp.ok) throw new Error(`GitHub API error: ${treeResp.status}`);
	const treeData = await treeResp.json();
	const entries: TreeEntry[] = treeData.tree || [];

	// 2. Categorize files
	const runFiles: string[] = [];          // quant_summary.json, accuracy.json, session files
	const aggregateFiles: string[] = [];    // results_*.json at model level
	const lifecycleFiles: string[] = [];    // status/, requests/, pending_requests/
	const runDirs = new Set<string>();

	for (const entry of entries) {
		if (entry.type !== 'blob') continue;

		// Lifecycle files
		if (LIFECYCLE_PREFIXES.some(p => entry.path.startsWith(p)) && entry.path.endsWith('.json')) {
			lifecycleFiles.push(entry.path);
			continue;
		}

		// Skip lm_eval_results files entirely
		if (entry.path.includes('lm_eval_results')) continue;

		if (!entry.path.startsWith('results/')) continue;

		// Run-level files
		if (NEEDED_FILE_RE.test(entry.path)) {
			runFiles.push(entry.path);
			// Extract run dir path
			const runMatch = entry.path.match(/^(results\/[^/]+\/[^/]+\/run_[^/]+)\//);
			if (runMatch) runDirs.add(runMatch[1]);
		}
		// Aggregate results
		else if (AGGREGATE_RE.test(entry.path)) {
			aggregateFiles.push(entry.path);
		}
	}

	// Also find run dirs from tree entries
	for (const entry of entries) {
		if (entry.type === 'tree' && /^results\/[^/]+\/[^/]+\/run_\d{4}-\d{2}-\d{2}[^/]*$/.test(entry.path)) {
			runDirs.add(entry.path);
		}
	}

	progress(`Downloading ${runFiles.length + aggregateFiles.length + lifecycleFiles.length} files...`);

	// 3. Download all needed files in parallel
	const allPaths = [...runFiles, ...aggregateFiles, ...lifecycleFiles];
	const fileData = await batchFetchJson(allPaths, 8);

	// 4. Build lifecycle index
	progress('Processing lifecycle data...');
	const lifecycleIndex = new Map<string, any>();
	// Load in priority order (lowest first)
	for (const prefix of ['requests/', 'pending_requests/', 'status/']) {
		for (const path of lifecycleFiles.filter(p => p.startsWith(prefix))) {
			const data = fileData.get(path);
			if (!data || typeof data !== 'object') continue;
			const key = modelKeyFromStatus(data);
			if (!key.includes('::')) continue;
			const existing = lifecycleIndex.get(key) || {};
			lifecycleIndex.set(key, { ...existing, ...data, _lifecycle_dir: prefix.replace('/', '') });
		}
	}

	// 5. Build aggregate index
	const aggregateIndex = new Map<string, any>();
	for (const path of aggregateFiles) {
		const data = fileData.get(path);
		if (!data) continue;
		// Walk to find records
		const walk = (node: any) => {
			if (!node) return;
			if (typeof node === 'object' && !Array.isArray(node)) {
				if (node.run_id || node.run_path || node.model_id || node.auto_quant_status) {
					const key = String(node.run_path || node.run_id || '').trim();
					if (key) aggregateIndex.set(key, node);
				}
				for (const v of Object.values(node)) walk(v);
			} else if (Array.isArray(node)) {
				for (const v of node) walk(v);
			}
		};
		walk(data);
	}

	// 6. Build run records
	progress('Building run records...');
	const records: RunRecord[] = [];
	const matchedLifecycleKeys = new Set<string>();

	for (const runDir of runDirs) {
		const relPath = runDir.replace('results/', '');
		const parts = relPath.split('/');
		const owner = parts[0] || 'unknown';
		const artifactName = parts[1] || 'unknown';
		const runId = parts[2] || '';

		const quantData = fileData.get(`${runDir}/quant_summary.json`);
		const accuracyData = fileData.get(`${runDir}/accuracy.json`);

		const aggregate = aggregateIndex.get(relPath) || aggregateIndex.get(runId) || {};

		const quantStatus = normalizeStatus(
			firstNonempty(quantData?.status, aggregate.auto_quant_status)
		);
		const evalStatus = normalizeStatus(
			firstNonempty(accuracyData?.status, aggregate.auto_eval_status)
		);

		const quantErrors = extractErrors(quantData?.errors);
		const evalErrors = extractErrors(accuracyData?.errors);
		const issues = [...new Set([...quantErrors, ...evalErrors])];

		const tasks: string[] = [];
		if (accuracyData?.tasks && typeof accuracyData.tasks === 'object' && !Array.isArray(accuracyData.tasks)) {
			tasks.push(...Object.keys(accuracyData.tasks));
		} else if (Array.isArray(accuracyData?.tasks)) {
			tasks.push(...accuracyData.tasks.map(String));
		} else if (accuracyData?.results && typeof accuracyData.results === 'object') {
			tasks.push(...Object.keys(accuracyData.results));
		}

		const record: RunRecord = {
			owner,
			artifact_name: artifactName,
			model_id: firstNonempty(aggregate.model_id, quantData?.model_id, artifactName) || artifactName,
			scheme: firstNonempty(quantData?.scheme, aggregate.scheme, 'unknown') || 'unknown',
			method: firstNonempty(quantData?.method, aggregate.method, 'unknown') || 'unknown',
			run_id: runId,
			run_timestamp: parseRunTimestamp(runId),
			run_path: relPath,
			auto_quant_status: quantStatus,
			auto_eval_status: evalStatus,
			quant_errors: quantErrors,
			eval_errors: evalErrors,
			issues,
			summary: String(firstNonempty(aggregate.summary, '') || ''),
			tasks,
			metrics_preview: metricsPreview(accuracyData),
			quant_num_gpus: firstNonempty(quantData?.num_gpus, quantData?.gpus, aggregate.quant_num_gpus),
			eval_num_gpus: firstNonempty(accuracyData?.num_gpus, aggregate.eval_num_gpus),
			quant_details: extractQuantDetails(quantData),
			eval_details: extractEvalDetails(accuracyData),
			pipeline: null,
			session_eval_url: null,
			session_quant_url: null,
			aggregate_result_url: null,
			updated_at: parseRunTimestamp(runId),
		};

		// Session URLs
		const sessionEvalFile = runFiles.find(f => f.startsWith(`${runDir}/session_eval_`));
		const sessionQuantFile = runFiles.find(f => f.startsWith(`${runDir}/session_quant_`));
		if (sessionEvalFile) record.session_eval_url = buildFileUrl(sessionEvalFile);
		if (sessionQuantFile) record.session_quant_url = buildFileUrl(sessionQuantFile);

		// Match lifecycle
		const lcKey = modelKeyFromRecord(record);
		const lcData = lifecycleIndex.get(lcKey);
		if (lcData) {
			record.pipeline = extractPipelineInfo(lcData);
			matchedLifecycleKeys.add(lcKey);
		}

		records.push(record);
	}

	// 7. Add pending jobs from lifecycle that don't have results
	for (const [key, data] of lifecycleIndex) {
		if (matchedLifecycleKeys.has(key)) continue;
		const normStatus = normalizePipelineStatus(data.status);
		if (normStatus === 'succeeded') continue;

		const model = data.model || '';
		const parts = model.split('/');
		const owner = parts.length > 1 ? parts[0] : 'unknown';
		const baseModel = parts.length > 1 ? parts[1] : model;
		let scheme = data.quant_scheme || 'unknown';
		const sm = scheme.match(/\((\w+)\)/);
		if (sm) scheme = sm[1];

		const submitted = data.submitted_time || '';
		const triggered = data.triggered_time || '';

		let quantStatus: RunStatus = 'unknown';
		let evalStatus: RunStatus = 'unknown';
		if (normStatus === 'pending' || normStatus === 'running') quantStatus = 'running';
		if (normStatus === 'failed') evalStatus = 'failed';

		records.push({
			owner,
			artifact_name: `${baseModel}-${scheme}`,
			model_id: baseModel,
			scheme,
			method: 'unknown',
			run_id: '',
			run_timestamp: submitted || new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
			run_path: '',
			auto_quant_status: quantStatus,
			auto_eval_status: evalStatus,
			quant_errors: [],
			eval_errors: [],
			issues: [],
			summary: '',
			tasks: [],
			metrics_preview: {},
			quant_num_gpus: data.gpu_nums,
			eval_num_gpus: data.gpu_nums,
			quant_details: null,
			eval_details: null,
			pipeline: extractPipelineInfo(data),
			session_eval_url: null,
			session_quant_url: null,
			aggregate_result_url: null,
			updated_at: triggered || submitted || '',
		});
	}

	// 8. Sort and build summary
	records.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));

	const latest = buildLatest(records);
	const summary = buildSummary(records, latest);

	return { runs: records, latest, summary };
}

function buildLatest(records: RunRecord[]): RunRecord[] {
	const byKey = new Map<string, RunRecord>();
	for (const r of records) {
		const key = `${r.owner}::${r.artifact_name}`;
		const existing = byKey.get(key);
		if (!existing || (r.run_timestamp || '') > (existing.run_timestamp || '')) {
			byKey.set(key, r);
		}
	}
	return [...byKey.values()].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
}

function buildSummary(records: RunRecord[], latest: RunRecord[]): SummaryData {
	const quant: Record<RunStatus, number> = { success: 0, failed: 0, running: 0, unknown: 0 };
	const eval_: Record<RunStatus, number> = { success: 0, failed: 0, running: 0, unknown: 0 };
	const pipeline: Record<PipelineStatus, number> = { pending: 0, running: 0, succeeded: 0, failed: 0, cancelled: 0, unknown: 0 };

	for (const r of records) {
		quant[r.auto_quant_status]++;
		eval_[r.auto_eval_status]++;
		const ps = (r.pipeline?.status || 'unknown') as PipelineStatus;
		pipeline[ps]++;
	}

	return {
		generated_at: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
		total_runs: records.length,
		latest_models_count: latest.length,
		quant,
		eval: eval_,
		pipeline,
	};
}
