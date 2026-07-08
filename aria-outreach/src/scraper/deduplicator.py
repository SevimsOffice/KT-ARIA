"""
Deduplicator — removes companies already in Google Sheets master.
Also cleans and validates prospect records before inserting.
"""

import logging
import re

logger = logging.getLogger(__name__)


def deduplicate(
    prospects: list[dict],
    existing_domains: set[str],
    existing_names: set[str] | None = None,
) -> list[dict]:
    """
    Filter out companies already in the master sheet.

    Checks by domain (primary) AND by company name (secondary — catches NOSAB
    companies which start with no domain but were already processed before).
    """
    fresh = []
    skipped_dupe = 0
    skipped_invalid = 0

    # Mutable copies so we can add intra-batch entries
    seen_domains = set(existing_domains)
    seen_names = set(existing_names or [])

    for p in prospects:
        domain = p.get("Domain", "").lower().strip()
        name   = p.get("Company_Name", "").strip()
        name_key = name.lower()

        if not name or len(name) < 3:
            skipped_invalid += 1
            continue

        # Domain match — skip if we've seen this domain before
        if domain and domain in seen_domains:
            skipped_dupe += 1
            continue

        # Name match — skip if this exact company name is already in the sheet
        if name_key in seen_names:
            skipped_dupe += 1
            continue

        fresh.append(p)
        if domain:
            seen_domains.add(domain)
        seen_names.add(name_key)

    logger.info(
        f"Dedup: {len(fresh)} new | {skipped_dupe} already in sheet | {skipped_invalid} invalid"
    )
    return fresh


def merge_sources(sources: list[list[dict]]) -> list[dict]:
    """
    Merge multiple scraper outputs, deduplicating by domain within the batch.
    Call this before passing to the master sheet dedup.
    """
    seen_domains = set()
    merged = []
    for batch in sources:
        for p in batch:
            domain = p.get("Domain", "").lower().strip()
            if domain and domain in seen_domains:
                continue
            if domain:
                seen_domains.add(domain)
            merged.append(p)
    return merged


def validate_and_clean(prospects: list[dict]) -> list[dict]:
    """Final cleaning pass — normalizes fields, removes garbage."""
    clean = []
    for p in prospects:
        name = p.get("Company_Name", "").strip()
        if not name:
            continue
        # Remove obvious non-company strings
        if re.match(r"^\d+$", name):
            continue
        if name.lower() in {"firma adı", "şirket adı", "company name", "name"}:
            continue
        domain = p.get("Domain", "").strip()
        # Validate domain looks like a real domain
        if domain and not re.match(r"^[\w\-]+\.[\w\.\-]+$", domain):
            p["Domain"] = ""
        clean.append(p)
    return clean
