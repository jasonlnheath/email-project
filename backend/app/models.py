"""SQLAlchemy models — mirrors existing relmgr schema."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.DB_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── User ──────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    openai_key_enc = Column(Text, nullable=True)
    anthropic_key_enc = Column(Text, nullable=True)
    preferred_provider = Column(String, default="openai")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


# ── Contacts (same schema as relmgr/store.py) ────────────────

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    normalized_name = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    emails = Column(Text, default="[]")
    phones = Column(Text, default="[]")
    organizations = Column(Text, default="[]")
    sources = Column(Text, default="[]")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    is_duplicate = Column(Boolean, default=False)
    merged_into = Column(String, nullable=True)
    is_vip = Column(Boolean, default=False)

    contact_sources = relationship("ContactSource", back_populates="contact")


class ContactSource(Base):
    __tablename__ = "contact_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String, ForeignKey("contacts.id"), nullable=False)
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    raw_data = Column(Text, nullable=True)
    fetched_at = Column(String, nullable=False)

    contact = relationship("Contact", back_populates="contact_sources")

    __table_args__ = (
        Index("idx_sources_contact", "contact_id"),
        Index("idx_sources_source", "source"),
        UniqueConstraint("contact_id", "source", "source_id", name="uq_contact_source"),
    )


class DedupLog(Base):
    __tablename__ = "dedup_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    primary_contact_id = Column(String, nullable=False)
    duplicate_contact_id = Column(String, nullable=False)
    match_type = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    resolved_by = Column(String, default="auto")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())

    __table_args__ = (
        Index("idx_dedup_primary", "primary_contact_id"),
    )


class VipContact(Base):
    __tablename__ = "vip_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String, ForeignKey("contacts.id"), nullable=False, unique=True)
    relationship_type = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
