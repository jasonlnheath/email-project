"""AI summarization routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import async_session
from ..routes.auth import _get_google_id, get_user_by_google_id, _decrypt
from ..services.summarizer import summarize_openai, summarize_anthropic, stream_openai, stream_anthropic

router = APIRouter()


@router.post("/summarize")
async def summarize(request: Request, db: AsyncSession = Depends(lambda: async_session())):
    """Summarize an email using the user's preferred AI provider."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    body = await request.json()
    sender = body.get("from", "Unknown")
    subject = body.get("subject", "(no subject)")
    email_body = body.get("body", "")
    stream = body.get("stream", False)

    provider = user.preferred_provider or "openai"

    if provider == "openai":
        if not user.openai_key_enc:
            raise HTTPException(400, "No OpenAI API key configured")
        api_key = _decrypt(user.openai_key_enc)
        if stream:
            return StreamingResponse(
                stream_openai(api_key, sender, subject, email_body),
                media_type="text/plain",
            )
        summary = await summarize_openai(api_key, sender, subject, email_body)
    elif provider == "anthropic":
        if not user.anthropic_key_enc:
            raise HTTPException(400, "No Anthropic API key configured")
        api_key = _decrypt(user.anthropic_key_enc)
        if stream:
            return StreamingResponse(
                stream_anthropic(api_key, sender, subject, email_body),
                media_type="text/plain",
            )
        summary = await summarize_anthropic(api_key, sender, subject, email_body)
    else:
        raise HTTPException(400, f"Unknown provider: {provider}")

    return {"summary": summary}
