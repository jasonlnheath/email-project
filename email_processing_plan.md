# Email Processing Plan — Hybrid Extraction + Queue-Based Server

## Current State (as of 2026-05-12)

### Data Status
- **Total cached emails**: 500 with bodies
- **Processed records**: 478 in tier3.jsonl
- **Records with purpose**: 474/478 (99%)
- **Records with entities**: 359/478 (75%)
- **Records with actions**: 101/478 (21%)
- **Remaining to process**: ~22 emails

### Retrieval Performance
| Metric | Score |
|--------|-------|
| Recall@5 | 72.0% |
| Precision@5 | 14.4% |
| Entity URL recall | 98.7% |
| Entity name recall | 77.5% |
| Entity amount recall | 69.5% |
| Entity date recall | 62.6% |
| Avg latency | 0.6ms |

### Server Status
- **Model**: Qwen3.6-35B-A3B-UD-Q4_K_M.gguf (reasoning model)
- **Average response time**: ~12 seconds per email
- **Throughput**: ~0.08 emails/sec with 2 concurrent slots
- **Timeout behavior**: HTTP 502 when server is overloaded
- **Output format**: reasoning_content only, content field empty

---

## Phase 1: Complete Remaining Extraction (Immediate)

### Goal: Process the remaining ~22 emails

**Approach:**
1. Use `run_hybrid_2slots.py` with reduced concurrency (1 slot) to avoid overwhelming the server
2. Add exponential backoff for retries on 502 errors
3. Process in small batches (5 at a time) with pauses between

**Commands:**
```bash
cd ~/.hermes/emails
# Run with 1 slot to be gentle on the server
python3 -c "
import json, time, threading
from hybrid_extract import process_email

with open('email_bodies_cache.json') as f:
    cache = json.load(f)

existing = {}
with open('tier3.jsonl') as f:
    for line in f:
        rec = json.loads(line)
        if rec.get('summary_purpose', '').strip():
            existing[rec['email_id']] = rec

remaining = [(eid, data) for eid, data in cache.items() 
             if eid not in existing and len(data.get('body', '')) >= 20]

print(f'Remaining: {len(remaining)}')

for i, (eid, data) in enumerate(remaining):
    subject = data.get('subject', '')
    body = data.get('body', '')
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = process_email(eid, subject, body)
            print(f'[{i+1}/{len(remaining)}] {eid[:8]}... OK')
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f'[{i+1}/{len(remaining)}] {eid[:8]}... retrying in {wait}s ({e})')
                time.sleep(wait)
            else:
                print(f'[{i+1}/{len(remaining)}] {eid[:8]}... FAILED: {e}')
" 2>&1
```

---

## Phase 2: Queue-Based Server Architecture (Medium Term)

### Problem
Current push-based approach causes server overload and timeouts. We need a pull-based system where the server pulls jobs when ready.

### Solution: Job Queue with Server Polling

**Architecture:**
```
[Client] --POST /jobs--> [Queue DB] <--GET /jobs?status=pending-- [Server]
                              |                                      |
                              v                                      v
                         [Results DB] <--POST /results-- [Server processes job]
```

**Implementation:**

1. **Queue Database** (SQLite):
   ```sql
   CREATE TABLE jobs (
       id TEXT PRIMARY KEY,
       email_id TEXT NOT NULL,
       subject TEXT,
       body TEXT,
       status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
       result TEXT,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       started_at TIMESTAMP,
       completed_at TIMESTAMP,
       retry_count INTEGER DEFAULT 0
   );
   
   CREATE TABLE results (
       email_id TEXT PRIMARY KEY,
       summary_purpose TEXT,
       summary_entities TEXT,
       summary_action_items TEXT,
       processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

2. **Server-side polling** (runs on sons-pc):
   ```python
   # server_poll.py - runs continuously on the LLM server
   import time, json
   from urllib.request import Request, urlopen
   
   QUEUE_URL = "http://localhost:8081/jobs"
   RESULT_URL = "http://localhost:8081/results"
   
   while True:
       # Get next pending job
       try:
           req = Request(f"{QUEUE_URL}?status=pending&limit=1")
           response = urlopen(req, timeout=5)
           job = json.loads(response.read())
           
           if not job:
               time.sleep(2)  # No jobs, wait
               continue
           
           # Process the job
           result = process_email(job['email_id'], job['subject'], job['body'])
           
           # Submit result
           payload = json.dumps({
               'email_id': job['email_id'],
               'result': result
           }).encode()
           req = Request(f"{RESULT_URL}", data=payload, method='POST')
           urlopen(req, timeout=10)
           
       except Exception as e:
           print(f"Error: {e}")
           time.sleep(5)
   ```

3. **Client-side queue management**:
   ```python
   # queue_client.py - runs on this machine
   import json
   
   def add_jobs_to_queue(email_ids):
       """Add emails to the queue for processing."""
       for eid in email_ids:
           # Check if already processed
           if is_completed(eid):
               continue
           
           # Add to queue
           req = Request("http://localhost:8081/jobs", 
                        data=json.dumps({'email_id': eid}).encode(),
                        method='POST')
           urlopen(req, timeout=5)
   
   def get_completion_status():
       """Check how many jobs are completed."""
       req = Request("http://localhost:8081/status")
       response = urlopen(req, timeout=5)
       return json.loads(response.read())
   ```

**Benefits:**
- Server controls its own processing rate
- No more timeouts from pushing too fast
- Easy to monitor progress
- Can run server-side polling as a background service
- Client can add jobs whenever ready, server processes at its own pace

---

## Phase 3: Optimization & Scaling (Long Term)

### A. Reduce LLM Calls

**Current approach:** 1 LLM call per email for purpose summary
**Optimization:** Batch multiple emails into one LLM call

```python
def batch_summarize(emails):
    """Summarize multiple emails in one LLM call."""
    prompt = "\n\n".join([
        f"Email {i+1}:\nSubject: {e['subject']}\nBody: {e['body'][:500]}\n"
        for i, e in enumerate(emails)
    ])
    
    prompt += "\n\nFor each email, provide: 1) One-sentence purpose, 2) Key entities"
    
    # Single LLM call returns all summaries
    response = call_llm(prompt)
    return parse_batch_response(response)
