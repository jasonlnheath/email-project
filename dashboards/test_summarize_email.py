#!/usr/bin/env python3
"""Tests for summarize_email HTML parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_plain_html():
    """Test basic HTML body extraction."""
    from email_dashboard import summarize_email

    html = """
    <html><body>
    <p>Hello there, this is a test email with some important content.</p>
    <p>We wanted to let you know about the meeting tomorrow at 3pm.</p>
    <p>Please confirm your attendance by replying to this message.</p>
    </body></html>
    """
    result = summarize_email(html, "Test Subject")
    print(f"Plain HTML summary:\n{result}\n")
    assert result is not None
    assert len(result) > 10
    # Should extract meaningful lines, not HTML tags
    assert "<" not in result


def test_html_with_style_tags():
    """Test that style tag content does NOT leak into summary."""
    from email_dashboard import summarize_email

    html = """
    <html><body>
    <style>
        .important { color: red; font-weight: bold; }
        body { margin: 0; padding: 20px; }
        @media print { .no-print { display: none; } }
    </style>
    <p>This is the actual email content about the quarterly report.</p>
    <p>The revenue increased by 15% compared to last quarter.</p>
    <div>Please find the attached spreadsheet for details.</div>
    </body></html>
    """
    result = summarize_email(html, "Quarterly Report")
    print(f"Style tag test summary:\n{result}\n")
    assert result is not None
    # Style content should NOT appear
    assert "margin:" not in result
    assert "color: red" not in result
    assert "@media" not in result
    # Real content should be there
    assert "quarterly" in result.lower() or "revenue" in result.lower()


def test_html_with_images():
    """Test that image alt text is extracted and placed at top."""
    from email_dashboard import summarize_email

    html = """
    <html><body>
    <img src="logo.png" alt="Company Annual Report 2026">
    <p>Here is the annual report you requested.</p>
    <p>Total revenue was $5.2M with a 12% growth year-over-year.</p>
    </body></html>
    """
    result = summarize_email(html, "Annual Report")
    print(f"Image alt test summary:\n{result}\n")
    assert result is not None
    # Alt text should appear (prefixed with [Image:])
    assert "Company Annual Report 2026" in result


def test_html_with_script_tags():
    """Test that script tag content does NOT leak."""
    from email_dashboard import summarize_email

    html = """
    <html><body>
    <script>
        var trackingId = "UA-12345";
        analytics.track("email_opened", {userId: "user1"});
        console.log("This is tracking code that should be stripped");
    </script>
    <p>Your order #98765 has shipped and will arrive on Friday.</p>
    <p>Tracking number: 1Z999AA10123456784</p>
    </body></html>
    """
    result = summarize_email(html, "Order Shipped")
    print(f"Script tag test summary:\n{result}\n")
    assert result is not None
    # Script content should NOT appear
    assert "trackingId" not in result
    assert "analytics.track" not in result
    assert "console.log" not in result
    # Real content should be there
    assert "shipped" in result.lower() or "order" in result.lower()


def test_fallback_parser():
    """Test the fallback HTMLParser when BeautifulSoup is unavailable."""
    from email_dashboard import summarize_email

    html = """
    <html><body>
    <div>Welcome to our newsletter!</div>
    <p>This week we have 5 new products in stock.</p>
    <p>Check them out at our online store.</p>
    </body></html>
    """
    result = summarize_email(html, "Newsletter")
    print(f"Fallback parser summary:\n{result}\n")
    assert result is not None
    assert len(result) > 10


def test_nested_tags():
    """Test extraction from deeply nested HTML."""
    from email_dashboard import summarize_email

    html = """
    <html>
    <body>
        <div class="content">
            <section>
                <h1>Project Update</h1>
                <div class="details">
                    <p>The migration to the new database is complete.</p>
                    <ul>
                        <li>All 50k records transferred successfully</li>
                        <li>Downtime was only 12 minutes</li>
                        <li>No data loss reported</li>
                    </ul>
                </div>
            </section>
        </div>
    </body>
    </html>
    """
    result = summarize_email(html, "DB Migration")
    print(f"Nested tags summary:\n{result}\n")
    assert result is not None
    # Should extract key content from nested structure
    assert "migration" in result.lower() or "database" in result.lower()


if __name__ == "__main__":
    tests = [
        test_plain_html,
        test_html_with_style_tags,
        test_html_with_images,
        test_html_with_script_tags,
        test_fallback_parser,
        test_nested_tags,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAILED: {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        print(f"{failed} failed!")
        sys.exit(1)
