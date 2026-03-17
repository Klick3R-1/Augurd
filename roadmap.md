# localmon roadmap

## Known gaps / hardening

- [ ] SSH host key checking is disabled (`known_hosts=None`) — fine for internal LAN, should be addressed before public release
- [ ] SSH password stored plaintext in SQLite — add encryption or enforce key-only auth
- [ ] Per-source alert cooldown — currently cooldown is per-server, not per log source

## Features

- [ ] Test connection button on server form (verify SSH before saving)
- [ ] Alert history page with filtering (by server, date range, keyword)
- [ ] Per-server alert count badge on dashboard auto-refreshes
- [ ] `.env` / config file for Ollama URL so it doesn't need UI setup on first run
- [ ] Discord embed template editor (customise fields, colors, format)
- [ ] Log source enable/disable toggle without removing it
- [ ] Worker auto-start on app restart (persist desired state in DB)

## Future

- [ ] Dockerise (Dockerfile + compose with Ollama on same network)
- [ ] Support piping logs in over stdin / named pipe (not just SSH)
- [ ] Multi-user auth (sit behind Caddy/NPM for TLS, basic auth header passthrough)
- [ ] Webhook support beyond Discord (Slack, ntfy, generic POST)
- [ ] Alert suppression rules (regex patterns to ignore known-noisy lines)
