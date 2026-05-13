<script lang="ts">
import type { RunStatus } from '$lib/types';

let { status = 'unknown' }: { status: RunStatus } = $props();
</script>

<span class={`badge ${status}`}>{status}</span>

<style>
.badge {
display: inline-block;
padding: 0.15rem 0.5rem;
border-radius: 999px;
font-size: 0.75rem;
font-weight: 600;
line-height: 1.2;
text-transform: capitalize;
}
.success {
background: #dcfce7;
color: #166534;
}
.failed {
background: #fee2e2;
color: #991b1b;
}
.running {
background: #fef3c7;
color: #92400e;
}
.unknown {
background: #e5e7eb;
color: #374151;
}
</style>
