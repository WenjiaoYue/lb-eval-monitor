export type RunStatus = 'success' | 'failed' | 'running' | 'unknown';

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
session_eval_url?: string | null;
session_quant_url?: string | null;
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
