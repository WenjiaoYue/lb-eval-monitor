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
const NEEDED_FILE_RE = /(?:^|\/)(?:quant_summary\.json|accuracy\.json|session_.*\.md)$/;
// Aggregate results at model level (NOT inside lm_eval_results/)
const AGGREGATE_RE = /^results\/[^/]+\/[^/]+\/results_[^/]+\.json$/;

const QUANTIZE_LOG_RE = /(?:^|\/)logs\/quantize\.log$/;
const SETUP_ENV_LOG_RE = /(?:^|\/)logs\/setup_env\.log$/;
const STATUS_JOB_TYPE = 'quantization & evaluation';

interface TreeEntry {
	path: string;
	type: string;
}

interface FileGroup {
	runDir: string; // e.g. "results/Qwen/Qwen3-0.6B-autoround-W4A16/run_2026-..."
	files: string[];
}

interface StatusIdentity {
	owner: string;
	modelName: string;
	scheme: string;
	method: string;
	statusTime: string | null;
}

interface ResultRunDir {
	runDir: string;
	owner: string;
	artifactName: string;
	runId: string;
	runTime: string;
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

async function fetchStaticJson<T>(path: string): Promise<T> {
	const resp = await fetch(path);
	if (!resp.ok) throw new Error(`Static data error: ${resp.status}`);
	return await resp.json() as T;
}

async function fetchStaticSnapshot(): Promise<FetchResult> {
	const [runs, latest, summary] = await Promise.all([
		fetchStaticJson<RunRecord[]>('/data/runs.json'),
		fetchStaticJson<RunRecord[]>('/data/latest.json'),
		fetchStaticJson<SummaryData>('/data/summary.json'),
	]);
	return { runs, latest, summary };
}

function normalizeKey(value: string | null | undefined): string {
	return String(value || '').trim().toLowerCase();
}

function normalizeScheme(value: string | null | undefined): string {
	const text = String(value || '').trim();
	if (!text) return '';
	const paren = text.match(/\(([^)]+)\)/);
	return paren ? paren[1] : text;
}

function normalizeStatus(value: any): RunStatus {
	if (value == null) return 'running';
	const text = String(value).trim().toLowerCase();
	if (!text) return 'running';
	if (['fail', 'error', 'exception', 'traceback'].some(t => text.includes(t))) return 'failed';
	if (['success', 'succeed', 'pass', 'done', 'complete'].some(t => text.includes(t))) return 'success';
	if (['running', 'pending', 'progress', 'started', 'queue'].some(t => text.includes(t))) return 'running';
	return 'running';
}

function normalizePipelineStatus(raw: string | null | undefined): PipelineStatus {
	if (!raw) return 'pending';
	const text = raw.trim().toLowerCase();
	if (text === 'finished') return 'succeeded';
	if (text.includes('fail')) return 'failed';
	if (text === 'pending' || text === 'queued') return 'pending';
	if (text === 'running' || text === 'started') return 'running';
	if (text.includes('cancel')) return 'cancelled';
	return 'pending';
}

function firstNonempty(...values: any[]): any {
	for (const v of values) {
		if (v != null && v !== '' && !(Array.isArray(v) && v.length === 0)) return v;
	}
	return null;
}

function extractOrgList(...values: any[]): string[] {
	const orgs: string[] = [];
	const add = (value: any) => {
		if (Array.isArray(value)) {
			for (const item of value) add(item);
			return;
		}
		if (value != null && value !== '') orgs.push(String(value));
	};
	for (const value of values) add(value);
	return [...new Set(orgs.map((org) => org.trim()).filter(Boolean))];
}

