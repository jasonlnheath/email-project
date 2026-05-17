"""Periodic re-summarization engine — handles new emails arriving in the inbox.

When new emails arrive, this module:
1. Classifies them into tiers based on recency thresholds
2. Detects which emails need new summaries (tier2) or cluster updates (tier3)
3. Generates a re-summarization plan with prioritized actions
4. Builds a context window from all tiers for the LLM

Dependencies: ONLY standard library. No external packages needed.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


class ResummarizationEngine:
    """Manages periodic re-summarization of email tiers as new mail arrives."""

    def __init__(
        self,
        raw_window_size: int = 50,
        tier2_threshold: int = 500,
        tier3_threshold: int = 500,
    ):
        """
        Parameters
        ----------
        raw_window_size : int
            Number of most recent emails kept verbatim (Tier 1).
        tier2_threshold : int
            Total email count at which Tier 2 summaries begin.
        tier3_threshold : int
            Total email count at which Tier 3 aggregation begins.
        """
        self.raw_window_size = raw_window_size
        self.tier2_threshold = tier2_threshold
        self.tier3_threshold = tier3_threshold

    # ── Tier classification ─────────────────────────────────────────────

    def classify_tiers(self, emails: List[Dict]) -> Dict[str, str]:
        """Classify each email into its appropriate tier based on recency.

        Parameters
        ----------
        emails : list of dict
            Each dict must have 'id' and 'date' fields. Sorted newest-first
            or will be sorted internally.

        Returns
        -------
        dict mapping email_id → tier label ('tier1', 'tier2', or 'tier3')
        """
        if not emails:
            return {}

        # Sort by date descending (newest first)
        sorted_emails = sorted(
            emails,
            key=lambda e: self._parse_date(e.get("date", "")),
            reverse=True,
        )

        classification: Dict[str, str] = {}
        for idx, email in enumerate(sorted_emails):
            email_id = email.get("id", f"auto_{idx}")
            if idx < self.raw_window_size:
                classification[email_id] = "tier1"
            elif idx < self.tier2_threshold:
                classification[email_id] = "tier2"
            else:
                classification[email_id] = "tier3"

        return classification

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse date string into datetime object."""
        if not date_str:
            return datetime.min
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.min

    # ── Change detection ────────────────────────────────────────────────

    def detect_new_emails(
        self, current: List[Dict], previous_ids: Set[str]
    ) -> List[Dict]:
        """Return emails that are in current but not in previous state."""
        current_ids = {e.get("id") for e in current}
        new_ids = current_ids - previous_ids
        return [e for e in current if e.get("id") in new_ids]

    def detect_tier_changes(
        self, previous: Dict[str, str], current: Dict[str, str]
    ) -> Dict[str, str]:
        """Identify emails that changed tiers between states.

        Returns dict mapping email_id → change description (e.g., 'tier1_to_tier2').
        """
        changes: Dict[str, str] = {}
        all_ids = set(previous.keys()) | set(current.keys())

        for email_id in all_ids:
            prev_tier = previous.get(email_id)
            curr_tier = current.get(email_id)

            if prev_tier != curr_tier:
                if prev_tier and curr_tier:
                    changes[email_id] = f"{prev_tier}_to_{curr_tier}"
                elif curr_tier == "tier1":
                    changes[email_id] = "new_to_tier1"
                else:
                    changes[email_id] = f"unknown_to_{curr_tier}"

        return changes

    # ── Re-summarization planning ───────────────────────────────────────

    def generate_resummarization_plan(
        self,
        new_emails: List[Dict],
        tier_changes: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """Generate a prioritized plan for re-summarization.

        Parameters
        ----------
        new_emails : list of dict
            Newly arrived emails that need summarization.
        tier_changes : dict, optional
            Email IDs that migrated tiers and may need re-classification.

        Returns
        -------
        dict with keys: actions, new_summaries_needed, tier_updates_needed, priority
        """
        actions: List[Dict] = []
        new_summaries_needed = 0
        tier_updates_needed = 0

        # Priority 1: Summarize new emails (they're fresh, high value)
        for email in new_emails:
            actions.append({
                "type": "summarize",
                "email_id": email.get("id"),
                "priority": "high",
                "reason": "new_email",
            })
            new_summaries_needed += 1

        # Priority 2: Handle tier migrations
        if tier_changes:
            for email_id, change_desc in tier_changes.items():
                if "tier1_to_tier2" in change_desc:
                    actions.append({
                        "type": "summarize",
                        "email_id": email_id,
                        "priority": "medium",
                        "reason": f"migrated_{change_desc}",
                    })
                    new_summaries_needed += 1
                elif "tier2_to_tier3" in change_desc:
                    actions.append({
                        "type": "recluster",
                        "email_id": email_id,
                        "priority": "low",
                        "reason": f"migrated_{change_desc}",
                    })
                    tier_updates_needed += 1

        # Sort by priority (high > medium > low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        actions.sort(key=lambda a: priority_order.get(a["priority"], 9))

        return {
            "actions": actions,
            "new_summaries_needed": new_summaries_needed,
            "tier_updates_needed": tier_updates_needed,
            "total_actions": len(actions),
            "priority": "high" if new_summaries_needed > 0 else ("medium" if tier_updates_needed > 0 else "none"),
        }

    # ── Context window building ─────────────────────────────────────────

    @staticmethod
    def _token_count(text: str) -> int:
        """Rough token count: ~4 chars per token (English avg)."""
        return max(1, len(text) // 4)

    def build_context_window(
        self,
        tier1: List[Dict],
        tier2: List[Dict],
        tier3: List[Dict],
        max_tokens: int = 64000,
    ) -> str:
        """Assemble all tiers into a single context string, respecting budget.

        Priority order: Tier 1 raw > Tier 2 summaries > Tier 3 clusters.
        Truncates content from lower-priority tiers if budget is exceeded.

        Parameters
        ----------
        tier1 : list of dict
            Raw emails with 'content' field.
        tier2 : list of dict
            Summarized emails with 'summary' field.
        tier3 : list of dict
            Aggregated clusters with 'summary' field.
        max_tokens : int
            Maximum token budget for the context window.

        Returns
        -------
        str — formatted context string ready for LLM consumption.
        """
        parts: List[str] = []
        tokens_used = 0

        # Tier 1: Raw emails (highest priority)
        for email in tier1:
            content = email.get("content", "")
            header = f"## [Tier 1 - Raw] ID:{email.get('id', '?')} ##\n"
            snippet_len = max(0, max_tokens - tokens_used - len(header))
            if snippet_len > 0:
                body = content[:snippet_len * 4] + ("..." if len(content) > snippet_len * 4 else "")
                section = header + body
                section_tokens = self._token_count(section)
                if tokens_used + section_tokens <= max_tokens:
                    parts.append(section)
                    tokens_used += section_tokens

        # Tier 2: Summaries (medium priority)
        for summary in tier2:
            content = summary.get("summary", "")
            header = f"## [Tier 2 - Summary] ID:{summary.get('id', '?')} ##\n"
            snippet_len = max(0, max_tokens - tokens_used - len(header))
            if snippet_len > 0:
                body = content[:snippet_len * 4] + ("..." if len(content) > snippet_len * 4 else "")
                section = header + body
                section_tokens = self._token_count(section)
                if tokens_used + section_tokens <= max_tokens:
                    parts.append(section)
                    tokens_used += section_tokens

        # Tier 3: Aggregated clusters (lowest priority)
        for cluster in tier3:
            content = cluster.get("summary", "")
            header = f"## [Tier 3 - Cluster] ID:{cluster.get('id', '?')} ##\n"
            snippet_len = max(0, max_tokens - tokens_used - len(header))
            if snippet_len > 0:
                body = content[:snippet_len * 4] + ("..." if len(content) > snippet_len * 4 else "")
                section = header + body
                section_tokens = self._token_count(section)
                if tokens_used + section_tokens <= max_tokens:
                    parts.append(section)
                    tokens_used += section_tokens

        return "\n\n".join(parts)

    # ── Full re-summarization cycle ─────────────────────────────────────

    def run_resummarization_cycle(
        self,
        current_emails: List[Dict],
        previous_ids: Set[str],
        previous_classification: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """Execute a full re-summarization cycle.

        This is the main entry point — call it periodically (e.g., every hour)
        to process new emails and update tier assignments.

        Parameters
        ----------
        current_emails : list of dict
            All current emails in the inbox.
        previous_ids : set of str
            Email IDs from the last processed state.
        previous_classification : dict, optional
            Previous tier classification for change detection.

        Returns
        -------
        dict with summary statistics about the re-summarization cycle.
        """
        # Step 1: Classify all emails into tiers
        classification = self.classify_tiers(current_emails)

        # Step 2: Detect changes
        new_emails = self.detect_new_emails(current_emails, previous_ids)
        tier_changes = {}
        if previous_classification:
            tier_changes = self.detect_tier_changes(previous_classification, classification)

        # Step 3: Generate re-summarization plan
        plan = self.generate_resummarization_plan(
            new_emails=new_emails,
            tier_changes=tier_changes,
        )

        # Step 4: Build context window from current state
        tier1_emails = [e for e in current_emails if classification.get(e.get("id")) == "tier1"]
        tier2_summaries = [e for e in current_emails if classification.get(e.get("id")) == "tier2"]
        tier3_clusters = [e for e in current_emails if classification.get(e.get("id")) == "tier3"]

        context = self.build_context_window(tier1_emails, tier2_summaries, tier3_clusters)

        return {
            "new_summaries": len(new_emails),
            "tier_changes": len(tier_changes),
            "plan": plan,
            "classification": classification,
            "total_context_tokens": self._token_count(context),
            "tier_counts": {
                "tier1": len(tier1_emails),
                "tier2": len(tier2_summaries),
                "tier3": len(tier3_clusters),
            },
        }
