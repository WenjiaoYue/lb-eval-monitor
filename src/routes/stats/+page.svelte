<script lang="ts">
import { base } from '$app/paths';
import { goto } from '$app/navigation';
import { onMount } from 'svelte';

onMount(() => {
	goto(`${base}/`, { replaceState: true });
});
</script>

<svelte:head>
	<title>Redirecting… | lb_eval monitor</title>
</svelte:head>

<p style="padding: 2rem; font-family: system-ui, sans-serif; color: #475569;">
	Statistics moved into the dashboard. <a href="{base}/">Go to dashboard →</a>
</p>