function parseRunTimestamp(runId: string | null): string {
	const m = (runId || '').match(/run_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})/);
	if (m) return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`;
	return new Date().toISOString().replace(/\.\d+Z$/, 'Z');
}

function timeTokenToRunId(value: string | null): string | null {
	const m = (value || '').match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
	if (!m) return null;
	return `run_${m[1]}-${m[2]}-${m[3]}-${m[4]}-${m[5]}-${m[6]}`;
}

function isoToComparable(value: string | null | undefined): string {
	if (!value) return '';
	const d = new Date(value);
	if (Number.isNaN(d.getTime())) return '';
	return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
}

function runIdToComparable(runId: string): string {
	const m = runId.match(/^run_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})$/);
	if (!m) return '';
	return `${m[1]}${m[2]}${m[3]}T${m[4]}${m[5]}${m[6]}Z`;
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

function parseStatusIdentity(path: string, data: any): StatusIdentity | null {
	const parts = path.split('/');
	if (parts.length < 3 || parts[0] !== 'status') return null;
	const pathOwner = parts[1] || '';
	const filename = parts.slice(2).join('/').replace(/\.json$/, '');
	const marker = '_quant_request_False_';
	const markerAt = filename.indexOf(marker);
	if (markerAt < 0) return null;

	const model = String(data?.model || '');
	const modelParts = model.split('/');
	const owner = modelParts.length > 1 ? modelParts[0] : pathOwner;
	const modelName = modelParts.length > 1 ? modelParts.slice(1).join('/') : filename.slice(0, markerAt);
	const tokens = filename.slice(markerAt + marker.length).split('_').filter(Boolean);
	const scheme = normalizeScheme(firstNonempty(data?.quant_scheme, tokens[0], ''));
	let method = '';
	let statusTime: string | null = null;
	for (const token of tokens.slice(3)) {
		if (/^\d{8}T\d{6}Z$/.test(token)) statusTime = token;
		else method = token;
	}

	return {
		owner,
		modelName,
		scheme,
		method: method || 'RTN',
		statusTime,
	};
}

function aggregatePathToRunDir(path: string): string | null {
	const match = path.match(/^(results\/[^/]+\/[^/]+)\/results_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})\.json$/);
	if (!match) return null;
	return `${match[1]}/run_${match[2]}-${match[3]}-${match[4]}-${match[5]}-${match[6]}-${match[7]}`;
}

function extractPathList(...values: any[]): string[] {
	const paths: string[] = [];
	const add = (value: any) => {
		if (Array.isArray(value)) {
			for (const item of value) add(item);
			return;
		}
		if (typeof value === 'string' && value.trim()) paths.push(value.trim());
	};
	for (const value of values) add(value);
	return [...new Set(paths)];
}

function runFileCandidates(resultRun: ResultRunDir, runFiles: string[], aggregate: any): string[] {
	return [...new Set([...runFiles, ...extractPathList(aggregate?.copied_files, aggregate?.output_files)])]
		.filter((path) => path.startsWith(resultRun.runDir) || path.includes(`/${resultRun.runId}/`));
}

function findSessionFile(resultRun: ResultRunDir, runFiles: string[], aggregate: any, kind: 'eval' | 'quant'): string | undefined {
	const kindRe = kind === 'eval'
		? /\/session_eval_.*\.md$/
		: /(?:\/logs\/(?:setup_env|quantize)\.log$|\/session_(?:quant|fix_quantize|fix_setup_env)_.*\.md$)/;
	return runFileCandidates(resultRun, runFiles, aggregate).find((path) => kindRe.test(path));
}

function resultRunFromDir(runDir: string): ResultRunDir | null {
	const relPath = runDir.replace('results/', '');
	const parts = relPath.split('/');
	if (parts.length < 3) return null;
	return {
		runDir,
		owner: parts[0] || '',
		artifactName: parts[1] || '',
		runId: parts[2] || '',
		runTime: runIdToComparable(parts[2] || ''),
	};
}

function artifactMatchesStatus(run: ResultRunDir, identity: StatusIdentity): boolean {
	if (normalizeKey(run.owner) !== normalizeKey(identity.owner)) return false;
	const artifact = run.artifactName.toLowerCase();
	const prefix = `${identity.modelName}-autoround-${identity.scheme}`.toLowerCase();
	if (!artifact.startsWith(prefix)) return false;
	const remainder = artifact.slice(prefix.length).replace(/^-/, '');
	const method = identity.method.toLowerCase();
	if (method === 'rtn') return remainder === '' || remainder === 'rtn';
	return remainder === method;
}

function findResultRun(identity: StatusIdentity, data: any, resultRunDirs: ResultRunDir[]): ResultRunDir | null {
	const candidates = resultRunDirs.filter((run) => artifactMatchesStatus(run, identity));
	if (candidates.length === 0) return null;
	const exactRunId = timeTokenToRunId(identity.statusTime);
	if (exactRunId) {
		const exact = candidates.find((run) => run.runId === exactRunId);
		if (exact) return exact;
	}
	const targetTime = identity.statusTime || isoToComparable(data?.submitted_time) || isoToComparable(data?.triggered_time);
	if (targetTime) {
		const afterTarget = candidates.filter((run) => run.runTime >= targetTime).sort((a, b) => a.runTime.localeCompare(b.runTime));
		if (afterTarget[0]) return afterTarget[0];
	}
	return [...candidates].sort((a, b) => b.runId.localeCompare(a.runId))[0];
}

function modelKeyFromStatus(data: any): string {
	const model = data.model || '';
	const scheme = normalizeScheme(data.quant_scheme || '');
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

function pipelineStatusToQuantStatus(status: PipelineStatus): RunStatus {
	if (status === 'succeeded') return 'success';
	if (status === 'failed') return 'failed';
	return 'running';
}

function buildStatusOnlyRecord(identity: StatusIdentity, data: any, pipelineStatus: PipelineStatus): RunRecord {
	const quantStatus = pipelineStatusToQuantStatus(pipelineStatus);
	const submitted = data?.submitted_time || '';
	const triggered = data?.triggered_time || '';
	return {
		owner: identity.owner,
		artifact_name: `${identity.modelName}-AutoRound-${identity.scheme}${identity.method ? `-${identity.method}` : ''}`,
		model_id: String(data?.model || `${identity.owner}/${identity.modelName}`),
		submitted_by: firstNonempty(data?.submitted_by),
		orgs: extractOrgList(data?.orgs, data?.org, data?.organizations),
		scheme: identity.scheme,
		method: identity.method,
		run_id: '',
		run_timestamp: submitted || new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
		run_path: '',
		auto_quant_status: quantStatus,
		quant_errors: [],
		eval_errors: [],
		issues: [],
		summary: '',
		tasks: [],
		metrics_preview: {},
		quant_num_gpus: firstNonempty(data?.quant_gpu_nums, data?.gpu_nums),
		eval_num_gpus: firstNonempty(data?.eval_gpu_nums, data?.gpu_nums),
		quant_details: null,
		eval_details: null,
		pipeline: extractPipelineInfo(data),
		session_eval_url: null,
		session_quant_url: null,
		aggregate_result_url: null,
		updated_at: triggered || submitted || '',
	};
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

async function batchFetchText(paths: string[], concurrency = 6): Promise<Map<string, string>> {
	const results = new Map<string, string>();
	const queue = [...paths];
	const workers = Array.from({ length: concurrency }, async () => {
		while (queue.length > 0) {
			const path = queue.shift()!;
			const text = await fetchRaw(path);
			if (text != null) results.set(path, text);
		}
	});
	await Promise.all(workers);
	return results;
}

function buildResultRecord(
	identity: StatusIdentity,
	data: any,
	resultRun: ResultRunDir,
	fileData: Map<string, any>,
	textData: Map<string, string>,
	runFiles: string[],
	availableFiles: string[],
	aggregateIndex: Map<string, any>,
	pipelineStatus: PipelineStatus
): RunRecord {
	const relPath = resultRun.runDir.replace('results/', '');
	const quantData = fileData.get(`${resultRun.runDir}/quant_summary.json`);
	const accuracyData = fileData.get(`${resultRun.runDir}/accuracy.json`);
	const aggregate = aggregateIndex.get(relPath) || aggregateIndex.get(resultRun.runId) || {};
	const fallbackQuantStatus = pipelineStatusToQuantStatus(pipelineStatus);
	const quantStatus = pipelineStatus === 'failed'
		? 'failed'
		: normalizeStatus(firstNonempty(quantData?.status, aggregate.auto_quant_status, fallbackQuantStatus));
	const failureSessionQuantFile = findSessionFile(resultRun, availableFiles, aggregate, 'quant');
	const failureLog = firstNonempty(
		textData.get(`${resultRun.runDir}/logs/quantize.log`),
		textData.get(`${resultRun.runDir}/logs/setup_env.log`),
		failureSessionQuantFile ? textData.get(failureSessionQuantFile) : null,
	);
	const quantErrors = pipelineStatus === 'failed' && failureLog ? [String(failureLog)] : extractErrors(quantData?.errors);
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
		owner: resultRun.owner,
		artifact_name: resultRun.artifactName,
		model_id: firstNonempty(aggregate.model_id, quantData?.model_id, data?.model, `${identity.owner}/${identity.modelName}`) || identity.modelName,
		submitted_by: firstNonempty(data?.submitted_by, aggregate.submitted_by),
		orgs: extractOrgList(data?.orgs, data?.org, data?.organizations, aggregate.orgs, aggregate.org, aggregate.organizations),
		scheme: firstNonempty(quantData?.scheme, aggregate.scheme, identity.scheme) || identity.scheme,
		method: firstNonempty(quantData?.method, aggregate.method, identity.method) || identity.method,
		run_id: resultRun.runId,
		run_timestamp: parseRunTimestamp(resultRun.runId),
		run_path: relPath,
		auto_quant_status: quantStatus,
		quant_errors: quantErrors,
		eval_errors: evalErrors,
		issues,
		summary: String(firstNonempty(aggregate.summary, '') || ''),
		tasks,
		metrics_preview: metricsPreview(accuracyData),
		quant_num_gpus: firstNonempty(quantData?.num_gpus, quantData?.gpus, aggregate.quant_num_gpus, data?.quant_gpu_nums, data?.gpu_nums),
		eval_num_gpus: firstNonempty(accuracyData?.num_gpus, aggregate.eval_num_gpus, data?.eval_gpu_nums, data?.gpu_nums),
		quant_details: extractQuantDetails(quantData),
		eval_details: extractEvalDetails(accuracyData),
		pipeline: extractPipelineInfo(data),
		session_eval_url: null,
		session_quant_url: null,
		aggregate_result_url: null,
		updated_at: parseRunTimestamp(resultRun.runId),
	};

	const sessionEvalFile = findSessionFile(resultRun, availableFiles, aggregate, 'eval');
	const sessionQuantFile = findSessionFile(resultRun, availableFiles, aggregate, 'quant');
	const aggregateFile = runFiles.find(f => f.startsWith(`results/${resultRun.owner}/${resultRun.artifactName}/results_`));
	if (sessionEvalFile) record.session_eval_url = buildFileUrl(sessionEvalFile);
	if (sessionQuantFile) record.session_quant_url = buildFileUrl(sessionQuantFile);
	if (aggregateFile) record.aggregate_result_url = buildFileUrl(aggregateFile);
	return record;
}

// ─── Main fetch logic ───────────────────────────────────────────────────────

export interface FetchResult {
	runs: RunRecord[];
	latest: RunRecord[];
	summary: SummaryData;
}

export async function fetchFromGitHub(onProgress?: (msg: string) => void): Promise<FetchResult> {
	const progress = onProgress || (() => {});
	const liveMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('live');
	if (!liveMode) {
		progress('Loading cached dashboard data...');
		return await fetchStaticSnapshot();
	}

	// 1. Fetch repo tree
	progress('Fetching repository tree...');
	const treeResp = await fetch(`${API_BASE}/git/trees/${BRANCH}?recursive=1`);
	if (!treeResp.ok) {
		progress(`GitHub API unavailable (${treeResp.status}); loading cached data...`);
		try {
			return await fetchStaticSnapshot();
		} catch {
			throw new Error(`GitHub API error: ${treeResp.status}`);
		}
	}
	const treeData = await treeResp.json();
	const entries: TreeEntry[] = treeData.tree || [];
	// 2. Categorize files
	const statusFiles: string[] = [];       // current source of truth
	const runFiles: string[] = [];          // result JSON/session/aggregate files
	const aggregateFiles: string[] = [];    // results_*.json at model level
	const quantizeLogFiles: string[] = [];  // failed quantization logs
	const setupEnvLogFiles: string[] = [];  // failed setup logs
	const runDirs = new Set<string>();

	for (const entry of entries) {
		if (entry.type !== 'blob') continue;
		if (entry.path.startsWith('status/') && entry.path.endsWith('.json')) {
			statusFiles.push(entry.path);
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
		else if (QUANTIZE_LOG_RE.test(entry.path)) {
			quantizeLogFiles.push(entry.path);
			const runMatch = entry.path.match(/^(results\/[^/]+\/[^/]+\/run_[^/]+)\//);
			if (runMatch) runDirs.add(runMatch[1]);
		}
		else if (SETUP_ENV_LOG_RE.test(entry.path)) {
			setupEnvLogFiles.push(entry.path);
			const runMatch = entry.path.match(/^(results\/[^/]+\/[^/]+\/run_[^/]+)\//);
			if (runMatch) runDirs.add(runMatch[1]);
		}
		// Aggregate results
		else if (AGGREGATE_RE.test(entry.path)) {
			aggregateFiles.push(entry.path);
			runFiles.push(entry.path);
			const runDir = aggregatePathToRunDir(entry.path);
			if (runDir) runDirs.add(runDir);
		}
	}

	// Also find run dirs from tree entries
	for (const entry of entries) {
		if (entry.type === 'tree' && /^results\/[^/]+\/[^/]+\/run_\d{4}-\d{2}-\d{2}[^/]*$/.test(entry.path)) {
			runDirs.add(entry.path);
		}
	}

	progress(`Downloading ${statusFiles.length + runFiles.length + quantizeLogFiles.length + setupEnvLogFiles.length} files...`);

	// 3. Download all needed files in parallel
	const allPaths = [...statusFiles, ...runFiles];
	const fileData = await batchFetchJson(allPaths, 8);
	console.log(`Fetched ${fileData.size} JSON files.`, fileData, allPaths);
	// 4. Build status list from status/ only.
	progress('Processing status data...');
	const statuses = statusFiles
		.map((path) => ({ path, data: fileData.get(path), identity: parseStatusIdentity(path, fileData.get(path)) }))
		.filter((item): item is { path: string; data: any; identity: StatusIdentity } => {
			if (!item.data || typeof item.data !== 'object' || !item.identity) return false;
			return normalizeKey(item.data.job_type) === STATUS_JOB_TYPE;
		});

	// 5. Build aggregate index
	const aggregateIndex = new Map<string, any>();
	for (const path of aggregateFiles) {
		const data = fileData.get(path);
		if (!data) continue;
		if (typeof data.run_dir === 'string') runDirs.add(data.run_dir);
		for (const copiedPath of extractPathList(data.copied_files, data.output_files)) {
			const runMatch = copiedPath.match(/^(results\/[^/]+\/[^/]+\/run_[^/]+)\//);
			if (runMatch) runDirs.add(runMatch[1]);
		}
		// Walk to find records
		const walk = (node: any) => {
			if (!node) return;
			if (typeof node === 'object' && !Array.isArray(node)) {
				if (node.run_id || node.run_path || node.run_dir || node.model_id || node.auto_quant_status) {
					const key = String(node.run_path || (typeof node.run_dir === 'string' ? node.run_dir.replace(/^results\//, '') : '') || node.run_id || '').trim();
					if (key) aggregateIndex.set(key, node);
				}
				for (const v of Object.values(node)) walk(v);
			} else if (Array.isArray(node)) {
				for (const v of node) walk(v);
			}
		};
		walk(data);
	}

	// 6. Build run records from status entries.
	progress('Building run records...');
	const records: RunRecord[] = [];
	const resultRunDirs = [...runDirs].map(resultRunFromDir).filter((run): run is ResultRunDir => Boolean(run));
	const matchedRunByStatus = new Map<string, ResultRunDir>();
	const failedLogPaths: string[] = [];
	for (const { path, data, identity } of statuses) {
		const normStatus = normalizePipelineStatus(data.status);
		if (normStatus !== 'succeeded' && normStatus !== 'failed') continue;
		const resultRun = findResultRun(identity, data, resultRunDirs);
		if (!resultRun) continue;
		matchedRunByStatus.set(path, resultRun);
		if (normStatus === 'failed') {
			const relPath = resultRun.runDir.replace('results/', '');
			const aggregate = aggregateIndex.get(relPath) || aggregateIndex.get(resultRun.runId) || {};
			const quantizeLogPath = `${resultRun.runDir}/logs/quantize.log`;
			const setupEnvLogPath = `${resultRun.runDir}/logs/setup_env.log`;
			const sessionLogPath = findSessionFile(resultRun, runFiles, aggregate, 'quant');
			if (quantizeLogFiles.includes(quantizeLogPath)) failedLogPaths.push(quantizeLogPath);
			else if (setupEnvLogFiles.includes(setupEnvLogPath)) failedLogPaths.push(setupEnvLogPath);
			else if (sessionLogPath) failedLogPaths.push(sessionLogPath);
		}
	}
	const textData = await batchFetchText([...new Set(failedLogPaths)], 8);
	const availableFiles = [...runFiles, ...quantizeLogFiles, ...setupEnvLogFiles];

	for (const { path, data, identity } of statuses) {
		const normStatus = normalizePipelineStatus(data.status);
		if (normStatus === 'succeeded' || normStatus === 'failed') {
			const resultRun = matchedRunByStatus.get(path);
			if (resultRun) {
				records.push(buildResultRecord(identity, data, resultRun, fileData, textData, runFiles, availableFiles, aggregateIndex, normStatus));
				continue;
			}
		}
		records.push(buildStatusOnlyRecord(identity, data, normStatus));
	}

	// 7. Sort and build summary
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
	const quant: Record<RunStatus, number> = { success: 0, failed: 0, running: 0 };
	const pipeline: Record<PipelineStatus, number> = { pending: 0, running: 0, succeeded: 0, failed: 0, cancelled: 0 };

	for (const r of latest) {
		quant[r.auto_quant_status]++;
		const ps = (r.pipeline?.status || 'pending') as PipelineStatus;
		pipeline[ps]++;
	}

	return {
		generated_at: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
		total_runs: records.length,
		latest_models_count: latest.length,
		quant,
		pipeline,
	};
}
