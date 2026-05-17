#!/usr/bin/env python3
"""Fix corrupted indentation in email_dashboard.py."""

with open('/home/jason/.hermes/dashboards/email_dashboard.py', 'r') as f:
    lines = f.readlines()

# Fix the corrupted section around line 686
# Lines 686-689 are corrupted and need to be replaced with correct for loop body
fixed_lines = []
for i, line in enumerate(lines):
    if i == 685:  # Line 686 (0-indexed)
        # Replace with correct for loop body
        fixed_lines.append('                    priority = email.get("tier_order", 2)\n')
        fixed_lines.append('                    SUMMARY_QUEUE.add(email["id"], email, priority=priority)\n')
    elif i in [686, 687, 688]:  # Lines 687-689 are corrupted labels block - skip them
        continue
    else:
        fixed_lines.append(line)

with open('/home/jason/.hermes/dashboards/email_dashboard.py', 'w') as f:
    f.writelines(fixed_lines)

print("Fixed!")
