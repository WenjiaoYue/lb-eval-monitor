export type RunStatus = 'success' | 'failed' | 'running' | 'pending';

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

export type PipelineStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface PipelineInfo {
	status: PipelineStatus;
	submitted_time?: string;
	triggered_time?: string;
	ci_run_id?: number;
	job_type?: string;
	quant_scheme?: string;
	hardware?: string;
	gpu_nums?: number;
	model_weight_gb?: number;
	quant_model_size_gb?: number;
	params?: number;
}

export interface RunRecord {
	owner: string;
	artifact_name: string;
	model_id: string;
	submitted_by?: string | null;
	orgs?: string[];
	scheme: string;
	method: string;
	run_id: string;
	run_timestamp: string;
	run_path: string;
	auto_quant_status: RunStatus;
	auto_eval_status?: RunStatus;
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
	pipeline?: PipelineInfo | null;
	session_eval_url?: string | null;
	session_quant_url?: string | null;
	aggregate_result_url?: string | null;
	status_url?: string | null;
	updated_at: string;
}

export interface SummaryData {
	generated_at: string;
	total_runs: number;
	latest_models_count: number;
	quant: Record<RunStatus, number>;
	pipeline?: Record<PipelineStatus, number>;
}
