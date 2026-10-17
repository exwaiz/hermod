# Production deployment — explicit approval required

Not executed. Do not interpret the shipped unit as a running service.

1. Review source/config and run unit/fixture/Heimdall contract tests. Preserve
   existing services, profiles, sessions, gateway data and backups.
2. After owner approval, run `sudo sh deploy/setup-permissions.sh --apply-approved`.
   Review resulting UID/GID. Separately approve adding the client account with
   `sudo usermod -aG hermod-clients haaland`. This changes account authority;
   renewed sessions and the gateway process need the new group membership.
3. Install immutable reviewed source/venv under `/opt/hermod`, browser under
   `/opt/hermod/chromium`, and a reviewed config as `/etc/hermod/config.toml`
   (`root:hermod`, 0640). Resolve browser architecture/dependencies and executable
   ownership. Do not grant the service access to `/home/haaland`.
4. Configure exact allowed client UIDs and owner-verified conversation references.
   Only operator configuration accepts URLs; RPC accepts references only. Real
   credentials stay exclusively under `/var/lib/hermod/browser-profile` (0700).
5. Install the reviewed unit, `daemon-reload`, validate the actual unit and run a
   transient/start-stop check under the dedicated UID with sandbox enabled. Check
   socket owner/group/modes, denial from an unauthorized UID, profile denial from
   the gateway UID, process RSS, disk usage and native model socket denial.
   The current template's `/opt/hermod/venv/bin/python` does not yet exist;
   `systemd-analyze verify` reported that missing executable, not a passed install.
6. Only after this test and explicit approval start/enable `hermod.service`.
   Hermod restart must not restart Heimdall or any other service. Validate queued
   and uncertain ledger states; never replay old submissions.
7. Login is optional and requires a private local GUI session. Stop Hermod first,
   run `scripts/browser_login.py --config /etc/hermod/config.toml` as its dedicated
   UID in that GUI, complete sign-in yourself, then close the tool. Never open a
   public VNC/CDP port or paste passwords into Telegram. No GUI is provisioned by
   this implementation; a private GUI access method still needs owner choice.
8. Review the Heimdall integration branch and back up its DB before deployment.
   Configure `[hermod] enabled=true` only after contract/security checks. Installing
   those changes/restarting the gateway needs separate approval. Existing ordinary
   text routing remains Codex unless `/chat route on` is explicitly selected.

Rollback: turn routing OFF; disable Heimdall integration; stop only Hermod. Retain
its ledger and private profile safely. Do not overwrite a live DB or delete
uncertain receipts. Additive gateway tables may remain inert when integration is
disabled. Removing a socket-group grant is an explicit separate authority change.
