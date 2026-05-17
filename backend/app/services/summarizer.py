"""AI summarization — OpenAI and Anthropic providers with SSE streaming."""

import re
from typing import AsyncIterator

import httpx
from fastapi.responses import StreamingResponse


SUMMARY_PROMPT = (
    "Analyze this email and return a brief 1-3 sentence summary capturing the key points.\n\n"
    "FROM: {sender}\n"
    "SUBJECT: {subject}\n\n"
    "BODY:\n{body}\n\n"
    "Return ONLY the summary text. No JSON, no markdown, no extra text."
)


def _clean_summary(text: str) -> str:
    text = re.sub(r"<\?xml.*?>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"</?think>", "", text).strip()
    return text


async def summarize_openai(api_key: str, sender: str, subject: str, body: str) -> str:
    """Summarize email using OpenAI API. Returns summary text."""
    truncated = body[:1000] if len(body) > 1000 else body
    prompt = SUMMARY_PROMPT.format(sender=sender, subject=subject, body=truncated)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 128,
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        return _clean_summary(data["choices"][0]["message"]["content"])


async def summarize_anthropic(api_key: str, sender: str, subject: str, body: str) -> str:
    """Summarize email using Anthropic API. Returns summary text."""
    truncated = body[:1000] if len(body) > 1000 else body
    prompt = SUMMARY_PROMPT.format(sender=sender, subject=subject, body=truncated)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 128,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        return _clean_summary(data["content"][0]["text"])


async def stream_openai(api_key: str, sender: str, subject: str, body: str) -> AsyncIterator[str]:
    """Stream summary from OpenAI API (SSE)."""
    truncated = body[:1000] if len(body) > 1000 else body
    prompt = SUMMARY_PROMPT.format(sender=sender, subject=subject, body=truncated)

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 128,
                "stream": True,
            },
            timeout=45,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    chunk = json.loads(line[6:])
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content


async def stream_anthropic(api_key: str, sender: str, subject: str, body: str) -> AsyncIterator[str]:
    """Stream summary from Anthropic API (SSE)."""
    truncated = body[:1000] if len(body) > 1000 else body
    prompt = SUMMARY_PROMPT.format(sender=sender, subject=subject, body=truncated)

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 128,
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    import json
                    try:
                        chunk = json.loads(line[6:])
                        if chunk.get("type") == "content_block_delta":
                            text = chunk.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        pass
