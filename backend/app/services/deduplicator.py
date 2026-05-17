"""Contact deduplication — ported from relmgr/deduplicator.py."""

DEDUP_EXACT = 0.9
DEDUP_REVIEW = 0.7


def _email_match(a: dict, b: dict) -> float:
    emails_a = {e["address"] for e in a.get("emails", []) if isinstance(e, dict)}
    emails_b = {e["address"] for e in b.get("emails", []) if isinstance(e, dict)}
    if emails_a & emails_b:
        return 1.0
    if emails_a and emails_b:
        for ea in emails_a:
            for eb in emails_b:
                if ea.split("@")[0] == eb.split("@")[0]:
                    return 0.85
    return 0.0


def _name_match(a: dict, b: dict) -> float:
    name_a = a.get("normalized_name", "").lower().strip()
    name_b = b.get("normalized_name", "").lower().strip()
    if not name_a or not name_b:
        return 0.0
    if name_a == name_b:
        return 1.0
    a_parts = set(name_a.replace(",", "").split())
    b_parts = set(name_b.replace(",", "").split())
    if a_parts and b_parts:
        overlap = len(a_parts & b_parts) / max(len(a_parts), len(b_parts))
        if overlap >= 0.8:
            return overlap
    return 0.0


def match_contacts(a: dict, b: dict) -> tuple[float, str]:
    """Compute match score between two contacts."""
    email_score = _email_match(a, b)
    name_score = _name_match(a, b)
    total = 0.5 * email_score + 0.5 * name_score
    primary = "email" if email_score >= name_score else "name"
    return (round(total, 3), primary)


def find_duplicates(contacts: list[dict]) -> list[tuple]:
    """Find duplicate pairs. Returns [(primary, dup, score, match_type)]."""
    duplicates = []
    n = len(contacts)
    for i in range(n):
        for j in range(i + 1, n):
            score, match_type = match_contacts(contacts[i], contacts[j])
            if score >= DEDUP_REVIEW:
                duplicates.append((contacts[i], contacts[j], score, match_type))
    return duplicates
