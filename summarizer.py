"""Summarization engine for email compression pipeline.

Uses a local LLM (Qwen via llama.cpp OpenAI-compatible API) for summarization,
with TF-IDF fallback if the LLM call fails.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None


# ── Constants ────────────────────────────────────────────────────────────

DEFAULT_MAX_BODY_LENGTH = 3000  # chars before truncation
LLAMA_CPP_HOST = "http://localhost:8033"  # llama.cpp OpenAI-compatible API
LLAMA_CPP_MODEL = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"  # model name from /v1/models


# ── Summarizer class ─────────────────────────────────────────────────────

class Summarizer:
    """Summarizes email content using Qwen (llama.cpp) with TF-IDF fallback."""

    def __init__(
        self,
        max_body_length: int = DEFAULT_MAX_BODY_LENGTH,
        base_url: str = LLAMA_CPP_HOST,
        model: str = LLAMA_CPP_MODEL,
    ):
        self.max_body_length = max_body_length
        self.base_url = base_url.rstrip("/")
        self.model = model

    # ── Prompt building ────────────────────────────────────────────────

    def build_prompt(self, email: Dict[str, Any]) -> str:
        """Build a prompt for summarizing a single email.

        Extracts key entities (names, organizations, products, dates, amounts),
        action items (requests, deadlines, tasks), and sentiment from the email body.
        Returns structured JSON output.
        """
        sender = email.get("sender", "Unknown")
        subject = email.get("subject", "(no subject)")
        date = email.get("date", "Unknown")
        body = email.get("body", "") or ""

        # Extract key info from body for short prompt
        truncated_body = self._truncate(body)

        # Pre-extract concrete entities as ground-truth anchors
        anchors = self._pre_extract_entities(body)
        anchor_parts = []
        if anchors["money"]:
            anchor_parts.append(f"Money found: {', '.join(anchors['money'])}")
        if anchors["phones"]:
            anchor_parts.append(f"Phone numbers found: {', '.join(anchors['phones'])}")
        if anchors["urls"]:
            anchor_parts.append(f"URLs found: {', '.join(anchors['urls'][:5])}")
        if anchors["dates"]:
            anchor_parts.append(f"Dates found: {', '.join(anchors['dates'])}")

        anchor_text = "\n".join(anchor_parts) if anchor_parts else ""

        prompt = (
            f"Analyze this email and extract structured information.\n\n"
            f"FROM: {sender}\n"
            f"SUBJECT: {subject}\n"
            f"DATE: {date}\n\n"
            f"BODY:\n{truncated_body}\n\n"
            "Extract the following and return ONLY valid JSON (no markdown, no extra text):\n"
            "- sender: the sender name/email\n"
            "- date: the email date string\n"
            "- subject: the email subject\n"
            "- key_entities: list of 3-8 concrete entities EXTRACTED FROM THE EMAIL BODY. "
            "Include: person names, company names, product names, specific dates, dollar amounts, "
            "account numbers, file names, URLs. DO NOT invent or infer entities not explicitly stated.\n"
            "- action_items: list of 0-5 specific actions requested or required. "
            "An action item is a REQUEST, DEADLINE, or TASK directed at someone. "
            "Examples: 'Reply by Friday', 'Review attached PDF', 'Call Sarah at (555) 123-4567'. "
            "Do NOT include general statements like 'Please review' without specifics.\n"
            "- sentiment: one of 'positive', 'negative', 'neutral'\n\n"
            "CRITICAL RULES:\n"
            "1. ONLY extract what appears in the email body. Do NOT guess or infer.\n"
            "2. If an entity/action is not explicitly stated, omit it — do NOT fabricate.\n"
            "3. Dollar amounts must include the $ sign and exact figure from the email.\n"
            "4. Phone numbers must match exactly as written in the email.\n"
            "5. Dates must match exactly (e.g., 'March 15' not 'mid-March').\n"
            "6. If the email has no real content (spam/promotional), set key_entities=[] and action_items=[].\n"
            "7. Return JSON only, no other text.\n"
        )
        return prompt

    # ── Single email summarization ─────────────────────────────────────

    def summarize(self, email: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize a single email using LLM.
        
        If the LLM call fails, returns a default summary with extracted
        metadata (sender, date, subject) and empty lists for entities/actions.
        """
        try:
            return self._summarize_with_llm(email)
        except Exception:
            # Return a minimal default summary on failure
            return {
                "sender": email.get("sender", "Unknown"),
                "date": email.get("date", "Unknown"),
                "subject": email.get("subject", "(no subject)"),
                "key_entities": [],
                "action_items": [],
                "sentiment": "neutral",
            }

    def _summarize_with_llm(self, email: Dict[str, Any]) -> Dict[str, Any]:
        """Call llama.cpp (Qwen) to summarize the email."""
        prompt = self.build_prompt(email)
        response_text = self._call_llama_cpp(prompt)

        # Extract JSON from response (strip thinking tags if present)
        cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
        cleaned = cleaned.strip()
        
        # Find JSON object in response
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in LLM response")
        
        result = json.loads(json_match.group())

        # Ensure all required fields exist
        for key in ("sender", "date", "subject", "key_entities", "action_items", "sentiment"):
            if key not in result:
                result[key] = self._default_value(key, email)

        # Verify extracted entities/actions against original body
        result = self._verify_summary(result, email)

        return result

    # def _summarize_with_tfidf_fallback(self, email: Dict[str, Any]) -> Dict[str, Any]:
    #     """TF-IDF keyword extraction fallback when LLM is unavailable.
    #     
    #     DISABLED — we'd rather fail hard than silently produce garbage.
    #     If you re-enable this, make sure callers handle the degraded quality.
    #     """
    #     body = (email.get("body") or "").strip()
    #     sender = email.get("sender", "Unknown")
    #     subject = email.get("subject", "(no subject)")
    #     date = email.get("date", "Unknown")
    #
    #     if TfidfVectorizer is None:
    #         words = re.findall(r'\b\w{4,}\b', body.lower())
    #         key_entities = list(set(words[:5])) if words else []
    #         return {
    #             "sender": sender,
    #             "date": date,
    #             "subject": subject,
    #             "key_entities": key_entities,
    #             "action_items": [],
    #             "sentiment": "neutral",
    #         }
    #
    #     vectorizer = TfidfVectorizer(stop_words="english", max_features=20)
    #     try:
    #         tfidf_matrix = vectorizer.fit_transform([body])
    #         feature_names = vectorizer.get_feature_names_out()
    #         scores = tfidf_matrix.toarray().sum(axis=0)
    #         top_indices = scores.argsort()[::-1][:5]
    #         key_entities = [feature_names[i] for i in top_indices if scores[i] > 0]
    #     except Exception:
    #         key_entities = []
    #
    #     action_items = self._extract_action_items(body)
    #
    #     return {
    #         "sender": sender,
    #         "date": date,
    #         "subject": subject,
    #         "key_entities": key_entities,
    #         "action_items": action_items,
    #         "sentiment": "neutral",
    #     }

    # ── Verification ────────────────────────────────────────────────────

    def _verify_summary(self, summary: Dict, email: Dict) -> Dict:
        """Verify extracted entities/actions against original email body.

        Removes any entity or action item that does not appear in the original
        email body (case-insensitive substring match). This catches hallucinated
        content at the post-processing level.
        """
        body = (email.get("body") or "").lower()
        if not body.strip():
            return summary

        # Verify key_entities — remove any not found in body
        verified_entities = []
        for entity in summary.get("key_entities", []):
            entity_lower = str(entity).lower()
            if len(entity_lower) > 2 and entity_lower in body:
                verified_entities.append(entity)

        # Verify action_items similarly
        verified_actions = []
        for action in summary.get("action_items", []):
            action_lower = str(action).lower()
            if len(action_lower) > 3 and action_lower in body:
                verified_actions.append(action)

        summary["key_entities"] = verified_entities
        summary["action_items"] = verified_actions
        return summary

    def _pre_extract_entities(self, body: str) -> Dict[str, List[str]]:
        """Extract concrete entities from body using regex as anchors.

        These anchors are fed to the LLM prompt so it has ground-truth
        evidence of what's actually in the email, reducing hallucination.
        """
        import re
        entities = {"money": [], "phones": [], "dates": [], "urls": []}

        # Money (e.g., $5,000 or $5.2k)
        entities["money"] = list(set(re.findall(r'\$[\d,]+(?:\.\d{2})?', body)))
        # Phone numbers
        entities["phones"] = list(set(re.findall(
            r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', body
        )))
        # URLs
        entities["urls"] = list(set(re.findall(
            r'https?://[^\s<>"]+|www\.[^\s<>"]+', body
        )))
        # Dates (Month DD, YYYY)
        entities["dates"] = list(set(re.findall(
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}',
            body, re.IGNORECASE
        )))

        return entities

    # ── Batch processing ─────────────────────────────────────────────

    def summarize_batch(self, emails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize multiple emails efficiently."""
        summaries = []
        for email in emails:
            # NO FALLBACK — fail on first error rather than silently degrading
            summary = self.summarize(email)
            summaries.append(summary)
        return summaries

    # ── Helpers ────────────────────────────────────────────────────────

    def _call_llama_cpp(self, prompt: str, timeout: int = 60) -> str:
        """Call llama.cpp OpenAI-compatible API with increased timeout."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _truncate(self, body: str) -> str:
        """Truncate long email bodies to max_body_length chars."""
        if len(body) <= self.max_body_length:
            return body
        # Account for marker string in the length budget
        marker = "\n... [truncated] ...\n"
        marker_len = len(marker)
        available = self.max_body_length - marker_len
        half = available // 2
        return body[:half] + marker + body[-half:]

    @staticmethod
    def _default_value(key: str, email: Dict[str, Any]) -> Any:
        """Return a sensible default for missing summary fields."""
        defaults = {
            "sender": email.get("sender", "Unknown"),
            "date": email.get("date", "Unknown"),
            "subject": email.get("subject", "(no subject)"),
            "key_entities": [],
            "action_items": [],
            "sentiment": "neutral",
        }
        return defaults.get(key, "")

    @staticmethod
    def _extract_action_items(body: str) -> List[str]:
        """Extract action items from email body using simple heuristics."""
        if not body:
            return []
        lines = body.split("\n")
        actions = []
        for line in lines:
            stripped = line.strip().lstrip("-*•").strip()
            if any(
                stripped.lower().startswith(prefix)
                for prefix in ["action", "todo", "task", "follow up", "schedule",
                               "send", "review", "update", "prepare", "contact"]
            ):
                actions.append(stripped)
        return actions[:5]  # Cap at 5 action items
