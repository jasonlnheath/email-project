# Email Summarization Pipeline

## Overview
Batch processing system for Gmail email summarization with three-tier output and semantic search.

## Architecture

```
Gmail API → Fetch Emails → Hybrid Extract → Tier Generation → Search Index
              ↓
         email_bodies_cache.json (500 emails)
              ↓
    hybrid_extract.py (478 processed)
              ↓
    tier1.jsonl (190K) - Tiny summaries
    tier2.jsonl (661K) - Medium summaries  
    tier3.jsonl (1.2M) - Full detailed summaries
```

## Components

### 1. Hybrid Extract (`hybrid_extract.py`)
- Regex-based entity extraction (names, amounts, dates, URLs, phones)
- LLM-powered purpose summarization
- Subject keyword extraction with stop word filtering
- Action item detection via heuristics

### 2. Queue System (`queue_system.py`)
- Pull-based architecture to avoid timeouts
- SQLite-backed job queue with status tracking
- Server poller that processes jobs at its own pace
- Client API for adding jobs and checking results

### 3. Retrieval API (`retrieval_api.py`)
- Tiered search across all three summary levels
- Sender filtering with partial match support
- Date range filtering
- Pagination support
- Export to JSON or CSV formats

### 4. TF-IDF Ranking (`tfidf_ranking.py`)
- Advanced semantic search using TF-IDF vectorization
- Cosine similarity scoring
- Document indexing and maintenance
- Batch operations for efficient updates

### 5. Incremental Updates (`incremental_update.py`)
- Sync new emails from Gmail
- Change detection (added, updated, deleted)
- Duplicate resolution
- Update logging and history tracking

## Usage

### Search Emails
```bash
# Basic search
python3 search_emails.py "budget meeting deadline" --tier tier1 --top 5

# Medium detail search
python3 search_emails.py "meeting tomorrow" --tier tier2 --top 10

# Full detail search
python3 search_emails.py "package delivery" --tier tier3 --top 5
```

### Query Results
Each result includes:
- Email ID, subject, sender, date
- Summary purpose (LLM-generated)
- Action required flag
- Tier-specific details (tier1=tiny, tier2=medium, tier3=full)

## Data Structure

### Tier1 (Tiny - 190K)
```json
{
  "email_id": "...",
  "subject": "...",
  "sender": "...",
  "date": "...",
  "summary_purpose": "...",
  "has_action_required": false,
  "tier": "tier1"
}
```

### Tier2 (Medium - 661K)
- All tier1 fields +
- `summary_key_details` (first 3)
- `summary_entities` (names, dates only)

### Tier3 (Full - 1.2M)
- All tier2 fields +
- Complete entity extraction
- Action items list
- Full metadata

## Test Coverage
- **48 tests** for hybrid extract (all passing)
- **16 tests** for queue system (all passing)
- **19 tests** for retrieval API (all passing)
- **9 tests** for TF-IDF ranking (all passing)
- **6 tests** for incremental updates (all passing)
- **Total: 98 tests** covering TDD cycle

## Current State
- ✅ 500 emails cached
- ✅ 478 processed with meaningful content
- ✅ 22 skipped (metadata-only)
- ✅ Three tiers generated
- ✅ Search index built and tested
- ✅ Retrieval interface/API complete
- ✅ TF-IDF + cosine similarity ranking implemented
- ✅ Incremental update system ready
- ⏳ Next: Integrate Gmail API for live sync
