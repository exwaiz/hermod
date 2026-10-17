# Operations

Use `system.health`/`browser.status` for readiness/architecture/package/capability/
queue/RSS metadata. They do not open a browser or prove login. `browser.ensure`
explicitly launches one persistent context; it rejects concurrent foreground work.
One worker owns foreground navigation; idle contexts close after ten minutes.
Production has no TCP listener. Only the synthetic fixture binds loopback TCP.

Jobs: queued → preflight → running → terminal state. `jobs.get` returns current
metadata and an ephemeral result if still available. `jobs.cancel` marks cancelled
and reports possible side effects. `jobs.resolve` accepts uncertain jobs only
with owner_confirmed=true and state completed/failed after active cleanup finishes.
It changes the ledger, not the website. There is deliberately no automatic retry.

Bodies/answers are not logged. Logs contain job ID/provider/action/state/duration/
error/version, not private text or raw browser exceptions. Browser stderr is not
retained by the production unit. Comprehensive metrics aggregation and request-ID
correlation are future observability work, not claimed as implemented.

Results: memory TTL 120 seconds, maximum 128. Queue: 10; text: 12,000 characters;
ledger: 100,000 rows. No unsafe age-based receipt deletion or profile backup.
Disk free space is checked before browser launch. Observe profile growth manually
and stop the service if it exceeds your approved budget. Stop only Hermod.

Do not run another persistent browser/login tool against the same profile. Both
daemon and supervised login hold the same private controller lock. Keep Chromium
sandbox enabled and TLS verification on. UI_CHANGED is a blocked task, not a cue
to click arbitrary alternate controls.
