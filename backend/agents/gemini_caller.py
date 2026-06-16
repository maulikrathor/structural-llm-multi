import os
import json
import base64
import re
import asyncio
import httpx

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

MAX_RETRIES = 3
RETRY_STATUSES = {503, 429}


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1)
    return json.loads(text)


def _parse_retry_delay(body: str, status: int) -> float:
    """Extract suggested retry delay from error body, with sensible defaults."""
    match = re.search(r"retry in ([0-9.]+)s", body)
    if match:
        return float(match.group(1)) + 2.0  # small buffer
    return 15.0 if status == 503 else 60.0


async def call_gemini(
    system_prompt: str,
    user_text: str,
    image_bytes: bytes | None = None,
    mime_type: str = "image/png",
    agent_name: str = "unknown",
) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")

    user_parts = []
    if image_bytes is not None:
        user_parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        })
    user_parts.append({"text": user_text})

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": user_parts}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }

    print(f"[gemini] starting {agent_name}")

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    GEMINI_API_URL,
                    headers={"x-goog-api-key": api_key},
                    json=payload,
                )
                response.raise_for_status()
                break  # success — exit retry loop

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                body = e.response.text[:500] if e.response is not None else ""

                if status in RETRY_STATUSES and attempt < MAX_RETRIES:
                    delay = _parse_retry_delay(body, status)
                    print(f"[gemini] {agent_name} got {status}, retrying in {delay:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    last_error = e
                    continue

                # Non-retryable or retries exhausted
                error_msg = f"Gemini {agent_name} failed with HTTP {status}: {body}"
                print(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg) from e
    else:
        # All retries exhausted
        raise RuntimeError(f"Gemini {agent_name} failed after {MAX_RETRIES} attempts") from last_error

    print(f"[gemini] completed {agent_name}")

    data = response.json()
    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Gemini response structure: {data}") from e

    try:
        return _extract_json(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {raw_text[:500]}") from e