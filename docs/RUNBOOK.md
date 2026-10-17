# Failure runbook

- Socket absent / FORBIDDEN: inspect service identity, exact socket owner/group,
  0770 directory / 0660 socket, configured UID and renewed client membership.
  Do not chmod a profile or home directory world-readable.
- ACTION_UNCERTAIN / RESULT_UNCERTAIN / TIMEOUT after submission: inspect the
  website manually. Do not resend. After cleanup stops, explicitly resolve the
  receipt; a new operation needs a new request/key and owner decision.
- AUTH_REQUIRED / HUMAN_ACTION_REQUIRED: stop unattended work. Ask the owner to
  use the supervised GUI. Unknown authentication is not evidence of logout.
- PAGE_MISMATCH / UI_CHANGED: verify configured reference/URL and provider version.
  No guesses, hidden endpoints, scraping, CAPTCHA bypass or certificate overrides.
- Stale owned socket: daemon probes before removing only an unreachable exact
  socket. A live socket or unexpected filesystem object is never replaced.
- Resource guard: stop only Hermod, inspect RSS/free disk/profile growth. This Pi
  lacks a hard memory controller; do not rely on MemoryMax to prevent exhaustion.
- Policy refusal on ChatGPT: expected. OPEN/handoff only; no configuration flag
  secretly enables SUBMIT/COLLECT. Consult a new reviewed provider decision.
- Gateway create ACK lost: local browser receipt stays uncertain. Inspect the
  standalone job ledger; do not reuse ordinary Codex retry for a browser action.
- Rollback: disable optional integration and routing; stop Hermod. Keep private
  data/receipts, original services and Codex authentication untouched.
