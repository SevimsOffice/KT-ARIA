"""
NOSAB (Nilüfer OSB) scraper — nosab.org.tr

NOSAB has ~320 member companies across 17 sectors.

Structure discovered via site inspection:
  - Listing pages: /firmalar/tr?harf=[LETTER]  (one per Turkish alphabet letter)
  - Detail pages:  /firma/[company-slug]/tr     (has email, website, phone)

Phase 1 (fast, ~60s): Iterate all letters → collect company names + detail URLs
Phase 2 (per-company): Caller fetches detail pages for enrichment
"""

import logging
import re
from urllib.parse import quote

from .base_scraper import (
    get_session, fetch_page, extract_domain,
    normalize_phone, clean_company_name
)

logger = logging.getLogger(__name__)

BASE_URL    = "https://www.nosab.org.tr"
LISTING_URL = f"{BASE_URL}/firmalar/tr"
OSB_NAME    = "NOSAB"

# Full Turkish alphabet
LETTERS = [
    "A", "B", "C", "Ç", "D", "E", "F", "G", "Ğ", "H",
    "I", "İ", "J", "K", "L", "M", "N", "O", "Ö", "P",
    "R", "S", "Ş", "T", "U", "Ü", "V", "Y", "Z"
]


def scrape_nosab() -> list[dict]:
    """
    Scrape all NOSAB company listings (Phase 1: fast, no detail pages).

    Returns list of dicts:
      Company_Name, Sector, Domain, Phone, Address, Email, OSB, detail_url

    Domain / Email will be empty at this stage.
    Call scrape_nosab_detail() to enrich individual companies.
    """
    session = get_session()
    seen_names: set[str] = set()
    companies: list[dict] = []

    logger.info("NOSAB: scraping A-Z listing pages...")

    for letter in LETTERS:
        url = f"{LISTING_URL}?harf={quote(letter)}"
        soup = fetch_page(url, session)
        if not soup:
            logger.warning(f"NOSAB: could not load letter {letter!r}")
            continue

        # Links have pattern: <a href="/firma/[slug]/tr">Company Name <img .../></a>
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/firma/" not in href or href.rstrip("/").endswith("/firmalar"):
                continue
            name = clean_company_name(
                a.get_text(separator=" ", strip=True)
            )
            if not name or len(name) < 3:
                continue
            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)

            detail_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            companies.append({
                "Company_Name": name,
                "Sector":     "",
                "Domain":     "",
                "Phone":      "",
                "Address":    "",
                "Email":      "",
                "OSB":        OSB_NAME,
                "City":       "Bursa",
                "detail_url": detail_url,
            })

    logger.info(f"NOSAB: found {len(companies)} companies total")
    return companies


def scrape_nosab_detail(session, detail_url: str) -> dict:
    """
    Fetch a single NOSAB company detail page.

    Returns dict with keys:
      email, domain, phone, address, sector
    (all strings, empty if not found)
    """
    result = {
        "email":   "",
        "domain":  "",
        "phone":   "",
        "address": "",
        "sector":  "",
    }

    soup = fetch_page(detail_url, session)
    if not soup:
        return result

    full_text = soup.get_text(separator=" ", strip=True)

    # Domains to skip when extracting company website
    _SOCIAL_DOMAINS = {
        "youtube.com", "youtu.be", "facebook.com", "instagram.com",
        "twitter.com", "x.com", "linkedin.com", "tiktok.com",
        "google.com", "maps.google.com", "whatsapp.com",
    }

    # ── Website ──────────────────────────────────────────────────────────────
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        if href.startswith("mailto:") or href.startswith("tel:"):
            continue
        if "nosab.org.tr" in href:
            continue
        if href.startswith("http") or href.startswith("www"):
            domain = extract_domain(href)
            if domain and "." in domain and domain not in _SOCIAL_DOMAINS:
                result["domain"] = domain
                break

    # ── Email: mailto: links first, then regex ────────────────────────────
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            email = href[7:].strip().lower()
            if "@" in email and "nosab.org.tr" not in email:
                result["email"] = email
                break
    if not result["email"]:
        m = re.search(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
            full_text,
        )
        if m:
            email = m.group().lower().strip()
            if "nosab.org.tr" not in email and len(email) < 80:
                result["email"] = email

    # ── Phone ─────────────────────────────────────────────────────────────
    phone_m = re.search(
        r"0\s*\(?(\d{3})\)?\s*(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})",
        full_text,
    )
    if phone_m:
        result["phone"] = normalize_phone(phone_m.group())

    # ── Sector: look for the sector breadcrumb or labeled field ───────────
    # NOSAB detail pages show breadcrumb: Home > Firmalar > Sector > CompanyName
    breadcrumbs = soup.find_all(
        ["li", "span", "a"],
        class_=lambda c: c and "breadcrumb" in " ".join(c).lower()
    )
    if breadcrumbs:
        texts = [b.get_text(strip=True) for b in breadcrumbs]
        sector_candidates = [t for t in texts if 3 < len(t) < 40]
        if len(sector_candidates) >= 2:
            result["sector"] = sector_candidates[-2]  # Second to last = sector

    return result
