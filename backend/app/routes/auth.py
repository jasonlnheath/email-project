"""Auth routes — Google Sign-In, API key management."""

from fastapi import APIRouter, Depends, HTTPException, Request
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, async_session
from ..config import fernet, settings

router = APIRouter()


class GoogleLoginRequest(BaseModel):
    id_token: str


class UpdateKeysRequest(BaseModel):
    openai_key: str | None = None
    anthropic_key: str | None = None
    preferred_provider: str | None = None


async def get_db():
    async with async_session() as session:
        yield session


def _encrypt(text: str) -> str:
    return fernet.encrypt(text.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode()).decode()


def _get_google_id(request: Request) -> str:
    """Extract and validate google_id from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
            return idinfo["sub"]
        except Exception:
            pass
    raise HTTPException(401, "Invalid or missing auth token")


async def get_user_by_google_id(google_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.google_id == google_id))
    return result.scalar_one_or_none()


@router.post("/google")
async def google_login(body: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    """Validate Google ID token and create/find user."""
    try:
        idinfo = id_token.verify_oauth2_token(
            body.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as e:
        raise HTTPException(400, f"Invalid ID token: {e}")

    google_id = idinfo.get("sub")
    email = idinfo.get("email", "")
    name = idinfo.get("name", "")

    if not google_id:
        raise HTTPException(400, "Missing sub in token")

    user = await get_user_by_google_id(google_id, db)
    if not user:
        user = User(google_id=google_id, email=email, name=name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "provider": user.preferred_provider,
    }


@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    """Return current user profile."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "provider": user.preferred_provider,
        "has_openai_key": user.openai_key_enc is not None,
        "has_anthropic_key": user.anthropic_key_enc is not None,
    }


@router.put("/keys")
async def update_keys(body: UpdateKeysRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Save user's OpenAI/Anthropic API keys (encrypted)."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    if body.openai_key:
        user.openai_key_enc = _encrypt(body.openai_key)
    if body.anthropic_key:
        user.anthropic_key_enc = _encrypt(body.anthropic_key)
    if body.preferred_provider:
        user.preferred_provider = body.preferred_provider

    await db.commit()
    return {"ok": True}
