"""
Hunter.io API client — fallback email finder when Apollo returns nothing.
Free tier: 25 searches/month.
"""

import logging
import requests

logger = logging.getLogger(__name__)

HUNTER_BASE = "https://api.hunter.io/v2"


class HunterClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    # Domains that must never be searched — social media, video platforms, etc.
    _BLOCKED_DOMAINS = {
        "youtube.com", "youtu.be", "facebook.com", "instagram.com",
        "twitter.com", "x.com", "linkedin.com", "tiktok.com",
        "google.com", "maps.google.com", "gmail.com", "hotmail.com",
        "yandex.com", "apple.com", "microsoft.com", "amazon.com",
        "whatsapp.com", "telegram.org", "zoom.us",
    }

    def find_email_by_domain(self, domain: str) -> dict | None:
        """
        Search Hunter.io domain for any verified email.
        Returns dict with email, first_name, last_name, position or None.
        """
        if not self._api_key or not domain:
            return None
        if domain.lower() in self._BLOCKED_DOMAINS:
            logger.warning(f"Hunter: skipping blocked/social domain: {domain}")
            return None

        try:
            resp = requests.get(
                f"{HUNTER_BASE}/domain-search",
                params={
                    "domain": domain,
                    "api_key": self._api_key,
                    "limit": 5,
                    "type": "personal",   # Prefer personal over generic
                },
                timeout=15,
            )
            if resp.status_code == 429:
                logger.warning("Hunter rate limit — skipping")
                return None
            resp.raise_for_status()
            data = resp.json().get("data", {})
            emails = data.get("emails", [])

            # Prefer management-level contacts
            priority_titles = ["müdür", "direktör", "genel", "ceo", "founder", "manager", "director"]
            for email_obj in sorted(
                emails,
                key=lambda e: any(t in (e.get("position") or "").lower() for t in priority_titles),
                reverse=True,
            ):
                email = email_obj.get("value", "")
                if email and email_obj.get("confidence", 0) >= 50:
                    return {
                        "email": email,
                        "first_name": email_obj.get("first_name", ""),
                        "last_name": email_obj.get("last_name", ""),
                        "title": email_obj.get("position", ""),
                        "source": "hunter",
                    }
        except requests.RequestException as e:
            logger.warning(f"Hunter API error for {domain}: {e}")

        return None

    def verify_email(self, email: str) -> bool:
        """Verify a single email address. Returns True if deliverable."""
        if not self._api_key or not email:
            return True  # Assume valid if can't check
        try:
            resp = requests.get(
                f"{HUNTER_BASE}/email-verifier",
                params={"email": email, "api_key": self._api_key},
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json().get("data", {}).get("result", "")
            return result in ("deliverable", "risky")
        except requests.RequestException:
            return True  # Assume valid on error
