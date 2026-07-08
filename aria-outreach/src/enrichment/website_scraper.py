"""
Website email scraper — finds real published email addresses from company websites.

Used as an enrichment step BEFORE Apollo/Hunter/guesser.
Visits the company's website contact page and extracts any mailto: links or
email patterns visible in the page text.

Only returns emails that are explicitly published on the site — no guessing.
"""

import logging
import re

from src.scraper.base_scraper import fetch_page, get_session

logger = logging.getLogger(__name__)

# Contact page paths to try, in order
_CONTACT_PATHS = [
    "/iletisim",
    "/contact",
    "/bize-ulasin",
    "/hakkimizda",
    "/about",
    "/iletisim.html",
    "/contact.html",
    "/tr/iletisim",
    "/en/contact",
]

# Email pattern — matches most standard addresses
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Domains to ignore even if found on page (analytics, CDN, social, etc.)
_IGNORE_DOMAINS = {
    "sentry.io", "google.com", "googleapis.com", "gstatic.com",
    "facebook.com", "twitter.com", "instagram.com", "linkedin.com",
    "youtube.com", "tiktok.com", "whatsapp.com", "telegram.org",
    "cloudflare.com", "jquery.com", "bootstrapcdn.com",
    "example.com", "test.com", "wixpress.com", "squarespace.com",
    "wordpress.com", "mailchimp.com", "sendgrid.net",
}


class WebsiteEmailScraper:
    def __init__(self):
        self._session = get_session()

    def find_email(self, domain: str) -> dict | None:
        """
        Visit the company website and extract a real published email.
        Returns dict with email + source='website', or None if not found.
        """
        if not domain:
            return None

        base = f"https://{domain}"
        urls_to_try = [base] + [base + path for path in _CONTACT_PATHS]

        for url in urls_to_try:
            emails = self._extract_from_url(url, domain)
            if emails:
                best = _pick_best(emails)
                logger.info(f"  Website scraper found: {best} at {url}")
                return {
                    "email":      best,
                    "first_name": "",
                    "last_name":  "",
                    "title":      "",
                    "source":     "website",
                }

        return None

    def _extract_from_url(self, url: str, company_domain: str) -> list[str]:
        try:
            soup = fetch_page(url, self._session)
        except Exception:
            return []
        if not soup:
            return []

        found = set()

        # 1. mailto: links (highest confidence)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                email = href[7:].split("?")[0].strip().lower()
                if _is_valid(email, company_domain):
                    found.add(email)

        # 2. Page text — emails written as plain text
        text = soup.get_text(" ")
        for match in _EMAIL_RE.findall(text):
            email = match.strip().lower()
            if _is_valid(email, company_domain):
                found.add(email)

        return list(found)


def _is_valid(email: str, company_domain: str) -> bool:
    """Accept only emails that belong to the company's own domain."""
    if not email or "@" not in email:
        return False
    _, domain_part = email.split("@", 1)
    # Must belong to the company domain (or its www variant)
    domain_part = domain_part.lstrip("www.")
    company_domain = company_domain.lstrip("www.")
    if domain_part != company_domain:
        return False
    if domain_part in _IGNORE_DOMAINS:
        return False
    return True


# Priority order for picking the best email when multiple found
_PREFIX_PRIORITY = [
    "info", "iletisim", "bilgi", "satis", "ihracat", "export",
    "mail", "ofis", "genel", "mudur", "yonetim",
]


def _pick_best(emails: list[str]) -> str:
    if len(emails) == 1:
        return emails[0]
    for prefix in _PREFIX_PRIORITY:
        for e in emails:
            if e.startswith(prefix + "@"):
                return e
    return sorted(emails)[0]
