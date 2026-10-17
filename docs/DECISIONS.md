# Decisions — 2026-10-17

1. Separate local Git repository/package and Unix-socket CLI, not an embedded
   Codex browser tool. The user explicitly requested independent and Heimdall use.
2. Implement standalone controller + fixture first; integrate through versioned
   JSONL only. No Telegram/model dependency in Hermod.
3. No credentialed production login in development. Reuse installed Playwright
   interpreter and browser executable, not an existing user browser profile.
4. ChatGPT gates follow the supplied design regardless of technical feasibility.
   Browser visited the official computer-use documentation and Playwright BrowserType
   documentation. The Terms URL returned a Cloudflare "Just a moment" page, so its
   contents were **not independently verified** in this run. No current legal
   interpretation is inferred from that failure. The owner's stricter capability
   gate remains: OPEN only. Sources:
   https://developers.openai.com/api/docs/guides/tools-computer-use
   https://playwright.dev/python/docs/api/class-browsertype
   https://openai.com/policies/row-terms-of-use/
5. Authentication unknown is different from authenticated or logged out. Real UI
   validation needs an owner-supervised login. Do not invent ChatGPT selectors.
6. Jobs store hashes/metadata only. Missing queued bodies after restart fail
   without replay; running work is uncertain. Results expire after 120 seconds.
7. Routing remains OFF unless explicitly enabled; when ON it is deterministic
   candidate advice, not automatic provider submission or automatic thread switching.
8. Dedicated user/group creation, adding the owner to the socket group, installing
   and starting/enabling a service, and restarting the existing gateway require
   explicit approval. None was performed during implementation.
9. At initial implementation, connected GitHub identity was exwaiz. Available connector supports commits and
   refs in existing repositories, but exposes no repository-creation operation;
   terminal GitHub push credentials are unavailable. Remote `exwaiz/hermod` creation
   was not performed by the implementation. The owner subsequently created
   `exwaiz/hermod`; publication uses that existing repository without forcing
   over its initial history. Local repository remains usable independently.
