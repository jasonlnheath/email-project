# Plan: Improve Bottom Metrics — Pareto-Focused Attack

## Goal

Raise the composite quality score from **0.601 (C grade)** to **≥0.80 (B+ grade)** by targeting the 20% of changes that drive 80% of the improvement.

## Current State

| Metric | Score | Grade | Impact on Composite |
|--------|-------|-------|---------------------|
| Factual Consistency | 0.573 | D | 30% weight |
| Entity Preservation | 0.504 | D | 20% weight |
| Semantic Similarity | 0.908 | A | 10% weight |
| Hallucination Rate | 0.414 | F | 20% weight (inverted) |
| Action Item Preservation | 0.224 | F | 15% weight |
| Sentiment Preservation | — | — | 5% weight |
| **Composite** | **0.601** | **C** | |

## Pareto Analysis: Root Cause Mapping

### The 20% of changes driving 80% of improvement

All three worst metrics share **one root cause**: the summarizer prompt + API parameters are poorly tuned for structured extraction from the Qwen3.6-35B-A3B reasoning model.

| Metric | Root Cause | Fix Category |
|--------|-----------|--------------|
| Hallucination (0.414) | No anti-hallucination instructions in prompt; temperature=0.7 too creative | Prompt fix |
| Entity Preservation (0.504) | max_tokens=512 truncates reasoning model output; no entity verification step | Parameter fix |
| Action Item Preservation (0.224) | Generic prompt, no action patterns/examples; model defaults to empty arrays | Prompt fix |

**Key insight**: Factual consistency (0.573) and hallucination rate (0.414) are two sides of the same coin — both measure whether the summary faithfully represents the original. Fixing one fixes both.

### Why Semantic Similarity is already good (0.908)

The char-trigram hashing captures overall topic/meaning well. This metric doesn't need improvement — it's already an A.

## Proposed Approach: 4 Changes, One File

All changes go into **`summarizer.py`** — the single file that controls summarization quality.

### Change 1: Lower temperature + increase max_tokens (2 lines)

**File:** `summarizer.py`, `_call_llama_cpp()` method

```python
# BEFORE:
"temperature": 0.7,
"max_tokens": 512,

# AFTER:
"temperature": 0.1,
"max_tokens": 2048,
```

**Why:**
- Temperature 0.7 makes the model creative — fine for prose, terrible for structured extraction where you want deterministic, faithful output
- Qwen3.6-35B-A3B is a reasoning model that generates thinking blocks before the JSON response. At 512 tokens, the actual JSON gets truncated or the model runs out of space to think through entity extraction
- The skill docs note: "reasoning models need 2048+, not 512"

**Expected impact:**
- Hallucination rate: 0.414 → ~0.20 (−0.21)
- Entity preservation: 0.504 → ~0.65 (+0.15)
- Action item preservation: 0.224 → ~0.45 (+0.23)

### Change 2: Rewrite the prompt with anti-hallucination guardrails (1 block)

**File:** `summarizer.py`, `build_prompt()` method

Replace the current generic prompt with one that has:
1. **Explicit anti-fabrication instruction**: "ONLY extract entities and actions that appear EXPLICITLY in the email body. Do NOT infer, guess, or fabricate."
2. **Self-verification step**: "Before returning JSON, verify each entity appears in the original text."
3. **Action item patterns**: Provide concrete examples of what counts as an action item vs. general content
4. **Structured output format**: Make the expected JSON schema explicit with field descriptions

```python
prompt = (
    f"Analyze this email and extract structured information.\n\n"
    f"FROM: {sender}\n"
    f"SUBJECT: {subject}\n"
    f"DATE: {date}\n\n"
    f"BODY:\n{truncated_body}\n\n"
    "Extract the following and return ONLY valid JSON (no markdown, no extra text):\n"
    "- sender: the sender name/email\n"
    "- date: the email date string\n"
    "- subject: the email subject\n"
    "- key_entities: list of 3-8 concrete entities EXTRACTED FROM THE EMAIL BODY. "
    "Include: person names, company names, product names, specific dates, dollar amounts, "
    "account numbers, file names, URLs. DO NOT invent or infer entities not explicitly stated.\n"
    "- action_items: list of 0-5 specific actions requested or required. "
    "An action item is a REQUEST, DEADLINE, or TASK directed at someone. "
    "Examples: 'Reply by Friday', 'Review attached PDF', 'Call Sarah at (555) 123-4567'. "
    "Do NOT include general statements like 'Please review' without specifics.\n"
    "- sentiment: one of 'positive', 'negative', 'neutral'\n\n"
    "CRITICAL RULES:\n"
    "1. ONLY extract what appears in the email body. Do NOT guess or infer.\n"
    "2. If an entity/action is not explicitly stated, omit it — do NOT fabricate.\n"
    "3. Dollar amounts must include the $ sign and exact figure from the email.\n"
    "4. Phone numbers must match exactly as written in the email.\n"
    "5. Dates must match exactly (e.g., 'March 15' not 'mid-March').\n"
    "6. If the email has no real content (spam/promotional), set key_entities=[] and action_items=[].\n"
    "7. Return JSON only, no other text.\n"
)
```

**Why:** The current prompt is too permissive. It says "extract key entities" but doesn't constrain the model to only what's in the text. This is the #1 cause of hallucination.

**Expected impact:**
- Hallucination rate: 0.414 → ~0.15 (−0.26)
- Factual consistency: 0.573 → ~0.75 (+0.18)

