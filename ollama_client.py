import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

TIMED_MAP_PROMPT = """\
You are a sysadmin reviewing a chunk of server logs. Flag anything suspicious in one line, or say OK.

Watch for: auth failures, brute force, crashes, segfaults, OOM kills, disk errors, \
service failures, kernel errors, suspicious network activity, privilege escalation.

Respond with EXACTLY one of:
- OK
- FLAG: <one-line description of the issue>

No explanation. One line only.

Log lines from server '{server_name}' (source: {source}):
{log_text}"""

TIMED_REDUCE_PROMPT = """\
You are a sysadmin reviewing flagged observations from a server log analysis of '{server_name}' (source: {source}) covering {window}.

Each line below is a flag raised from a chunk of logs:
{flags}

Produce a final verdict. Respond with EXACTLY one of:
- OK
- ALERT: <brief one-line summary of the most critical issue>

No explanation beyond the format above."""

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
        return False, "", ""


async def _ollama_post(ollama_url: str, model: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
        )
        if resp.status_code != 200:
            logger.error(f"Ollama error {resp.status_code}: {resp.text}")
            return ""
        return resp.json().get("response", "").strip()


async def map_reduce_analyze(
    ollama_url: str,
    model: str,
    server_name: str,
    source: str,
    lines: list[str],
    window: str,
    chunk_size: int = 50,
    concurrency: int = 4,
) -> tuple[bool, str]:
    """Map-reduce log analysis for timed fetch. Returns (is_alert, reason)."""
    chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
    sem = asyncio.Semaphore(concurrency)

    async def map_chunk(chunk: list[str]) -> str | None:
        async with sem:
            prompt = TIMED_MAP_PROMPT.format(
                server_name=server_name,
                source=source,
                log_text="\n".join(chunk),
            )
            result = await _ollama_post(ollama_url, model, prompt)
            if result.upper().startswith("FLAG"):
                flag = result[5:].lstrip(": ").strip()
                logger.info(f"[{server_name}] Timed fetch flag ({source}): {flag}")
                return flag
            return None

    results = await asyncio.gather(*[map_chunk(c) for c in chunks])
    flags = [r for r in results if r]

    logger.info(f"[{server_name}] Timed fetch map done: {len(flags)} flag(s) from {len(chunks)} chunk(s)")

    if not flags:
        return False, ""

    reduce_prompt = TIMED_REDUCE_PROMPT.format(
        server_name=server_name,
        source=source,
        window=window,
        flags="\n".join(f"- {f}" for f in flags),
    )
    verdict = await _ollama_post(ollama_url, model, reduce_prompt)
    logger.info(f"[{server_name}] Timed fetch verdict ({source}): {verdict}")

    if verdict.upper().startswith("ALERT"):
        reason = verdict[6:].lstrip(": ").strip()
        return True, reason

    return False, ""
