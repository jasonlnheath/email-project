# Plan: Build Tier Pipeline — Connect Batch Output to Retrieval System

## Goal
Build the missing pipeline that converts batch pipeline checkpoint files into retrieval-ready tier JSONL files (tier1, tier2, tier3), enabling the existing `QueryRouter` to search across all three tiers.

## Current Context
- **Batch pipeline** (`batch_pipeline.py`) outputs `batch_output/checkpoint_*.json` files with full email objects
- **Retrieval system** (`retrieval.py`) expects `tier1.jsonl`, `tier2.jsonl`, `tier3.jsonl` on disk
- **No glue code existed** between these two subsystems
- The retrieval algorithms (BM25, TF-IDF+KNN, cluster routing) are correct and functional — they just had no data

## Proposed Approach
Create `tier_builder.py` that:
1. Reads checkpoint JSON → deduplicates by email_id
2. Writes tier1.jsonl (raw content for BM25)
3. Writes tier2.jsonl (summaries with entities/actions for TF-IDF search)
4. Runs clustering on tier2 → writes tier3.jsonl (cluster summaries)

## Files Created/Modified
- **NEW**: `tier_builder.py` — main pipeline module
- **NEW**: `test_tier_builder.py` — 11 tests covering all functionality
- **MODIFIED**: `retrieval.py` — fixed tier2 ID lookup bug (`email_id` → `id` fallback)

## Tests / Validation
- 11 new tests: tier building, tier loading, BM25 search, TF-IDF search, query routing, context window building
- All 349 tests pass (1 pre-existing BadZipFile failure unrelated to changes)
- End-to-end verification: built tiers from real checkpoint (790 emails → 10 unique after dedup), tested BM25 and TF-IDF search, confirmed context window generation

## Risks & Tradeoffs
- **Checkpoint data quality**: The checkpoint had only 10 unique emails repeated 79x each. Added dedup as a safety net in tier_builder. The root cause is in the fetcher's dedup logic.
- **Summary quality**: Tier2 summaries use SimpleSummarizer which produces key-value formatted text. Not ideal for semantic search but functional. Future improvement: use LLM-generated summaries.
- **Clustering silhouette**: Auto-detected k=10 with silhouette=1.0 on small datasets indicates overfitting. With real data (thousands of emails), this should stabilize.

## Next Steps
1. Fix the fetcher dedup bug (emails repeating in checkpoints)
2. Add an orchestrator script that runs `build_tiers()` automatically after each fetch
3. Integrate with the main agent loop so tiers are always fresh

## Root Cause Analysis

### Problem 1: Entity preservation at 0.273
- `_select_top_sentences_with_enforcement` enforces entities but is capped at `max_sentences=5`
- Entity boost values (0.15–0.3) are too small to overcome TF-IDF scores
- With only 5 sentences, most entities never appear in the selection pool
- **Result:** Names, dates, amounts, URLs get dropped because their containing sentences don't score high enough on TF-IDF

### Problem 2: Action item preservation at 0.418
- Only ONE action sentence guaranteed (`action_sentences[:1]`)
- Emails often have 2–4 action items ("Please review by Friday", "Contact Sarah about budget", "Submit report by Monday")
- **Result:** 2–3 action items silently dropped

### Problem 3: Hallucination rate at 0.506
- Generic sentences (boilerplate, pleasantries) score well on TF-IDF
- No penalty for sentences that contain zero unique entities or facts
- **Result:** Summaries are full of "Please review" and "Thank you" with no actual content

## Proposed Fixes (3 changes, all in `simple_summarizer.py`)

### Fix A: Increase entity boost weights + increase max_sentences

**File:** `simple_summarizer.py`
**Lines to change:** ~240–270 (`_score_sentences`) and `__init__` default

```python
# In __init__:
self.max_sentences = 8  # Was 5 — more room for entity-rich sentences

# In _score_sentences, increase entity boosts:
if has_money and re.search(r'\$[\d,]+(?:\.\d{2})?', sent_text):
    entity_bonus += 0.6  # Was 0.3 — money is critical
if has_phone and re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', sent_text):
    entity_bonus += 0.5  # Was 0.3 — phone numbers are critical
if has_date and re.search(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}', sent_text, re.IGNORECASE):
    entity_bonus += 0.4  # Was 0.2 — dates matter for meetings/deadlines
if has_url and re.search(r'https?://', sent_text):
    entity_bonus += 0.4  # Was 0.2 — URLs are hard to reconstruct
if has_name and re.search(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b', sent_text):
    entity_bonus += 0.35  # Was 0.15 — names are critical
if has_day and re.search(r'\b(Tuesday|Thursday|Wednesday|Monday|Friday|Saturday|Sunday)\b', sent_text, re.IGNORECASE):
    entity_bonus += 0.3  # Was 0.15 — day names anchor meeting times
```

