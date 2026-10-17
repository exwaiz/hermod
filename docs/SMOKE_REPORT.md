# Implementation / smoke report — 2026-10-17, Raspberry Pi

## Observed environment

- Linux aarch64; Python 3.13.5; Playwright 1.64.0.
- Chromium 156.0.8078.4 at the actually discovered ARM64 executable under
  `/home/haaland/.cache/ms-playwright/chromium-1248/chrome-linux-arm64/chrome`.
- Development interpreter: `/home/haaland/.local/share/router-browser-venv/bin/python`.
- Host RAM approximately 3,795 MiB; initial available approximately 2,481 MiB;
  disk free approximately 98 GiB. Memory cgroup controller unavailable.
- No `hermod` OS account or `hermod-clients` group existed. Neither was created.
- Existing gateway PID 966720 remained active throughout. Existing other-service
  running/failed states were unchanged; pre-existing failed auxiliary units were
  not repaired or restarted as part of this unrelated project.

## Actual checks

Final suites: **Hermod 23 passed** (38.204 seconds) and **Heimdall 336 passed**
(35.343 seconds), including the real optional browser contract (not skipped).
Existing standalone gateway suite also passed 326 tests before adding the new
integration tests. Compile/shell syntax/whitespace checks passed; imported SPEC
matches the user-supplied Markdown byte-for-byte.

1. Chromium launch with `chromium_sandbox=True`; real browser opened official
   documentation pages. The policy page was blocked by a security-check page;
   no bypass or logged-in session was attempted. No external mutation.
2. Independent daemon **OS process**, separate CLI process and UDS health call
   succeeded. SIGTERM shutdown exited cleanly and removed the exact owned socket.
   This smoke did not start a browser.
3. Real local fixture browser flow over real UDS: verified thread, compose,
   submit, streaming response, receipt/completion check, retrieve. One submission
   despite duplicate create requests. In-memory synthetic PNG generated (19,206
   bytes), no private screenshot file retained.
4. Fixture run measured 2,678 ms and 628,371,456 bytes aggregate controller/browser
   RSS (about 599 MiB). An earlier run measured 2,797 ms / 628,031,488 bytes.
   These are single-run observations, not p95 or worst-case guarantees. No CPU
   utilization benchmark is claimed.
5. Hermod unit/browser tests cover version/size/schema/UID rejection, URL policy,
   duplicate conflict, queue cap, cancellation, recovery, timeout-after-submit,
   UI mismatch/auth/human-action fixtures, receipt validation, ephemeral result
   expiry, profile lock and no body text in ledger/logs. No real account tests.
6. Gateway integration tests cover explicit ZIP import/consent/traversal rejection,
   snapshot catalogue/no guessed URL, owner-only commands, default OFF, route
   previews, manual handoff, lost ACK no replay and fake Telegram → real UDS →
   real Chromium → existing outbox. Existing Codex/Knowledge/image tests ran too.

## Explicit gates / remaining work

- PR-0/1/2 core and default-OFF development integration are implemented and locally
  tested. PR-3 is a conservative OPEN-only adapter, not a verified authenticated
  ChatGPT integration. Auth remains unknown absent an observed login redirect.
- Dedicated UID/group/socket OS boundary, production systemd hardening and native
  Codex sandbox denial require approved installation. Same-UID synthetic tests
  cannot prove that isolation. Unit-template verification reported only the
  missing not-yet-installed `/opt/hermod/venv/bin/python`; production start/stop
  was not run or claimed.
- No service enable/start/restart, gateway runtime code deployment, operating DB
  import/migration, owner browser login, real Telegram message, real Codex model
  call, cookie transfer or profile backup was performed.
- ChatGPT SUBMIT/COLLECT/SEARCH/READ_HISTORY and future provider automation remain
  blocked. No secret switches or hidden endpoints implement them.
- Export summaries require explicit private import. Source export stays outside
  repositories; age-based catalogue/ledger lifecycle beyond current bounds needs
  further policy. Replay-safe receipt cleanup, comprehensive metrics and automatic
  lost-ACK reconciliation remain follow-up work.
- At initial implementation, connected GitHub identity was confirmed, but repository creation and terminal push
  credentials were unavailable. Independent local Git repository is prepared;
  repository creation was not performed. The owner subsequently created
  `exwaiz/hermod`; source publication is a separate, explicitly requested step.

Reproduce using the commands in README. Optional combined gateway test requires
Hermod src and installed Playwright/dependency paths on PYTHONPATH. Do not run
real-account smoke as a substitute for these synthetic fixtures.
