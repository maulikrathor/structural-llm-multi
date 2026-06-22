import os
import json
import base64
import re
import time
import asyncio
import httpx

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

MAX_RETRIES = 3
RETRY_STATUSES = {503, 429}

# Generation time scales with output size (corners/segments/components and
# inference_chain steps), so complex drawings need a much longer read budget
# than a typical request. connect/write/pool stay short so a genuine network
# failure (vs. a slow generation) still fails fast.
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, write=30.0, pool=10.0, read=300.0)


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

    print(f"[gemini] {agent_name}: starting (timeout read={REQUEST_TIMEOUT.read}s)")
    start = time.monotonic()

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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

            except httpx.TimeoutException as e:
                elapsed = time.monotonic() - start
                error_msg = (
                    f"Gemini {agent_name} timed out after {elapsed:.1f}s "
                    f"({type(e).__name__}, read budget={REQUEST_TIMEOUT.read}s). "
                    f"The drawing may be too complex to generate within the current limit."
                )
                print(f"[ERROR] {error_msg}")
                raise RuntimeError(error_msg) from e
    else:
        # All retries exhausted
        raise RuntimeError(f"Gemini {agent_name} failed after {MAX_RETRIES} attempts") from last_error

    elapsed = time.monotonic() - start
    print(f"[gemini] {agent_name}: completed in {elapsed:.1f}s")

    data = response.json()
    candidate = (data.get("candidates") or [{}])[0]
    finish_reason = candidate.get("finishReason", "UNKNOWN")
    usage = data.get("usageMetadata", {})

    try:
        raw_text = candidate["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected Gemini response structure: {data}") from e

    print(
        f"[gemini] {agent_name}: diagnostics finish_reason={finish_reason} "
        f"raw_chars={len(raw_text)} "
        f"prompt_tokens={usage.get('promptTokenCount')} "
        f"thoughts_tokens={usage.get('thoughtsTokenCount')} "
        f"output_tokens={usage.get('candidatesTokenCount')} "
        f"total_tokens={usage.get('totalTokenCount')}"
    )

    try:
        return _extract_json(raw_text)
    except json.JSONDecodeError as e:
        tail = raw_text[max(0, e.pos - 150):e.pos]
        print(
            f"[gemini] {agent_name}: JSON parse FAILED at char {e.pos}/{len(raw_text)} "
            f"finish_reason={finish_reason} text_before_failure={tail!r}"
        )
        raise ValueError(
            f"Gemini returned invalid JSON (finish_reason={finish_reason}, "
            f"raw_chars={len(raw_text)}, output_tokens={usage.get('candidatesTokenCount')}, "
            f"parse_failed_at_char={e.pos}): {raw_text[:500]}"
        ) from e