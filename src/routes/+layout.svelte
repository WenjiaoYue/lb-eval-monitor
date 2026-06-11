<script lang="ts">
let { children } = $props();
</script>

<svelte:head>
<title>lb_eval monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
</svelte:head>

{@render children()}

<style>
:global(*) {
	box-sizing: border-box;
}
:global(body) {
	margin: 0;
	font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
	background: #eef2f7;
	color: #1e293b;
	-webkit-font-smoothing: antialiased;
	-moz-osx-font-smoothing: grayscale;
	line-height: 1.5;
}
:global(button) {
	font-family: inherit;
}
:global(input, select, textarea) {
	font-family: inherit;
}
:global(::-webkit-scrollbar) {
	width: 6px;
	height: 6px;
}
:global(::-webkit-scrollbar-track) {
	background: transparent;
}
:global(::-webkit-scrollbar-thumb) {
	background: #cbd5e1;
	border-radius: 3px;
}
:global(::-webkit-scrollbar-thumb:hover) {
	background: #94a3b8;
}
</style>
