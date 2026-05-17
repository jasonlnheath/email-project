"""Email enrichment routes."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import async_session, Contact, VipContact
from ..routes.auth import _get_google_id, get_user_by_google_id
from ..services.enrichment import enrich_batch, build_vip_map

router = APIRouter()


async def _load_vip_map(user_id: str, db: AsyncSession) -> dict:
    """Load VIP contact lookup map for a user."""
    vip_rows = (await db.execute(
        select(VipContact).where(VipContact.contact_id == Contact.id)
        .where(Contact.user_id == user_id)
    )).scalars().all()

    # Get all contacts for this user that are VIP
    contact_ids = [v.contact_id for v in vip_rows]
    if not contact_ids:
        return {}

    contacts = (await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )).scalars().all()

    vip_data = [{"contact_id": v.contact_id, "relationship_type": v.relationship_type} for v in vip_rows]
    contact_data = [
        {"id": c.id, "normalized_name": c.normalized_name, "emails": c.emails}
        for c in contacts
    ]
    return build_vip_map(vip_data, contact_data)


@router.post("/enrich")
async def enrich_emails(request: Request, db: AsyncSession = Depends(lambda: async_session())):
    """Classify + enrich a batch of emails."""
    body = await request.json()
    emails = body.get("emails", [])
    if not emails:
        raise HTTPException(400, "No emails provided")

    google_id = _get_google_id(request)
    user = await get_user_by_google_id(google_id, db)
    if not user:
        raise HTTPException(404, "User not found")

    vip_map = await _load_vip_map(user.id, db)
    enriched = enrich_batch(emails, vip_map)

    return {"emails": enriched, "count": len(enriched)}
