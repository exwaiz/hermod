# Threat model

| Boundary | Control | Remaining limitation |
|---|---|---|
| Caller → local RPC | Private socket, SO_PEERCRED, exact schema/size/version, bounded clients/timeouts | Approved UID processes are trusted; shared UID is not process authentication |
| Heimdall → browser credentials | Separate service UID, 0700 state, no cookie-return method | Production account/group/sandbox check requires approval and deployment |
| Caller → navigation | Registered ref, exact host/scheme, immutable capabilities | Application route filters are not a kernel network firewall |
| DOM → action | Fixed semantic locators, unique targets, target/receipt verification | ChatGPT authenticated UI unknown; never claim logged-in readiness |
| Send → retry | Unique key plus payload hash, durable attempt before compose/click, uncertain recovery | Already-submitted actions cannot be recalled |
| Logs/ledger → private body | No request/response text persistence, bounded ephemeral result cache | Browser profile itself contains sensitive state; never publish/back up it |
| Queue/browser → Pi resources | Single foreground worker, 10 queued/active jobs, deadlines, soft RSS/disk guards | No enforced memory cgroup on current Pi |

Chromium runs with its sandbox enabled. Production systemd hardening must be
tested under the dedicated account; namespace incompatibility is a blocker, not
justification to disable the browser sandbox. Fixtures and tests use synthetic
data only. Existing unrelated services are explicitly outside installation scope.
