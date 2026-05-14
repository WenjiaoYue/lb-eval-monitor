export type RunStatus = 'success' | 'failed' | 'running' | 'unknown';

export interface QuantDetails {
	original_size_mb?: number;
	quantized_size_mb?: number;
	compression_ratio?: number;
	duration_seconds?: number;
	hf_repo?: string;
	export_format?: string;
	device?: string;
	model_id?: string;
	output_dir?: string;
	quantized_model_dir?: string;
}

export interface TaskResult {
	accuracy?: number;
	accuracy_stderr?: number;
	[key: string]: number | string | undefined;
}

export interface EvalDetails {
	duration_seconds?: number;
	eval_framework?: string;
	task_results?: Record<string, TaskResult>;
}

export interface LmEvalTaskMetrics {
	'acc,none'?: number;
	'acc_stderr,none'?: number;
	'acc_norm,none'?: number;
	'acc_norm_stderr,none'?: number;
	'exact_match,none'?: number;
	'exact_match_stderr,none'?: number;
	alias?: string;
}

export interface LmEvalResults {
	results: Record<string, LmEvalTaskMetrics>;
	model?: string;
	model_path?: string;
	total_time_seconds?: number;
}

export interface RunRecord {
	owner: string;
	artifact_name: string;
	model_id: string;
	scheme: string;
	method: string;
	run_id: string;
	run_timestamp: string;
	run_path: string;
	auto_quant_status: RunStatus;
	auto_eval_status: RunStatus;
	quant_errors: string[];
	eval_errors: string[];
	issues: string[];
	summary: string;
	tasks: string[];
	metrics_preview: Record<string, number | string>;
	quant_num_gpus?: number | string | null;
	eval_num_gpus?: number | string | null;
	quant_details?: QuantDetails | null;
	eval_details?: EvalDetails | null;
	lm_eval_results?: LmEvalResults | null;
	session_eval_url?: string | null;
	session_quant_url?: string | null;
	lm_eval_results_url?: string | null;
	aggregate_result_url?: string | null;
	updated_at: string;
}

export interface SummaryData {
	generated_at: string;
	total_runs: number;
	latest_models_count: number;
	quant: Record<RunStatus, number>;
	eval: Record<RunStatus, number>;
}
