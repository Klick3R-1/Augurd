# augurd roadmap

## Security (priority)

- [ ] Encrypt secrets at rest in SQLite (SSH keys, passwords, Discord webhook URL)
- [ ] Built-in web UI authentication (before relying solely on reverse proxy)
- [ ] CSRF protection on all state-changing form actions
- [ ] Per-server known_hosts verification (opt-in, with UI warning when disabled)
- [ ] Secret redaction filter for outbound Discord content — scrub common patterns (API keys, tokens, passwords) from log snippets and alert reasons before they leave the network

## Hardening / correctness

- [ ] SSH host key checking is disabled (`known_hosts=None`) — per-server opt-in verification
- [ ] Per-source alert cooldown — currently cooldown is per-server, not per log source
- [ ] Worker auto-start on app restart (persist desired running state in DB)
- [ ] Handle Ollama prompt injection via log lines more robustly

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
- [x] Password auth mode (disables SSH agent)
- [x] Ollama model dropdown populated from installed models
