"""
Istanbul OSB scrapers — covers the four largest organized industrial zones:
  - İkitelli OSB  (iosb.org.tr)
  - Tuzla OSB     (tuzlaosb.org.tr)
  - Hadımköy OSB  (hadimkoyosb.org.tr)
  - Dudullu OSB   (dudulluosb.org.tr)

Each sub-scraper tries multiple URL patterns and returns an empty list
gracefully if the site is unreachable.
"""

import logging
import re

from .base_scraper import (
    get_session, fetch_page, extract_domain,
    normalize_phone, clean_company_name,
)

logger = logging.getLogger(__name__)

CITY = "İstanbul"

# (osb_name, candidate_bases, candidate_paths)
_OSB_CONFIGS = [
    (
        "IKİTELLİ",
        ["https://www.iosb.org.tr", "https://iosb.org.tr"],
        ["/firmalar", "/uyeler", "/uye-firmalar", "/firmalarimiz", "/uyelerimiz"],
    ),
    (
        "TUZLA",
        ["https://www.tuzlaosb.org.tr", "https://tuzlaosb.org.tr"],
        ["/firmalar", "/uyeler", "/uye-firmalar", "/firmalarimiz", "/uyelerimiz"],
    ),
    (
        "HADIMKÖY",
        ["https://www.hadimkoyosb.org.tr", "https://hadimkoyosb.org.tr"],
        ["/firmalar", "/uyeler", "/uye-firmalar", "/firmalarimiz", "/uyelerimiz"],
    ),
    (
        "DUDULLU",
        ["https://www.dudulluosb.org.tr", "https://dudulluosb.org.tr"],
        ["/firmalar", "/uyeler", "/uye-firmalar", "/firmalarimiz", "/uyelerimiz"],
    ),
]


def scrape_istanbul() -> list[dict]:
    """Scrape all Istanbul OSBs and return combined list."""
    session = get_session()
    all_companies: list[dict] = []
    for osb_name, bases, paths in _OSB_CONFIGS:
        companies = _scrape_one_osb(session, osb_name, bases, paths)
        all_companies.extend(companies)
    logger.info(f"İstanbul toplam: {len(all_companies)} firma")
    return all_companies


def _scrape_one_osb(session, osb_name: str, bases: list[str], paths: list[str]) -> list[dict]:
    soup = None
    working_base = None

    for base in bases:
        for path in paths:
            url = base + path
            soup = fetch_page(url, session)
            if soup and len(soup.get_text(strip=True)) > 500:
                working_base = base
                logger.info(f"{osb_name}: çalışan URL bulundu: {url}")
                break
        if soup:
            break

    if not soup:
        logger.warning(f"{osb_name}: site ulaşılamıyor — atlanıyor")
        return []

    companies = _parse_table_layout(soup, osb_name, working_base)
    if not companies:
        companies = _parse_card_layout(soup, osb_name)

    # Pagination
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if text.isdigit() and int(text) > 1:
            next_url = href if href.startswith("http") else (working_base or "") + href
            next_soup = fetch_page(next_url, session)
            if next_soup:
                companies.extend(_parse_table_layout(next_soup, osb_name, working_base))
                companies.extend(_parse_card_layout(next_soup, osb_name))

    # Dedup by name within this OSB
    seen: set[str] = set()
    unique = []
    for c in companies:
        key = c["Company_Name"].lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(c)

    logger.info(f"{osb_name}: {len(unique)} firma")
    return unique


def _parse_table_layout(soup, osb_name: str, base_url: str = "") -> list[dict]:
    companies = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:
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
            companies.append(_make_record(name, "", extract_domain(website), phone, osb_name))
    return companies


def _parse_card_layout(soup, osb_name: str) -> list[dict]:
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
        companies.append(_make_record(name, "", extract_domain(website), phone, osb_name))
    return companies


def _make_record(name: str, sector: str, domain: str, phone: str, osb_name: str) -> dict:
    return {
        "Company_Name": name,
        "Sector":       sector,
        "Domain":       domain,
        "Phone":        phone,
        "Address":      "",
        "Email":        "",
        "OSB":          osb_name,
        "City":         CITY,
    }
