"""
Base scraper with shared utilities: polite delays, session management,
URL normalization, and domain extraction.
"""

import logging
import time
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}

REQUEST_DELAY = 2.0   # seconds between requests — polite scraping
TIMEOUT       = 15    # seconds per request


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_page(url: str, session: requests.Session) -> BeautifulSoup | None:
    """Fetch a URL and return parsed BeautifulSoup, or None on error."""
    try:
        time.sleep(REQUEST_DELAY)
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding  # Handle Turkish chars
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def extract_domain(url: str) -> str:
    """
    Extract clean domain from a URL.
    'http://www.akarcatekstil.com.tr/about' → 'akarcatekstil.com.tr'
    """
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    domain = re.sub(r"^www\.", "", domain)
    return domain


def normalize_phone(phone: str) -> str:
    """Normalize Turkish phone numbers to consistent format."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"0{digits[:3]} {digits[3:6]} {digits[6:8]} {digits[8:]}"
    return phone.strip()


def clean_company_name(name: str) -> str:
    """Remove excessive whitespace and common artifacts."""
    if not name:
        return ""
    name = re.sub(r"\s+", " ", name)
    return name.strip()
