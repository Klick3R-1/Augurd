import aiosqlite
from pathlib import Path

DB_PATH = Path("localmon.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER DEFAULT 22,
    username TEXT NOT NULL,
    ssh_key_path TEXT,
    ssh_password TEXT,
    force_password_auth INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS log_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('journalctl', 'file')),
    source TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    server_name TEXT NOT NULL,
    log_source TEXT NOT NULL,
    reason TEXT NOT NULL,
    log_snippet TEXT,
    triggered_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);
"""

DEFAULT_SETTINGS = {
    "discord_webhook_url": "",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2",
    "buffer_lines": "20",
    "buffer_seconds": "30",
    "alert_cooldown_minutes": "5",
}


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        # Migration: add force_password_auth if upgrading from older schema
        try:
            await db.execute("ALTER TABLE servers ADD COLUMN force_password_auth INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # Column already exists
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await db.commit()


# --- Servers ---

async def get_all_servers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM servers ORDER BY name") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_server(server_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM servers WHERE id = ?", (server_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_server(name, host, port, username, ssh_key_path=None, ssh_password=None, force_password_auth=False):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO servers (name, host, port, username, ssh_key_path, ssh_password, force_password_auth) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, host, int(port), username, ssh_key_path or None, ssh_password or None, 1 if force_password_auth else 0),
        )
        await db.commit()
        return cur.lastrowid


async def update_server(server_id, name, host, port, username, ssh_key_path=None, ssh_password=None, force_password_auth=False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE servers SET name=?, host=?, port=?, username=?, ssh_key_path=?, ssh_password=?, force_password_auth=? WHERE id=?",
            (name, host, int(port), username, ssh_key_path or None, ssh_password or None, 1 if force_password_auth else 0, server_id),
        )
        await db.commit()


async def delete_server(server_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await db.commit()


# --- Log sources ---

async def get_log_sources(server_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM log_sources WHERE server_id = ? ORDER BY id", (server_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_log_source(server_id: int, source_type: str, source: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO log_sources (server_id, type, source) VALUES (?, ?, ?)",
            (server_id, source_type, source),
        )
        await db.commit()
        return cur.lastrowid


async def toggle_log_source(source_id: int, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE log_sources SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, source_id),
        )
        await db.commit()


async def delete_log_source(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM log_sources WHERE id = ?", (source_id,))
        await db.commit()


# --- Settings ---

async def get_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM settings") as cur:
            return {r["key"]: r["value"] for r in await cur.fetchall()}


async def update_settings(updates: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in updates.items():
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await db.commit()


# --- Alerts ---

async def save_alert(server_id, server_name, log_source, reason, log_snippet):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO alerts (server_id, server_name, log_source, reason, log_snippet) VALUES (?, ?, ?, ?, ?)",
            (server_id, server_name, log_source, reason, log_snippet),
        )
        await db.commit()


async def get_recent_alerts(limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts ORDER BY triggered_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_server_alerts(server_id: int, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts WHERE server_id = ? ORDER BY triggered_at DESC LIMIT ?",
            (server_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
