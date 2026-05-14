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
	background: rgba(16, 185, 129, 0.1);
	color: #059669;
}
.badge--failed {
	background: rgba(239, 68, 68, 0.1);
	color: #dc2626;
}
.badge--running {
	background: rgba(245, 158, 11, 0.1);
	color: #d97706;
}
.badge--unknown {
	background: rgba(107, 114, 128, 0.1);
	color: #6b7280;
}
</style>
