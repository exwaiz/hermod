# Security boundaries

Production runs as a separate non-root `hermod` user. Profile and ledger/state
directories are owned by that UID and mode 0700; database mode is 0600. RPC uses
filesystem access plus Linux SO_PEERCRED UID allowlisting, not a bearer token.
Client group membership exposes browser operations, not cookie/profile files.
Unix groups are an OS boundary, not proof that same-UID sandboxed model tools
cannot connect: the Heimdall adapter additionally denies `/run/hermod`,
`/var/lib/hermod` and `/etc/hermod` in model permission profiles. The real deployed
UID/group and native model sandbox test remains a pre-deployment approval gate.

No arbitrary URL, selector, script, shell command, cookie or storage-state RPC
parameter. References are operator-configured; ChatGPT links must be explicitly
verified by the owner. Exact origins, request routing, blocked service workers,
blocked WebSockets, popup closing and download cancellation bound browser actions.
This is application-level filtering, not a substitute for an audited OS egress
firewall. Privileged/network namespace hardening is not claimed as tested.

No CAPTCHA/stealth bypass, hidden API, certificate-ignore flag, root browser,
remote debugging listener or `--no-sandbox`. Manual login is a supervised local
GUI operation, never a Telegram password exchange. Profile backups, traces, HAR,
DOM dumps and private screenshots are excluded by default.

Routine jobs use no model/API. Request/response bodies live only in process
memory, not the durable job ledger or logs. Ledger fields include reference,
creator, policy, hashes, states and receipt timestamps. Heimdall separately owns
its normal private outbox/catalogue data. Idempotency receipts remain durable;
ledger is capped at 100,000 rows. Age-based deletion is deliberately not shipped:
deleting receipts would permit replay. Archive/retention with replay-safe
tombstones requires a separately reviewed implementation.

After attempted submission, timeout/error becomes uncertain. Cancellation may
have side effects and never promises retraction. Resolving a job needs explicit
owner confirmation and never reruns it. Browser outcomes are not external truth.
UI drift is a failure, not permission to guess clicks. Browser data remains
untrusted; deterministic provider code never evaluates it as instructions.

MemoryHigh/MemoryMax are advisory here because this Pi lacks a memory controller.
Hermod measures descendant RSS, checks it before launch, closes idle browsers,
limits queues/results and checks disk space. This is a soft limit, not a hard OOM
guarantee; profile growth and in-flight RSS still need operator monitoring.
