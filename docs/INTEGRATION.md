# Heimdall contract

Heimdall's `feature/hermod-integration` contains a standard-library-only
`HermodClient`, optional config, explicit local export importer, owner-only
commands, separate browser job receipts and candidate router. Hermod itself can
run without any of these modules. No browser cookies or storage state cross RPC.

```toml
[hermod]
enabled = false
socket_path = "/run/hermod/hermod.sock"
fixture_enabled = false
```

`/hermod status`, `/hermod doctor` query safe health metadata (doctor is not a
browser launch). `/chat find <query>`, `/chat route test <query>` use local export
snapshots and cached Codex names, no model. `/chat open HC-000001` queues only a
registered manual-handoff browser operation. `/chat status HB-000001` polls its
receipt and `/chat cancel HB-000001` requests cancellation. `/chat handoff` gives
an owner-verified link plus optional copied question. No verified link → no
invented deep-link. No binding/permission changes are made.

Export import is a local CLI, not an arbitrary Telegram path-read command. Use
`scripts/import_conversations.py --config ... --owner-confirmed import <zip>` in
the gateway's existing private owner environment. ZIP paths/symlinks/member
counts/sizes/expansion are checked; no extractall. `conversations.json` is required.
Only bounded titles/text summaries are indexed. Export data is private, explicit
opt-in, and a stale snapshot, never a web scrape. Link a candidate separately
with the CLI `link HC-000001 <owner-url> cgpt:<operator-ref>`; register the exact
same reference/URL in Hermod config. Do not copy exports into either repository.
The gateway passes an expected URL SHA-256 with its reference; Hermod rejects a
different configured target before navigation without accepting an arbitrary URL.
The source export must be owner-owned inside an owner-only (0700) import directory.

`/chat route on` opts into keyword candidate advice on matching general messages;
it does not auto-send to ChatGPT or auto-select a Codex thread. No candidates →
existing Codex path. OFF is default and leaves original chat behavior unchanged.
Private last-question text is kept in the existing gateway DB only to supply a
copyable handoff; Hermod's ledger never stores that body. Ordinary model prompts,
Auto-Memory, images and existing backups retain their independent code paths.

Hermod job identity is per authorized OS UID. Gateway receipts bind chat/user/
message → remote HB ID separately from Codex jobs. Missing create ACK becomes
uncertain locally and is not resent automatically. Reconciliation currently
requires operator inspection of the standalone ledger; it is not an automated
cross-service recovery protocol. Fixture test command `/hermod fixture <text>`
requires both the explicit gateway fixture flag and Hermod test mode. Production
Hermod rejects the fixture provider even if the gateway flag is misconfigured.

RPC v1: one UTF-8 JSONL request/response per UDS connection, 64 KiB request,
256 KiB response, Linux peer UID allowlist, strict fields/version. `jobs.create`
requires idempotency_key/provider/action/conversation_ref/requested_by/purpose/
policy_version. Free-standing collect is rejected: collection belongs to a send
receipt, to prevent returning an unrelated previous answer. Unknown fields,
arbitrary selectors/URLs/scripts/cookies and unsupported capabilities fail closed.
