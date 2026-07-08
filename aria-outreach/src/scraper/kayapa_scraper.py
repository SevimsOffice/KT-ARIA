"""
KAYAPA OSB scraper — kayapaosb.org.tr

NOTE: As of 2025-2026, the KAYAPA OSB website has been frequently unavailable
(504 Gateway Timeout / 404). This scraper tries multiple URL patterns and
returns an empty list gracefully if the site is down.

If the site is up, it looks for company listings in table or card layout.
"""

import logging
import re

from .base_scraper import (
    get_session, fetch_page, extract_domain,
    normalize_phone, clean_company_name
)

logger = logging.getLogger(__name__)

OSB_NAME = "KAYAPA"

# Try these base URLs in order
CANDIDATE_BASES = [
    "https://www.kayapaosb.org.tr",
    "https://kayapaosb.org.tr",
    "https://www.kayapa.org.tr",
]

# Try these paths per base URL
CANDIDATE_PATHS = [
    "/firmalar",
    "/uyeler",
    "/uye-firmalar",
    "/firmalarimiz",
    "/uyelerimiz",
    "/katilimci-firmalar",
]


def scrape_kayapa() -> list[dict]:
    """
    Attempt to scrape KAYAPA OSB member companies.
    Returns empty list (without raising) if site is unreachable.
    """
    session = get_session()
    soup = None
    working_base = None

    # Try each base + path combination
    for base in CANDIDATE_BASES:
        for path in CANDIDATE_PATHS:
            url = base + path
            soup = fetch_page(url, session)
            if soup and len(soup.get_text(strip=True)) > 500:
                working_base = base
                logger.info(f"KAYAPA: found working URL: {url}")
                break
        if soup:
            break

    if not soup:
        logger.warning("KAYAPA: site unreachable — skipping (will retry tomorrow)")
        return []

    companies = _parse_table_layout(soup, working_base)
    if not companies:
        companies = _parse_card_layout(soup)

    # Handle pagination
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if text.isdigit() and int(text) > 1:
            next_url = href if href.startswith("http") else (working_base or "") + href
            next_soup = fetch_page(next_url, session)
            if next_soup:
                companies.extend(_parse_table_layout(next_soup, working_base))
                companies.extend(_parse_card_layout(next_soup))

    # Dedup by name
    seen: set[str] = set()
    unique = []
    for c in companies:
        key = c["Company_Name"].lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(c)

    logger.info(f"KAYAPA: scraped {len(unique)} companies")
    return unique


def _parse_table_layout(soup, base_url: str = "") -> list[dict]:
    companies = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:    # Skip header
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue
            name = clean_company_name(cols[0].get_text())
            if not name or len(name) < 3:
                continue
            website = phone = ""
            for col in cols:
                link = col.find("a", href=True)
                if link:
                    href = link["href"]
                    if href.startswith("http") or "www." in href:
                        website = href
                text = col.get_text()
                if re.search(r"0\d{10}", re.sub(r"\s", "", text)):
                    phone = normalize_phone(text)
            companies.append(_make_record(name, "", extract_domain(website), phone, ""))
    return companies


def _parse_card_layout(soup) -> list[dict]:
    companies = []
    containers = soup.find_all(
        ["div", "li", "article"],
        class_=lambda c: c and any(
            x in " ".join(c).lower()
            for x in ["firma", "uye", "üye", "company", "member", "card", "item", "post"]
        ),
    )
    for div in containers:
        name_el = div.find(["h2", "h3", "h4", "strong", "b"])
        if not name_el:
            name_el = div.find("a")
        if not name_el:
            continue
        name = clean_company_name(name_el.get_text())
        if not name or len(name) < 3:
            continue
        website = ""
        for a in div.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") or "www." in href:
                website = href
                break
        text = div.get_text()
        phone_m = re.search(r"0\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", text)
        phone = normalize_phone(phone_m.group() if phone_m else "")
        companies.append(_make_record(name, "", extract_domain(website), phone, ""))
    return companies


def _make_record(name, sector, domain, phone, address) -> dict:
    return {
        "Company_Name": name,
        "Sector":       sector,
        "Domain":       domain,
        "Phone":        phone,
        "Address":      address,
        "Email":        "",
        "OSB":          OSB_NAME,
        "City":         "Bursa",
    }
