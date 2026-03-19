# Augurd

**Augurd** is a self-hosted log monitoring tool focused on **actionable signal, not dashboards**.

It connects to your servers over SSH, ingests logs in real time or via timed polling, and uses a local Ollama model to decide one thing:

> is this worth your attention right now?

If yes → you get a Discord alert (optional)
If not → it stays noise

---

> **Status: Alpha (0.1.x)**
> Core functionality is in place. Security hardening and advanced features are in progress. Expect rough edges and breaking changes.

---

## What Augurd is (and is not)

### ✔ Augurd is
- A **log signal filter** for self-hosted environments
- Built for **operators who already understand their systems**
- Focused on **low-friction deployment and real-world setups**
- Designed around **local-first analysis (Ollama)** for privacy and cost control

### ✖ Augurd is not
- A full SIEM
- A metrics/observability platform
- A multi-tenant SaaS
- A "set and forget" enterprise tool

Augurd assumes you know your infrastructure — it helps you notice when it behaves differently.

---

## Why this exists

Most log monitoring tools fall into two categories:

- **Too heavy** — complex pipelines, high setup cost, overkill for small/medium environments
- **Too naive** — simple alerting with no context, resulting in constant noise

Augurd sits in between: lightweight to deploy, aware enough to filter noise, flexible enough to adapt per server.

There are plenty of existing solutions, but I wanted something tailored to my own servers and the servers I manage. This is the result of that work.

A few things to keep in mind:

**The dashboard should never be exposed to the clearnet.** Keep it on your local network. It can be exposed through a Cloudflare Tunnel with Cloudflare Access in front — authentication is enforced at the edge before traffic reaches your machine, and since the tunnel is outbound-only, no ports need to be open on your server.

**On SSH access for log fetching:** I use Cloudflare Tunnels for SSH, which is why `cloudflared` is a first-class option. Plain SSH over the internet is also supported, but use key auth only — password auth is vulnerable to brute force and should not be used on internet-facing servers.

**On TOFU and MITM protection:** Host key fingerprints are stored on first connection and verified on every subsequent one. This protects against MITM after the first connection. The caveat is the first connection itself — if you're on an untrusted network when adding a server, verify the fingerprint manually (see Security section).

---

## Core idea

Instead of rules first, Augurd is built around:

> "Let the model classify the event, then constrain it with context."

Each server can have its own model, its own prompt, and its own noise profile. This makes it viable across home labs, mixed workloads, and imperfect environments.

---

## What it does

- Web UI to configure servers, SSH connections, and log sources
- Streams logs over SSH (`journalctl`, full journal, or `tail -F`)
- Timed fetch mode for polling-based setups with deduplication
- Buffers log lines and sends them to a local Ollama model for analysis
- Fires Discord alerts when events are flagged as relevant (optional — alerts always appear on the dashboard)
- Per-server model + prompt overrides
- ProxyCommand support (e.g. Cloudflare Tunnels via `cloudflared`)
- Cloudflare auth URL surfaced in UI when required
- SSH host key TOFU with mismatch protection
- Test Connection button before saving servers
- Worker state persistence across restarts
- Blacklist rules to suppress known noise before analysis

---

## Design principles

**Local-first by default**
Logs may contain sensitive operational data. Augurd requires no external API calls and no data leaves your network during analysis.

**Signal over volume**
The goal is fewer, more meaningful alerts — not complete visibility.

**Works with real-world setups**
SSH over Cloudflare Tunnel, mixed log sources, imperfect configs. Augurd is designed for how systems actually look, not how they "should" look.

---

## Stack

