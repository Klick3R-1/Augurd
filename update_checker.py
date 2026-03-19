import asyncio
import logging
from datetime import datetime, timedelta

import httpx

import database
from version import __version__, GITHUB_REPO

logger = logging.getLogger(__name__)

CHECK_INTERVAL_HOURS = 2

# In-memory cache — populated on startup and after each check
_latest_version: str | None = None
_latest_url: str | None = None


async def check_if_due():
    """Run update check if CHECK_INTERVAL_HOURS have passed since last check."""
    global _latest_version, _latest_url

    settings = await database.get_settings()

    # Restore last known result from DB into memory cache
    _latest_version = settings.get("update_latest_version") or None
    _latest_url = settings.get("update_latest_url") or None

    last_checked_str = settings.get("update_last_checked", "")
    if last_checked_str:
        try:
            last_checked = datetime.fromisoformat(last_checked_str)
            if datetime.now() - last_checked < timedelta(hours=CHECK_INTERVAL_HOURS):
                logger.info(f"Update check skipped — last checked at {last_checked_str}")
                return
        except ValueError:
            pass

    await _do_check()


async def _do_check():
    global _latest_version, _latest_url

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 404:
                logger.info("Update check: no releases found yet")
                return
            resp.raise_for_status()

            data = resp.json()
            tag = data.get("tag_name", "").lstrip("v")
            url = data.get("html_url", "")

            _latest_version = tag
            _latest_url = url

            await database.update_settings({
                "update_last_checked": datetime.now().isoformat(),
                "update_latest_version": tag,
                "update_latest_url": url,
            })

            if tag and tag != __version__:
                logger.info(f"Update available: v{tag} (running v{__version__})")
            else:
                logger.info(f"augurd is up to date (v{__version__})")

    except Exception as e:
        logger.warning(f"Update check failed: {e}")


async def daily_loop():
    """Background task — re-checks for updates once every 24 hours."""
    while True:
        await asyncio.sleep(24 * 60 * 60)
        await _do_check()


def update_available() -> tuple[str | None, str | None]:
    """Returns (latest_version, url) if a newer version is available, else (None, None)."""
    if _latest_version and _latest_version != __version__:
        return _latest_version, _latest_url
    return None, None