**Why this works:** A sentence with money + date gets a 1.0 × (1.0+0.6+0.4) = 2.0x boost. This pushes entity-rich sentences above generic TF-IDF winners.

### Fix B: Guarantee ALL action sentences, not just one

**File:** `simple_summarizer.py`
**Lines to change:** ~319–330 (`_select_top_sentences_with_enforcement`)

```python
# OLD: Only guarantee first action sentence
if action_sentences and not any(asent in selected_set for asent in action_sentences):
    for asent in action_sentences[:1]:  # ← Only first one!
        ...

# NEW: Guarantee all action sentences (up to a reasonable limit)
if action_sentences:
    guaranteed = min(len(action_sentences), 3)  # Cap at 3 to avoid bloat
    for asent in action_sentences[:guaranteed]:
        if asent not in selected_set:
            if len(selected) >= n:
                to_remove = _find_lowest_scoring()
                if to_remove:
                    selected.remove(to_remove)
                    selected_set.discard(to_remove)
            selected.append(asent)
            selected_set.add(asent)
```

**Why this works:** If an email has 3 action items, all 3 get preserved. The cap of 3 prevents runaway bloat on emails with many action items.

### Fix B2 (bonus): Deduplicate boilerplate sentences before scoring

**File:** `simple_summarizer.py`
**Lines to add:** Before `_score_sentences`, filter out near-duplicate boilerplate

```python
# In _score_sentences, add at the top:
# Remove near-duplicate sentences (same core words, different formatting)
seen_core = set()
unique_sentences = []
for sent_text, pos in sentences:
    core = re.sub(r'\s+', ' ', sent_text.lower()).strip()
    if core not in seen_core:
        seen_core.add(core)
        unique_sentences.append((sent_text, pos))
return self._compute_scores(unique_sentences, full_text)  # rest of method
```

**Why this works:** Emails often have repeated "Thank you for your time" or "Please let me know" across forwarded/replied chains. Deduplication prevents these from taking up slots.

### Fix C (bonus): Add entity enforcement pass AFTER sentence selection

**File:** `simple_summarizer.py`
**Lines to change:** `_select_top_sentences_with_enforcement`

After the existing entity enforcement loop, add a second pass that's more aggressive:

```python
# Second enforcement pass: if entities still missing, pull from ALL remaining sentences
# This catches entities in low-scoring but factually critical sentences
for entity in critical_entities:
    if entity.lower() not in selected_text:
        # Find best sentence containing this entity (highest score among unselected)
        best_entity_sent = None
        best_entity_score = -1
        for score, sent_text, pos in scored:
            if entity in sent_text and sent_text not in selected_set:
                if score > best_entity_score:
                    best_entity_score = score
                    best_entity_sent = sent_text
        
        if best_entity_sent is not None:
            if len(selected) >= n:
                to_remove = _find_lowest_scoring()
                if to_remove:
                    selected.remove(to_remove)
                    selected_set.discard(to_remove)
            selected.append(best_entity_sent)
            selected_set.add(best_entity_sent)
        
        # Recalculate selected_text for next iteration
        selected_text = ' '.join(selected).lower()
```

**Why this works:** The existing enforcement only replaces the lowest-scoring selected sentence. This second pass ensures that even if an entity's containing sentence scored low, it still gets pulled in if it's missing from the summary.

## Expected Impact

| Metric | Current | After Fix | Delta |
|---|---|---|---|
| Entity preservation | 0.273 | ~0.55–0.65 | +0.30 |
| Action item preservation | 0.418 | ~0.70–0.80 | +0.30 |
| Hallucination rate | 0.506 | ~0.30–0.40 | -0.15 |
| **Composite score** | **0.562** | **~0.68–0.75** | **+0.12** |

## Files to Change
- `simple_summarizer.py` — all 3 fixes (lines ~68, ~240–270, ~319–330, ~280–336)

## Tests to Run
```bash
cd /home/jason/.hermes/emails && python -m pytest test_compression_quality.py -v
```

## Risks & Tradeoffs
- **More sentences = longer summaries** — Going from 5 to 8 sentences increases output length by ~60%. This reduces compression ratio slightly but improves quality. Acceptable tradeoff.
- **Entity boost too high?** — If entity-rich sentences dominate and push out all other content, we could get summaries that are just a list of entities. Mitigation: keep TF-IDF as the base score, only apply boosts multiplicatively (not additively).
- **Action item cap at 3** — Some emails have more than 3 action items. The cap prevents bloat but may drop some. Acceptable for now; can increase later if needed.

## Open Questions
1. Should `max_sentences` be adaptive based on email length? (e.g., 5 for <500 chars, 8 for 500–2000, 12 for >2000)
2. Should we also boost sentences that contain multiple entity types? (e.g., a sentence with both money AND date gets 1.0 × (1+0.6+0.4) = 2.0x)
3. Is the hallucination detection heuristic too aggressive? (50% hallucination rate seems high — might be the metric itself, not just the summarizer)
