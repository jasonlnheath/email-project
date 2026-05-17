"""Email Action API — FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import init_db
from .routes import auth, emails, ai, contacts


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Email Action API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(emails.router, prefix="/emails", tags=["emails"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])


@app.get("/health")
async def health():
    return {"status": "ok"}
