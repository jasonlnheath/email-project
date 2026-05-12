# Email Context Compression Plan

## Goal
Fit thousands of emails into a 64K context window without losing retrieval quality, using a multi-tier compression strategy inspired by DeepSeek-V4's hybrid CSA/HCA attention architecture.

## Inspiration from DeepSeek V4 Paper

The DeepSeek V4 paper (58 pages, May 2026) provides architectural validation for our approach:

- **CSA (Compressed Sparse Attention)**: Compresses every `m=4` tokens into 1 KV entry, then uses a learned "Lightning Indexer" to select top-k most relevant compressed blocks per query
- **HCA (Heavily Compressed Attention)**: More aggressive — compresses every `m'=128` tokens into 1 entry with dense attention (no sparsity)
- **Hybrid interleaving**: CSA and HCA alternate across layers, giving fine-grained recent context + coarse-grained long-range coverage
- **Mixed precision**: BF16 for positional embeddings, FP8 for everything else → ~50% KV cache reduction
- **On-disk KV cache**: Compressed entries stored to disk; only incomplete tail blocks need recomputation
- **Training curriculum**: 4K → 16K → 64K → 1M tokens, introducing sparse attention after 1T dense tokens
- **Efficiency at scale**: At 1M context, achieves 27% of baseline FLOPs and 10% of KV cache size

**Key insight for us**: Blind compression loses retrieval quality. The Lightning Indexer (learned top-k selector) is critical — it routes attention to the most relevant compressed blocks. We need a similar learned or heuristic routing mechanism.

## Architecture

### Three-Tier Compression (analogous to CSA/HCA/SWA)

| Tier | Name | Analog | Compression | Retention |
|------|------|--------|-------------|-----------|
| 1 | **Raw** | SWA (Sliding Window Attention) | 1:1 (no compression) | Last ~50 emails (~5K tokens) |
| 2 | **Summarized** | CSA (Compressed Sparse Attention) | ~8-16:1 | Emails 51-500 (~400 emails, ~50K→3K tokens) |
| 3 | **Aggregated** | HCA (Heavily Compressed Attention) | ~50-100:1 | Emails 501+ (>400 emails, ~500K→5K tokens) |

### Tier Details

#### Tier 1: Raw (Recent Context)
- Last ~50 most recent emails stored verbatim
- ~5K tokens of raw text
- Directly accessible — no retrieval needed
- Analogous to DeepSeek's SWA (sliding window attention) with n_win=128

#### Tier 2: Summarized (Mid-Range)
- Each email compressed via LLM summarization (~8-16x compression)
- ~400 emails → ~3K tokens total
- Each summary includes: sender, date, subject, key entities, action items, sentiment
- Indexed by: sender, keywords, date, entities
- Analogous to CSA with m=4 compression + Lightning Indexer for sparse selection

#### Tier 3: Aggregated (Long-Tail)
- Grouped by month/quarter, then by topic clusters
- Each cluster gets a single paragraph summary
- ~500K raw tokens → ~5K tokens aggregated
- Includes: time range, topics covered, key people, outcomes, open threads
- Analogous to HCA with m'=128 aggressive compression

### Retrieval System

#### The "Lightning Indexer" Equivalent
Instead of a learned neural indexer, we use a multi-stage retrieval pipeline:

1. **Query decomposition**: Parse user question into entities, dates, senders, topics
2. **Tier 1 check**: Is the answer in the last 50 emails? (direct scan)
3. **Tier 2 vector search**: Embed query + search summarized email index (FAISS/Milvus)
4. **Tier 3 topic routing**: If query mentions old time periods or specific topics, route to relevant aggregated clusters
5. **On-demand decompression**: If a Tier 2 summary looks promising but needs detail, fetch the original email

#### Index Structure
```
email_compression_store/
├── raw/                    # Last N emails, verbatim
│   └── emails.jsonl        # {id, date, sender, subject, body, ...}
├── summaries/              # Compressed mid-range emails
│   ├── index.faiss         # FAISS vector index
│   └── embeddings.bin      # Embedding vectors
│   └── data.jsonl          # {id, summary, sender, date, entities, keywords, embedding_ref}
├── aggregated/             # Long-tail clusters
│   └── clusters.json       # {cluster_id, time_range, topics, people, summary, member_ids[]}
└── metadata.json           # Store counts, compression ratios, last update time
```

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Build email ingestion pipeline (read from Gmail API / local mailbox)
- [ ] Implement Tier 1 raw storage (last 50 emails verbatim)
- [ ] Create basic indexing by date, sender, subject
- [ ] Simple keyword search across raw tier

### Phase 2: Summarization Engine (Week 3-4)
- [ ] Design LLM summarization prompt (sender, date, entities, action items, sentiment)
- [ ] Batch summarize emails beyond the raw window
- [ ] Build FAISS vector index for semantic search
- [ ] Implement retrieval: query → embed → search summaries → return top-k

### Phase 3: Aggregation & Routing (Week 5-6)
- [ ] Cluster old emails by topic (using embeddings + clustering)
- [ ] Generate cluster-level summaries (time range, topics, people, outcomes)
- [ ] Implement multi-tier retrieval pipeline with on-demand decompression
- [ ] Build query router that decides which tier(s) to search

### Phase 4: Optimization (Week 7-8)
- [ ] Tune compression ratios per tier (balance context usage vs recall)
- [ ] Add learned reranking for retrieved summaries (the "Lightning Indexer" equivalent)
- [ ] Implement periodic re-summarization as new emails arrive
- [ ] Benchmark: recall@k across different query types, context window utilization

