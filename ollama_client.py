import httpx
import logging

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """\
You are a sysadmin monitoring server logs. Analyze the following log lines and determine if anything requires immediate attention (errors, crashes, authentication failures, unusual activity, resource issues, service failures, segfaults, OOM kills, etc.).

Respond with EXACTLY one of:
- OK
- ALERT: <brief one-line reason>

Do not add any explanation beyond the format above.

Log lines from server '{server_name}' (source: {source}):
{log_text}"""


async def get_models(ollama_url: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning(f"Could not fetch Ollama models: {e}")
        return []


async def analyze_logs(
    ollama_url: str,
    model: str,
    server_name: str,
    source: str,
    lines: list[str],
    prompt_template: str | None = None,
) -> tuple[bool, str, str]:
    """Returns (is_alert, reason). reason is empty string when OK."""
    log_text = "\n".join(lines)
    template = prompt_template or ANALYSIS_PROMPT
    prompt = template.format(
        server_name=server_name,
        source=source,
        log_text=log_text,
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            if resp.status_code != 200:
                logger.error(f"Ollama error {resp.status_code}: {resp.text}")
                return False, ""
            result = resp.json().get("response", "").strip()

        logger.info(f"Ollama raw response [{server_name}/{source}]: {result}")

        if result.upper().startswith("ALERT"):
            body = result[6:].lstrip(": ").strip() if len(result) > 6 else result
            # Split off Reasoning: line if present
            reasoning = ""
            if "\nReasoning:" in body:
                parts = body.split("\nReasoning:", 1)
                reason = parts[0].strip()
                reasoning = parts[1].strip()
            else:
                reason = body
            return True, reason, reasoning

        return False, "", ""
    except Exception as e:
        logger.error(f"Ollama analysis error: {e}")
        return False, ""