### Change 3: Add self-verification pass (new method)

**File:** `summarizer.py`, add `_verify_summary()` method

After the LLM returns JSON, run a lightweight verification step that:
1. Checks each entity against the original email body using substring matching
2. Flags entities not found in the body for removal
3. Returns the cleaned summary

```python
def _verify_summary(self, summary: Dict, email: Dict) -> Dict:
    """Verify extracted entities/actions against original email body."""
    body = (email.get("body") or "").lower()
    
    # Verify key_entities — remove any not found in body
    verified_entities = []
    for entity in summary.get("key_entities", []):
        entity_lower = str(entity).lower()
        if len(entity_lower) > 2 and entity_lower in body:
            verified_entities.append(entity)
        # If not in body, it's likely hallucinated — drop it silently
    
    # Verify action_items similarly
    verified_actions = []
    for action in summary.get("action_items", []):
        action_lower = str(action).lower()
        if len(action_lower) > 3 and action_lower in body:
            verified_actions.append(action)
    
    summary["key_entities"] = verified_entities
    summary["action_items"] = verified_actions
    return summary
```

**Why:** This catches hallucinations at the post-processing level. Even if the LLM generates a fake entity, the verification step removes it before it reaches the tier files.

**Expected impact:**
- Hallucination rate: further reduced to ~0.05 (near-zero)
- Entity preservation: slight decrease (we drop fake entities), but factual consistency improves significantly

### Change 4: Add entity extraction pre-filter (regex-based)

**File:** `summarizer.py`, add `_pre_extract_entities()` method

Before sending to the LLM, run regex-based entity extraction on the body and include these in the prompt as "anchors" — giving the model concrete evidence of what's in the text.

```python
def _pre_extract_entities(self, body: str) -> Dict[str, List[str]]:
    """Extract concrete entities from body using regex as anchors for the LLM."""
    import re
    entities = {"money": [], "phones": [], "dates": [], "urls": [], "names": []}
    
    # Money
    entities["money"] = list(set(re.findall(r'\$[\d,]+(?:\.\d{2})?', body)))
    # Phone numbers
    entities["phones"] = list(set(re.findall(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', body)))
    # URLs
    entities["urls"] = list(set(re.findall(r'https?://[^\s<>]+|www\.[^\s<>]+', body)))
    # Dates (common patterns)
    date_matches = re.findall(
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}',
        body, re.IGNORECASE
    )
    entities["dates"].extend(date_matches)
    
    return entities
```

Then include these in the prompt: "Here are concrete entities found in this email — use these as anchors when building your summary."

**Why:** This gives the LLM ground-truth anchors. Instead of guessing what entities exist, it sees them explicitly listed and can verify/expand on them.

**Expected impact:**
- Entity preservation: 0.504 → ~0.75 (+0.25)
- Hallucination rate: further reduced (fewer invented entities)

## Expected Impact Summary

| Metric | Current | After Changes | Delta |
|--------|---------|---------------|-------|
| Factual Consistency | 0.573 | ~0.80 | +0.23 |
| Entity Preservation | 0.504 | ~0.75 | +0.25 |
| Semantic Similarity | 0.908 | ~0.92 | +0.01 (already good) |
| Hallucination Rate | 0.414 | ~0.05 | −0.36 |
| Action Item Preservation | 0.224 | ~0.55 | +0.33 |
| Sentiment Preservation | — | ~0.85 | (estimated) |
| **Composite Score** | **0.601** | **~0.82** | **+0.22** |

**Target: B+ grade (≥0.80)**

## Files to Change

- **`summarizer.py`** — All 4 changes (prompt rewrite, temperature/token fix, verification pass, pre-extraction)
- **`tests/test_summarizer.py`** — Add tests for the new methods and verify existing tests still pass

## Tests / Validation

```bash
cd /home/jason/.hermes/emails && python -m pytest tests/test_summarizer.py -v
```

Then re-run evaluation:
```bash
cd /home/jason/.hermes/emails && python3 evaluate_compression.py
```

Compare `evaluation_results.json` before and after.

## Risks & Tradeoffs

1. **max_tokens=2048 increases cost**: Each LLM call uses more tokens. With ~35 emails per batch, that's ~70K extra tokens per run. Acceptable for quality improvement.
2. **Verification pass adds latency**: Substring matching is fast (O(n*m) but n,m are small), adds ~50ms per email. Negligible.
3. **Pre-extraction adds prompt length**: The anchor entities add ~200 chars to each prompt. The LLM has a large context window so this is fine.
4. **Over-verification could drop valid entities**: If an entity appears in the body but with slightly different casing/formatting, substring match might miss it. Mitigation: use `.lower()` comparison and fuzzy matching for names.

## Open Questions

1. Should we also add a second LLM pass (separate call) for verification, or is regex-based verification sufficient?
2. Should entity pre-extraction be configurable (enabled by default, toggleable)?
3. How do we handle HTML emails where entity extraction from the raw body might pick up HTML artifacts?

## Implementation Order

1. **Change 1** (temperature + max_tokens) — 2 lines, lowest risk, immediate effect
2. **Change 2** (prompt rewrite) — medium effort, highest impact on hallucination
3. **Change 3** (verification pass) — new method, catches remaining hallucinations
4. **Change 4** (pre-extraction anchors) — bonus improvement for entity preservation

Run tests after each change to catch regressions early.
