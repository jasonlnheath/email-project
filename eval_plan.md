# Email Compression Evaluation Plan

## Objective
Quantitatively and qualitatively evaluate how well our email compression pipeline preserves important information, and identify specific failure modes.

## Current State (100-email benchmark)

### Compression Performance
| Metric | Value | Assessment |
|--------|-------|------------|
| Avg compression ratio | 9.9x | Good for context budgeting |
| Median ratio | 1.9x | Many emails are short/nearly unchanged |
| Max ratio | 113.2x | Some emails compress heavily |

### Quality Metrics (averages across 98 emails)
| Metric | Score | Assessment |
|--------|-------|------------|
| Factual Consistency | 0.573 | **POOR** — nearly half of claims aren't traceable to original |
| Entity Preservation | 0.504 | **MEDIUM** — about half of names/amounts/dates/URLs preserved |
| Semantic Similarity | 0.908 | **GOOD** — overall meaning is well-captured |
| Hallucination Rate | 0.414 | **CRITICAL** — 41% of extracted claims are hallucinated! |
| Action Item Preservation | 0.224 | **POOR** — only 22% of action items survive compression |
| **Composite Score** | **0.601** | **C grade** — barely passing |

### Grade Distribution
- A: 1 (1%)
- B: 16 (16%)
- C: 33 (34%)
- D: 4 (4%)
- F: 44 (45%) ← **Nearly half fail completely**

### Loss Analysis
- Total items lost: 2,116 across 98 emails
- Critical losses: 217
- Average per email: 21.6 lost items

## Critical Findings

### 1. Hallucination Rate is Unacceptable (0.414)
The rule-based summarizer is generating claims that don't exist in the original text. This is likely caused by:
- HTML parsing artifacts being treated as content
- Cross-referencing between unrelated parts of long emails
- Template extraction from repetitive footer/header sections

### 2. Action Items Are Systematically Lost (0.224 preservation)
Of the 217 critical losses, 186 are action-related. The summarizer strips:
- Meeting times and phone numbers
- Order confirmation details
- Survey links
- Account security instructions

**Example**: Netflix "new device" email → compressed version loses "Please review who's using your account" and "If it was someone else: Please remember that we only allow the people in your household to use your account."

### 3. Entity Preservation is Inconsistent (0.504)
- Amounts: Often lost ($50, $120, $35 in promotional emails)
- Names/Addresses: Frequently dropped (Bradley Berger's phone number, meeting address)
- URLs: Mixed — some preserved, many stripped
- Dates: Often lost ("next week", "May 19")

### 4. HTML Emails Compress Poorly
Emails with heavy HTML (Fidelity ETF, Merrill Lynch) compress to extreme ratios (75x, 48x) while losing critical content. The summarizer extracts CSS classes and HTML structure instead of actual content.

### 5. Boilerplate vs. Content Mismatch
The summarizer preserves repetitive footer text ("Rankings and recognition from Forbes are no guarantee...") while dropping the actual email body. This is a priority inversion in the extraction logic.

## Qualitative Loss Examples

### Email: Netflix Security Alert
**Original**: "A new device signed in to your account. Device: iPhone Safari. Location: Michigan, United States."
**Compressed**: Extracts CSS classes and help center URLs instead of the security alert.
**Lost**: Device type, location, account action required.

### Email: Amazon Order Confirmation
**Original**: "Order #113-4910035-1972206, Mom of 2 Boys Lower Battery Son Mothers Day Birthday T-Shirt, $14.19"
**Compressed**: Extracts HTML structure and customer service URLs.
**Lost**: Order number, product name, price, shipping notification.

### Email: Merrill Lynch Follow-up
**Original**: "Hey Brad, I'm sorry but I double booked! Are you available on Tuesday morning? Say 10am?"
**Compressed**: Extracts Forbes disclaimer boilerplate.
**Lost**: Meeting reschedule request entirely.

## Evaluation Methodology

### Quantitative Metrics (implemented)
1. **Factual Consistency** — Jaccard similarity between original claims and compressed claims
2. **Entity Preservation** — Ratio of extracted entities found in original text
3. **Semantic Similarity** — Cosine similarity of TF-IDF vectors
4. **Hallucination Rate** — Fraction of compressed claims not found in original
5. **Action Item Preservation** — Ratio of action items preserved
6. **Sentiment Match** — Binary check if sentiment is preserved

### Qualitative Assessment (implemented)
1. **Loss Categorization** — Each lost item tagged as: action, amounts, dates, names, urls, content
2. **Severity Scoring** — Critical/High/Medium/Low based on category and context
3. **Side-by-Side Comparison** — Original vs compressed text for manual review
4. **Grade Assignment** — A/B/C/D/F based on composite score thresholds

## Recommendations

### Immediate Fixes
1. **Fix HTML parsing** — Strip HTML tags before summarization, extract text content only
2. **Prioritize actionable content** — Boost scores for sentences containing action verbs, URLs with CTAs, dates/times
3. **Reduce hallucination** — Add validation step: each extracted claim must have a verbatim or near-verbatim match in the original
4. **Entity extraction improvement** — Use regex patterns for phone numbers, amounts, dates, emails to ensure preservation

### Medium-term Improvements
1. **Category-aware compression** — Different rules for transactional vs marketing vs personal emails
2. **Multi-pass compression** — First pass extracts entities and actions, second pass summarizes remaining content
3. **Loss-aware summarization** — Track what's been preserved and avoid dropping it again

### Evaluation Infrastructure
1. **Automated regression testing** — Run 100-email benchmark on every code change
2. **Threshold enforcement** — Fail CI if hallucination rate > 0.1 or action item preservation < 0.5
3. **Manual review queue** — Flag emails with composite score < 0.5 for human review

## Files
- `compression.py` — Compression optimizer (tier-based)
- `metrics.py` — Quantitative evaluation metrics
- `simple_summarizer.py` — Rule-based summarizer (needs fixes)
- `compression_evaluator.py` — End-to-end evaluation pipeline
- `batch_pipeline.py` — Large-scale processing
- `run_full_eval.py` — Single-run evaluator (19 emails, detailed output)
- `run_large_eval.py` — Batch evaluator (100 emails, aggregate stats)
- `analyze_losses.py` — Loss category analysis
- `eval_results_full.json` — 19-email detailed results
- `eval_results_large.json` — 100-email aggregate results
