"""Email enrichment — classification, tier assignment, newsletter detection.

Ported from email_dashboard.py enrichment logic.
"""

import re


def extract_sender_email(from_field: str) -> tuple[str, str]:
    """Extract (email_address, display_name) from a From header."""
    match = re.search(r"<([^>]+)>", from_field)
    if match:
        return match.group(1).lower().strip(), from_field.split("<")[0].strip().strip('"')
    parts = from_field.split("<")
    if len(parts) > 1:
        return parts[-1].rstrip(">").lower().strip(), parts[0].strip().strip('"')
    return from_field.lower().strip(), from_field


def is_newsletter_email(email: dict) -> bool:
    categories = {"CATEGORY_UPDATES", "CATEGORY_PROMOTIONS"}
    keywords = ["newsletter", "subscribe", "unsubscribe", "mailing", "campaign", "digest"]
    labels = set(email.get("labels", []))
    snippet = f"{email.get('subject', '')} {email.get('snippet', '')}".lower()
    return bool(labels & categories) or any(kw in snippet for kw in keywords)


def is_school_email(email: dict) -> bool:
    keywords = ["school", "edu", "class", "teacher", "student", "parent"]
    text = f"{email.get('from', '')} {email.get('subject', '')} {email.get('snippet', '')}".lower()
    return any(kw in text for kw in keywords)


def extract_unsubscribe_url(headers: dict) -> str | None:
    """Extract unsubscribe URL from List-Unsubscribe header."""
    for h_name, h_value in headers.items():
        if h_name.lower() == "list-unsubscribe":
            urls = re.findall(r"<([^>]+)>", h_value)
            if urls:
                return urls[0]
    return None


def get_priority(email: dict, vip_map: dict) -> tuple[str, int, dict | None]:
    """Determine priority tier: (tier_name, tier_order, vip_info)."""
    from_field = email.get("from", "")
    sender_email, display_name = extract_sender_email(from_field)

    vip_info = vip_map.get(sender_email)
    if not vip_info and display_name:
        vip_info = vip_map.get(f"vip_name_{display_name.lower()}")

    if vip_info:
        return ("VIP_HIGH", 0, vip_info)

    high_keywords = [
        "school", "trip", "deadline", "payment", "due", "security", "alert",
        "password", "login", "transaction", "bank", "financial", "urgent",
    ]
    text = f"{email.get('subject', '')} {email.get('snippet', '')}".lower()
    labels = set(email.get("labels", []))

    if any(kw in text for kw in high_keywords):
        return ("HIGH", 1, None)

    if labels & {"CATEGORY_UPDATES"}:
        return ("MEDIUM", 2, None)

    if labels & {"CATEGORY_PROMOTIONS"}:
        return ("LOW", 3, None)

    newsletter_kw = ["newsletter", "unsubscribe", "mailing", "campaign", "digest", "promo"]
    if any(kw in text for kw in newsletter_kw):
        return ("LOW", 3, None)

    return ("MEDIUM", 2, None)


def build_vip_map(vip_contacts: list[dict], all_contacts: list[dict]) -> dict:
    """Build a lookup map from VIP contact emails/names to their info.

    vip_contacts: list of dicts with 'contact_id', 'relationship_type'
    all_contacts: list of dicts with 'id', 'normalized_name', 'emails' (JSON string)
    """
    import json

    contact_by_id = {c["id"]: c for c in all_contacts}
    vip_map = {}

    for vip in vip_contacts:
        cid = vip["contact_id"]
        rel_type = vip.get("relationship_type", "")
        contact = contact_by_id.get(cid)
        if not contact:
            continue

        name = contact.get("normalized_name", "")
        emails_raw = contact.get("emails", "[]")
        try:
            emails_list = json.loads(emails_raw) if isinstance(emails_raw, str) else emails_raw
        except (json.JSONDecodeError, TypeError):
            emails_list = []

        for e in emails_list:
            addr = e.get("address", "").lower().strip() if isinstance(e, dict) else ""
            if addr:
                vip_map[addr] = {"name": name, "relationship_type": rel_type}

        if name:
            vip_map[f"vip_name_{name.lower()}"] = {
                "name": name,
                "relationship_type": rel_type,
                "by_name": True,
            }

    return vip_map


def enrich_batch(raw_emails: list[dict], vip_map: dict) -> list[dict]:
    """Enrich a batch of emails with tiers, newsletter flags, and VIP info."""
    enriched = []
    for e in raw_emails:
        tier_name, tier_order, vip_info = get_priority(e, vip_map)
        summary = e.get("summary") or e.get("snippet", "")
        headers = e.get("headers", {})
        unsub_url = extract_unsubscribe_url(headers) if isinstance(headers, dict) else None

        enriched.append({
            **e,
            "tier": tier_name,
            "tier_order": tier_order,
            "vip_info": vip_info,
            "summary": summary,
            "is_newsletter": is_newsletter_email(e),
            "is_school": is_school_email(e),
            "unsubscribe_url": unsub_url,
        })

    enriched.sort(key=lambda x: x["tier_order"])
    return enriched
