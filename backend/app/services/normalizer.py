"""Contact normalization — ported from relmgr/normalizer.py."""

import re
from typing import Optional


def normalize_name(raw: str) -> tuple[str, str, str]:
    """Parse raw name into (normalized, first_name, last_name)."""
    if not raw or not raw.strip():
        return ("", "", "")

    raw = raw.strip()
    titles = {"dr", "prof", "mr", "mrs", "ms", "miss", "rev", "hon"}
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v", "the 2nd", "the third"}

    if "," in raw:
        comma_idx = raw.index(",")
        last = raw[:comma_idx].strip().rstrip(".")
        rest = raw[comma_idx + 1:].strip()
        while rest and rest.split()[0].lower() in titles:
            rest = " ".join(rest.split()[1:])
        while rest and rest.split()[-1].lower() in suffixes:
            rest = " ".join(rest.split()[:-1])
        first = rest.strip()
        return (f"{last}, {first}", first, last)

    parts = re.split(r"\s+", raw)
    parts = [p.strip().strip(".") for p in parts if p.strip()]
    while parts and parts[0].lower() in titles:
        parts.pop(0)
    while parts and parts[-1].lower() in suffixes:
        parts.pop()

    if len(parts) == 0:
        return (raw, "", "")

    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    normalized = f"{last}, {first}" if last else first
    return (normalized, first, last)


def normalize_email(raw) -> Optional[dict]:
    if not raw:
        return None
    if isinstance(raw, dict):
        address = raw.get("value", raw.get("address", ""))
        email_type = raw.get("type", "other")
        if not address or "@" not in str(address):
            return None
        address = str(address).lower()
        domain = address.split("@")[-1]
        personal = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com"}
        if domain in personal:
            email_type = "personal"
        elif email_type == "other":
            email_type = "work"
        return {"address": address, "type": email_type}
    if isinstance(raw, str):
        email = raw.strip().lower()
        if not email or "@" not in email:
            return None
        domain = email.split("@")[-1]
        email_type = "personal" if domain in {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"} else "work"
        return {"address": email, "type": email_type}
    return None


def normalize_phone(raw) -> Optional[str]:
    if not raw or not raw.strip():
        return None
    raw = raw.strip()
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else None


def normalize_contact(raw: dict, source: str = "google") -> dict:
    """Normalize a raw contact from any source."""
    raw_name = raw.get("name", raw.get("displayName", raw.get("display_name", "")))
    normalized_name, first_name, last_name = normalize_name(raw_name)

    raw_emails = raw.get("emails", raw.get("emailAddresses", []))
    if isinstance(raw_emails, str):
        raw_emails = [{"value": raw_emails}]
    emails = [e for e in (normalize_email(e) for e in raw_emails) if e]

    raw_phones = raw.get("phones", raw.get("phoneNumbers", []))
    if isinstance(raw_phones, str):
        raw_phones = [{"value": raw_phones}]
    phones = [{"number": normalize_phone(p.get("value", p) if isinstance(p, dict) else p), "type": "other"}
              for p in raw_phones if normalize_phone(p.get("value", p) if isinstance(p, dict) else p)]

    return {
        "normalized_name": normalized_name,
        "first_name": first_name,
        "last_name": last_name,
        "emails": emails,
        "phones": phones,
        "organizations": [],
        "source": source,
        "source_id": raw.get("id", raw.get("resourceName", "")),
        "raw_data": raw,
    }
