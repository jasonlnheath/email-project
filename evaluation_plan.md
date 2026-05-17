# Email Compression Evaluation Plan

## Research Summary

### What DeepSeek V4 Actually Does (and Doesn't Do)

DeepSeek V4's compression is **KV cache compression**, not text summarization. Key distinction:

| Aspect | DeepSeek V4 | Our Approach |
|--------|-------------|--------------|
| **What's compressed** | KV cache entries (attention state) | Email text content |
| **Compression ratio** | 4:1 (CSA) to 128:1 (HCA) on KV entries | ~10-100:1 on text tokens |
| **How it works** | Weighted combination of m=4 or m'=128 tokens into single KV vector, then sparse selection via Lightning Indexer | LLM summarization with structured metadata |
| **Retrieval mechanism** | Learned indexer scores compressed blocks per query | Vector search + keyword matching |
| **On-demand decompression** | Recompute tail blocks from scratch | Fetch original email from Gmail API |

**Critical insight**: DeepSeek V4 achieves high compression ratios because it compresses *attention state* (KV pairs), not the raw text. The KV cache is a mathematical representation of what the model "remembers" about each token — it's inherently lossy and can be aggressively compressed because the model was *trained* to work with compressed attention.

Our approach compresses *text content* before it ever reaches the LLM. This is fundamentally different:
- We're reducing input tokens, not KV cache entries
- There's no "training" on our compressed format — the LLM sees whatever we give it
- We need to preserve *semantic meaning* for retrieval, not just attention state

### What Research Says About Summarization Evaluation

**SummEval** (Fabbri et al., ACL 2022) re-evaluated 14 automatic metrics against human judgments and found:
- No single metric correlates well with human judgment across all models
- **BERTScore** and **ROUGE-L** have the highest correlation with human quality judgments
- **Factual consistency** is poorly captured by any existing automatic metric
- Human evaluation remains necessary for comprehensive assessment

**SummFactScore** (Aloraini et al., 2025) introduces a claim-centric approach:
- Decompresses summaries into atomic claims
- Uses NLI (Natural Language Inference) to verify each claim against source
- Reference-free — doesn't need a gold summary to compare against
- This is the most relevant approach for our use case

### Key Papers Reviewed

1. **DeepSeek V4** (May 2026, 58 pages) — KV cache compression architecture
2. **SummEval** (Fabbri et al., ACL 2022) — Comprehensive summarization evaluation benchmark
3. **SummFactScore** (Aloraini et al., 2025) — Claim-centric factual consistency
4. **EvolKV** (Yu & Chai, EMNLP 2025) — Evolutionary KV cache optimization
5. **Key, Value, Compress** (Javidnia et al.) — Systematic survey of KV cache techniques
6. **The Long Context Conundrum** (Biswas) — Survey of long-context challenges

---

## Evaluation Framework

### Tier 1: Quantitative Metrics (Automated)

#### 1. Compression Ratio
```
ratio = original_token_count / summary_token_count
```
- **Target**: Tier 2 → 8-16x, Tier 3 → 50-100x
- **Measurement**: Count tokens using tiktoken (cl100k_base for GPT-4, qwen3 for Qwen)
- **Threshold**: < 3x = insufficient compression; > 200x = likely over-compressed

#### 2. Factual Consistency (Claim-Level)
Based on SummFactScore methodology:
```
1. Extract atomic claims from summary (each claim = one verifiable fact)
2. For each claim, check if it's entailed by the original email
3. Score = (entailed_claims / total_claims) * 100
```
- **Tool**: NLI model (e.g., `all-MiniLM-L6-v2` for fast inference)
- **Threshold**: ≥ 95% factual consistency required; < 80% = unacceptable
- **Critical**: This is the most important metric — losing facts is worse than losing detail

#### 3. Entity Preservation Rate
Track preservation of specific entity types:
| Entity Type | Extraction Method | Target |
|-------------|-------------------|--------|
| Person names | spaCy NER | ≥ 80% |
| Organizations | spaCy NER | ≥ 80% |
| Dates/times | dateutil + regex | ≥ 90% |
| Monetary values | regex ($X,XXX) | 100% (critical) |
| URLs | regex URL detection | ≥ 70% (action items must survive) |
| Locations | spaCy NER | ≥ 85% |
| Device/browser info | regex patterns | ≥ 90% |
| Action items | Keyword + pattern matching | 100% (critical) |

#### 4. Semantic Similarity
```
score = cosine_similarity(embed(summary), embed(original))
```
- **Model**: `all-MiniLM-L6-v2` (fast, good for short texts)
- **Target**: ≥ 0.75 semantic similarity
- **Note**: This measures overall meaning preservation, not factual accuracy

#### 5. Hallucination Detection
Based on SummFactScore methodology:
```
1. Extract all claims from summary
2. For each claim, check if it's contradicted by the original email
3. Score = (contradicted_claims / total_claims) * 100
```
- **Tool**: NLI model (contradiction detection)
- **Threshold**: ≤ 5% hallucination rate required; > 10% = unacceptable

### Tier 2: Qualitative Metrics (Human/LLM-as-Judge)

