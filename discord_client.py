import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def send_alert(
    webhook_url: str,
    server_name: str,
    server_host: str,
    log_source: str,
    source_type: str,
    reason: str,
    snippet: list[str],
    reasoning: str = "",
):
    if not webhook_url:
        logger.warning("Discord webhook URL not configured, skipping alert")
        return

    # Truncate snippet to last 10 lines and cap total length
    snippet_text = "\n".join(snippet[-10:])
    if len(snippet_text) > 1000:
        snippet_text = "..." + snippet_text[-997:]

    embed = {
        "title": f"\u26a0\ufe0f Alert: {server_name}",
        "color": 0xFF4444,
        "fields": [
            {"name": "Host", "value": f"`{server_host}`", "inline": True},
            {"name": "Source", "value": f"`{log_source}`", "inline": True},
            {"name": "Type", "value": source_type, "inline": True},
            {"name": "Reason", "value": reason, "inline": False},
            *(
                [{"name": "Reasoning", "value": reasoning, "inline": False}]
                if reasoning else []
            ),
            {
                "name": "Log Snippet",
                "value": f"```\n{snippet_text}\n```",
                "inline": False,
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "Augurd"},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={"embeds": [embed]})
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Discord webhook error: {e}")