- [FastAPI](https://fastapi.tiangolo.com) + Jinja2 + [HTMX](https://htmx.org) + [Pico CSS](https://picocss.com)
- [asyncssh](https://asyncssh.readthedocs.io) — async SSH streaming
- [aiosqlite](https://aiosqlite.omnilib.dev) — SQLite for config and alert history
- [httpx](https://www.python-httpx.org) — Ollama API + Discord webhook
- Python 3.11+ — no Docker yet, planned

---

## Setup

```bash
git clone https://github.com/Klick3R-1/Augurd
cd augurd
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and:

1. **Settings** — set your Ollama URL and pick a model. Optionally paste a Discord webhook URL if you want alerts sent to Discord
2. **Add Server** — fill in SSH connection details, use "Test Connection" to verify before saving
3. **Add log sources** — `journalctl` unit name (e.g. `sshd.service`), `*` for all system logs, or a file path
4. **Start Worker** — Augurd SSHes in and begins monitoring; it will auto-restart on app restart

### Ollama

Ollama must be reachable from the machine running Augurd. By default it only listens on `127.0.0.1` — to expose it on your network:

```bash
# Temporarily
OLLAMA_HOST=0.0.0.0 ollama serve

# Permanently via systemd override
sudo systemctl edit ollama
# Add:
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0"
```

### Reverse proxy (required for external access)

Augurd has **no built-in authentication**. Do not expose it directly to the internet. Place it behind [Caddy](https://caddyserver.com), [Nginx Proxy Manager](https://nginxproxymanager.com), or Cloudflare Access.

---

## Configuration reference

### Global settings (`/settings`)

| Setting | Description |
|---|---|
| Discord Webhook URL | Where alerts are sent (optional) |
| Ollama URL | URL of your Ollama instance |
| Model | Default model for all servers |
| Buffer Lines | Flush to Ollama after N lines |
| Buffer Seconds | Flush to Ollama after N seconds of silence |
| Cooldown (min) | Minimum time between alerts per server |
| Analysis Prompt | The prompt sent to Ollama — editable, takes effect on next flush |

### Per-server overrides

Each server can override the global model and analysis prompt, useful when you want a faster model for low-priority servers or a specialised prompt for specific services. Discord alerts can also be toggled per server with an optional per-server webhook URL.

### ProxyCommand

Supports arbitrary proxy commands using `%h` (hostname) and `%p` (port) placeholders — the same syntax as OpenSSH. Example for Cloudflare Tunnels:

```
cloudflared access ssh --hostname %h
```

When the proxy command outputs a browser authentication URL, Augurd surfaces it as a clickable link in the UI.

### Blacklist

Per-server blacklist rules drop log lines before they reach Ollama. Each rule specifies one or more comma-separated terms — a line is dropped only if **all** terms appear in it. Useful for silencing known-noisy sources like mDNS, DHCP, or health check traffic.

---

## Analysis prompt

The default prompt instructs the model to respond with `OK` or `ALERT: <reason>`. You can extend it to request reasoning:

```
Respond with EXACTLY one of:
- OK
- ALERT: <brief one-line reason>
  Reasoning: <one sentence explaining why>
```

Add context to reduce false positives for your environment:

```
This is a home server. Ignore routine noise such as avahi/mDNS announcements,
DHCP lease renewals, and NetworkManager connectivity checks.
```

---

## Why local inference (Ollama)

Augurd is built around local models because:

- logs contain sensitive operational data — none of it leaves your network
- continuous streaming generates high request volume, making external APIs costly
- local inference keeps latency predictable and cost near zero

Support for external providers may be added at some point, but local-first is the intended model. The timed fetch mode reduces request volume if you want to experiment, but the privacy concern remains regardless.

---

## Security

> **Read this before deploying, especially outside a trusted network.**

Augurd is an early-stage project and is **not secure by default**. It assumes a controlled environment and an operator who understands the risks.

### Implemented protections

**SSH host key verification (TOFU)**
On first connection, the server's host key fingerprint is stored. On subsequent connections:
- fingerprint matches → connection proceeds
- fingerprint changes → worker stops after 3 attempts, error shown in UI

You can clear a stored fingerprint from the server settings page when a key legitimately changes.

### Known limitations

**No web UI authentication**
The web interface has no built-in login. Anyone who can access the UI can view all server configs, read stored credentials, start/stop workers, and modify settings.

👉 You **must** place Augurd behind an authenticated reverse proxy.

---

**Secrets stored in plaintext**
Sensitive data is stored unencrypted in `augurd.db`:
- SSH private keys (if pasted)
- SSH passwords
- Discord webhook URL

Anyone with read access to this file has access to those secrets. Encryption at rest is planned.

---

**No CSRF protection**
State-changing actions are not protected by CSRF tokens. A malicious webpage could trigger actions if you have access to the UI. Middleware is planned.

---

**SSRF via Ollama URL**
The Ollama URL field can point to arbitrary internal addresses. If the UI is exposed, this could be abused to probe internal services.

---

**Log data may leave your network (Discord alerts)**
Alert payloads sent to Discord may include log lines, hostnames, IPs, and service output. If your logs contain sensitive data, that data will be transmitted externally when Discord alerts are enabled.

---

**Prompt injection via logs**
Log content is passed to an LLM. A crafted log line could attempt to influence model output. Impact is limited to false positives and noisy alerts — no code execution occurs.

---

### Notes on first connection (TOFU)

The first SSH connection is trusted blindly. If you are on an untrusted network when adding a server, verify the fingerprint manually before accepting it:

```bash
ssh-keyscan <host>
# or on the server:
cat /etc/ssh/ssh_host_*.pub
```

### Recommended deployment

- Run Augurd on a trusted internal network only
- Place it behind a reverse proxy with authentication (Caddy, NPM, or Cloudflare Access)
- Restrict database permissions: `chmod 600 augurd.db`
- Prefer SSH key authentication over passwords

### Security roadmap

Planned improvements:
- Encrypted secret storage
- Built-in authentication and session management
- CSRF protection
- Improved alert sanitisation before external dispatch

Until then, treat Augurd as a **trusted-network tool**, not an internet-facing service.

---

## Roadmap

See [roadmap.md](roadmap.md) for the full list. Security hardening is the top priority for upcoming work.

---

## License

MIT — see LICENSE file
