# Claude Code Supervision Hint

**17 test failures remaining. Root causes identified:**

## Fix 1: Missing imports in test_email_attachments.py (7 failures)

Add to top of file:
```python
from reference_content_extraction import (
    extract_pdf_tables, extract_pdf_headings, extract_excel_column_stats,
    extract_word_headings, pptx_slide_content, image_exif_data, transcribe_audio
)
```

Note: test uses `word_heading_hierarchy` but source has `extract_word_headings` — check names match.

## Fix 2: CompressionOptimizer.compression_ratio undefined (6 failures)

compression.py:735 calls `CompressionOptimizer.compression_ratio(original, summary)` but that method doesnt