#### 6. Retrieval Quality (Recall@k)
```
For each query in test set:
  1. Retrieve top-k summaries
  2. Check if correct email is in top-k
  3. Recall@k = (emails_found_in_top_k / total_queries) * 100
```
- **Test set**: 50+ queries covering different types (sender, date, topic, action item)
- **Target**: Recall@3 ≥ 90%, Recall@5 ≥ 95%

#### 7. Action Item Detection
```
For each summary:
  1. Extract action items from original email
  2. Check if each action item is mentioned in summary
  3. Score = (action_items_found / total_action_items) * 100
```
- **Target**: 100% action item preservation (non-negotiable)
- **Measurement**: Manual verification + automated keyword matching

#### 8. Sentiment/Intent Preservation
```
1. Classify sentiment of original email (positive/negative/neutral)
2. Classify sentiment of summary
3. Score = accuracy of sentiment preservation
```
- **Tool**: Simple sentiment classifier or LLM-as-judge
- **Target**: ≥ 90% sentiment preservation

### Tier 3: System-Level Metrics

#### 9. Context Window Utilization
```
For a given query + retrieved context:
  utilization = (tokens_used_for_relevant_context / total_context_window) * 100
```
- **Measurement**: Track token usage per query
- **Target**: ≥ 60% utilization (avoid wasting context on irrelevant content)

#### 10. Retrieval Latency
```
latency = time_from_query_to_first_relevant_result
```
- **Measurement**: Wall-clock time for retrieval pipeline
- **Target**: < 2 seconds for Tier 2, < 5 seconds for Tier 3

---

## Test Dataset Construction

### Ground Truth Generation
For each email in the test set:
1. **Extract ground truth facts**: Person names, dates, amounts, URLs, action items, locations
2. **Generate queries**: Create 3-5 natural language queries per email
   - "What did [sender] say about [topic]?"
   - "When is the deadline for [action item]?"
   - "What's the amount mentioned in [email]?"
   - "Who are the people involved in [thread]?"
3. **Label correct answers**: Manually verify which emails answer each query

### Test Set Composition (50+ emails)
| Category | Count | Description |
|----------|-------|-------------|
| Transactional | 10 | Password resets, security alerts, receipts |
| Conversational | 15 | Multi-thread email chains |
| Notifications | 10 | Service updates, alerts, digests |
| Documents | 10 | Emails with attachments (PDFs, spreadsheets) |
| Long-form | 5 | Detailed proposals, reports, articles |

---

## Evaluation Procedure

### Phase 1: Baseline Measurement
1. Run all test emails through current compression pipeline
2. Compute all quantitative metrics (compression ratio, factual consistency, entity preservation, etc.)
3. Document baseline scores for each metric

### Phase 2: Ablation Studies
Test different compression strategies:
| Variant | Description | Expected Impact |
|---------|-------------|-----------------|
| **Baseline** | Current summarization prompt | Reference point |
| **No metadata** | Summary without structured fields | ↓ entity preservation |
| **Aggressive** | Shorter summaries, fewer details | ↑ compression ratio, ↓ factual consistency |
| **Conservative** | Longer summaries, more detail | ↓ compression ratio, ↑ factual consistency |
| **URL-preserving** | Modified prompt to keep action-item URLs | ↑ URL preservation, ↓ compression ratio |

### Phase 3: Iterative Improvement
1. Identify weakest metric(s) from baseline
2. Modify compression prompt/strategy to improve weakest metric
3. Re-run evaluation and compare to baseline
4. Repeat until all metrics meet thresholds

---

## Success Criteria

| Metric | Target | Critical? |
|--------|--------|-----------|
| Compression ratio (Tier 2) | ≥ 8x | Yes |
| Factual consistency | ≥ 95% | **Critical** |
| Entity preservation (names) | ≥ 80% | Yes |
| Entity preservation (money) | 100% | **Critical** |
| Entity preservation (URLs) | ≥ 70% | Yes |
| Hallucination rate | ≤ 5% | **Critical** |
| Action item detection | 100% | **Critical** |
| Semantic similarity | ≥ 0.75 | Yes |
| Recall@3 | ≥ 90% | Yes |
| Context utilization | ≥ 60% | Yes |

---

## Implementation Notes

### Tools Required
- `tiktoken` — Token counting for accurate ratio measurement
- `sentence-transformers` — Embedding model for semantic similarity
- `transformers` (HuggingFace) — NLI model for factual consistency/hallucination detection
- `spacy` — Named entity recognition for entity preservation tracking
- `dateutil` — Date/time extraction and validation

### Automation Pipeline
```bash
# 1. Generate test dataset
python generate_test_dataset.py --emails=test_emails.jsonl --output=ground_truth.json

# 2. Run compression pipeline
python compress_emails.py --input=test_emails.jsonl --output=summaries.jsonl

# 3. Compute quantitative metrics
python evaluate_quantitative.py --summaries=summaries.jsonl --ground-truth=ground_truth.json

# 4. Compute qualitative metrics (LLM-as-judge)
python evaluate_qualitative.py --summaries=summaries.jsonl --queries=test_queries.jsonl

# 5. Generate report
python generate_report.py --results=all_metrics.json --output=evaluation_report.md
```

### Continuous Evaluation
- Run evaluation on every new email batch (incremental)
- Track metric trends over time (dashboard)
- Alert when any metric drops below threshold
- Periodic re-evaluation with updated prompts/models
