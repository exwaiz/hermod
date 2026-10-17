# Hermod

Independent, single-owner Python browser controller. Run it directly with its
CLI/Unix socket, or call the same versioned socket from Heimdall. It does not
depend on Telegram, Heimdall, Codex, a language model or an OpenAI API key.

Implemented: durable bounded queue, peer-UID authorization, strict RPC v1,
idempotent submissions, manual uncertain resolution, persistent private browser
profile, fail-closed provider policy, real local-fixture browser automation and
an optional default-OFF Heimdall adapter. Imported design: [SPEC.md](SPEC.md).

ChatGPT supports **verified-link navigation/manual handoff only**. Sending,
collecting, searching and reading web history are blocked by policy. Its login
state is currently **unknown** unless an explicit login redirect is observed;
no authenticated UI contract or live ChatGPT login has been tested. Navigation
success is not proof of account access. Full send/stream/collect is tested only
on our synthetic local fixture. See [limitations and measurements](docs/SMOKE_REPORT.md).

## Standalone quick check on this Pi

The installed development interpreter has Playwright 1.64.0 and Chromium:

```sh
cd /path/to/hermod-checkout
PYTHONPATH=src /home/haaland/.local/share/router-browser-venv/bin/python scripts/doctor.py
PYTHONPATH=src /home/haaland/.local/share/router-browser-venv/bin/python scripts/smoke_fixture.py
PYTHONPATH=src /home/haaland/.local/share/router-browser-venv/bin/python scripts/smoke_uds.py
PYTHONPATH=src /home/haaland/.local/share/router-browser-venv/bin/python -m unittest discover -s tests -v
```

Smoke uses a disposable profile and loopback server. No account login, model call,
real Telegram message or external-site mutation is performed. A test screenshot
is generated in memory only. The profile is cleaned up when the test exits.

For a portable installation create a dedicated venv, install this package with
`python -m pip install -e .`, and explicitly provision the pinned browser using
`python -m playwright install chromium`. These installation steps are not run
automatically by Hermod. Production browser binaries must be readable by the
dedicated service account; do not open your home directory to that account.

## Standalone daemon and client

Review `config.fixture.example.toml` (especially UID and unused loopback port).
In separate terminals, with the interpreter above and `PYTHONPATH=src`:

```sh
python scripts/serve_fixture.py --port 18767
python -m hermod --config config.fixture.example.toml serve
python -m hermod --config config.fixture.example.toml call system.health
```

To create a fixture conversation job, pass the following JSON through stdin to
`python -m hermod --config config.fixture.example.toml call jobs.create --params-stdin`:

```json
{"idempotency_key":"manual:demo1","provider":"local_fixture","action":"conversation.send","conversation_ref":"fixture:demo","requested_by":"operator","purpose":"fixture_test","policy_version":"hermod-v1","text":"Synthetic example"}
```

Then call `jobs.get --params-stdin` with `{"job_id":"HB-000001"}`. Same key and
same payload always return the same job, not a second send. Same key with a
different payload fails. Results expire after 120 seconds and are capped at 128
in memory; after a restart only ledger metadata remains. Queued bodies are not
durable, so queued jobs fail `PAYLOAD_UNAVAILABLE` after restart. Running/preflight
jobs become uncertain. Never automatically resend them.

Production daemon startup requires the `hermod` OS identity. The same-UID test
configuration is **not** a security isolation boundary and must never hold real
login credentials. No service/account/group has been installed or enabled here.

[Deployment](docs/DEPLOYMENT.md) · [Operations](docs/OPERATIONS.md) ·
[Integration](docs/INTEGRATION.md) · [Security](SECURITY.md) ·
[Threat model](docs/THREAT_MODEL.md) · [Decisions](docs/DECISIONS.md).
