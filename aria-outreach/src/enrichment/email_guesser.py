"""
Email pattern guesser — last resort when Apollo and Hunter find nothing.
Generates likely email addresses from company domain using common Turkish
business email patterns. Marks them as "guessed" so we know to be gentle.

If no domain is available (e.g. DOSAB companies from Excel), attempts to
derive a candidate domain from the Turkish company name.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Most common Turkish SMB email patterns, ordered by probability
GENERIC_PATTERNS = [
    "info",
    "iletisim",
    "bilgi",
    "satis",
    "mail",
    "ofis",
    "admin",
    "muhasebe",
    "ihracat",
]

# Turkish company suffixes to strip before building a domain guess
_STRIP_WORDS = {
    "sanayi", "sanayii", "san", "ticaret", "tic", "limited", "sirket",
    "sirketi", "anonim", "anonim sirketi", "ve", "a.s", "as", "ltd",
    "ltdsti", "sti", "dis", "ithalat", "ihracat", "uretim", "ur",
    "makine", "endustri", "dis ticaret", "iç ticaret", "ic ticaret",
    "tekstil", "kimya", "plastik", "metal", "insaat", "gida",
    "otomotiv", "elektrik", "elektronik", "lojistik", "danismanlik",
    "musavirlik", "muhendislik", "muh",
}

# Turkish → ASCII for domain normalization (dict form avoids encoding issues)
_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o",
    "ş": "s", "Ş": "s",
    "ü": "u", "Ü": "u",
    "â": "a", "Â": "a",
    "î": "i", "Î": "i",
    "û": "u", "Û": "u",
})


def guess_domain_from_company_name(company_name: str) -> str:
    """
    Derive a plausible domain from a Turkish company name.

    Strategy:
      1. Uppercase normalize Turkish chars → ASCII
      2. Remove punctuation / legal suffixes (A.Ş., LTD.ŞTİ., SAN., TİC. …)
      3. Take first 1-2 meaningful words (≥ 2 chars each)
      4. Concatenate and append .com.tr

    Returns empty string if no meaningful words remain.

    Examples:
      "A G MENSUCAT SANAYİ VE TİCARET A.Ş." → "agmensucat.com.tr"
      "ALFA PLASTİK SAN. TİC. LTD. ŞTİ."   → "alfaplastik.com.tr"
      "BORSA TEKSTİL A.Ş."                  → "borsatekstil.com.tr"
    """
    if not company_name:
        return ""

    # Step 1: translate Turkish chars, lowercase
    name = company_name.translate(_TR_MAP).lower()

    # Step 2: strip punctuation (keep alphanumeric and spaces)
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # Step 3: split into tokens
    tokens = name.split()

    # Step 4: filter out stop-words / suffix words
    meaningful = []
    for tok in tokens:
        if tok in _STRIP_WORDS or len(tok) < 2:
            continue
        meaningful.append(tok)

    if not meaningful:
        return ""

    # Use first 2 meaningful words to build domain core
    domain_core = "".join(meaningful[:2])

    # Return both .com.tr and .com candidates — caller decides which to try
    return f"{domain_core}.com.tr"


def guess_emails(domain: str, first_name: str = "", last_name: str = "") -> list[dict]:
    """
    Generate candidate email addresses for a domain.
    Returns list sorted by most likely first.
    Only the first one is used for outreach — others as fallback if bounce.
    """
    if not domain:
        return []

    candidates = []

    # 1. Generic patterns first (most reliable for Turkish SMBs)
    for prefix in GENERIC_PATTERNS:
        candidates.append({
            "email": f"{prefix}@{domain}",
            "first_name": "",
            "last_name": "",
            "title": "",
            "source": "guessed_generic",
            "confidence": 40,
        })

    # 2. Personal email patterns if we have a name
    if first_name and last_name:
        fn = _clean(first_name)
        ln = _clean(last_name)
        personal_patterns = [
            f"{fn}.{ln}@{domain}",
            f"{fn}{ln}@{domain}",
            f"{fn[0]}{ln}@{domain}",
            f"{fn}@{domain}",
        ]
        for email in personal_patterns:
            candidates.append({
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "title": "",
                "source": "guessed_personal",
                "confidence": 55,
            })
        # Re-sort: personal patterns are more likely if we have a real name
        candidates = sorted(candidates, key=lambda c: c["confidence"], reverse=True)

    return candidates


def best_guess(
    domain: str = "",
    first_name: str = "",
    last_name: str = "",
    company_name: str = "",
) -> dict | None:
    """
    Return the single best email guess for a company.

    If `domain` is empty but `company_name` is provided, derives a candidate
    domain from the company name before generating email patterns.
    """
    derived = False
    if not domain and company_name:
        domain = guess_domain_from_company_name(company_name)
        derived = bool(domain)
        if derived:
            logger.info(f"  Email guesser: derived domain '{domain}' from company name '{company_name}'")

    candidates = guess_emails(domain, first_name, last_name)
    if candidates:
        result = candidates[0].copy()
        if derived:
            result["source"] = "guessed_from_name"
        return result
    return None


def _clean(name: str) -> str:
    """Normalize name for email: lowercase, remove accents, spaces."""
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "â": "a", "î": "i", "û": "u",
    }
    for tr, en in replacements.items():
        name = name.replace(tr, en)
    # Remove non-alphanumeric
    name = re.sub(r"[^a-z0-9]", "", name)
    return name
