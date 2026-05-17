"""Contacts sync, dedupe, VIP routes."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import async_session, Contact, ContactSource, DedupLog, VipContact
from ..routes.auth import _get_google_id, get_user_by_google_id
from ..services.normalizer import normalize_contact
from ..services.deduplicator import find_duplicates, DEDUP_EXACT

router = APIRouter()


@router.post("/sync")
async def sync_contacts(request: Request, db: AsyncSession = Depends(lambda: async_session())):
    """Import Google contacts, normalize, dedupe, store."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    body = await request.json()
    raw_contacts = body.get("contacts", [])
    if not raw_contacts:
        raise HTTPException(400, "No contacts provided")

    # Normalize all contacts
    normalized = [normalize_contact(c, source="google") for c in raw_contacts]

    # Deduplicate
    dupes = find_duplicates(normalized)
    dup_ids = set()
    for primary, dup, score, match_type in dupes:
        if score >= DEDUP_EXACT:
            dup_ids.add(id(dup))

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    merged = 0

    for contact_data in normalized:
        if id(contact_data) in dup_ids:
            merged += 1
            continue

        cid = str(uuid.uuid4())
        contact = Contact(
            id=cid,
            user_id=user.id,
            normalized_name=contact_data["normalized_name"],
            first_name=contact_data["first_name"],
            last_name=contact_data["last_name"],
            emails=json.dumps(contact_data["emails"]),
            phones=json.dumps(contact_data["phones"]),
            organizations=json.dumps(contact_data.get("organizations", [])),
            sources=json.dumps([contact_data["source"]]),
            created_at=now,
            updated_at=now,
        )
        db.add(contact)

        source = ContactSource(
            contact_id=cid,
            source=contact_data["source"],
            source_id=contact_data["source_id"],
            raw_data=json.dumps(contact_data.get("raw_data", {})),
            fetched_at=now,
        )
        db.add(source)
        inserted += 1

    await db.commit()

    return {
        "imported": inserted,
        "merged": merged,
        "total_raw": len(raw_contacts),
    }


@router.get("/")
async def list_contacts(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(lambda: async_session()),
):
    """List contacts with optional search."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    stmt = select(Contact).where(Contact.user_id == user.id, Contact.is_duplicate == False)
    if q:
        stmt = stmt.where(Contact.normalized_name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Contact.normalized_name)

    rows = (await db.execute(stmt)).scalars().all()
    return {
        "contacts": [
            {
                "id": c.id,
                "name": c.normalized_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "emails": json.loads(c.emails),
                "phones": json.loads(c.phones),
                "is_vip": c.is_vip,
            }
            for c in rows
        ],
        "count": len(rows),
    }


@router.put("/{contact_id}/vip")
async def toggle_vip(contact_id: str, request: Request, db: AsyncSession = Depends(lambda: async_session())):
    """Toggle VIP flag on a contact."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    contact = (await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == user.id)
    )).scalar_one_or_none()

    if not contact:
        raise HTTPException(404, "Contact not found")

    body = await request.json()
    is_vip = body.get("is_vip", not contact.is_vip)
    relationship = body.get("relationship_type", "")

    contact.is_vip = is_vip
    if is_vip:
        existing = (await db.execute(
            select(VipContact).where(VipContact.contact_id == contact_id)
        )).scalar_one_or_none()
        if not existing:
            db.add(VipContact(contact_id=contact_id, relationship_type=relationship))
        elif relationship:
            existing.relationship_type = relationship
    else:
        existing = (await db.execute(
            select(VipContact).where(VipContact.contact_id == contact_id)
        )).scalar_one_or_none()
        if existing:
            await db.delete(existing)

    await db.commit()
    return {"ok": True, "is_vip": is_vip}


@router.get("/vip")
async def list_vip(request: Request, db: AsyncSession = Depends(lambda: async_session())):
    """List VIP contacts only."""
    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    rows = (await db.execute(
        select(Contact, VipContact)
        .join(VipContact, VipContact.contact_id == Contact.id)
        .where(Contact.user_id == user.id, Contact.is_duplicate == False)
    )).all()

    return {
        "contacts": [
            {
                "id": contact.id,
                "name": contact.normalized_name,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "emails": json.loads(contact.emails),
                "relationship_type": vip.relationship_type,
            }
            for contact, vip in rows
        ],
        "count": len(rows),
    }
