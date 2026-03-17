import asyncio
import asyncssh
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import database
import ollama_client
import discord_client

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 10  # seconds between reconnect attempts


class ServerWorker:
    def __init__(self, server: dict, log_sources: list[dict], settings: dict):
        self.server = server
        self.log_sources = log_sources
        self.settings = settings

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        self.status = "stopped"
        self.error: Optional[str] = None
        self.last_alert: Optional[datetime] = None
        self.alert_count = 0

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self):
        if self.is_running():
            return
        self._stop_event.clear()
        self.status = "connecting"
        self.error = None
        self._task = asyncio.create_task(self._run_loop(), name=f"worker-{self.server['id']}")

    async def stop(self):
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=15)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self.status = "stopped"

    async def _run_loop(self):
        """Outer reconnect loop — keeps trying until stop() is called."""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_monitor()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.status = "error"
                self.error = str(e)
                logger.error(f"[{self.server['name']}] Worker error: {e}")

            if self._stop_event.is_set():
                break

            logger.info(f"[{self.server['name']}] Reconnecting in {RECONNECT_DELAY}s…")
            self.status = "reconnecting"
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=RECONNECT_DELAY)
            except asyncio.TimeoutError:
                pass

        self.status = "stopped"

    async def _connect_and_monitor(self):
        connect_kwargs: dict = {
            "host": self.server["host"],
            "port": self.server["port"],
            "username": self.server["username"],
            "known_hosts": None,  # Internal network — disable strict host checking
        }

        key_path = self.server.get("ssh_key_path")
        password = self.server.get("ssh_password")
        force_password = bool(self.server.get("force_password_auth", 0))

        if force_password:
            # Skip SSH agent and all keys — password only (pssh mode)
            connect_kwargs["agent_path"] = None
            connect_kwargs["client_keys"] = []
            if password:
                connect_kwargs["password"] = password
        else:
            if key_path:
                connect_kwargs["client_keys"] = [str(Path(key_path).expanduser())]
            if password:
                connect_kwargs["password"] = password

        active_sources = [s for s in self.log_sources if s["enabled"]]
        if not active_sources:
            logger.info(f"[{self.server['name']}] No active log sources, worker idle")
            await self._stop_event.wait()
            return

        async with asyncssh.connect(**connect_kwargs) as conn:
            self.status = "running"
            self.error = None
            logger.info(f"[{self.server['name']}] SSH connected, monitoring {len(active_sources)} source(s)")
            await asyncio.gather(*[self._monitor_source(conn, src) for src in active_sources])

    async def _monitor_source(self, conn: asyncssh.SSHClientConnection, source: dict):
        if source["type"] == "journalctl":
            unit = source["source"].strip()
            if unit and unit != "*":
                cmd = f"journalctl -f -u {unit} --no-pager -o short-iso"
            else:
                cmd = "journalctl -f --no-pager -o short-iso"
        else:
            cmd = f"tail -F {source['source']}"

        buffer_lines = int(self.settings.get("buffer_lines", 20))
        buffer_seconds = float(self.settings.get("buffer_seconds", 30))

        buffer: list[str] = []

        async with conn.create_process(cmd) as proc:
            while not self._stop_event.is_set():
                try:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(), timeout=buffer_seconds
                    )
                    if not line:
                        # EOF — process ended
                        break
                    line = line.rstrip("\n")
                    if line:
                        buffer.append(line)
                    if len(buffer) >= buffer_lines:
                        await self._flush(buffer.copy(), source)
                        buffer.clear()
                except asyncio.TimeoutError:
                    # No new lines for buffer_seconds — flush what we have
                    if buffer:
                        await self._flush(buffer.copy(), source)
                        buffer.clear()

        # Flush any remaining lines on exit
        if buffer:
            await self._flush(buffer, source)

    async def _flush(self, lines: list[str], source: dict):
        cooldown = int(self.settings.get("alert_cooldown_minutes", 5)) * 60
        if self.last_alert and (datetime.now() - self.last_alert).total_seconds() < cooldown:
            return

        ollama_url = self.settings.get("ollama_url", "http://localhost:11434")
        model = self.settings.get("ollama_model", "llama3.2")

        is_alert, reason = await ollama_client.analyze_logs(
            ollama_url=ollama_url,
            model=model,
            server_name=self.server["name"],
            source=source["source"],
            lines=lines,
        )

        if not is_alert:
            return

        self.last_alert = datetime.now()
        self.alert_count += 1
        snippet = "\n".join(lines[-10:])

        logger.warning(f"[{self.server['name']}] ALERT ({source['source']}): {reason}")

        await database.save_alert(
            server_id=self.server["id"],
            server_name=self.server["name"],
            log_source=source["source"],
            reason=reason,
            log_snippet=snippet,
        )

        await discord_client.send_alert(
            webhook_url=self.settings.get("discord_webhook_url", ""),
            server_name=self.server["name"],
            server_host=self.server["host"],
            log_source=source["source"],
            source_type=source["type"],
            reason=reason,
            snippet=lines,
        )