```

**Expected improvement:** 3-5x throughput increase (one call for 3-5 emails instead of 3-5 separate calls)

### B. Improve Entity Extraction

**Current regex patterns miss:**
- Email addresses (need to add)
- Organization names (need NER or keyword matching)
- Project names (context-dependent)
- Relative dates ("next week", "tomorrow") → convert to absolute

**Additions:**
```python
# Email pattern
re.findall(r'[\w\.-]+@[\w\.-]+', text)

# Organization keywords
org_patterns = [r'\b(?:Inc|LLC|Corp|Ltd|Co)\b', r'\b(?:Department|Division|Office)\b']

# Relative date conversion
date_mapping = {
    'today': '2026-05-12',
    'tomorrow': '2026-05-13',
    'yesterday': '2026-05-11',
    'next week': '2026-05-19',
    'last week': '2026-05-05'
}
```

### C. Tiered Processing Strategy

**Tier 1 (High Priority):** Recent emails (last 7 days) + flagged emails
**Tier 2 (Medium Priority):** Emails with entities already extracted
**Tier 3 (Low Priority):** Everything else

Process tiers in order, so the most important emails are always available first.

### D. Monitoring & Alerting

Add progress tracking:
```python
def monitor_progress():
    total = get_total_emails()
    processed = get_processed_count()
    pending = total - processed
    
    print(f"Progress: {processed}/{total} ({100*processed/total:.1f}%)")
    print(f"Pending: {pending} emails")
    
    if pending == 0:
        print("All emails processed!")
        return False
    return True
```

---

## Phase 4: Retrieval Rate Improvements

### Current Bottlenecks
1. **Precision@5 is only 14.4%** — most retrieved results are irrelevant
2. **Entity date recall is 62.6%** — regex misses relative dates
3. **No semantic search** — only TF-IDF, no embeddings

### Solutions

**A. Add BM25 (better than TF-IDF for search):**
```python
from rank_bm25 import BM25Okapi
import nltk

bm25 = BM25Okapi([nltk.word_tokenize(text) for text in texts])
scores = bm25.get_scores(query_tokens)
```

**B. Add semantic search (embeddings):**
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(texts)

# Query embedding
query_emb = model.encode([query])[0]

# Cosine similarity
similarities = embeddings @ query_emb / (np.linalg.norm(embeddings) * np.linalg.norm(query_emb))
```

**C. Hybrid scoring:**
```python
final_score = 0.4 * bm25_score + 0.6 * semantic_score
```

### Expected Results
| Metric | Current | Target |
|--------|---------|--------|
| Recall@5 | 72.0% | 85%+ |
| Precision@5 | 14.4% | 30%+ |
| Entity date recall | 62.6% | 85%+ |

---

## Immediate Next Steps

1. **Complete remaining ~22 emails** (Phase 1) — ~5 minutes
2. **Implement queue-based architecture** (Phase 2) — 1-2 hours
3. **Add batch summarization** (Phase 3A) — 30 minutes
4. **Improve entity extraction** (Phase 3B) — 1 hour
5. **Add BM25 search** (Phase 4A) — 30 minutes

**Total estimated time:** 3-4 hours of focused work

---

## Key Lessons Learned

1. **Reasoning models need different prompts** — they output in reasoning_content, not content
2. **max_tokens matters** — 1024 is too low for reasoning models, use 2048+
3. **Regex is better than LLM for entities** — faster, more reliable, no timeouts
4. **Server overload is real** — need queue-based architecture, not push-based
5. **Hybrid approach works** — regex for entities + LLM for purpose = best results
6. **Monitoring is essential** — log everything, track progress, alert on failures
