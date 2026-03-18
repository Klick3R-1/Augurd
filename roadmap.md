# augurd roadmap

## Security (priority)

- [x] SSH host key trust-on-first-use (TOFU) — store fingerprint on first connect, reject if it changes; critical for internet-facing servers (Hetzner etc.)
- [ ] Encrypt secrets at rest in SQLite (SSH keys, passwords, Discord webhook URL)
- [ ] Built-in web UI authentication (before relying solely on reverse proxy)
- [ ] CSRF protection on all state-changing form actions
- [ ] Secret redaction filter for outbound Discord content — scrub common patterns (API keys, tokens, passwords) from log snippets and alert reasons before they leave the network

## Hardening / correctness

- [ ] Prompt injection hardening — public-facing servers can write crafted log lines to manipulate LLM analysis
- [ ] Per-source alert cooldown — currently cooldown is per-server, not per log source
- [ ] Worker auto-start on app restart (persist desired running state in DB)
- [ ] Handle Ollama prompt injection via log lines more robustly

## Hardening / correctness (continued)

- [ ] Shared asyncio semaphore across workers to cap concurrent Ollama calls (prevents pile-up with many servers)

## Features

- [ ] Test connection button on server form (verify SSH before saving)
- [ ] Alert history page with filtering (by server, date range, keyword)
- [ ] `.env` / config file for Ollama URL so it doesn't need UI setup on first run
- [ ] Log source enable/disable toggle without removing it
- [ ] Discord embed template editor (customise fields, colors, format per server)
- [ ] Alert suppression rules (regex patterns to ignore known-noisy lines before hitting Ollama)

## Future

- [ ] Dockerise (Dockerfile + compose with Ollama on same network)
- [ ] Support piping logs in over stdin / named pipe (not only SSH)
- [ ] Webhook support beyond Discord (Slack, ntfy, generic POST)
- [ ] Thinking model support (parse `<think>` blocks when available)

## Completed

- [x] Core SSH log streaming → Ollama → Discord alert loop
- [x] Web UI (FastAPI + HTMX + Pico CSS)
- [x] journalctl unit, full journal (`*`), and file tail support
- [x] Per-server model and prompt overrides
- [x] Editable global analysis prompt (live, no restart needed)
- [x] Reasoning field in Discord embed (per-server toggle)
- [x] ProxyCommand support via socketpair (cloudflared tunnels working)
- [x] Cloudflare auth URL surfaced as clickable link in UI
- [x] SSH key paste field (stored in DB, loaded via asyncssh directly)
- [x] SSH host key TOFU — fingerprint stored on first connect, mismatch stops worker after 3 retries
- [x] Password auth mode (disables SSH agent)
- [x] Ollama model dropdown populated from installed models