## Key Design Decisions & Trade-offs

### Compression Ratios
- **Tier 1**: 1:1 — raw text, ~50 emails
- **Tier 2**: ~10:1 average — LLM summaries with structured metadata
- **Tier 3**: ~100:1 average — cluster-level paragraph summaries

### Context Budget Allocation (64K tokens)
| Component | Tokens | % of Budget |
|-----------|--------|-------------|
| System prompt + instructions | ~2K | 3% |
| Tier 1 raw emails | ~5K | 8% |
| Tier 2 summaries (retrieved top-k) | ~15K | 23% |
| Tier 3 aggregated context | ~5K | 8% |
| Retrieved email bodies (on-demand) | ~20K | 31% |
| Conversation history | ~5K | 8% |
| Output / reasoning tokens | ~7K | 11% |
| Buffer / overhead | ~5K | 8% |

### Trade-offs
- **More raw emails** → better recent recall but less room for deep retrieval
- **Aggressive Tier 3 compression** → saves context but loses granular detail
- **On-demand decompression** → preserves quality but costs API calls and latency
- **Vector search vs keyword** → vector is more semantic but needs embedding model; keyword is faster but misses synonyms

## Evaluation Metrics
- **Recall@k**: Can we find the right email when asked about it? (measured against ground truth)
- **Context utilization**: % of 64K window used effectively vs wasted
- **Retrieval latency**: Time from query to relevant context
- **Summarization fidelity**: Does the summary preserve key facts? (human eval or LLM-as-judge)

## Attachment Handling

### Supported Formats & Extraction Methods

| Format | Method | Context Cost | Quality | Dependencies |
|--------|--------|-------------|---------|--------------|
| Text-based PDF | `pymupdf` → raw text | Low (~100 bytes/page) | Good | ✅ Already installed (`pymupdf`) |
| Scanned PDF (OCR) | `marker-pdf` → markdown | Medium (~500 bytes/page) | Excellent | Needs install (~5GB, PyTorch + models) |
| Images (.png/.jpg/.webp) | `vision_analyze()` / `browser_vision()` | Medium (per frame) | High (Qwen3.6 vision) | ✅ Built-in |
| PowerPoint (.pptx) | `markitdown[pptx]` → slide text + notes | Low-Medium | Good | Needs install (`pip install "markitdown[pptx]"`) |
| Excel (.xlsx) | `openpyxl` → cell values as CSV | Low | Good | Needs install (`pip install openpyxl`) |
| Word (.docx) | `python-docx` → structured text | Low | Excellent | Needs install (`pip install python-docx`) |
| Audio (.mp3/.wav/.ogg) | `faster-whisper` → STT transcript | Medium (depends on length) | Good | **NOT installed** — needs install (`pip install faster-whisper`) |
| Video (.mp4/.mov) | Extract key frames → `vision_analyze()` | High (per frame) | Limited (frame-level, no temporal reasoning) | Built-in vision; frame extraction via `ffmpeg` |

### ⚠️ Whisper Status

The Hermes config has `stt.enabled: true` with `provider: local`, but **no Whisper binary or Python package is actually installed**. The STT system is configured but non-functional. To enable audio/video transcript extraction, we need to install `faster-whisper` (recommended for speed/memory efficiency).

### Retrieval Strategy: Manifest + On-Demand Fetching

Analogous to DeepSeek V4's on-disk KV cache — attachments are never fully materialized in the context window upfront. Instead:

1. **Manifest Phase** (always): Parse attachment metadata → manifest entry
   - Filename, type, size, page count (PDFs), slide count (PPTX), sheet names (Excel)
   - Cost: ~50-100 bytes per attachment
2. **On-Demand Extraction** (when needed): Extract content only when context is required
   - PDF → `pymupdf` text extraction → summarize if >1 page
   - PPTX → extract slide text + speaker notes → summarize if >5 slides
   - Excel → read cells as CSV → summarize table structure + key values
   - Word → parse document structure → summarize sections
   - Audio → STT transcript → summarize key points
   - Video → extract representative frames → vision analysis of each frame
3. **Attachment-Level Summarization**: Never inject raw attachment content into context — always summarize first

### Manifest Schema

```json
{
  "attachment_id": "att_001",
  "filename": "Q3_Report.pdf",
  "type": "pdf",
  "size_bytes": 245000,
  "page_count": 12,
  "has_images": true,
  "is_scanned": false,
  "summary": "Q3 financial report with revenue breakdown by region and product line",
  "extraction_status": "extracted" | "pending" | "failed"
}
```

### Dependency Installation Checklist

```bash
# Already installed
pip install pymupdf          # ✅ Text-based PDF extraction

# Need to install for attachment support
pip install markitdown[pptx]  # PowerPoint + general office docs
pip install openpyxl          # Excel (.xlsx) reading
pip install python-docx       # Word (.docx) parsing
pip install faster-whisper    # Audio transcription (STT)
pip install marker-pdf        # OCR for scanned PDFs (~5GB)
pip install ffmpeg            # Video frame extraction (system package: apt install ffmpeg)
```

## Risks & Mitigations
1. **Summarization loses critical details**: Mitigate with on-demand decompression + structured summaries that flag action items/decisions
2. **Vector search misses exact matches**: Combine vector search with keyword/BM25 fallback
3. **Aggregation too coarse**: Use hierarchical clustering — month-level + topic-level summaries
4. **Cost of summarization at scale**: Batch process during idle hours; incremental updates for new emails only
5. **Attachment extraction failures**: Graceful degradation — if extraction fails, note in manifest and skip; don't block email processing
