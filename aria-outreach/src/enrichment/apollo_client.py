"""
Apollo.io API client — finds email addresses and contact names by company domain.
Free tier: 50 credits/month. Used as first enrichment step.
"""

import logging
import requests

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"


class ApolloClient:
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

    _BLOCKED_DOMAINS = {
        "youtube.com", "youtu.be", "facebook.com", "instagram.com",
        "twitter.com", "x.com", "linkedin.com", "tiktok.com",
        "google.com", "maps.google.com", "gmail.com", "hotmail.com",
        "yandex.com", "apple.com", "microsoft.com", "amazon.com",
        "whatsapp.com", "telegram.org", "zoom.us",
    }

    def find_contact_by_domain(self, domain: str, company_name: str = "") -> dict | None:
        """
        Search for decision-maker email at a given company domain.
        Targets: Genel Müdür, CEO, Direktör, Manager roles first.
        Returns dict with keys: email, first_name, last_name, title or None.
        """
        if not self._api_key or not domain:
            return None
        if domain.lower() in self._BLOCKED_DOMAINS:
            logger.warning(f"Apollo: skipping blocked/social domain: {domain}")
            return None

        payload = {
            "api_key": self._api_key,
            "q_organization_domains": domain,
            "page": 1,
            "per_page": 5,
            "person_seniorities": ["owner", "founder", "c_suite", "vp", "director", "manager"],
        }

        try:
            resp = requests.post(
                f"{APOLLO_BASE}/mixed_people/search",
                json=payload,
                headers=self._headers,
                timeout=15,
            )
            if resp.status_code == 429:
                logger.warning("Apollo rate limit hit — skipping")
                return None
            resp.raise_for_status()
            data = resp.json()

            people = data.get("people", [])
            for person in people:
                email = person.get("email", "")
                if email and "@" in email and not email.endswith("@gmail.com"):
                    return {
                        "email": email,
                        "first_name": person.get("first_name", ""),
                        "last_name": person.get("last_name", ""),
                        "title": person.get("title", ""),
                        "source": "apollo",
                    }
        except requests.RequestException as e:
            logger.warning(f"Apollo API error for {domain}: {e}")

        return None

    def enrich_company(self, domain: str) -> dict | None:
        """Get company-level details from Apollo."""
        if not self._api_key or not domain:
            return None
        try:
            resp = requests.get(
                f"{APOLLO_BASE}/organizations/enrich",
                params={"api_key": self._api_key, "domain": domain},
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("organization", {})
            if data:
                return {
                    "company_name": data.get("name", ""),
                    "industry": data.get("industry", ""),
                    "employee_count": data.get("estimated_num_employees", 0),
                    "source": "apollo",
                }
        except requests.RequestException as e:
            logger.warning(f"Apollo enrich error for {domain}: {e}")
        return None
