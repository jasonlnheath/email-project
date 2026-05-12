# Email Context Compression — Implementation & Test Plan

## Status
- **All 108 existing tests PASS** across 6 modules (compression, clustering, retrieval, reranker, resummarize, benchmark)
- **4 of 4 plan phases have code scaffolding** but Phase 2 summarization is mock-only
- **No qwendev used** — pure TDD with todo lists and parallel subagents

## Existing Modules (all implemented, all tested)

| Module | Class(es) | Tests | Status |
|--------|-----------|-------|--------|
| `compression.py` | `CompressionOptimizer` | 14 tests | ✅ Complete |
| `clustering.py` | `EmailClusteringEngine` | 16 tests | ✅ Complete |
| `retrieval.py` | `QueryRouter`, `RetrievalPipeline`, `SimpleBM25` | 20 tests | ✅ Complete |
| `reranker.py` | `CrossEncoderReranker`, `RerankingPipeline` | 14 tests | ✅ Complete |
| `resummarize.py` | `ResummarizationEngine` | 17 tests | ✅ Complete |
| `benchmark.py` | `BenchmarkSuite` | 13 tests | ✅ Complete |
| `test_email_attachments.py` | — | (standalone) | ✅ Exists |

## Gaps to Fill (Phase 2: Summarization Engine)

### Gap 1: Gmail Email Fetcher
**What's missing:** No code to actually pull emails from Gmail. All tiers use mock data or file I/O.

**TDD Tests to write first:**
- `test_gmail_fetcher_imports` — module importable
- `test_fetcher_auth_via_google_workspace` — uses existing OAuth token at `~/.hermes/google_token.json`
- `test_fetcher_limits_results` — respects max_results parameter (Gmail API caps at 500)
- `test_fetcher_parses_email_fields` — extracts id, subject, snippet, body, sender, date, attachments
- `test_fetcher_date_range_filtering` — filters by after/before dates
- `test_fetcher_handles_empty_inbox` — returns empty list gracefully

**Implementation:**
- Use `google-api-python-client` (already available via google-workspace skill)
- Authenticate with existing OAuth token
- Fetch emails with pagination support
- Parse MIME parts for body text extraction
- Return structured list of email dicts matching the expected schema

### Gap 2: LLM Summarization Engine (Tier 2)
**What's missing:** No actual LLM-based summarization. The clustering module uses TF-IDF keyword extraction but not LLM summaries.

**TDD Tests to write first:**
- `test_summarizer_imports` — module importable
- `test_summarizer_prompt_format` — generates correct prompt structure
- `test_summarizer_structured_output` — returns dict with sender, date, subject, key_entities, action_items, sentiment
- `test_summarizer_batch_processing` — processes multiple emails efficiently
- `test_summarizer_empty_content_handling` — handles emails with no body gracefully
- `test_summarizer_long_email_truncation` — truncates very long bodies before sending to LLM

**Implementation:**
- Design structured summarization prompt (sender, date, subject, entities, action items, sentiment)
- Batch process emails beyond the raw window (~50)
- Use local Qwen model for summarization (avoid API costs)
- Output JSONL summaries matching the expected schema
- Include fallback: if LLM call fails, use TF-IDF keyword extraction as fallback

### Gap 3: End-to-End Evaluation on Real Data
**What's missing:** No evaluation of compression quality on actual Gmail data.

**TDD Tests to write first:**
- `test_evaluate_real_data_pipeline` — full pipeline runs on real emails
- `test_compression_ratio_measured` — measures actual compression ratio
- `test_retrieval_recall_on_real_queries` — tests retrieval quality with real email content
- `test_context_budget_respected` — verifies total context stays within 64K

**Implementation:**
1. Fetch 20-50 recent emails from Gmail (small cross-section)
2. Run through the full pipeline: classify tiers → summarize → cluster
3. Measure: compression ratios, context window utilization, retrieval recall
4. Output evaluation results as JSON + human-readable summary

## Overnight Cron Job Plan

### Task 1: Write TDD Tests for Gmail Fetcher
- Create `test_gmail_fetcher.py` with failing tests
- Implement `gmail_fetcher.py` to make them pass

### Task 2: Write TDD Tests for Summarization Engine
- Create `test_summarizer.py` with failing tests
- Implement `summarizer.py` to make them pass

### Task 3: End-to-End Evaluation Script
- Create `evaluate_compression.py` that:
  1. Fetches 20-50 real emails from Gmail
  2. Runs compression pipeline
  3. Measures quality metrics (recall, compression ratio, context utilization)
  4. Outputs results to `evaluation_results.json`

### Task 4: Run & Validate
- Run all existing tests + new tests
- Run evaluation on real data
- Save results to `~/.hermes/emails/evaluation_results.json`

## Success Criteria
- [ ] All 108 existing tests still pass
- [ ] New Gmail fetcher tests pass (6+ tests)
- [ ] New summarizer tests pass (6+ tests)
- [ ] Evaluation runs on real Gmail data
- [ ] Compression ratios measured and reported
- [ ] Context budget validation passes
- [ ] Results saved to disk
