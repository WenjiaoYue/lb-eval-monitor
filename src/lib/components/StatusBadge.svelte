<script lang="ts">
import type { RunStatus } from '$lib/types';

let { status = 'unknown' }: { status: RunStatus } = $props();
</script>

<span class={`badge badge--${status}`}>{status}</span>

<style>
.badge {
	display: inline-flex;
	align-items: center;
	padding: 0.1875rem 0.5rem;
	border-radius: 6px;
	font-size: 0.6875rem;
	font-weight: 600;
	line-height: 1.2;
	text-transform: capitalize;
	letter-spacing: 0.02em;
	white-space: nowrap;
}
.badge--success {
	background: #ecfdf5;
	color: #059669;
	border: 1px solid #a7f3d0;
}
.badge--failed {
	background: #fef2f2;
	color: #dc2626;
	border: 1px solid #fecaca;
}
.badge--running {
	background: #fffbeb;
	color: #d97706;
	border: 1px solid #fde68a;
}
.badge--unknown {
	background: #f1f5f9;
	color: #64748b;
	border: 1px solid #e2e8f0;
}
</style>
